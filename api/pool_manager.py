from api.models import APIKey
from django.conf import settings
from django.utils import timezone

def get_api_key(agente, servicio):
    """
    Retorna la API key correcta según el plan del agente.
    Free → usa su cuenta del pool asignada
    Pago → usa la key global del .env
    """
    plan = getattr(agente, 'plan_nombre', 'free') or 'free'

    if plan != 'free':
        # Planes de pago: usar keys globales
        keys_globales = {
            'gemini': settings.GEMINI_API_KEY,
            'elevenlabs': getattr(settings, 'ELEVENLABS_API_KEY', ''),
            'uploadpost': getattr(settings, 'UPLOADPOST_API_KEY', ''),
        }
        return keys_globales.get(servicio, '')

    # Plan free: buscar cuenta asignada del pool
    cuenta = APIKey.objects.filter(
        assigned_to=agente,
        servicio=servicio,
        status='assigned'
    ).first()

    if cuenta:
        return cuenta.api_key

    # Si no tiene cuenta asignada, asignar una libre
    cuenta_libre = APIKey.objects.filter(
        assigned_to=None,
        servicio=servicio,
        status='available'
    ).first()

    if cuenta_libre:
        cuenta_libre.assigned_to = agente
        cuenta_libre.status = 'assigned'
        cuenta_libre.assigned_at = timezone.now()
        cuenta_libre.save()
        return cuenta_libre.api_key

    # No hay cuentas disponibles en el pool, usar keys globales como fallback
    keys_globales = {
        'gemini': settings.GEMINI_API_KEY,
        'elevenlabs': getattr(settings, 'ELEVENLABS_API_KEY', ''),
        'uploadpost': getattr(settings, 'UPLOADPOST_API_KEY', ''),
    }
    return keys_globales.get(servicio, None)

def marcar_agotada(agente, servicio):
    """Marca la cuenta del pool como agotada cuando la API falla"""
    APIKey.objects.filter(
        assigned_to=agente,
        servicio=servicio,
        status='assigned'
    ).update(status='exhausted')
