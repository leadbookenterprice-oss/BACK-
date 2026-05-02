from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db.models import Count, Sum, Avg, F
from datetime import timedelta
from api.models import Agent, APIKey, APIRequestLog, AdminAlert, UserBanRecord
from api.services.pool_service import APIPoolService
import requests

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_stats_v2(request):
    """Stats globales para el admin dashboard."""
    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)
    
    total_users = Agent.objects.count()
    free_users = Agent.objects.filter(plan_nombre='free').count()
    paid_users = total_users - free_users
    
    requests_today = APIRequestLog.objects.filter(created_at__date=hoy).count()
    requests_month = APIRequestLog.objects.filter(created_at__date__gte=inicio_mes).count()
    
    # Pool stats
    pool_stats = APIPoolService.get_pool_stats()
    
    # Top users today
    top_users = list(APIRequestLog.objects.filter(created_at__date=hoy)
                     .values('user__email')
                     .annotate(total=Count('id'))
                     .order_by('-total')[:5])
                     
    # Top errors today
    top_errors = list(APIRequestLog.objects.filter(created_at__date=hoy, success=False)
                      .values('error_message')
                      .annotate(total=Count('id'))
                      .order_by('-total')[:5])

    return Response({
        "total_users": total_users,
        "free_users": free_users,
        "paid_users": paid_users,
        "requests_today": requests_today,
        "requests_month": requests_month,
        "pool_stats": pool_stats,
        "top_users_today": top_users,
        "top_errors_today": top_errors
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_api_keys_list(request):
    """Lista paginada de todas las keys con filtros."""
    service = request.query_params.get('service')
    status_filter = request.query_params.get('status')
    
    keys = APIKey.objects.all().order_by('-created_at')
    if service:
        keys = keys.filter(servicio=service)
    if status_filter:
        keys = keys.filter(status=status_filter)
        
    data = []
    for k in keys:
        data.append({
            "id": k.id,
            "service": k.servicio,
            "status": k.status,
            "assigned_to": k.assigned_to.email if k.assigned_to else None,
            "daily_limit": k.daily_limit,
            "requests_today": k.requests_today,
            "last_health_status": k.last_health_status,
            "error_count": k.error_count
        })
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_api_keys_create(request):
    """Crear nueva key."""
    servicio = request.data.get('service')
    api_key_str = request.data.get('api_key')
    limit = request.data.get('daily_limit', 1500)
    
    if not servicio or not api_key_str:
        return Response({"error": "Faltan datos"}, status=400)
        
    key = APIKey.objects.create(
        servicio=servicio,
        api_key=api_key_str,
        daily_limit=limit,
        status='available'
    )
    return Response({"id": key.id, "status": "created"}, status=201)

@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def admin_api_keys_detail(request, pk):
    try:
        key = APIKey.objects.get(pk=pk)
    except APIKey.DoesNotExist:
        return Response(status=404)
        
    if request.method == 'DELETE':
        key.delete()
        return Response(status=204)
        
    # PATCH
    if 'status' in request.data:
        key.status = request.data['status']
    if 'daily_limit' in request.data:
        key.daily_limit = request.data['daily_limit']
    if 'notes' in request.data:
        key.notes = request.data['notes']
    key.save()
    
    return Response({"id": key.id, "status": key.status})

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_api_keys_test(request, pk):
    """Hace un health check manual a esa key."""
    try:
        key = APIKey.objects.get(pk=pk)
    except APIKey.DoesNotExist:
        return Response(status=404)
        
    is_healthy = False
    error = None
    try:
        if key.servicio == 'gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={key.api_key}"
            res = requests.post(url, json={"contents":[{"parts":[{"text":"hello"}]}]}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
        elif key.servicio == 'elevenlabs':
            url = "https://api.elevenlabs.io/v1/voices"
            res = requests.get(url, headers={"xi-api-key": key.api_key}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
        elif key.servicio == 'uploadpost':
            url = "https://api.upload-post.com/api/uploadposts/users"
            res = requests.get(url, headers={"Authorization": f"Apikey {key.api_key}"}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
    except Exception as e:
        error = str(e)
        
    key.last_health_status = is_healthy
    key.last_health_check = timezone.now()
    if not is_healthy:
        key.error_count += 1
    key.save()
    
    return Response({"healthy": is_healthy, "error": error})

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_api_keys_reassign(request, pk):
    try:
        key = APIKey.objects.get(pk=pk)
    except APIKey.DoesNotExist:
        return Response(status=404)
        
    user = key.assigned_to
    if not user:
        return Response({"error": "Key is not assigned to any user"}, status=400)
        
    new_key = APIPoolService.rotate_key(user, key.servicio)
    return Response({"old_key": key.id, "new_key": new_key.id if new_key else None})

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_users_list(request):
    users = Agent.objects.all()[:100] # Limite temporal
    data = []
    for u in users:
        data.append({
            "id": u.id,
            "email": u.email,
            "plan": u.plan_nombre,
            "is_active": u.is_active,
            "is_banned": hasattr(u, 'bans') and u.bans.filter(is_active=True).exists()
        })
    return Response(data)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_users_detail(request, pk):
    try:
        u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response(status=404)
        
    keys = list(APIKey.objects.filter(assigned_to=u).values('id', 'servicio', 'status', 'requests_today'))
    logs = list(APIRequestLog.objects.filter(user=u).order_by('-created_at').values('service', 'endpoint', 'success', 'created_at')[:50])
    
    # Proxy para "online"
    is_online = False
    if u.last_login:
        is_online = (timezone.now() - u.last_login).total_seconds() < 300 # 5 mins
    
    return Response({
        "id": u.id,
        "email": u.email,
        "nombre": u.nombre,
        "telefono": u.telefono,
        "agencia": u.agencia,
        "nombre_inmobiliaria": u.nombre_inmobiliaria,
        "nicho": u.nicho,
        "pais": u.pais,
        "plan": u.plan_nombre,
        "fecha_registro": u.fecha_registro,
        "last_login": u.last_login,
        "is_online": is_online,
        "is_active": u.is_active,
        "keys": keys,
        "recent_logs": logs
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_user_info_general(request, pk):
    """Endpoint específico para información general solicitado por el usuario."""
    try:
        u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response(status=404)
    
    is_online = False
    if u.last_login:
        is_online = (timezone.now() - u.last_login).total_seconds() < 300
        
    return Response({
        "nombre": u.nombre,
        "nombre_negocio": u.nombre_inmobiliaria,
        "telefono": u.telefono,
        "email": u.email,
        "contraseña": "ENC_HASH", # No podemos mostrar texto plano
        "is_online": is_online,
        "ultima_conexion": u.last_login,
        "fecha_registro": u.fecha_registro,
        "agencia": u.agencia,
        "nicho": u.nicho,
        "pais": u.pais
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_user_api_pool(request, pk):
    """Endpoint específico para APIs asignadas."""
    try:
        u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response(status=404)
    
    keys = APIKey.objects.filter(assigned_to=u)
    data = []
    for k in keys:
        data.append({
            "id": k.id,
            "servicio": k.servicio,
            "status": k.status,
            "requests_today": k.requests_today,
            "daily_limit": k.daily_limit,
            "last_used": k.last_used_at
        })
    return Response(data)

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_users_hard_delete(request, pk):
    """Borrado físico del usuario de la base de datos."""
    try:
        u = Agent.objects.get(pk=pk)
        u.delete() # Esto borra físicamente al usuario y sus relaciones en cascada (si está definido)
        return Response({"status": "deleted_permanently"}, status=200)
    except Agent.DoesNotExist:
        return Response(status=404)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_users_ban(request, pk):
    try:
        u = Agent.objects.get(pk=pk)
        UserBanRecord.objects.create(
            user=u,
            banned_by=request.user,
            reason=request.data.get('reason', 'Sin razón provista')
        )
        u.is_active = False
        u.save()
        APIPoolService.release_keys_from_user(u)
        return Response({"status": "banned"})
    except Agent.DoesNotExist:
        return Response(status=404)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_users_unban(request, pk):
    try:
        u = Agent.objects.get(pk=pk)
        UserBanRecord.objects.filter(user=u, is_active=True).update(is_active=False)
        u.is_active = True
        u.save()
        if u.plan_nombre == 'free':
            APIPoolService.assign_keys_to_user(u)
        return Response({"status": "unbanned"})
    except Agent.DoesNotExist:
        return Response(status=404)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_requests_list(request):
    logs = APIRequestLog.objects.all().order_by('-created_at')[:100]
    data = []
    for l in logs:
        data.append({
            "id": l.id,
            "user": l.user.email if l.user else None,
            "service": l.service,
            "endpoint": l.endpoint,
            "success": l.success,
            "time_ms": l.response_time_ms,
            "created_at": l.created_at
        })
    return Response(data)

@api_view(['GET', 'PATCH'])
@permission_classes([IsAdminUser])
def admin_alerts_list(request):
    if request.method == 'GET':
        alerts = AdminAlert.objects.filter(is_read=False).order_by('-created_at')[:50]
        data = list(alerts.values('id', 'type', 'severity', 'title', 'message', 'created_at'))
        return Response(data)
    else:
        # Marcar leídas
        ids = request.data.get('ids', [])
        AdminAlert.objects.filter(id__in=ids).update(is_read=True)
        return Response({"status": "updated"})

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_analytics_timeseries(request):
    # Simulación simple de time series
    return Response({"data": "Time series analytics will be here."})

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_analytics_top(request):
    # Simulación simple de rankings
    return Response({"data": "Top analytics will be here."})

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_health_status(request):
    # Porcentaje de keys sanas
    total = APIKey.objects.count()
    healthy = APIKey.objects.filter(last_health_status=True).count()
    return Response({
        "healthy_percentage": (healthy / total * 100) if total > 0 else 0,
        "total_keys": total,
        "healthy_keys": healthy
    })
