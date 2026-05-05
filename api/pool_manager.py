from api.models import APIKey, APIBundle, APIBundleAssignment
from django.conf import settings
from django.utils import timezone


def get_api_key(agente, servicio):
    """
    Devuelve la API key string correcta desde el pool asignado al usuario.
    Si el usuario no tiene un bundle, se le asigna uno.
    Como fallback final, se usa la key global del .env.
    """
    # Buscar bundle asignado y activo
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
        # No tiene bundle asignado, intentar asignar uno disponible
        bundle_asignado = _asignar_bundle(agente)
        if bundle_asignado:
            key_val = bundle_asignado.get_key_for(servicio)
            if key_val:
                return key_val

    # Legacy: buscar key individual directa (compatibilidad hacia atrás)
    cuenta = APIKey.objects.filter(
        assigned_to=agente,
        servicio=servicio,
        status='assigned'
    ).first()
    if cuenta:
        return cuenta.api_key
    # Fallback final: No hay key asignada
    return None

def _get_global_key(servicio):
    """Retorna la key global configurada en el .env para el servicio dado."""
    keys = {
        'gemini':      getattr(settings, 'GEMINI_API_KEY', ''),
        'elevenlabs':  getattr(settings, 'ELEVENLABS_API_KEY', ''),
        'uploadpost':  getattr(settings, 'UPLOADPOST_API_KEY', ''),
        'groq':        getattr(settings, 'GROQ_API_KEY', ''),
        'openai':      getattr(settings, 'OPENAI_API_KEY', ''),
        'anthropic':   getattr(settings, 'ANTHROPIC_API_KEY', ''),
    }
    return keys.get(servicio, None)


def _asignar_bundle(agente):
    """
    Busca un bundle disponible y completo, lo asigna al agente y lo devuelve.
    Devuelve el objeto APIBundle asignado, o None si no hay disponibles.
    """
    bundle = APIBundle.objects.filter(status='available').first()
    if not bundle or not bundle.is_complete():
        return None

    bundle.status = 'assigned'
    bundle.save(update_fields=['status'])

    APIBundleAssignment.objects.create(
        bundle=bundle,
        usuario=agente,
    )
    return bundle


def liberar_bundle(agente):
    """
    Libera el bundle asignado a un agente (por ejemplo, al hacer upgrade o baja).
    """
    try:
        asig = APIBundleAssignment.objects.get(usuario=agente, activo=True)
        asig.activo = False
        asig.liberado_en = timezone.now()
        asig.save(update_fields=['activo', 'liberado_en'])

        asig.bundle.status = 'available'
        asig.bundle.save(update_fields=['status'])
    except APIBundleAssignment.DoesNotExist:
        pass


def marcar_agotada(agente, servicio):
    """
    Marca la key individual (legacy) como agotada.
    En el nuevo sistema de bundles, esto no es necesario pero se mantiene por compatibilidad.
    """
    APIKey.objects.filter(
        assigned_to=agente,
        servicio=servicio,
        status='assigned'
    ).update(status='exhausted')
