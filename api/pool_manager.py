from api.models import APIKey
from api.services.pool_service import APIPoolService


LIMIT_REACHED_MESSAGE = "Limite de generacion alcanzado. Podes comprar mas creditos o actualizar tu plan."


def _resolve_usage_window(key, servicio_nombre):
    svc = str(servicio_nombre or '').strip().lower()
    if svc == 'elevenlabs':
        limit = key.google_monthly_limit or 10000
        usage = key.requests_this_month or 0
        return usage, limit
    if svc == 'cerebras':
        limit = key.google_daily_limit or 1000000
        if limit < 100000:
            limit = 1000000
        usage = key.slot_tokens_today or 0
        return usage, limit
    limit = key.google_daily_limit or 0
    usage = key.requests_today or 0
    return usage, limit


def _key_usage_ratio(key, servicio_nombre):
    usage, limit = _resolve_usage_window(key, servicio_nombre)
    if limit <= 0:
        return 0
    return usage / limit


def get_next_available_api(agente, servicio, exclude_keys=None):
    """
    Devuelve una key del pool interno de LeadBook para un servicio.
    El usuario no es dueño de la key: solo se guarda como actor en logs/cuotas.
    """
    servicio_nombre = str(servicio or '').strip().lower()
    if not servicio_nombre:
        return None

    APIPoolService.ensure_user_quotas(agente)
    excluded_values = {str(value) for value in (exclude_keys or []) if value}

    if servicio_nombre == 'uploadpost':
        assignment = APIPoolService.ensure_uploadpost_assignment(agente)
        if not assignment or not assignment.apikey_id:
            return None
        key = assignment.apikey
        if str(key.api_key) in excluded_values:
            return None
        usage, limit = _resolve_usage_window(key, servicio_nombre)
        if limit and usage >= limit:
            key.status = 'exhausted'
            key.save(update_fields=['status', 'updated_at'])
            return None
        if key.status == 'available':
            key.status = 'assigned'
            key.save(update_fields=['status', 'updated_at'])
        if key.status not in {'assigned', 'available'}:
            return None
        return key.api_key

    candidates = []
    keys = (
        APIKey.objects
        .filter(servicio__nombre__iexact=servicio_nombre, status='available')
        .order_by('requests_today', 'slot_tokens_today', 'last_used_at', 'id')
    )
    for key in keys:
        if str(key.api_key) in excluded_values:
            continue

        usage, limit = _resolve_usage_window(key, servicio_nombre)
        if limit and usage >= limit:
            key.status = 'exhausted'
            key.save(update_fields=['status', 'updated_at'])
            continue
        candidates.append(key)

    if not candidates:
        return None

    selected = min(
        candidates,
        key=lambda key: (
            _key_usage_ratio(key, servicio_nombre),
            _resolve_usage_window(key, servicio_nombre)[0],
            key.last_used_at or key.creado_en,
            key.id,
        ),
    )
    return selected.api_key


def get_api_key(agente, servicio):
    """Alias de compatibilidad para llamadas existentes."""
    return get_next_available_api(agente, servicio)


def liberar_bundle(agente):
    """Alias de compatibilidad v1 -> pool interno."""
    return APIPoolService.release_keys_from_user(agente)


def marcar_agotada(agente, servicio, is_monthly=False):
    """
    Compatibilidad: marca agotada la key disponible mas consumida del servicio.
    Las keys ya no se marcan por usuario porque no hay asignacion por usuario.
    """
    servicio_nombre = str(servicio or '').strip().lower()
    if servicio_nombre == 'uploadpost':
        assignment = APIPoolService.ensure_uploadpost_assignment(agente)
        key = assignment.apikey if assignment else None
        if not key:
            return
        key.status = 'exhausted'
        monthly_limit = key.google_monthly_limit or 10
        key.requests_this_month = max(key.requests_this_month, monthly_limit or 0)
        key.save(update_fields=['status', 'requests_this_month', 'updated_at'])
        return

    keys = APIKey.objects.filter(
        servicio__nombre__iexact=servicio_nombre,
        status__in=['available', 'in_use'],
    ).order_by('-requests_today', '-requests_this_month', '-slot_tokens_today', 'id')

    key = keys.first()
    if not key:
        return

    key.status = 'exhausted'
    if is_monthly:
        monthly_limit = key.google_monthly_limit or (10000 if servicio_nombre == 'elevenlabs' else key.google_daily_limit)
        key.requests_this_month = max(key.requests_this_month, monthly_limit or 0)
        key.save(update_fields=['status', 'requests_this_month', 'updated_at'])
    else:
        key.save(update_fields=['status', 'updated_at'])
