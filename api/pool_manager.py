from api.models import APIKey, APIBundle, APIBundleAssignment
from api.services.pool_service import APIPoolService
from django.conf import settings
from django.utils import timezone


def get_api_key(agente, servicio):
    """
    Devuelve la API key string correcta desde el pool asignado al usuario.
    Orden: 1. Bundle suscripción -> 2. Key individual -> 3. Recursos Extra comprados.
    """
    # 1. Buscar bundle asignado y activo (Suscripción principal)
    try:
        asig = APIBundleAssignment.objects.select_related('bundle__key_gemini',
                                                           'bundle__key_elevenlabs',
                                                           'bundle__key_uploadpost').get(
            usuario=agente, activo=True
        )
        key_val = asig.bundle.get_key_for(servicio)
        if key_val:
            from api.models import APIKey
            k_obj = APIKey.objects.filter(api_key=key_val).first()
            if k_obj and k_obj.status not in ['exhausted', 'dead', 'disabled']:
                return key_val
    except APIBundleAssignment.DoesNotExist:
        pass

    # 2. Buscar key individual directa
    cuenta = APIKey.objects.filter(
        assigned_to=agente,
        servicio__nombre__iexact=servicio,
    ).exclude(status__in=['exhausted', 'dead', 'disabled']).first()

    if cuenta:
        return cuenta.api_key

    # 3. Buscar en APIs extra compradas (Reserva final)
    from api.models import BundleAPIExtra
    extra = BundleAPIExtra.objects.filter(
        usuario=agente,
        servicio__nombre__iexact=servicio,
        activa=True,
        api_key__status__in=['available', 'active', 'assigned', 'in_bundle']
    ).select_related('api_key').first()
    
    if extra and extra.api_key:
        return extra.api_key.api_key

    # 4. Si no tiene nada o todo está agotado, disparar reparación/asignación
    assigned_services = APIPoolService.assign_keys_to_user(agente)
    if servicio in assigned_services:
        return get_api_key(agente, servicio)

    return None


def liberar_bundle(agente):
    """Alias para mantener compatibilidad, usa el servicio centralizado."""
    return APIPoolService.release_bundle_from_user(agente)


def marcar_agotada(agente, servicio, is_monthly=False):
    """Marca la key del servicio como agotada."""
    keys = APIKey.objects.filter(
        assigned_to=agente,
        servicio__nombre__iexact=servicio,
        status__in=['available', 'active', 'assigned', 'in_bundle']
    )
    for k in keys:
        k.status = 'exhausted'
        if is_monthly:
            k.is_monthly_exhausted = True
        k.save(update_fields=['status', 'is_monthly_exhausted'])

