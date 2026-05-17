from api.models import APIKey, UserAPIAssignment
from api.services.pool_service import APIPoolService


LIMIT_REACHED_MESSAGE = "Límite de generación alcanzado. Podés comprar más créditos o actualizar tu plan."


def _key_usage_ratio(key):
    limit = key.google_daily_limit or 0
    if limit <= 0:
        return 0
    return key.requests_today / limit


def get_next_available_api(agente, servicio):
    """
    Devuelve la próxima API key usable del usuario para un servicio.
    Rota por menor requests_today y excluye exhausted/dead/disabled.
    """
    servicio_nombre = str(servicio or '').strip().lower()
    if not servicio_nombre:
        return None

    def _buscar_asignada():
        assignments = UserAPIAssignment.objects.filter(
            user=agente,
            servicio__nombre__iexact=servicio_nombre,
            activo=True,
            apikey__status__in=['assigned', 'available']
        ).select_related('apikey').order_by('assigned_at')

        candidates = []
        for asig in assignments:
            key = asig.apikey
            if not key:
                continue

            limit = key.google_daily_limit or 0
            if limit and key.requests_today >= limit:
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
                asig.apikey.requests_today,
                _key_usage_ratio(asig.apikey),
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
    keys = APIKey.objects.filter(
        assignments__user=agente,
        assignments__activo=True,
        servicio__nombre__iexact=servicio,
        status__in=['available', 'assigned']
    ).distinct()

    for k in keys:
        k.status = 'exhausted'
        if is_monthly:
            k.requests_this_month = k.google_monthly_limit or max(k.requests_this_month, k.google_daily_limit)
            k.save(update_fields=['status', 'requests_this_month', 'updated_at'])
        else:
            k.save(update_fields=['status', 'updated_at'])
