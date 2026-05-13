import functools
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from api.models import APIKey, APIRequestLog, AdminAlert, Servicio, UserAPIAssignment, UserAPIQuota
from api.services.pool_service import APIPoolService


def _emit_service_exhausted_event(agente, servicio):
    emit_ws_event({
        'type': 'api_service_exhausted',
        'data': {
            'user': getattr(agente, 'email', ''),
            'user_id': getattr(agente, 'id', None),
            'service': servicio.nombre,
            'percentage': 100,
        },
    })


def _mark_service_exhausted(agente, servicio, quota, key_obj=None, reason='servicio agotado'):
    limit = quota.user_daily_limit or servicio.default_daily_limit or 1500
    quota.requests_today = max(quota.requests_today, limit)
    quota.is_blocked = True
    quota.blocked_reason = reason[:255]
    quota.save(update_fields=['requests_today', 'is_blocked', 'blocked_reason', 'updated_at'])

    AdminAlert.objects.get_or_create(
        tipo='quota_warning',
        severidad='critical',
        related_user=agente,
        related_api_key=key_obj,
        creado_en__date=timezone.now().date(),
        defaults={
            'titulo': f'{servicio.nombre} al 100% para {agente.email}',
            'mensaje': f'El usuario {agente.email} agotó el 100% de {servicio.nombre}. Motivo: {reason}.',
        },
    )
    _emit_service_exhausted_event(agente, servicio)


def _raise_service_exhausted(service, message):
    if str(service or '').lower() == 'gemini':
        from api.ai_services import GeminiQuotaExhaustedError
        raise GeminiQuotaExhaustedError(message)
    raise Exception(message)


def emit_ws_event(event_data):
    """Envía un evento al consumer de WebSockets del Admin Dashboard."""
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        async_to_sync(channel_layer.group_send)("admin_dashboard", event_data)
    except Exception:
        # No romper la request si Redis/Channels falla.
        pass


def track_api_call(service, action=''):
    """Decorator de tracking adaptado al schema v2."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            agente = kwargs.get('agente')

            # Llamadas internas sin usuario no se trackean a nivel cuota.
            if not agente:
                return func(*args, **kwargs)

            servicio = Servicio.objects.filter(nombre__iexact=service).first()
            if not servicio:
                # Si el servicio no existe en catálogo, no bloquear ejecución.
                return func(*args, **kwargs)

            quota, _ = UserAPIQuota.objects.get_or_create(
                user=agente,
                servicio=servicio,
                defaults={
                    'user_daily_limit': servicio.default_daily_limit,
                    'user_monthly_limit': servicio.default_monthly_limit,
                },
            )
            quota.maybe_reset_daily()

            if quota.is_blocked:
                _mark_service_exhausted(agente, servicio, quota, reason=quota.blocked_reason or 'límite alcanzado')
                _raise_service_exhausted(service, f"Servicio {service} agotado: {quota.blocked_reason or 'límite alcanzado'}")

            if quota.requests_today >= quota.user_daily_limit:
                _mark_service_exhausted(agente, servicio, quota, reason='Límite diario alcanzado')
                _raise_service_exhausted(service, f"Servicio {service} agotado: límite diario alcanzado")

            assignment = UserAPIAssignment.objects.filter(
                user=agente,
                servicio=servicio,
                is_primary=True,
                activo=True,
            ).select_related('apikey').order_by('assigned_at').first()
            if assignment and assignment.apikey.status == 'exhausted':
                _mark_service_exhausted(agente, servicio, quota, assignment.apikey, reason='API key obligatoria agotada')
                _raise_service_exhausted(service, f"Servicio {service} agotado para este usuario")
            if assignment and assignment.apikey.status in {'dead', 'disabled'}:
                raise Exception(f"Servicio {service} no disponible para este usuario")

            from api.pool_manager import get_api_key

            key_str = get_api_key(agente, service)
            if not key_str:
                raise Exception(f"No hay API Key disponible para {service}")

            key_obj = APIKey.objects.filter(
                api_key=key_str,
                servicio=servicio,
            ).first()

            start_time = time.time()
            success = False
            status_code = None
            error_msg = None

            try:
                response = func(*args, **kwargs)
                success = True
                status_code = 200
                return response
            except Exception as e:
                error_msg = str(e)
                status_code = 500

                if e.__class__.__name__ == 'GeminiQuotaExhaustedError':
                    _mark_service_exhausted(
                        agente,
                        servicio,
                        quota,
                        key_obj,
                        reason='Gemini devolvió cuota agotada',
                    )

                if key_obj:
                    key_obj.error_count += 1
                    if key_obj.error_count >= 10:
                        APIPoolService.mark_key_dead(key_obj)
                    else:
                        key_obj.save(update_fields=['error_count', 'updated_at'])
                raise
            finally:
                elapsed_ms = int((time.time() - start_time) * 1000)

                quota.requests_today += 1
                quota.requests_this_month += 1
                quota.save(update_fields=['requests_today', 'requests_this_month', 'updated_at'])

                if key_obj:
                    key_obj.requests_today += 1
                    key_obj.requests_this_month += 1
                    key_obj.total_requests += 1
                    key_obj.last_used_at = timezone.now()
                    key_obj.save(
                        update_fields=[
                            'requests_today',
                            'requests_this_month',
                            'total_requests',
                            'last_used_at',
                            'updated_at',
                        ]
                    )

                    limit = key_obj.google_daily_limit or 0
                    if limit and key_obj.requests_today >= int(limit * 0.8):
                        AdminAlert.objects.get_or_create(
                            tipo='quota_warning',
                            severidad='warning',
                            related_api_key=key_obj,
                            creado_en__date=timezone.now().date(),
                            defaults={
                                'titulo': f"Key al {int((key_obj.requests_today / limit) * 100)}% de uso diario",
                                'mensaje': f"La key de {service} para {agente.email} está por agotarse.",
                            },
                        )

                    APIRequestLog.objects.create(
                        api_key=key_obj,
                        user=agente,
                        servicio=servicio,
                        endpoint=func.__name__,
                        method='POST',
                        success=success,
                        status_code=status_code,
                        response_time_ms=elapsed_ms,
                        error_message=error_msg,
                    )

                emit_ws_event(
                    {
                        'type': 'api_request_made',
                        'data': {
                            'user': agente.email,
                            'service': service,
                            'action': action,
                            'success': success,
                            'time_ms': elapsed_ms,
                        },
                    }
                )

        return wrapper

    return decorator
