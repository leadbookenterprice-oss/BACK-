from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from api.models import APIKey


CEREBRAS_DAILY_TOKEN_LIMIT = int(getattr(settings, 'CEREBRAS_DAILY_TOKEN_LIMIT', 1000000) or 1000000)
CEREBRAS_SLOT_TTL_SECONDS = int(getattr(settings, 'CEREBRAS_SLOT_TTL_SECONDS', 900) or 900)

TASK_MAX_COMPLETION_TOKENS = {
    'listing_description': 1400,
    'video_script': 1200,
    'video_scene': 500,
    'pdf_description': 1200,
    'html_design': 1200,
    'html_full': 3600,
    'post_caption': 1200,
    'carousel_caption': 1500,
    'story_caption': 650,
    'email': 1200,
    'ads_json': 1200,
    'general': 1600,
}


class CerebrasSlotUnavailable(Exception):
    def __init__(self, message, *, retry_after_seconds=None, quota_state='soft_rate_limited', scope='slot'):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.quota_state = quota_state
        self.scope = scope


@dataclass(frozen=True)
class CerebrasSlotReservation:
    key_id: int
    api_key: str
    estimated_tokens: int
    budget_tokens: int
    tokens_today: int
    locked_until: object


def resolve_cerebras_max_completion_tokens(task='general', requested=None):
    task_key = str(task or 'general').strip().lower()
    default_limit = TASK_MAX_COMPLETION_TOKENS.get(task_key, TASK_MAX_COMPLETION_TOKENS['general'])
    if requested is None:
        return default_limit
    try:
        requested_int = int(requested)
    except (TypeError, ValueError):
        return default_limit
    if requested_int <= 0:
        return default_limit
    return min(requested_int, default_limit)


def estimate_cerebras_tokens(prompt='', *, system_prompt='', max_completion_tokens=None):
    prompt_chars = len(str(prompt or '')) + len(str(system_prompt or ''))
    prompt_tokens = max(1, int(prompt_chars / 4) + 1)
    completion_tokens = int(max_completion_tokens or TASK_MAX_COMPLETION_TOKENS['general'])
    return max(1, prompt_tokens + completion_tokens)


def _budget_for_key(key):
    raw_limit = int(getattr(key, 'google_daily_limit', 0) or 0)
    return raw_limit if raw_limit >= 100000 else CEREBRAS_DAILY_TOKEN_LIMIT


def _reset_key_budget_if_needed(key, now):
    reset_at = getattr(key, 'slot_tokens_reset_at', None)
    if reset_at is not None and reset_at.date() == now.date():
        return False

    key.slot_tokens_today = 0
    key.slot_tokens_reset_at = now
    key.slot_last_error = None
    if key.status == 'exhausted':
        key.status = 'available'
    return True


def _clear_slot_lock(key):
    key.slot_locked_by = None
    key.slot_locked_listado = None
    key.slot_locked_at = None
    key.slot_locked_until = None
    if key.status in {'assigned', 'in_use'}:
        key.status = 'available'


def release_expired_cerebras_slots(now=None):
    now = now or timezone.now()
    APIKey.objects.filter(
        servicio__nombre__iexact='cerebras',
        slot_locked_until__lt=now,
        status='in_use',
    ).update(
        status='available',
        slot_locked_by=None,
        slot_locked_listado=None,
        slot_locked_at=None,
        slot_locked_until=None,
        updated_at=now,
    )


def reserve_cerebras_slot(user=None, *, listado_id=None, estimated_tokens=1):
    now = timezone.now()
    release_expired_cerebras_slots(now)
    user_id = getattr(user, 'id', None)
    try:
        listado_id = int(listado_id) if listado_id else None
    except (TypeError, ValueError):
        listado_id = None
    estimated_tokens = max(int(estimated_tokens or 1), 1)
    lock_until = now + timedelta(seconds=CEREBRAS_SLOT_TTL_SECONDS)

    with transaction.atomic():
        keys = list(
            APIKey.objects.select_for_update()
            .filter(servicio__nombre__iexact='cerebras')
            .exclude(status__in=['dead', 'disabled'])
            .order_by('slot_tokens_today', 'requests_today', 'id')
        )

        if not keys:
            raise CerebrasSlotUnavailable(
                'No hay slots Cerebras cargados en el pool.',
                quota_state='hard_exhausted',
                scope='pool',
            )

        reusable = []
        available = []
        locked_retry_after = None
        any_budget_remaining = False

        for key in keys:
            changed = _reset_key_budget_if_needed(key, now)
            is_locked = bool(key.slot_locked_until and key.slot_locked_until > now)
            budget = _budget_for_key(key)
            remaining = budget - int(key.slot_tokens_today or 0)
            if remaining >= estimated_tokens:
                any_budget_remaining = True

            if is_locked:
                if user_id and key.slot_locked_by_id == user_id and (
                    not listado_id or key.slot_locked_listado_id == listado_id
                ):
                    reusable.append((key, budget, remaining, changed))
                else:
                    seconds = int((key.slot_locked_until - now).total_seconds())
                    if locked_retry_after is None or seconds < locked_retry_after:
                        locked_retry_after = max(5, seconds)
                continue

            if key.status == 'exhausted':
                continue

            available.append((key, budget, remaining, changed))

        for bucket in (reusable, available):
            for key, budget, remaining, changed in bucket:
                if remaining < estimated_tokens:
                    if changed:
                        key.save(update_fields=['slot_tokens_today', 'slot_tokens_reset_at', 'slot_last_error', 'status', 'updated_at'])
                    continue
                key.status = 'in_use'
                key.slot_locked_by_id = user_id
                key.slot_locked_listado_id = listado_id
                key.slot_locked_at = key.slot_locked_at or now
                key.slot_locked_until = lock_until
                key.slot_last_error = None
                key.save(update_fields=[
                    'status',
                    'slot_locked_by',
                    'slot_locked_listado',
                    'slot_locked_at',
                    'slot_locked_until',
                    'slot_tokens_today',
                    'slot_tokens_reset_at',
                    'slot_last_error',
                    'updated_at',
                ])
                return CerebrasSlotReservation(
                    key_id=key.id,
                    api_key=key.api_key,
                    estimated_tokens=estimated_tokens,
                    budget_tokens=budget,
                    tokens_today=int(key.slot_tokens_today or 0),
                    locked_until=lock_until,
                )

        if any_budget_remaining and locked_retry_after:
            raise CerebrasSlotUnavailable(
                'Todos los slots Cerebras están ocupados. Esperá a que termine la generación en curso.',
                retry_after_seconds=min(max(locked_retry_after, 5), 60),
                quota_state='soft_rate_limited',
                scope='slot',
            )

        raise CerebrasSlotUnavailable(
            'Los slots Cerebras no tienen presupuesto de tokens suficiente para esta generación.',
            quota_state='hard_exhausted',
            scope='provider',
        )


def record_cerebras_slot_result(slot_id, *, estimated_tokens=1, actual_tokens=None, success=True, error_message=''):
    if not slot_id:
        return
    now = timezone.now()
    if success:
        try:
            actual_tokens_value = int(actual_tokens) if actual_tokens is not None else None
        except (TypeError, ValueError):
            actual_tokens_value = None
        if actual_tokens_value is not None and actual_tokens_value >= 0:
            charged_tokens = actual_tokens_value
        else:
            charged_tokens = max(int(estimated_tokens or 1), 1)
    else:
        charged_tokens = 0
    with transaction.atomic():
        key = APIKey.objects.select_for_update().filter(pk=slot_id, servicio__nombre__iexact='cerebras').first()
        if not key:
            return
        _reset_key_budget_if_needed(key, now)
        key.slot_tokens_today = int(key.slot_tokens_today or 0) + charged_tokens
        key.requests_today = int(key.requests_today or 0) + 1
        key.requests_this_month = int(key.requests_this_month or 0) + charged_tokens
        key.total_requests = int(key.total_requests or 0) + 1
        key.last_used_at = now
        key.slot_last_error = '' if success else str(error_message or '')[:4000]
        budget = _budget_for_key(key)
        if key.slot_tokens_today >= budget:
            key.status = 'exhausted'
            key.slot_locked_by = None
            key.slot_locked_listado = None
            key.slot_locked_at = None
            key.slot_locked_until = None
        key.save(update_fields=[
            'slot_tokens_today',
            'slot_tokens_reset_at',
            'requests_today',
            'requests_this_month',
            'total_requests',
            'last_used_at',
            'slot_last_error',
            'status',
            'slot_locked_by',
            'slot_locked_listado',
            'slot_locked_at',
            'slot_locked_until',
            'updated_at',
        ])


def mark_cerebras_slot_exhausted(slot_id, error_message=''):
    if not slot_id:
        return
    APIKey.objects.filter(pk=slot_id, servicio__nombre__iexact='cerebras').update(
        status='exhausted',
        slot_locked_by=None,
        slot_locked_listado=None,
        slot_locked_at=None,
        slot_locked_until=None,
        slot_last_error=str(error_message or '')[:4000],
        updated_at=timezone.now(),
    )
