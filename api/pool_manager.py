from api.models import APIKey, UserAPIAssignment
from api.services.pool_service import APIPoolService


LIMIT_REACHED_MESSAGE = "Límite de generación alcanzado. Podés comprar más créditos o actualizar tu plan."


def _resolve_usage_window(key, servicio_nombre):
    svc = str(servicio_nombre or '').strip().lower()
    if svc == 'elevenlabs':
        limit = key.google_monthly_limit or 10000
        usage = key.requests_this_month or 0
        return usage, limit
    limit = key.google_daily_limit or 0
    usage = key.requests_today or 0
    return usage, limit


def _key_usage_ratio(key, servicio_nombre):
    usage, limit = _resolve_usage_window(key, servicio_nombre)
    if limit <= 0:
        return 0
    return usage / limit


def get_next_available_api(agente, servicio):
    """
    Devuelve la próxima API key usable del usuario para un servicio.
    Rota por menor requests_today y excluye exhausted/dead/disabled.
    """
    servicio_nombre = str(servicio or '').strip().lower()
    if not servicio_nombre:
        return None
    soft_retry_services = {'gemini', 'elevenlabs'}

    def _buscar_asignada():
        statuses = ['assigned', 'available', 'exhausted'] if servicio_nombre in soft_retry_services else ['assigned', 'available']
        assignments = UserAPIAssignment.objects.filter(
            user=agente,
            servicio__nombre__iexact=servicio_nombre,
            activo=True,
            apikey__status__in=statuses
        ).select_related('apikey').order_by('assigned_at')

        candidates = []
        for asig in assignments:
            key = asig.apikey
            if not key:
                continue

            usage, limit = _resolve_usage_window(key, servicio_nombre)
            if limit and usage >= limit:
                if servicio_nombre not in soft_retry_services:
                    key.status = 'exhausted'
                    key.save(update_fields=['status', 'updated_at'])
                    continue

            if key.status == 'available':
                key.status = 'assigned'
                key.save(update_fields=['status', 'updated_at'])

            candidates.append(asig)

        if not candidates:
            return None

        selected = min(
            candidates,
            key=lambda asig: (
                _resolve_usage_window(asig.apikey, servicio_nombre)[0],
                _key_usage_ratio(asig.apikey, servicio_nombre),
                asig.apikey.last_used_at or asig.assigned_at,
                asig.apikey_id,
            ),
        )
        return selected.apikey.api_key if selected.apikey else None

    key_val = _buscar_asignada()
    if key_val:
        return key_val

    # Reparación lazy: asegurar APIs críticas en usuarios existentes
    assigned_services = APIPoolService.assign_keys_to_user(agente)
    if servicio_nombre in assigned_services:
        return _buscar_asignada()

    return None


def get_api_key(agente, servicio):
    """Alias de compatibilidad para llamadas existentes."""
    return get_next_available_api(agente, servicio)


def liberar_bundle(agente):
    """Alias de compatibilidad v1 -> v2."""
    return APIPoolService.release_keys_from_user(agente)


def marcar_agotada(agente, servicio, is_monthly=False):
    """Marca la key del servicio como agotada."""
    servicio_nombre = str(servicio or '').strip().lower()
    keys = APIKey.objects.filter(
        assignments__user=agente,
        assignments__activo=True,
        servicio__nombre__iexact=servicio,
        status__in=['available', 'assigned']
    ).distinct()

    for k in keys:
        k.status = 'exhausted'
        if is_monthly:
            monthly_limit = k.google_monthly_limit or (10000 if servicio_nombre == 'elevenlabs' else k.google_daily_limit)
            k.requests_this_month = max(k.requests_this_month, monthly_limit or 0)
            k.save(update_fields=['status', 'requests_this_month', 'updated_at'])
        else:
            k.save(update_fields=['status', 'updated_at'])
