import functools
import json
import time
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from api.models import (
    APIKey, APIRequestLog, AdminAlert, Servicio, SocialPublicationLog,
    UserAPIAssignment, UserAPIQuota
)
from api.services.pool_service import APIPoolService


FREE_POOL_SERVICES = {'gemini', 'elevenlabs'}
LIMIT_REACHED_MESSAGE = "Límite de generación alcanzado. Podés comprar más créditos o actualizar tu plan."
UPLOADPOST_LIMIT_REACHED_MESSAGE = "Límite de publicaciones automáticas alcanzado. Podés actualizar tu plan para publicar más."


def _get_uploadpost_service():
    servicio = Servicio.objects.filter(nombre__iexact='uploadpost').first()
    return servicio


def _ensure_uploadpost_quota(agente):
    servicio = _get_uploadpost_service()
    if not servicio:
        return None
    quota, _ = UserAPIQuota.objects.get_or_create(
        user=agente,
        servicio=servicio,
        defaults={
            'user_daily_limit': servicio.default_daily_limit,
            'user_monthly_limit': servicio.default_monthly_limit,
        },
    )
    return quota


def _json_safe(value):
    try:
        return json.loads(json.dumps(value or {}, default=str))
    except Exception:
        return {'raw': str(value)}


def _as_dict(value):
    safe = _json_safe(value)
    return safe if isinstance(safe, dict) else {'value': safe}


def _first_platform(platforms=None, platform=None):
    if platform:
        return str(platform).strip().lower()[:50] or 'instagram'
    if isinstance(platforms, str):
        return platforms.strip().lower()[:50] or 'instagram'
    if isinstance(platforms, (list, tuple)) and platforms:
        return str(platforms[0]).strip().lower()[:50] or 'instagram'
    return 'instagram'


def _response_field(response, *names):
    if not isinstance(response, dict):
        return None
    for name in names:
        value = response.get(name)
        if value not in (None, ''):
            return value
    return None


def _publication_status(success=True, response=None, status_value=None):
    if status_value:
        normalized = str(status_value).strip().lower()
    else:
        normalized = str(_response_field(response, 'status', 'state', 'job_status') or '').strip().lower()
    if normalized in {'queued', 'pending', 'processing', 'scheduled'}:
        return 'queued'
    if normalized in {'completed', 'complete', 'published', 'done', 'success', 'finished'}:
        return 'completed'
    if normalized in {'failed', 'failure', 'error', 'rejected'}:
        return 'failed'
    return 'queued' if success else 'failed'


def _media_count_from_payload(media_type=None, images=None, image_url=None, video_url=None, document_url=None, response=None, media_count=None):
    if media_count not in (None, ''):
        try:
            return max(int(media_count), 0)
        except Exception:
            pass
    response_count = _response_field(response, 'media_count')
    if response_count not in (None, ''):
        try:
            return max(int(response_count), 0)
        except Exception:
            pass
    if str(media_type or '').lower() in {'carousel', 'carrusel'}:
        return len(images or []) if isinstance(images, list) else 0
    return 1 if image_url or video_url or document_url else 0


def sync_uploadpost_quota_from_sql(agente, quota=None):
    quota = quota or _ensure_uploadpost_quota(agente)
    if not quota:
        return None

    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    counted_logs = SocialPublicationLog.objects.filter(user=agente, success=True, counted=True)
    today_count = counted_logs.filter(creado_en__gte=start_of_day).count()
    month_count = counted_logs.filter(creado_en__gte=start_of_month).count()

    updates = []
    if quota.requests_today != today_count:
        quota.requests_today = today_count
        updates.append('requests_today')
    if quota.requests_this_month != month_count:
        quota.requests_this_month = month_count
        updates.append('requests_this_month')

    monthly_limit = quota.user_monthly_limit
    monthly_exhausted = monthly_limit is not None and month_count >= monthly_limit
    if monthly_exhausted and (not quota.is_blocked or quota.blocked_reason != 'Límite mensual alcanzado'):
        quota.is_blocked = True
        quota.blocked_reason = 'Límite mensual alcanzado'
        updates.extend(['is_blocked', 'blocked_reason'])
    elif not monthly_exhausted and quota.blocked_reason and 'mensual' in quota.blocked_reason.lower():
        quota.is_blocked = False
        quota.blocked_reason = None
        updates.extend(['is_blocked', 'blocked_reason'])

    if updates:
        quota.save(update_fields=list(dict.fromkeys(updates + ['updated_at'])))
    return quota


def get_uploadpost_quota(agente):
    quota = _ensure_uploadpost_quota(agente)
    if not quota:
        return None
    quota.maybe_reset_daily()
    quota.maybe_reset_monthly()
    quota.recalcular_limite(plan=agente.plan_nombre)
    return sync_uploadpost_quota_from_sql(agente, quota)


def record_uploadpost_publication(
    agente,
    count=1,
    *,
    success=True,
    provider='uploadpost',
    platform=None,
    platforms=None,
    media_type='unknown',
    request_id=None,
    job_id=None,
    batch_id=None,
    status_value=None,
    caption='',
    media_count=None,
    payload=None,
    response=None,
    error_message=None,
):
    """Persiste publicaciones sociales en SQL y sincroniza la cuota desde esa tabla."""
    servicio = _get_uploadpost_service()
    response_dict = response if isinstance(response, dict) else {}
    base_request_id = (
        request_id
        or _response_field(response_dict, 'request_id', 'id')
        or (f"job-{job_id}" if job_id else None)
        or (f"job-{_response_field(response_dict, 'job_id')}" if _response_field(response_dict, 'job_id') else None)
        or f"sql-{getattr(agente, 'id', 'anon')}-{uuid.uuid4().hex[:16]}"
    )
    increment = max(int(count or 1), 1)
    saved_logs = []
    normalized_provider = str(provider or 'uploadpost').strip().lower()[:30] or 'uploadpost'
    normalized_media_type = str(media_type or _response_field(response_dict, 'media_type') or 'unknown').strip().lower()[:30]
    normalized_status = _publication_status(success=success, response=response_dict, status_value=status_value)
    normalized_platform = _first_platform(platforms=platforms, platform=platform)
    safe_payload = _as_dict(payload)
    safe_response = _as_dict(response_dict)
    if platforms is not None:
        safe_payload.setdefault('platforms', _json_safe(platforms))
    error_text = str(error_message or _response_field(response_dict, 'error', 'message') or '')[:2000]
    resolved_job_id = str(job_id or _response_field(response_dict, 'job_id') or '')[:128]
    resolved_batch_id = str(batch_id or safe_payload.get('batch_id') or '')[:64]
    resolved_media_count = _media_count_from_payload(
        media_type=normalized_media_type,
        images=safe_payload.get('images'),
        image_url=safe_payload.get('image_url'),
        video_url=safe_payload.get('video_url'),
        document_url=safe_payload.get('document_url'),
        response=response_dict,
        media_count=media_count,
    )

    for index in range(increment):
        row_request_id = str(base_request_id if index == 0 else f"{base_request_id}-{index + 1}")[:128]
        existing = SocialPublicationLog.objects.filter(
            user=agente,
            provider=normalized_provider,
            request_id=row_request_id,
        ).first()
        counted = bool(success)
        row_success = bool(success)
        row_status = normalized_status
        if existing and existing.counted and not success:
            counted = existing.counted
            row_success = existing.success
            row_status = existing.status

        defaults = {
            'servicio': servicio,
            'platform': normalized_platform,
            'media_type': normalized_media_type,
            'job_id': resolved_job_id,
            'batch_id': resolved_batch_id,
            'success': row_success,
            'counted': counted,
            'status': row_status,
            'caption': str(caption or '')[:10000],
            'media_count': resolved_media_count,
            'payload': safe_payload,
            'response': safe_response,
            'error_message': error_text,
        }
        log, _ = SocialPublicationLog.objects.update_or_create(
            user=agente,
            provider=normalized_provider,
            request_id=row_request_id,
            defaults=defaults,
        )
        saved_logs.append(log)

    sync_uploadpost_quota_from_sql(agente)
    return saved_logs[0] if saved_logs else None


def _uses_soft_exhaustion(servicio):
    return str(getattr(servicio, 'nombre', servicio) or '').strip().lower() in FREE_POOL_SERVICES


def _limit_message_for_service(service):
    if str(service or '').strip().lower() == 'uploadpost':
        return UPLOADPOST_LIMIT_REACHED_MESSAGE
    return LIMIT_REACHED_MESSAGE


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


def _mark_service_monthly_exhausted(agente, servicio, quota, key_obj=None, reason='Límite mensual alcanzado'):
    quota.is_blocked = True
    quota.blocked_reason = reason[:255]
    quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])

    AdminAlert.objects.get_or_create(
        tipo='quota_warning',
        severidad='critical',
        related_user=agente,
        related_api_key=key_obj,
        creado_en__date=timezone.now().date(),
        defaults={
            'titulo': f'{servicio.nombre} mensual agotado para {agente.email}',
            'mensaje': f'El usuario {agente.email} agotó el límite mensual de {servicio.nombre}.',
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
            soft_exhaustion = _uses_soft_exhaustion(servicio)
            is_uploadpost = str(service or '').strip().lower() == 'uploadpost'

            if is_uploadpost:
                quota = get_uploadpost_quota(agente)
            else:
                quota, _ = UserAPIQuota.objects.get_or_create(
                    user=agente,
                    servicio=servicio,
                    defaults={
                        'user_daily_limit': servicio.default_daily_limit,
                        'user_monthly_limit': servicio.default_monthly_limit,
                    },
                )
                quota.maybe_reset_daily()
                quota.recalcular_limite(plan=agente.plan_nombre)
                quota.maybe_reset_monthly()

            monthly_limit = quota.user_monthly_limit
            if monthly_limit and quota.requests_this_month >= monthly_limit:
                _mark_service_monthly_exhausted(agente, servicio, quota, reason='Límite mensual alcanzado')
                _raise_service_exhausted(service, _limit_message_for_service(service))

            if soft_exhaustion and quota.is_blocked:
                quota.is_blocked = False
                quota.blocked_reason = None
                quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])
            elif quota.is_blocked and quota.requests_today < quota.user_daily_limit:
                quota.is_blocked = False
                quota.blocked_reason = None
                quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])

            if not soft_exhaustion and quota.is_blocked:
                _mark_service_exhausted(agente, servicio, quota, reason=quota.blocked_reason or 'límite alcanzado')
                _raise_service_exhausted(service, f"Servicio {service} agotado: {quota.blocked_reason or 'límite alcanzado'}")

            if not soft_exhaustion and quota.requests_today >= quota.user_daily_limit:
                _mark_service_exhausted(agente, servicio, quota, reason='Límite diario alcanzado')
                _raise_service_exhausted(service, f"Servicio {service} agotado: límite diario alcanzado")

            usable_statuses = ['assigned', 'available', 'exhausted'] if soft_exhaustion else ['assigned', 'available']
            usable_assignment = UserAPIAssignment.objects.filter(
                user=agente,
                servicio=servicio,
                activo=True,
                apikey__status__in=usable_statuses,
            ).select_related('apikey').order_by('-is_primary', 'assigned_at').first()

            if not usable_assignment and not soft_exhaustion:
                exhausted_assignment = UserAPIAssignment.objects.filter(
                    user=agente,
                    servicio=servicio,
                    activo=True,
                    apikey__status='exhausted',
                ).select_related('apikey').order_by('-is_primary', 'assigned_at').first()
                if exhausted_assignment:
                    _mark_service_exhausted(agente, servicio, quota, exhausted_assignment.apikey, reason='API keys agotadas')
                    _raise_service_exhausted(service, f"Servicio {service} agotado para este usuario")

            disabled_assignment = UserAPIAssignment.objects.filter(
                user=agente,
                servicio=servicio,
                activo=True,
                apikey__status__in=['dead', 'disabled'],
            ).select_related('apikey').first()
            if disabled_assignment and not usable_assignment:
                raise Exception(f"Servicio {service} no disponible para este usuario")

            from api.pool_manager import get_next_available_api

            key_str = get_next_available_api(agente, service)
            if not key_str:
                _raise_service_exhausted(service, _limit_message_for_service(service))

            key_obj = APIKey.objects.filter(
                api_key=key_str,
                servicio=servicio,
            ).first()

            start_time = time.time()
            success = False
            status_code = None
            error_msg = None
            response_payload = None

            try:
                response = func(*args, **kwargs)
                response_payload = response
                success = not (isinstance(response, dict) and response.get('success') is False)
                status_code = 200 if success else 400
                if not success and isinstance(response, dict):
                    error_msg = str(response.get('error') or response.get('message') or '')[:500]
                return response
            except Exception as e:
                error_msg = str(e)
                status_code = 500

                is_quota_exception = e.__class__.__name__ == 'GeminiQuotaExhaustedError'

                if is_quota_exception and not soft_exhaustion:
                    _mark_service_exhausted(
                        agente,
                        servicio,
                        quota,
                        key_obj,
                        reason='Gemini devolvió cuota agotada',
                    )
                elif is_quota_exception and key_obj:
                    key_obj.status = 'exhausted'
                    key_obj.save(update_fields=['status', 'updated_at'])

                if key_obj and not is_quota_exception:
                    key_obj.error_count += 1
                    if key_obj.error_count >= 10:
                        APIPoolService.mark_key_dead(key_obj)
                    else:
                        key_obj.save(update_fields=['error_count', 'updated_at'])
                raise
            finally:
                elapsed_ms = int((time.time() - start_time) * 1000)
                should_count_usage = success or not is_uploadpost

                if is_uploadpost:
                    payload = {
                        'media_type': kwargs.get('media_type'),
                        'caption': kwargs.get('caption'),
                        'image_url': kwargs.get('image_url'),
                        'video_url': kwargs.get('video_url'),
                        'document_url': kwargs.get('document_url'),
                        'images': kwargs.get('images'),
                        'platforms': kwargs.get('platforms'),
                        'scheduled_at': kwargs.get('scheduled_at'),
                        'request_id': kwargs.get('request_id'),
                        'batch_id': kwargs.get('batch_id'),
                    }
                    record_uploadpost_publication(
                        agente,
                        success=success,
                        provider='uploadpost',
                        platforms=kwargs.get('platforms'),
                        media_type=kwargs.get('media_type') or _response_field(response_payload, 'media_type'),
                        request_id=(
                            _response_field(response_payload, 'request_id')
                            or kwargs.get('request_id')
                        ),
                        job_id=_response_field(response_payload, 'job_id'),
                        batch_id=kwargs.get('batch_id'),
                        status_value=_response_field(response_payload, 'status', 'state', 'job_status'),
                        caption=kwargs.get('caption') or '',
                        media_count=_response_field(response_payload, 'media_count'),
                        payload=payload,
                        response=response_payload,
                        error_message=error_msg,
                    )
                elif should_count_usage:
                    quota.requests_today += 1
                    quota.requests_this_month += 1
                    quota.save(update_fields=['requests_today', 'requests_this_month', 'updated_at'])

                if key_obj:
                    if should_count_usage:
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
                    if should_count_usage and limit and key_obj.requests_today >= limit:
                        key_obj.status = 'exhausted'
                        key_obj.save(update_fields=['status', 'updated_at'])

                    if should_count_usage and limit and key_obj.requests_today >= int(limit * 0.8):
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
                            'message': f'Request de {service}',
                            'user': agente.email,
                            'user_email': agente.email,
                            'service': service,
                            'action': action,
                            'success': success,
                            'time_ms': elapsed_ms,
                            'timestamp': timezone.now().isoformat(),
                        },
                    }
                )

        return wrapper

    return decorator
