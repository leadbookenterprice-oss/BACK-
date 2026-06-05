from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils.timezone import now

from api.models import (
    APIKey,
    APIRequestLog,
    AdminAlert,
    CerebrasUsageLog,
    CloudinaryStorageLog,
    ContentGenerationRun,
    SocialPublicationLog,
    UserAPIAssignment,
)


ALERT_WARNING_PERCENT = 80
ALERT_CRITICAL_PERCENT = 90
ALERT_EXHAUSTED_PERCENT = 100
HIGH_ERROR_MIN_REQUESTS = 10
HIGH_ERROR_MIN_FAILURES = 5
HIGH_ERROR_RATE = 0.5
PERSISTENT_429_MIN_COUNT = 2
DEFAULT_CEREBRAS_SAFE_LIMIT = 800000


def _safe_int(value, default=0):
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _service_name(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'nvidia', 'nvidia_nim'}:
        return 'nim'
    return normalized


def _service_filter_q(field_name, service):
    if not service:
        return Q()
    normalized = _service_name(service)
    if normalized == 'nim':
        return Q(**{f'{field_name}__iexact': 'nim'}) | Q(**{f'{field_name}__iexact': 'nvidia'})
    return Q(**{f'{field_name}__iexact': normalized})


def _percent(usage, limit, fallback=None):
    if fallback is not None:
        return max(0, min(100, int(round(_safe_float(fallback)))))
    usage_value = _safe_float(usage)
    limit_value = _safe_float(limit)
    if limit_value <= 0:
        return 0
    return max(0, min(100, int(round((usage_value / limit_value) * 100))))


def _masked_key_label(key):
    if key.label:
        return key.label
    raw = str(key.api_key or '')
    if len(raw) <= 12:
        return '*' * len(raw)
    return f'{raw[:6]}...{raw[-4:]}'


def _assigned_user_payload(key):
    assignment = (
        UserAPIAssignment.objects
        .filter(apikey=key, activo=True, is_primary=True)
        .select_related('user')
        .first()
    )
    if not assignment or not assignment.user_id:
        return None
    user = assignment.user
    return {
        'id': user.id,
        'email': user.email,
        'nombre': getattr(user, 'nombre', '') or user.email,
    }


def _recent_error_stats(key, service):
    since = now() - timedelta(hours=1)
    if service == 'cerebras':
        qs = CerebrasUsageLog.objects.filter(api_key=key, creado_en__gte=since)
        total = qs.count()
        failed = qs.filter(success=False).count()
        rate_limited = qs.filter(status_code=429).count()
    elif service == 'cloudinary':
        qs = CloudinaryStorageLog.objects.filter(api_key=key, creado_en__gte=since)
        total = qs.count()
        failed = qs.exclude(status='success').count()
        rate_limited = 0
    else:
        qs = APIRequestLog.objects.filter(api_key=key, creado_en__gte=since)
        total = qs.count()
        failed = qs.filter(success=False).count()
        rate_limited = qs.filter(status_code=429).count()

    return {
        'window': '1h',
        'total': total,
        'failed': failed,
        'rate_limited': rate_limited,
        'failure_rate': round((failed / total), 3) if total else 0,
    }


def _last_log_payload(key, service):
    if service == 'cerebras':
        item = CerebrasUsageLog.objects.filter(api_key=key).order_by('-creado_en', '-id').first()
        if not item:
            return None
        return {
            'source': 'cerebras',
            'id': item.id,
            'success': item.success,
            'status_code': item.status_code,
            'task': item.task,
            'model': item.model,
            'actual_tokens': item.actual_tokens,
            'charged_tokens': item.charged_tokens,
            'retry_after_seconds': item.retry_after_seconds,
            'created_at': item.creado_en,
        }
    if service == 'cloudinary':
        item = CloudinaryStorageLog.objects.filter(api_key=key).order_by('-creado_en', '-id').first()
        if not item:
            return None
        return {
            'source': 'cloudinary',
            'id': item.id,
            'success': item.status == 'success',
            'status': item.status,
            'operation': item.operation,
            'asset_type': item.asset_type,
            'bytes': item.bytes,
            'created_at': item.creado_en,
        }

    item = APIRequestLog.objects.filter(api_key=key).order_by('-creado_en', '-id').first()
    if not item:
        return None
    return {
        'source': 'api_request',
        'id': item.id,
        'success': item.success,
        'status_code': item.status_code,
        'endpoint': item.endpoint,
        'tokens_used': item.tokens_used,
        'response_time_ms': item.response_time_ms,
        'created_at': item.creado_en,
    }


def _key_usage_window(key, service):
    if service == 'cerebras':
        limit = _safe_int(key.google_daily_limit or 1000000)
        if limit < 100000:
            limit = 1000000
        return {
            'usage': _safe_int(key.slot_tokens_today),
            'limit': limit,
            'unit': 'tokens',
            'window': 'day',
        }
    if service == 'cloudinary':
        used = _safe_int(key.cloudinary_used_bytes)
        total = _safe_int(key.cloudinary_total_bytes)
        if not total and (key.cloudinary_free_bytes is not None or used):
            total = used + _safe_int(key.cloudinary_free_bytes)
        return {
            'usage': used,
            'limit': total,
            'unit': 'bytes',
            'window': 'account',
            'percent_override': key.cloudinary_usage_percent,
        }
    if service == 'elevenlabs':
        return {
            'usage': _safe_int(key.requests_this_month),
            'limit': _safe_int(key.google_monthly_limit or 10000),
            'unit': 'characters',
            'window': 'month',
        }
    return {
        'usage': _safe_int(key.requests_today),
        'limit': _safe_int(key.google_daily_limit or 1500),
        'unit': 'requests',
        'window': 'day',
    }


def _emit_event(event_type, data):
    try:
        from api.tracking import emit_ws_event
        emit_ws_event({'type': event_type, 'data': data})
    except Exception:
        pass


def _alert_payload(alert):
    return {
        'id': alert.id,
        'type': alert.tipo,
        'severity': alert.severidad,
        'title': alert.titulo,
        'message': alert.mensaje,
        'api_key_id': alert.related_api_key_id,
        'user_id': alert.related_user_id,
        'timestamp': alert.creado_en,
        'is_read': alert.is_read,
    }


def _create_alert_once(*, key, tipo, severidad, titulo, mensaje, user=None):
    today = now().date()
    exists = AdminAlert.objects.filter(
        tipo=tipo,
        severidad=severidad,
        titulo=titulo,
        related_api_key=key,
        related_user=user,
        creado_en__date=today,
    ).exists()
    if exists:
        return None

    alert = AdminAlert.objects.create(
        tipo=tipo,
        severidad=severidad,
        titulo=titulo,
        mensaje=mensaje,
        related_api_key=key,
        related_user=user,
    )
    _emit_event('api_alert_created', _alert_payload(alert))
    return alert


def _evaluate_alerts(key, snapshot, error_stats):
    alerts = []
    service = snapshot['service']
    label = snapshot['label']
    percent = snapshot['percent']
    status = snapshot['status']

    if status in {'dead', 'disabled'}:
        alert = _create_alert_once(
            key=key,
            tipo='api_dead',
            severidad='critical',
            titulo=f'{service} key {label} no disponible',
            mensaje=f'La key {label} de {service} esta en estado {status}.',
        )
        if alert:
            alerts.append(_alert_payload(alert))

    if status == 'exhausted' or percent >= ALERT_EXHAUSTED_PERCENT:
        alert = _create_alert_once(
            key=key,
            tipo='quota_warning',
            severidad='critical',
            titulo=f'{service} key {label} al 100%',
            mensaje=f'La key {label} de {service} llego al limite operativo ({snapshot["usage"]}/{snapshot["limit"]} {snapshot["unit"]}).',
        )
        if alert:
            alerts.append(_alert_payload(alert))
    elif percent >= ALERT_CRITICAL_PERCENT:
        alert = _create_alert_once(
            key=key,
            tipo='quota_warning',
            severidad='critical',
            titulo=f'{service} key {label} supera 90%',
            mensaje=f'La key {label} de {service} esta al {percent}% de uso.',
        )
        if alert:
            alerts.append(_alert_payload(alert))
    elif percent >= ALERT_WARNING_PERCENT:
        alert = _create_alert_once(
            key=key,
            tipo='quota_warning',
            severidad='warning',
            titulo=f'{service} key {label} supera 80%',
            mensaje=f'La key {label} de {service} esta al {percent}% de uso.',
        )
        if alert:
            alerts.append(_alert_payload(alert))

    if error_stats['rate_limited'] >= PERSISTENT_429_MIN_COUNT:
        alert = _create_alert_once(
            key=key,
            tipo='high_error_rate',
            severidad='critical',
            titulo=f'{service} key {label} con 429 persistente',
            mensaje=f'La key {label} de {service} recibio {error_stats["rate_limited"]} respuestas 429 en la ultima hora.',
        )
        if alert:
            alerts.append(_alert_payload(alert))

    if (
        error_stats['total'] >= HIGH_ERROR_MIN_REQUESTS
        and error_stats['failed'] >= HIGH_ERROR_MIN_FAILURES
        and error_stats['failure_rate'] >= HIGH_ERROR_RATE
    ):
        alert = _create_alert_once(
            key=key,
            tipo='high_error_rate',
            severidad='critical',
            titulo=f'{service} key {label} con alto error rate',
            mensaje=f'La key {label} de {service} fallo {error_stats["failed"]}/{error_stats["total"]} llamadas en la ultima hora.',
        )
        if alert:
            alerts.append(_alert_payload(alert))

    return alerts


def _key_snapshot(key, create_alerts=True):
    raw_service = str(getattr(getattr(key, 'servicio', None), 'nombre', '') or '').strip().lower()
    service = _service_name(raw_service)
    usage_window = _key_usage_window(key, service)
    usage = usage_window['usage']
    limit = usage_window['limit']
    percent = _percent(usage, limit, usage_window.get('percent_override'))
    assigned_user = _assigned_user_payload(key)
    locked_user = None
    if key.slot_locked_by_id and key.slot_locked_by:
        locked_user = {
            'id': key.slot_locked_by_id,
            'email': key.slot_locked_by.email,
            'nombre': getattr(key.slot_locked_by, 'nombre', '') or key.slot_locked_by.email,
        }

    error_stats = _recent_error_stats(key, service)
    active_run = None
    if service == 'cerebras':
        run = (
            ContentGenerationRun.objects
            .filter(api_key=key, status__in=['pending', 'running', 'waiting_slot', 'waiting_rate_limit'])
            .select_related('user', 'listado')
            .order_by('-started_at')
            .first()
        )
        if run:
            active_run = {
                'id': run.id,
                'status': run.status,
                'current_step': run.current_step,
                'user_id': run.user_id,
                'user_email': run.user.email if run.user_id else None,
                'listado_id': run.listado_id,
                'started_at': run.started_at,
            }

    snapshot = {
        'id': key.id,
        'service': service,
        'service_raw': raw_service,
        'label': _masked_key_label(key),
        'status': key.status,
        'usage': usage,
        'limit': limit,
        'unit': usage_window['unit'],
        'window': usage_window['window'],
        'percent': percent,
        'requests_today': _safe_int(key.requests_today),
        'requests_this_month': _safe_int(key.requests_this_month),
        'total_requests': _safe_int(key.total_requests),
        'error_count': _safe_int(key.error_count),
        'last_used_at': key.last_used_at,
        'last_health_check': key.last_health_check,
        'last_health_status': key.last_health_status,
        'assigned_user': assigned_user,
        'assigned_user_email': assigned_user['email'] if assigned_user else None,
        'locked_user': locked_user,
        'locked_user_email': locked_user['email'] if locked_user else None,
        'locked_listado_id': key.slot_locked_listado_id,
        'locked_until': key.slot_locked_until,
        'last_error': key.slot_last_error or key.cloudinary_error or '',
        'last_rate_limit_headers': key.slot_last_rate_limit_headers or {},
        'last_rate_limit_at': key.slot_last_rate_limit_at,
        'cloudinary': {
            'used_bytes': _safe_int(key.cloudinary_used_bytes),
            'total_bytes': _safe_int(key.cloudinary_total_bytes),
            'free_bytes': _safe_int(key.cloudinary_free_bytes),
            'usage_percent': key.cloudinary_usage_percent,
            'status': key.cloudinary_status,
            'last_tested_at': key.cloudinary_last_tested_at,
            'upload_probe_ok': key.cloudinary_upload_probe_ok,
        } if service == 'cloudinary' else None,
        'cerebras': {
            'tokens_today': _safe_int(key.slot_tokens_today),
            'safe_daily_limit': min(limit, DEFAULT_CEREBRAS_SAFE_LIMIT),
            'slot_locked_by_id': key.slot_locked_by_id,
            'slot_locked_listado_id': key.slot_locked_listado_id,
            'slot_locked_until': key.slot_locked_until,
            'active_run': active_run,
            'rate_limit_headers': key.slot_last_rate_limit_headers or {},
        } if service == 'cerebras' else None,
        'recent_error_stats': error_stats,
        'last_log': _last_log_payload(key, service),
        'alerts_created': [],
    }
    if create_alerts:
        snapshot['alerts_created'] = _evaluate_alerts(key, snapshot, error_stats)
    return snapshot


def _service_totals(keys):
    totals = defaultdict(lambda: {
        'service': '',
        'keys_count': 0,
        'available': 0,
        'assigned': 0,
        'busy': 0,
        'exhausted': 0,
        'dead': 0,
        'disabled': 0,
        'usage': 0,
        'limit': 0,
        'unit': '',
        'window': '',
        'percent': 0,
        'errors_last_hour': 0,
        'rate_limited_last_hour': 0,
    })

    for item in keys:
        bucket = totals[item['service']]
        bucket['service'] = item['service']
        bucket['keys_count'] += 1
        bucket[item['status']] = bucket.get(item['status'], 0) + 1
        if item.get('locked_until'):
            bucket['busy'] += 1
        bucket['usage'] += _safe_int(item['usage'])
        bucket['limit'] += _safe_int(item['limit'])
        bucket['unit'] = bucket['unit'] or item['unit']
        bucket['window'] = bucket['window'] or item['window']
        bucket['errors_last_hour'] += _safe_int(item['recent_error_stats']['failed'])
        bucket['rate_limited_last_hour'] += _safe_int(item['recent_error_stats']['rate_limited'])

    output = []
    for bucket in totals.values():
        bucket['percent'] = _percent(bucket['usage'], bucket['limit'])
        output.append(bucket)
    return sorted(output, key=lambda row: row['service'])


def build_api_usage_summary(*, service=None, create_alerts=True):
    keys_qs = (
        APIKey.objects
        .select_related('servicio', 'slot_locked_by', 'slot_locked_listado')
        .order_by('servicio__nombre', '-creado_en')
    )
    if service:
        keys_qs = keys_qs.filter(_service_filter_q('servicio__nombre', service))

    keys = [_key_snapshot(key, create_alerts=create_alerts) for key in keys_qs]
    services = _service_totals(keys)
    cerebras_keys = [item for item in keys if item['service'] == 'cerebras']
    active_runs = list(
        ContentGenerationRun.objects
        .filter(status__in=['pending', 'running', 'waiting_slot', 'waiting_rate_limit'])
        .select_related('api_key', 'user', 'listado')
        .order_by('-started_at')[:30]
    )
    cerebras = {
        'tokens_today': sum(_safe_int(item['cerebras']['tokens_today']) for item in cerebras_keys if item.get('cerebras')),
        'safe_daily_limit': sum(_safe_int(item['cerebras']['safe_daily_limit']) for item in cerebras_keys if item.get('cerebras')),
        'busy_slots': sum(1 for item in cerebras_keys if item.get('locked_until')),
        'total_slots': len(cerebras_keys),
        'active_runs': [
            {
                'id': run.id,
                'api_key_id': run.api_key_id,
                'status': run.status,
                'current_step': run.current_step,
                'user_id': run.user_id,
                'user_email': run.user.email if run.user_id else None,
                'listado_id': run.listado_id,
                'started_at': run.started_at,
                'last_rate_limit_headers': run.last_rate_limit_headers or {},
            }
            for run in active_runs
        ],
        'rate_limit_headers': [
            {
                'api_key_id': item['id'],
                'headers': item['last_rate_limit_headers'],
                'at': item['last_rate_limit_at'],
            }
            for item in cerebras_keys
            if item.get('last_rate_limit_headers')
        ],
    }

    recent_alerts = [
        _alert_payload(alert)
        for alert in AdminAlert.objects
        .filter(tipo__in=['quota_warning', 'api_dead', 'high_error_rate'])
        .select_related('related_api_key', 'related_user')
        .order_by('-creado_en')[:20]
    ]

    payload = {
        'generated_at': now(),
        'thresholds': {
            'warning': ALERT_WARNING_PERCENT,
            'critical': ALERT_CRITICAL_PERCENT,
            'exhausted': ALERT_EXHAUSTED_PERCENT,
        },
        'services': services,
        'keys': keys,
        'cerebras': cerebras,
        'alerts': recent_alerts,
    }
    _emit_event('api_usage_updated', {
        'services': services,
        'keys_count': len(keys),
        'alerts_count': len(recent_alerts),
        'generated_at': payload['generated_at'],
    })
    return payload


def _bool_filter(value):
    text = str(value).strip().lower()
    if text in {'true', '1', 'yes', 'ok'}:
        return True
    if text in {'false', '0', 'no', 'error'}:
        return False
    return None


def _log_common(item, *, source, service, success, created_at, **extra):
    payload = {
        'source': source,
        'id': item.id,
        'service': _service_name(service),
        'success': bool(success),
        'created_at': created_at,
        'timestamp': created_at,
    }
    payload.update(extra)
    return payload


def build_api_usage_logs(*, service=None, api_key_id=None, user_id=None, success=None, limit=100):
    limit = max(1, min(_safe_int(limit, 100), 500))
    normalized_service = _service_name(service)
    success_filter = _bool_filter(success) if success is not None else None
    logs = []

    include_cerebras = not normalized_service or normalized_service == 'cerebras'
    include_cloudinary = not normalized_service or normalized_service == 'cloudinary'
    include_social = not normalized_service or normalized_service in {'uploadpost', 'meta'}
    include_generic = not normalized_service or normalized_service not in {'cerebras', 'cloudinary', 'uploadpost', 'meta'}

    if include_generic:
        qs = APIRequestLog.objects.select_related('api_key', 'user', 'servicio').order_by('-creado_en', '-id')
        if normalized_service:
            qs = qs.filter(_service_filter_q('servicio__nombre', normalized_service))
        else:
            qs = qs.exclude(servicio__nombre__iexact='cerebras')
        if api_key_id:
            qs = qs.filter(api_key_id=api_key_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if success_filter is not None:
            qs = qs.filter(success=success_filter)
        for item in qs[:limit]:
            logs.append(_log_common(
                item,
                source='api_request',
                service=item.servicio.nombre if item.servicio_id else '',
                success=item.success,
                created_at=item.creado_en,
                api_key_id=item.api_key_id,
                api_key_label=_masked_key_label(item.api_key) if item.api_key_id and item.api_key else None,
                user_id=item.user_id,
                user_email=item.user.email if item.user_id and item.user else None,
                endpoint=item.endpoint,
                action=item.endpoint,
                method=item.method,
                status_code=item.status_code,
                tokens_used=item.tokens_used,
                response_time_ms=item.response_time_ms,
                error_message=item.error_message or '',
            ))

    if include_cerebras:
        qs = CerebrasUsageLog.objects.select_related('api_key', 'user', 'listado', 'run', 'step').order_by('-creado_en', '-id')
        if api_key_id:
            qs = qs.filter(api_key_id=api_key_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if success_filter is not None:
            qs = qs.filter(success=success_filter)
        for item in qs[:limit]:
            logs.append(_log_common(
                item,
                source='cerebras',
                service='cerebras',
                success=item.success,
                created_at=item.creado_en,
                api_key_id=item.api_key_id,
                api_key_label=_masked_key_label(item.api_key) if item.api_key_id and item.api_key else None,
                user_id=item.user_id,
                user_email=item.user.email if item.user_id and item.user else None,
                listado_id=item.listado_id,
                run_id=item.run_id,
                run_status=item.run.status if item.run_id and item.run else None,
                step=item.step.step if item.step_id and item.step else None,
                model=item.model,
                task=item.task,
                endpoint=item.endpoint,
                status_code=item.status_code,
                estimated_tokens=item.estimated_tokens,
                actual_tokens=item.actual_tokens,
                charged_tokens=item.charged_tokens,
                response_time_ms=item.response_time_ms,
                rate_limit_headers=item.rate_limit_headers or {},
                retry_after_seconds=item.retry_after_seconds,
                error_message=item.error_message or '',
            ))

    if include_cloudinary:
        qs = CloudinaryStorageLog.objects.select_related('api_key', 'user', 'listado').order_by('-creado_en', '-id')
        if api_key_id:
            qs = qs.filter(api_key_id=api_key_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if success_filter is not None:
            qs = qs.filter(status='success' if success_filter else 'failed')
        for item in qs[:limit]:
            logs.append(_log_common(
                item,
                source='cloudinary',
                service='cloudinary',
                success=item.status == 'success',
                created_at=item.creado_en,
                api_key_id=item.api_key_id,
                api_key_label=_masked_key_label(item.api_key) if item.api_key_id and item.api_key else None,
                user_id=item.user_id,
                user_email=item.user.email if item.user_id and item.user else None,
                listado_id=item.listado_id,
                operation=item.operation,
                status=item.status,
                asset_type=item.asset_type,
                bytes=item.bytes,
                response_time_ms=item.duration_ms,
                error_message=item.error_message or '',
                metadata=item.metadata or {},
            ))

    if include_social and not api_key_id:
        qs = SocialPublicationLog.objects.select_related('user', 'servicio').order_by('-creado_en', '-id')
        if normalized_service == 'meta':
            qs = qs.filter(provider='meta')
        elif normalized_service == 'uploadpost':
            qs = qs.filter(provider='uploadpost')
        if user_id:
            qs = qs.filter(user_id=user_id)
        if success_filter is not None:
            qs = qs.filter(success=success_filter)
        for item in qs[:limit]:
            service_name = item.provider or (item.servicio.nombre if item.servicio_id else 'uploadpost')
            logs.append(_log_common(
                item,
                source='social_publication',
                service=service_name,
                success=item.success,
                created_at=item.creado_en,
                api_key_id=None,
                user_id=item.user_id,
                user_email=item.user.email if item.user_id and item.user else None,
                provider=item.provider,
                platform=item.platform,
                media_type=item.media_type,
                status=item.status,
                request_id=item.request_id,
                job_id=item.job_id,
                batch_id=item.batch_id,
                media_count=item.media_count,
                error_message=item.error_message or '',
            ))

    logs.sort(key=lambda row: row.get('created_at') or now(), reverse=True)
    return {
        'generated_at': now(),
        'logs': logs[:limit],
        'count': len(logs[:limit]),
        'limit': limit,
    }
