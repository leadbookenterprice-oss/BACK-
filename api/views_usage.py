"""
api/views_usage.py — LeadBook v2.0
Estadísticas de uso de APIs para usuarios y admin.
Lógica migrada al nuevo schema de Servicio / UserAPIQuota / UserAPIAssignment.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from api.models import APIKey, UserAPIQuota, Servicio, UserAPIAssignment
from django.utils import timezone
import requests


# Nombres amigables para el frontend
SERVICIO_MAP = {
    'gemini': {
        'nombre': "Generación de Contenido IA",
        'unidad': "peticiones",
        'icono': "brain"
    },
    'elevenlabs': {
        'nombre': "Voces Neurales",
        'unidad': "caracteres",
        'icono': "mic"
    },
    'uploadpost': {
        'nombre': "Gestor de Redes",
        'unidad': "publicaciones",
        'icono': "share"
    }
}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mi_uso_apis(request):
    """
    Devuelve el uso de APIs del usuario actual.
    Cruza datos de UserAPIQuota con las keys asignadas en UserAPIAssignment.
    """
    user = request.user
    
    # 1. Obtener todas las cuotas del usuario
    quotas = UserAPIQuota.objects.filter(user=user).select_related('servicio')
    
    # Si no tiene cuotas, intentar repararlas (asignar keys si es nuevo)
    if not quotas.exists():
        from api.services.pool_service import APIPoolService
        APIPoolService.assign_keys_to_user(user)
        quotas = UserAPIQuota.objects.filter(user=user).select_related('servicio')

    stats = []
    for q in quotas:
        q.maybe_reset_daily()
        q.recalcular_limite(plan=user.plan_nombre)
        if q.is_blocked and q.requests_today < q.user_daily_limit:
            q.is_blocked = False
            q.blocked_reason = None
            q.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])

        svc_name = q.servicio.nombre
        soft_exhaustion = svc_name in {'gemini', 'elevenlabs', 'uploadpost'}
        info = SERVICIO_MAP.get(svc_name, {
            'nombre': svc_name.capitalize(),
            'unidad': "unidades",
            'icono': "api"
        })
        
        limite = q.user_daily_limit or 1500
        consumido = q.requests_today
        usable_statuses = ['assigned', 'available', 'exhausted'] if soft_exhaustion else ['assigned', 'available']
        active_assignments = UserAPIAssignment.objects.filter(
            user=user,
            servicio=q.servicio,
            activo=True,
            apikey__status__in=usable_statuses,
        ).select_related('apikey')
        if soft_exhaustion:
            has_usable_key = active_assignments.exists()
            exhausted_by_key = False
            if q.is_blocked:
                q.is_blocked = False
                q.blocked_reason = None
                q.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])
        else:
            has_usable_key = any(
                not (a.apikey.google_daily_limit and a.apikey.requests_today >= a.apikey.google_daily_limit)
                for a in active_assignments
            )
            exhausted_by_key = not has_usable_key and UserAPIAssignment.objects.filter(
                user=user,
                servicio=q.servicio,
                activo=True,
                apikey__status='exhausted',
            ).exists()
        extras_activos = UserAPIAssignment.objects.filter(
            user=user,
            servicio=q.servicio,
            activo=True,
            is_primary=False,
        ).count()
        
        # ElevenLabs: si es posible, consultar a la API real para mayor precisión
        # (Solo si tiene una key asignada y activa)
        if svc_name == 'elevenlabs':
            asig = UserAPIAssignment.objects.filter(user=user, servicio=q.servicio, activo=True).first()
            if asig and asig.apikey:
                try:
                    # Opcional: consulta en vivo a ElevenLabs. 
                    # Por ahora usamos el contador interno para velocidad.
                    pass
                except Exception:
                    pass

        porcentaje = min(100, int((consumido / limite) * 100)) if limite else 0
        if q.is_blocked or exhausted_by_key:
            porcentaje = 100
            consumido = max(consumido, limite)
            if not q.is_blocked:
                q.is_blocked = True
                q.blocked_reason = 'API key obligatoria agotada'
                q.requests_today = consumido
                q.save(update_fields=['is_blocked', 'blocked_reason', 'requests_today', 'updated_at'])
            
        stats.append({
            "servicio": svc_name,
            "nombre": info['nombre'],
            "icono": info['icono'],
            "consumido": consumido,
            "limite": limite,
            "extras_activos": extras_activos,
            "unidad": info['unidad'],
            "porcentaje": porcentaje,
            "status": "ok" if soft_exhaustion else ("exhausted" if q.is_blocked or exhausted_by_key else "ok")
        })

    return Response({
        "success": True,
        "plan": user.plan_nombre,
        "stats": stats
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_uso_global(request):
    """
    Dashboard administrativo de uso de llaves.
    Muestra el estado de salud y consumo de cada APIKey en la bodega.
    """
    keys = APIKey.objects.all().select_related('servicio').order_by('servicio', '-total_requests')
    
    resultado = []
    for k in keys:
        limite = k.google_daily_limit or 1500
        consumido = k.requests_today
        porcentaje = min(100, int((consumido / limite) * 100)) if limite else 0
        if k.status == 'exhausted':
            porcentaje = 100
            consumido = max(consumido, limite)
        
        resultado.append({
            "id": k.id,
            "servicio": k.servicio.nombre,
            "label": k.label or f"{k.api_key[:8]}...",
            "empresa": k.empresa,
            "status": k.status,
            "consumido_hoy": consumido,
            "limite_hoy": limite,
            "porcentaje": porcentaje,
            "total_requests": k.total_requests,
            "error_count": k.error_count,
            "ultima_vez": k.last_used_at
        })
        
    return Response({
        "success": True,
        "keys": resultado
    })
