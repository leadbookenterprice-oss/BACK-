from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from api.models import APIBundleAssignment, APIKey
from django.utils import timezone
import requests

# Default limits si la key no tiene límite configurado
DEFAULT_LIMITS = {
    'gemini': 1500,       # Peticiones al mes estimadas
    'elevenlabs': 10000,  # Caracteres al mes
    'uploadpost': 10      # Posteos al mes estimados
}

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mi_uso_apis(request):
    """
    Devuelve el uso en tiempo real de las APIs asignadas al usuario logueado.
    ElevenLabs: consulta a su API.
    Gemini / UploadPost: lectura del contador interno.
    """
    user = request.user
    plan = getattr(user, 'plan_nombre', 'free') or 'free'
    
    stats = []
    
    # Si es usuario pago, usa llaves globales, por lo que mostramos su cuota personal (UserAPIQuota)
    if plan != 'free':
        from api.models import UserAPIQuota
        servicios = ['gemini', 'elevenlabs', 'uploadpost']
            # Si está bloqueado por cuota diaria, mostrar 100%
            if quota.is_blocked:
                consumido = limite
                status_val = 'exhausted'
            else:
                status_val = 'ok'
            
            stats.append({
                "servicio": svc,
                "nombre": nombre_display,
                "consumido": consumido,
                "limite": limite,
                "unidad": unidad_display,
                "porcentaje": min(100, int((consumido / limite) * 100)) if limite else 0,
                "status": status_val
            })
            
        return Response({
            "success": True,
            "bundle_nombre": f"Plan {plan.capitalize()} (Global Keys)",
            "stats": stats
        })
    
    # 1. Buscar el bundle activo del usuario (Free)
    assignment = APIBundleAssignment.objects.filter(usuario=user, activo=True).select_related('bundle').first()
    
    # Si no tiene bundle y es Free, intentar asignarle uno on-the-fly
    if not assignment or not assignment.bundle:
        from api.services.pool_service import APIPoolService
        bundle_asignado, _ = APIPoolService.assign_bundle_to_user(user)
        
        if bundle_asignado:
            # Recargar assignment
            assignment = APIBundleAssignment.objects.filter(usuario=user, activo=True).select_related('bundle').first()
        else:
            # Fallback a UserAPIQuota para usuarios free si no hay bundles disponibles
            from api.models import UserAPIQuota
            # Si está bloqueado por cuota diaria, mostrar 100%
            if quota.is_blocked:
                consumido = limite
                status_val = 'exhausted'
            else:
                status_val = 'ok'
                
            stats.append({
                "servicio": svc,
                "nombre": nombre_display,
                "consumido": consumido,
                "limite": limite,
                "unidad": unidad_display,
                "porcentaje": min(100, int((consumido / limite) * 100)) if limite else 0,
                "status": status_val
            })
                
            return Response({
                "success": True,
                "bundle_nombre": "Asignación Pendiente (Global Fallback)",
                "stats": stats
            })
        
    bundle = assignment.bundle
    
    # 2. Buscar si hay una key asignada directamente al usuario (ej. desde Admin Dashboard)
    key_gemini_directa = APIKey.objects.filter(assigned_to=user, servicio='gemini').order_by('-assigned_at', '-id').first()
    
    keys = {
        'gemini': key_gemini_directa if key_gemini_directa else bundle.key_gemini,
        'elevenlabs': bundle.key_elevenlabs,
        'uploadpost': bundle.key_uploadpost
    }
    
    for servicio, key in keys.items():
        if not key:
            continue
            
        limite = key.monthly_limit or (key.daily_limit * 30 if getattr(key, 'daily_limit', None) else DEFAULT_LIMITS.get(servicio, 100))
        
        # ELEVENLABS: Tiempo real 100%
        if servicio == 'elevenlabs':
            try:
                headers = {"xi-api-key": key.api_key}
                resp = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    consumido = data.get("character_count", 0)
                    limite = data.get("character_limit", limite)
                else:
                    consumido = key.requests_this_month
            except Exception:
                consumido = key.requests_this_month
                
            porcentaje = min(100, int((consumido / limite) * 100)) if limite else 0
            if key.status in ['exhausted', 'dead']:
                porcentaje = 100
                consumido = limite # Para que se vea coherente

            stats.append({
                "servicio": "elevenlabs",
                "nombre": "Voces Neurales",
                "consumido": consumido,
                "limite": limite,
                "unidad": "caracteres",
                "porcentaje": porcentaje,
                "status": key.status
            })
            
        # GEMINI / UPLOADPOST: Conteo Interno
        else:
            consumido = key.requests_this_month
            nombre_display = "Generación de Contenido IA" if servicio == 'gemini' else "Gestor de Redes"
            unidad_display = "peticiones" if servicio == 'gemini' else "publicaciones"
            
            # Verificar si el usuario está bloqueado individualmente para este servicio
            from api.models import UserAPIQuota
            user_quota, _ = UserAPIQuota.objects.get_or_create(user=user, service=servicio)
            
            porcentaje = min(100, int((consumido / limite) * 100)) if limite else 0
            current_status = key.status
            
            if user_quota.is_blocked:
                porcentaje = 100
                consumido = limite
                current_status = 'exhausted'
            elif key.status in ['exhausted', 'dead']:
                porcentaje = 100
                consumido = limite
                
            stats.append({
                "servicio": servicio,
                "nombre": nombre_display,
                "consumido": consumido,
                "limite": limite,
                "unidad": unidad_display,
                "porcentaje": porcentaje,
                "status": current_status
            })
            
    return Response({
        "success": True,
        "bundle_nombre": bundle.nombre,
        "stats": stats
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_uso_global(request):
    """
    Devuelve las estadísticas crudas de uso de todas las keys para el dashboard Admin.
    Para no hacer spam a la API de ElevenLabs, esto devuelve los contadores internos 
    para TODAS las keys, excepto que se pida refresh en vivo (opcional futuro).
    """
    keys = APIKey.objects.all().values(
        'id', 'servicio', 'label', 'status', 'empresa',
        'requests_today', 'requests_this_month', 'monthly_limit'
    )
    
    # Agregar % calculado y formatear
    resultado = []
    for k in keys:
        limite = k['monthly_limit'] or DEFAULT_LIMITS.get(k['servicio'], 100)
        consumido = k['requests_this_month']
        
        # Para elevenlabs en admin, podríamos consultar en vivo, pero si hay 100 keys
        # podría ser lento o causar un Rate Limit. Usaremos el trackeo interno para
        # mostrar algo aproximado, o podemos advertir que ElevenLabs real es por Key.
        
        porcentaje = min(100, int((consumido / limite) * 100)) if limite else 0
        
        k['limite'] = limite
        k['porcentaje'] = porcentaje
        resultado.append(k)
        
    return Response({
        "success": True,
        "keys": resultado
    })
