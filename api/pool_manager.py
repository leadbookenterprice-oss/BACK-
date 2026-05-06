from api.models import APIKey, APIBundle, APIBundleAssignment
from api.services.pool_service import APIPoolService
from django.conf import settings
from django.utils import timezone


def get_api_key(agente, servicio):
    """
    Devuelve la API key string correcta desde el pool asignado al usuario.
    Si el usuario no tiene un bundle ni keys, intenta asignarle lo que falte.
    """
    # 1. Buscar bundle asignado y activo
    try:
        asig = APIBundleAssignment.objects.select_related('bundle__key_gemini',
                                                           'bundle__key_elevenlabs',
                                                           'bundle__key_uploadpost').get(
            usuario=agente, activo=True
        )
        key_val = asig.bundle.get_key_for(servicio)
        if key_val:
            return key_val
    except APIBundleAssignment.DoesNotExist:
        # No tiene bundle activo, pasamos a keys directas
        pass

    # 2. Buscar key individual directa (assigned o in_bundle o activa)
    cuenta = APIKey.objects.filter(
        assigned_to=agente,
        servicio__iexact=servicio,
        status__in=['available', 'active', 'assigned', 'in_bundle']
    ).first()
    
    if cuenta:
        return cuenta.api_key

    # 3. Si no tiene nada, disparar reparación/asignación rápida creando un bundle o agrupando keys
    assigned_services = APIPoolService.assign_keys_to_user(agente)
    if servicio in assigned_services:
        # Intentar de nuevo tras la reparación
        return get_api_key(agente, servicio)

    # Fallback final: No hay key asignada y no se pudo reparar
    return None


def liberar_bundle(agente):
    """Alias para mantener compatibilidad, usa el servicio centralizado."""
    return APIPoolService.release_bundle_from_user(agente)


def marcar_agotada(agente, servicio):
    """Marca la key individual como agotada."""
    APIKey.objects.filter(
        assigned_to=agente,
        servicio__iexact=servicio,
        status__in=['available', 'active', 'assigned', 'in_bundle']
    ).update(status='exhausted')

