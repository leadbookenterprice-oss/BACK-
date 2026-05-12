import functools
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from api.models import APIKey, APIRequestLog, AdminAlert, Servicio, UserAPIQuota
from api.services.pool_service import APIPoolService


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
                raise Exception(f"Usuario bloqueado para el servicio {service}: {quota.blocked_reason}")

            if quota.requests_today >= quota.user_daily_limit:
                quota.is_blocked = True
                quota.blocked_reason = 'Límite diario alcanzado'
                quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])
                raise Exception(f"Límite diario alcanzado para el servicio {service}")

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
