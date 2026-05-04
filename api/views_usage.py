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
    'uploadpost': 50      # Posteos al mes estimados
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
    
    # 1. Buscar el bundle activo del usuario
    assignment = APIBundleAssignment.objects.filter(usuario=user, activo=True).select_related('bundle').first()
    
    if not assignment or not assignment.bundle:
        return Response({
            "success": False,
            "error": "No tienes APIs asignadas."
        }, status=404)
        
    bundle = assignment.bundle
    keys = {
        'gemini': bundle.key_gemini,
        'elevenlabs': bundle.key_elevenlabs,
        'uploadpost': bundle.key_uploadpost
    }
    
    stats = []
    
    for servicio, key in keys.items():
        if not key:
            continue
            
        limite = key.monthly_limit or DEFAULT_LIMITS.get(servicio, 100)
        
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
                
            stats.append({
                "servicio": "elevenlabs",
                "nombre": "ElevenLabs",
                "consumido": consumido,
                "limite": limite,
                "unidad": "caracteres",
                "porcentaje": min(100, int((consumido / limite) * 100)) if limite else 0
            })
            
        # GEMINI / UPLOADPOST: Conteo Interno
        else:
            consumido = key.requests_this_month
            nombre_display = "Gemini AI" if servicio == 'gemini' else "UploadPost"
            unidad_display = "peticiones" if servicio == 'gemini' else "publicaciones"
            
            stats.append({
                "servicio": servicio,
                "nombre": nombre_display,
                "consumido": consumido,
                "limite": limite,
                "unidad": unidad_display,
                "porcentaje": min(100, int((consumido / limite) * 100)) if limite else 0
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
