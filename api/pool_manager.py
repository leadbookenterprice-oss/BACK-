from django.conf import settings

from api.models import APIKey, UserAPIAssignment
from api.services.pool_service import APIPoolService


SERVICE_ENV_FALLBACKS = {
    'gemini': 'GEMINI_API_KEY',
}


def _fallback_key_from_settings(servicio_nombre):
    setting_name = SERVICE_ENV_FALLBACKS.get(servicio_nombre)
    if not setting_name:
        return None
    key = str(getattr(settings, setting_name, '') or '').strip()
    return key or None


def get_api_key(agente, servicio):
    """
    Devuelve la API key asignada al usuario para un servicio.
    Usa schema v2: UserAPIAssignment + APIKey.
    """
    servicio_nombre = str(servicio or '').strip().lower()
    if not servicio_nombre:
        return None

    def _buscar_asignada():
        asig = UserAPIAssignment.objects.filter(
            user=agente,
            servicio__nombre__iexact=servicio_nombre,
            activo=True,
            apikey__status__in=['assigned', 'available']
        ).select_related('apikey').order_by('-is_primary', 'assigned_at').first()
        return asig.apikey.api_key if asig and asig.apikey else None

    UserAPIAssignment.objects.filter(
        user=agente,
        servicio__nombre__iexact=servicio_nombre,
        is_primary=True,
        activo=True,
    ).exclude(apikey__status__in=['assigned', 'available']).update(activo=False)

    key_val = _buscar_asignada()
    if key_val:
        return key_val

    # Reparación lazy: asegurar APIs críticas en usuarios existentes
    assigned_services = APIPoolService.assign_keys_to_user(agente)
    if servicio_nombre in assigned_services:
        return _buscar_asignada()

    return _fallback_key_from_settings(servicio_nombre)


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
