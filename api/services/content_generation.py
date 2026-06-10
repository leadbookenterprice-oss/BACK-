from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from api.models import (
    APIKey,
    CerebrasUsageLog,
    ContentGenerationRun,
    ContentGenerationStep,
    Listado,
)
from api.plan_utils import registrar_uso_listado_si_completo
from api.services.cerebras_slots import (
    CEREBRAS_DAILY_TOKEN_LIMIT,
    CerebrasSlotUnavailable,
    reserve_cerebras_slot,
)


CONTENT_PACK_STEPS = ['pdf', 'post', 'story', 'carrusel', 'email']
CONTENT_PACK_STEP_LABELS = {
    'pdf': 'PDF',
    'post': 'Post',
    'story': 'Story',
    'carrusel': 'Carrusel',
    'email': 'Email',
}
TASK_TO_STEP = {
    'pdf_description': 'pdf',
    'html_design': 'pdf',
    'html_full': 'pdf',
    'post_caption': 'post',
    'story_caption': 'story',
    'carousel_caption': 'carrusel',
    'email': 'email',
}

ACTIVE_RUN_STATUSES = ['pending', 'running', 'waiting_slot', 'waiting_rate_limit']
CEREBRAS_FATAL_ERROR_CODES = {
    'hard_exhausted',
    'api_key_unavailable',
    'quota_exhausted',
    'cuota_ia_agotada',
}
CEREBRAS_SAFE_DAILY_LIMIT = int(getattr(settings, 'CEREBRAS_SAFE_DAILY_TOKEN_LIMIT', 800000) or 800000)
CEREBRAS_PACK_ESTIMATED_TOKENS = int(getattr(settings, 'CEREBRAS_PACK_ESTIMATED_TOKENS', 25000) or 25000)


def _safe_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def extract_generation_run_id(payload):
    if not isinstance(payload, dict):
        return None
    return _safe_int(payload.get('generation_run_id') or payload.get('generationRunId') or payload.get('run_id'), None)


def extract_generation_step(payload, fallback=None):
    if isinstance(payload, dict):
        raw = payload.get('generation_step') or payload.get('generationStep') or payload.get('step')
        if raw:
            raw = str(raw).strip().lower()
            if raw in CONTENT_PACK_STEPS:
                return raw
    return fallback if fallback in CONTENT_PACK_STEPS else None


def infer_step_from_task(task, fallback=None):
    return TASK_TO_STEP.get(str(task or '').strip().lower()) or fallback


def extract_rate_limit_headers(headers):
    if not headers:
        return {}
    result = {}
    for key, value in dict(headers).items():
        normalized = str(key or '').strip().lower()
        if normalized.startswith('x-ratelimit-') or normalized == 'retry-after':
            result[normalized] = str(value)
    return result


def retry_after_from_headers(headers, fallback=None):
    headers = headers or {}
    raw = headers.get('retry-after') or headers.get('Retry-After')
    retry_after = _safe_int(raw, None)
    if retry_after is not None and retry_after > 0:
        return retry_after
    reset_candidates = []
    now = timezone.now()
    for key, value in headers.items():
        normalized = str(key or '').strip().lower()
        if not normalized.startswith('x-ratelimit-reset'):
            continue
        parsed_int = _safe_int(value, None)
        if parsed_int is not None and parsed_int > 0:
            if parsed_int > 10_000_000_000:
                parsed_int = int(parsed_int / 1000)
            if parsed_int > 1_000_000_000:
                seconds = parsed_int - int(now.timestamp())
            else:
                seconds = parsed_int
            if seconds > 0:
                reset_candidates.append(seconds)
                continue
        parsed_dt = parse_datetime(str(value or '').strip())
        if parsed_dt:
            if timezone.is_naive(parsed_dt):
                parsed_dt = timezone.make_aware(parsed_dt, timezone.get_current_timezone())
            seconds = int((parsed_dt - now).total_seconds())
            if seconds > 0:
                reset_candidates.append(seconds)
    if reset_candidates:
        return min(reset_candidates)
    return fallback


def _serialize_step(step):
    return {
        'id': step.id,
        'step': step.step,
        'label': CONTENT_PACK_STEP_LABELS.get(step.step, step.step),
        'order': step.order,
        'status': step.status,
        'estimated_tokens': step.estimated_tokens,
        'actual_tokens': step.actual_tokens,
        'requests_count': step.requests_count,
        'rate_limit_headers': step.rate_limit_headers or {},
        'result': step.result or {},
        'error_code': step.error_code or '',
        'error_message': step.error_message or '',
        'started_at': step.started_at,
        'completed_at': step.completed_at,
        'updated_at': step.updated_at,
    }


def _serialize_log(log):
    return {
        'id': log.id,
        'api_key_id': log.api_key_id,
        'user_id': log.user_id,
        'listado_id': log.listado_id,
        'run_id': log.run_id,
        'step_id': log.step_id,
        'model': log.model,
        'task': log.task,
        'status_code': log.status_code,
        'success': log.success,
        'estimated_tokens': log.estimated_tokens,
        'actual_tokens': log.actual_tokens,
        'charged_tokens': log.charged_tokens,
        'response_time_ms': log.response_time_ms,
        'rate_limit_headers': log.rate_limit_headers or {},
        'retry_after_seconds': log.retry_after_seconds,
        'error_message': log.error_message or '',
        'creado_en': log.creado_en,
    }


def serialize_generation_run(run, *, include_logs=True, logs_limit=20):
    steps = list(run.steps.all().order_by('order', 'id'))
    payload = {
        'id': run.id,
        'listado_id': run.listado_id,
        'user_id': run.user_id,
        'api_key_id': run.api_key_id,
        'status': run.status,
        'current_step': run.current_step,
        'total_estimated_tokens': run.total_estimated_tokens,
        'total_actual_tokens': run.total_actual_tokens,
        'requests_count': run.requests_count,
        'safe_daily_limit': run.safe_daily_limit,
        'last_rate_limit_headers': run.last_rate_limit_headers or {},
        'error_code': run.error_code or '',
        'error_message': run.error_message or '',
        'metadata': run.metadata or {},
        'started_at': run.started_at,
        'completed_at': run.completed_at,
        'updated_at': run.updated_at,
        'steps': [_serialize_step(step) for step in steps],
    }
    if include_logs:
        logs = run.cerebras_usage_logs.select_related('api_key', 'step').order_by('-creado_en', '-id')[:logs_limit]
        payload['logs'] = [_serialize_log(log) for log in logs]
    return payload


def _ensure_steps(run):
    existing = set(run.steps.values_list('step', flat=True))
    missing = [
        ContentGenerationStep(run=run, step=step, order=index + 1)
        for index, step in enumerate(CONTENT_PACK_STEPS)
        if step not in existing
    ]
    if missing:
        ContentGenerationStep.objects.bulk_create(missing, ignore_conflicts=True)


def _key_budget(key):
    raw_limit = _safe_int(getattr(key, 'google_daily_limit', 0), 0)
    provider_limit = raw_limit if raw_limit >= 100000 else CEREBRAS_DAILY_TOKEN_LIMIT
    return min(provider_limit, CEREBRAS_SAFE_DAILY_LIMIT)


def _safe_budget_preflight(user, listado_id, estimated_tokens):
    now = timezone.now()
    user_id = getattr(user, 'id', None)
    safe_retry_after = None
    saw_safe_locked = False
    saw_key = False
    saw_budget_remaining = False

    keys = (
        APIKey.objects
        .filter(servicio__nombre__iexact='cerebras')
        .exclude(status__in=['dead', 'disabled', 'exhausted'])
        .order_by('slot_tokens_today', 'requests_today', 'id')
    )
    for key in keys:
        saw_key = True
        budget = _key_budget(key)
        reset_at = getattr(key, 'slot_tokens_reset_at', None)
        tokens_today = 0 if reset_at is None or reset_at.date() != now.date() else int(key.slot_tokens_today or 0)
        remaining = budget - tokens_today
        if remaining < estimated_tokens:
            continue
        saw_budget_remaining = True
        is_locked = bool(key.slot_locked_until and key.slot_locked_until > now)
        if is_locked:
            is_same_owner = user_id and key.slot_locked_by_id == user_id and (
                not listado_id or key.slot_locked_listado_id == listado_id
            )
            if is_same_owner:
                return None
            saw_safe_locked = True
            seconds = int((key.slot_locked_until - now).total_seconds())
            if safe_retry_after is None or seconds < safe_retry_after:
                safe_retry_after = max(5, seconds)
            continue
        return None

    if not saw_key:
        return CerebrasSlotUnavailable(
            'No hay slots Cerebras cargados en el pool.',
            quota_state='hard_exhausted',
            scope='pool',
        )
    if saw_safe_locked:
        return CerebrasSlotUnavailable(
            'Todos los slots Cerebras con presupuesto seguro estan ocupados.',
            retry_after_seconds=min(max(safe_retry_after or 5, 5), 60),
            quota_state='soft_rate_limited',
            scope='slot',
        )
    if not saw_budget_remaining:
        return CerebrasSlotUnavailable(
            'Los slots Cerebras llegaron al limite operativo seguro del dia.',
            quota_state='hard_exhausted',
            scope='provider',
        )
    return CerebrasSlotUnavailable(
        'No hay slot Cerebras seguro disponible para esta generacion.',
        quota_state='hard_exhausted',
        scope='provider',
    )


def _provider_from_metadata(metadata=None, default='cerebras'):
    metadata = metadata if isinstance(metadata, dict) else {}
    raw = (
        metadata.get('ai_provider')
        or metadata.get('aiProvider')
        or metadata.get('provider')
        or metadata.get('ai_root_provider')
        or ''
    )
    provider = str(raw or '').strip().lower()
    if provider in {'nvidia_nim', 'nim'}:
        provider = 'nvidia'
    return provider or default


def release_generation_run_slot(run):
    if not run or not run.api_key_id:
        return
    now = timezone.now()
    with transaction.atomic():
        key = APIKey.objects.select_for_update().filter(pk=run.api_key_id, servicio__nombre__iexact='cerebras').first()
        if not key:
            return
        is_same_run_lock = (
            key.slot_locked_by_id == run.user_id
            and key.slot_locked_listado_id == run.listado_id
        )
        if not is_same_run_lock:
            return
        key.slot_locked_by = None
        key.slot_locked_listado = None
        key.slot_locked_at = None
        key.slot_locked_until = None
        if key.status in {'assigned', 'in_use'}:
            key.status = 'available'
        key.save(update_fields=[
            'status',
            'slot_locked_by',
            'slot_locked_listado',
            'slot_locked_at',
            'slot_locked_until',
            'updated_at',
        ])


def start_or_resume_generation_run(user, listado, *, metadata=None):
    metadata = metadata or {}
    now = timezone.now()
    requested_provider = _provider_from_metadata(metadata)
    run = (
        ContentGenerationRun.objects
        .select_related('api_key', 'listado', 'user')
        .filter(user=user, listado=listado, status__in=ACTIVE_RUN_STATUSES)
        .order_by('-started_at', '-id')
        .first()
    )
    created = False
    if not run:
        run = ContentGenerationRun.objects.create(
            user=user,
            listado=listado,
            status='pending',
            current_step=CONTENT_PACK_STEPS[0],
            total_estimated_tokens=CEREBRAS_PACK_ESTIMATED_TOKENS,
            safe_daily_limit=CEREBRAS_SAFE_DAILY_LIMIT,
            metadata={
                'pack_steps': CONTENT_PACK_STEPS,
                'estimated_tokens_per_pack': CEREBRAS_PACK_ESTIMATED_TOKENS,
                'model_primary': 'gpt-oss-120b',
                'model_fallback': 'zai-glm-4.7',
                'ai_provider': requested_provider,
                **metadata,
            },
        )
        _ensure_steps(run)
        created = True
    else:
        _ensure_steps(run)
        existing_provider = _provider_from_metadata(run.metadata or {})
        incoming_provider = _provider_from_metadata(metadata, default='') if metadata else ''
        requested_provider = incoming_provider or existing_provider
        run.metadata = {
            **(run.metadata or {}),
            **metadata,
            'ai_provider': requested_provider,
        }

    if requested_provider != 'cerebras':
        if run.status in {'pending', 'waiting_slot'}:
            run.status = 'running'
            run.current_step = run.current_step or CONTENT_PACK_STEPS[0]
            run.error_code = ''
            run.error_message = ''
        run.save(update_fields=['status', 'current_step', 'error_code', 'error_message', 'metadata', 'updated_at'])
        return run, {
            'created': created,
            'reserved': False,
            'retry_after_seconds': None,
            'error': None,
        }

    retry_after_seconds = None
    reserved = False
    error = None

    should_reserve = True
    if run.api_key_id:
        key = APIKey.objects.filter(pk=run.api_key_id, servicio__nombre__iexact='cerebras').first()
        should_reserve = not (
            key
            and key.slot_locked_until
            and key.slot_locked_until > now
            and key.slot_locked_by_id == user.id
            and key.slot_locked_listado_id == listado.id
        )

    if should_reserve:
        try:
            preflight_error = _safe_budget_preflight(user, listado.id, CEREBRAS_PACK_ESTIMATED_TOKENS)
            if preflight_error:
                raise preflight_error
            slot = reserve_cerebras_slot(user, listado_id=listado.id, estimated_tokens=CEREBRAS_PACK_ESTIMATED_TOKENS)
            run.api_key_id = slot.key_id
            run.status = 'running'
            run.current_step = run.current_step or CONTENT_PACK_STEPS[0]
            run.error_code = ''
            run.error_message = ''
            run.metadata = {
                **(run.metadata or {}),
                'slot_budget_tokens': slot.budget_tokens,
                'slot_tokens_today_at_start': slot.tokens_today,
                'slot_locked_until': slot.locked_until.isoformat() if hasattr(slot.locked_until, 'isoformat') else str(slot.locked_until),
            }
            run.save(update_fields=['api_key', 'status', 'current_step', 'error_code', 'error_message', 'metadata', 'updated_at'])
            reserved = True
        except CerebrasSlotUnavailable as exc:
            retry_after_seconds = getattr(exc, 'retry_after_seconds', None)
            run.status = 'waiting_slot'
            run.current_step = run.current_step or CONTENT_PACK_STEPS[0]
            run.error_code = getattr(exc, 'quota_state', 'soft_rate_limited') or 'soft_rate_limited'
            run.error_message = str(exc)[:1000]
            run.save(update_fields=['status', 'current_step', 'error_code', 'error_message', 'updated_at'])
            error = exc
    elif run.status in {'pending', 'waiting_slot'}:
        run.status = 'running'
        run.error_code = ''
        run.error_message = ''
        run.save(update_fields=['status', 'error_code', 'error_message', 'updated_at'])

    return run, {
        'created': created,
        'reserved': reserved,
        'retry_after_seconds': retry_after_seconds,
        'error': error,
    }


def _refresh_run_totals(run):
    totals = run.steps.aggregate(
        estimated=Sum('estimated_tokens'),
        actual=Sum('actual_tokens'),
        requests=Sum('requests_count'),
    )
    run.total_estimated_tokens = _safe_int(totals.get('estimated'), 0)
    run.total_actual_tokens = _safe_int(totals.get('actual'), 0)
    run.requests_count = _safe_int(totals.get('requests'), 0)


def _is_fatal_generation_error(error_code='', error_message=''):
    code = str(error_code or '').strip().lower()
    message = str(error_message or '').strip().lower()
    if code in CEREBRAS_FATAL_ERROR_CODES:
        return True
    return any(term in message for term in (
        'hard_exhausted',
        'cuota agotada',
        'quota exhausted',
        'insufficient credits',
        'billing',
        'payment',
    ))


def _next_actionable_step(steps):
    return next((item for item in steps if item.status in {'pending', 'waiting_rate_limit'}), None)


def mark_generation_step(run_id, step_name, status_value, *, result=None, error_code='', error_message='', rate_limit_headers=None):
    run_id = _safe_int(run_id, None)
    if not run_id or step_name not in CONTENT_PACK_STEPS:
        return None
    now = timezone.now()
    with transaction.atomic():
        run = ContentGenerationRun.objects.select_for_update().filter(pk=run_id).first()
        if not run:
            return None
        step, _ = ContentGenerationStep.objects.select_for_update().get_or_create(
            run=run,
            step=step_name,
            defaults={'order': CONTENT_PACK_STEPS.index(step_name) + 1},
        )

        step.status = status_value
        if status_value in {'running', 'uploading'} and not step.started_at:
            step.started_at = now
        if status_value == 'done':
            step.completed_at = step.completed_at or now
            step.error_code = ''
            step.error_message = ''
        if status_value == 'failed':
            step.completed_at = step.completed_at or now
            step.error_code = str(error_code or 'step_failed')[:80]
            step.error_message = str(error_message or '')[:4000]
        if status_value == 'waiting_rate_limit':
            step.error_code = str(error_code or 'soft_rate_limited')[:80]
            step.error_message = str(error_message or '')[:4000]
        if result is not None:
            step.result = result if isinstance(result, dict) else {'value': str(result)}
        if rate_limit_headers:
            step.rate_limit_headers = rate_limit_headers
        step.save()

        _refresh_run_totals(run)
        run.current_step = step_name
        if status_value in {'running', 'uploading'}:
            run.status = 'running'
        elif status_value == 'waiting_rate_limit':
            run.status = 'waiting_rate_limit'
            run.error_code = step.error_code
            run.error_message = step.error_message
            if rate_limit_headers:
                run.last_rate_limit_headers = rate_limit_headers
        elif status_value == 'failed':
            all_steps = list(run.steps.all().order_by('order', 'id'))
            pending = _next_actionable_step(all_steps)
            is_fatal = _is_fatal_generation_error(step.error_code, step.error_message)
            if pending and not is_fatal:
                run.status = 'running'
                run.current_step = pending.step
                run.error_code = ''
                run.error_message = ''
                run.completed_at = None
            elif not is_fatal and all(item.status in {'done', 'failed', 'skipped'} for item in all_steps):
                run.status = 'done'
                run.current_step = ''
                run.completed_at = run.completed_at or now
                run.error_code = ''
                run.error_message = ''
            else:
                run.status = 'failed'
                run.completed_at = run.completed_at or now
                run.error_code = step.error_code
                run.error_message = step.error_message
        elif status_value == 'done':
            all_steps = list(run.steps.all())
            if all(item.status in {'done', 'failed', 'skipped'} for item in all_steps):
                run.status = 'done'
                run.current_step = ''
                run.completed_at = run.completed_at or now
                run.error_code = ''
                run.error_message = ''
            else:
                pending = next((item.step for item in all_steps if item.status not in {'done', 'failed', 'skipped'}), None)
                run.status = 'running'
                run.current_step = pending or step_name

        run.save(update_fields=[
            'status',
            'current_step',
            'total_estimated_tokens',
            'total_actual_tokens',
            'requests_count',
            'last_rate_limit_headers',
            'error_code',
            'error_message',
            'completed_at',
            'updated_at',
        ])

    if run.status == 'done':
        registrar_uso_listado_si_completo(run.listado, generation_run_id=run.id)

    if run.status in {'done', 'failed', 'cancelled'}:
        release_generation_run_slot(run)
    return run


def mark_generation_step_from_exception(run_id, step_name, exc):
    quota_state = str(getattr(exc, 'quota_state', '') or '').strip().lower()
    status_value = 'waiting_rate_limit' if quota_state == 'soft_rate_limited' else 'failed'
    error_code = quota_state or exc.__class__.__name__
    return mark_generation_step(
        run_id,
        step_name,
        status_value,
        error_code=error_code,
        error_message=str(exc),
    )


def record_cerebras_usage(
    *,
    slot_id=None,
    user=None,
    listado_id=None,
    run_id=None,
    step_name=None,
    model='',
    task='',
    status_code=None,
    success=False,
    estimated_tokens=0,
    actual_tokens=None,
    response_time_ms=0,
    rate_limit_headers=None,
    retry_after_seconds=None,
    error_message='',
    metadata=None,
):
    now = timezone.now()
    run = None
    step = None
    run_id = _safe_int(run_id, None)
    listado_id = _safe_int(listado_id, None)
    step_name = step_name or infer_step_from_task(task)

    if run_id:
        run = ContentGenerationRun.objects.filter(pk=run_id).first()
        if run and not listado_id:
            listado_id = run.listado_id
        if run and not slot_id and run.api_key_id:
            slot_id = run.api_key_id
        if run and step_name in CONTENT_PACK_STEPS:
            step, _ = ContentGenerationStep.objects.get_or_create(
                run=run,
                step=step_name,
                defaults={'order': CONTENT_PACK_STEPS.index(step_name) + 1},
            )
            if step.status in {'pending', 'waiting_rate_limit'}:
                step.status = 'running' if success or status_code != 429 else 'waiting_rate_limit'
                step.started_at = step.started_at or now

    estimated_tokens = max(_safe_int(estimated_tokens, 0), 0)
    actual_tokens_value = max(_safe_int(actual_tokens, 0), 0)
    charged_tokens = actual_tokens_value if actual_tokens_value > 0 else (estimated_tokens if success else 0)
    rate_limit_headers = rate_limit_headers or {}
    retry_after_seconds = retry_after_seconds or retry_after_from_headers(rate_limit_headers, None)

    log = CerebrasUsageLog.objects.create(
        api_key_id=slot_id,
        user=user if getattr(user, 'is_authenticated', False) else None,
        listado_id=listado_id,
        run=run,
        step=step,
        model=str(model or '')[:120],
        task=str(task or '')[:80],
        status_code=status_code,
        success=bool(success),
        estimated_tokens=estimated_tokens,
        actual_tokens=actual_tokens_value,
        charged_tokens=max(charged_tokens, 0),
        response_time_ms=max(_safe_int(response_time_ms, 0), 0),
        rate_limit_headers=rate_limit_headers,
        retry_after_seconds=retry_after_seconds,
        error_message=str(error_message or '')[:4000],
        metadata=metadata or {},
    )

    if slot_id and rate_limit_headers:
        APIKey.objects.filter(pk=slot_id, servicio__nombre__iexact='cerebras').update(
            slot_last_rate_limit_headers=rate_limit_headers,
            slot_last_rate_limit_at=now,
        )

    if step:
        step.estimated_tokens = int(step.estimated_tokens or 0) + estimated_tokens
        step.actual_tokens = int(step.actual_tokens or 0) + max(charged_tokens, 0)
        step.requests_count = int(step.requests_count or 0) + 1
        if rate_limit_headers:
            step.rate_limit_headers = rate_limit_headers
        if status_code == 429 and not success:
            step.status = 'waiting_rate_limit'
            step.error_code = 'soft_rate_limited'
            step.error_message = str(error_message or 'Cerebras rate limited')[:4000]
        step.save(update_fields=[
            'status',
            'estimated_tokens',
            'actual_tokens',
            'requests_count',
            'rate_limit_headers',
            'error_code',
            'error_message',
            'started_at',
            'updated_at',
        ])

    if run:
        _refresh_run_totals(run)
        if rate_limit_headers:
            run.last_rate_limit_headers = rate_limit_headers
        if slot_id and not run.api_key_id:
            run.api_key_id = slot_id
        if status_code == 429 and not success:
            run.status = 'waiting_rate_limit'
            run.current_step = step_name or run.current_step
            run.error_code = 'soft_rate_limited'
            run.error_message = str(error_message or 'Cerebras rate limited')[:4000]
        elif run.status in {'pending', 'waiting_slot', 'waiting_rate_limit'}:
            run.status = 'running'
            run.current_step = step_name or run.current_step
        run.save(update_fields=[
            'api_key',
            'status',
            'current_step',
            'total_estimated_tokens',
            'total_actual_tokens',
            'requests_count',
            'last_rate_limit_headers',
            'error_code',
            'error_message',
            'updated_at',
        ])

    return log


def get_generation_run_for_user(user, run_id):
    return (
        ContentGenerationRun.objects
        .select_related('api_key', 'listado', 'user')
        .prefetch_related('steps')
        .filter(pk=run_id, user=user)
        .first()
    )


def get_listado_for_generation(user, listado_id):
    return Listado.objects.filter(pk=listado_id, agente=user).first()
