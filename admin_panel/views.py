from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Count, Sum, Avg, F, Q
from datetime import timedelta
from api.models import Agent, APIKey, APIRequestLog, AdminAlert, UserBanRecord, Listado, Plan
from api.services.pool_service import APIPoolService
from decouple import config
import requests

ADMIN_KEY = config('ADMIN_KEY', default='leadbook_admin_2026')

def _check_admin(request):
    if request.headers.get('X-Admin-Key') == ADMIN_KEY and ADMIN_KEY:
        return True
    return request.user and request.user.is_authenticated and request.user.is_staff

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats_v2(request):
    """Stats globales para el admin dashboard."""
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)

    total_users = Agent.objects.filter(eliminado_en__isnull=True).count()
    free_users = Agent.objects.filter(plan_nombre='free', eliminado_en__isnull=True).count()
    paid_users = total_users - free_users
    active_apis = APIKey.objects.filter(status='available').count()
    pending_alerts = AdminAlert.objects.filter(is_read=False).count()

    requests_today = 0
    requests_month = 0
    try:
        requests_today = APIRequestLog.objects.filter(created_at__date=hoy).count()
        requests_month = APIRequestLog.objects.filter(created_at__date__gte=inicio_mes).count()
    except Exception:
        pass

    # Requests last 7 days for chart
    history = []
    for i in range(6, -1, -1):
        day = hoy - timedelta(days=i)
        try:
            cnt = APIRequestLog.objects.filter(created_at__date=day).count()
        except Exception:
            cnt = 0
        history.append({'date': day.strftime('%d/%m'), 'count': cnt})

    # Service usage pie
    service_usage = []
    try:
        service_usage = list(
            APIRequestLog.objects.filter(created_at__date__gte=inicio_mes)
            .values('service').annotate(value=Count('id'))
            .order_by('-value')[:5]
        )
    except Exception:
        pass

    # Plan distribution
    plan_dist = {}
    for row in Agent.objects.filter(eliminado_en__isnull=True).values('plan_nombre').annotate(total=Count('id')):
        plan_dist[row['plan_nombre'] or 'free'] = row['total']

    # Top users
    top_users = []
    try:
        top_users = list(
            APIRequestLog.objects.filter(created_at__date=hoy)
            .values('user__email').annotate(requests=Count('id'))
            .order_by('-requests')[:5]
        )
        for u in top_users:
            u['email'] = u.pop('user__email', '')
            u['cost'] = round(u['requests'] * 0.001, 4)
    except Exception:
        pass

    return Response({
        'stats': {
            'totalUsers': total_users,
            'freeUsers': free_users,
            'paidUsers': paid_users,
            'activeApis': active_apis,
            'pendingAlerts': pending_alerts,
            'requestsToday': requests_today,
            'requestsMonth': requests_month,
        },
        'charts': {
            'requests_history': history,
            'service_usage': service_usage,
        },
        'top_users': top_users,
        # legacy flat fields for compatibility
        'total_users': total_users,
        'free_users': free_users,
        'paid_users': paid_users,
        'requests_today': requests_today,
        'requests_month': requests_month,
        'usuarios_por_plan': plan_dist,
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_api_keys_list(request):
    """Lista paginada de todas las keys con filtros."""
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    service = request.query_params.get('service') or request.query_params.get('servicio')
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
            "servicio": k.servicio,  # frontend might expect 'servicio'
            "service": k.servicio,
            "status": k.status,
            "api_key": k.api_key,
            "key_masked": k.api_key[:10] + "..." if k.api_key else "",
            "assigned_to": k.assigned_to.email if k.assigned_to else None,
            "assigned_to_email": k.assigned_to.email if k.assigned_to else None,
            "assigned_to_id": k.assigned_to.id if k.assigned_to else None,
            "assigned_to_nombre": k.assigned_to.nombre if k.assigned_to else None,
            "daily_limit": k.daily_limit,
            "requests_today": k.requests_today,
            "last_health_status": k.last_health_status,
            "error_count": k.error_count
        })
    return Response(data)

@api_view(['POST'])
@permission_classes([AllowAny])
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

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_bulk_create(request):
    """Crear múltiples keys de forma masiva."""
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
        
    keys_data = request.data.get('keys', [])
    if not keys_data:
        return Response({"error": "No se enviaron keys"}, status=400)
        
    new_keys = []
    for data in keys_data:
        servicio = data.get('service') or data.get('servicio')
        api_key_str = data.get('api_key') or data.get('key')
        limit = data.get('daily_limit', 1500)
        label_str = data.get('label')
        
        if servicio and api_key_str:
            # Avoid exact duplicates
            if not APIKey.objects.filter(api_key=api_key_str, servicio=servicio).exists():
                new_keys.append(APIKey(
                    servicio=servicio,
                    api_key=api_key_str,
                    daily_limit=limit,
                    label=label_str,
                    status='available'
                ))
                
    counts = {}
    if new_keys:
        APIKey.objects.bulk_create(new_keys)
        for k in new_keys:
            counts[k.servicio] = counts.get(k.servicio, 0) + 1
        
    return Response({
        "status": "created", 
        "count": len(new_keys), 
        "counts_by_service": counts,
        "ignored": len(keys_data) - len(new_keys)
    }, status=201)

@api_view(['PATCH', 'DELETE'])
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
def admin_users_list(request):
    users = Agent.objects.all().order_by('-fecha_registro')[:100] # Limite temporal
    data = []
    for u in users:
        data.append({
            "id": u.id,
            "email": u.email,
            "nombre": u.nombre,
            "logo_url": u.logo_url,
            "plan": u.plan_nombre,
            "is_active": u.is_active,
            "is_suspended": not u.is_active
        })
    return Response(data)

@api_view(['GET'])
@permission_classes([AllowAny])
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
        "logo_url": u.logo_url,
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
def admin_users_hard_delete(request, pk):
    """Borrado físico del usuario de la base de datos."""
    try:
        u = Agent.objects.get(pk=pk)
        
        # Liberar APIs atadas a esta cuenta ANTES de borrar físicamente
        from api.services.pool_service import APIPoolService
        APIPoolService.release_keys_from_user(u)
        
        u.delete() # Esto borra físicamente al usuario y sus relaciones en cascada
        return Response({"status": "deleted_permanently"}, status=200)
    except Agent.DoesNotExist:
        return Response(status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_users_ban(request, pk):
    try:
        u = Agent.objects.get(pk=pk)
        UserBanRecord.objects.create(
            user=u,
            banned_by=request.user if request.user.is_authenticated else None,
            reason=request.data.get('reason', 'Sin razón provista')
        )
        u.is_active = False
        u.save()
        APIPoolService.release_keys_from_user(u)
        
        # Añadir email a la blacklist permanente para que nunca se pueda re-registrar
        from api.models import BannedEmail, BannedIP
        BannedEmail.objects.get_or_create(
            email=u.email,
            defaults={'reason': request.data.get('reason', 'Baneado por el administrador')}
        )
        
        # Añadir IP a la blacklist si existe
        if u.last_login_ip:
            BannedIP.objects.get_or_create(
                ip_address=u.last_login_ip,
                defaults={'reason': request.data.get('reason', 'Baneado por el administrador (IP compartida o router)')}
            )
        
        return Response({
            "status": "banned_permanently", 
            "email": u.email,
            "ip_banned": bool(u.last_login_ip)
        })
    except Agent.DoesNotExist:
        return Response(status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
def admin_analytics_timeseries(request):
    # Simulación simple de time series
    return Response({"data": "Time series analytics will be here."})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_analytics_top(request):
    # Simulación simple de rankings
    return Response({"data": "Top analytics will be here."})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_health_status(request):
    # Porcentaje de keys sanas
    total = APIKey.objects.count()
    healthy = APIKey.objects.filter(last_health_status=True).count()
    return Response({
        "healthy_percentage": (healthy / total * 100) if total > 0 else 0,
        "total_keys": total,
        "healthy_keys": healthy
    })


# ── Stubs / Aliases requeridos por urls.py ────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_health_check_trigger(request):
    from api.tasks import health_check_all_keys
    try:
        health_check_all_keys.delay()
    except Exception:
        health_check_all_keys()
    return Response({"success": True, "message": "Health check disparado"})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_alert_read(request, alert_id):
    try:
        alert = AdminAlert.objects.get(id=alert_id)
        alert.is_read = True
        alert.save()
        return Response({"success": True})
    except AdminAlert.DoesNotExist:
        return Response({"error": "Alerta no encontrada"}, status=404)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    from django.db.models import Count
    qs = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    data = [{"id": l.id, "titulo": l.titulo, "ciudad": l.ciudad,
             "agente": l.agente.email, "video_status": l.video_status,
             "creado_en": l.creado_en.isoformat()} for l in qs]
    return Response({"listados": data, "total": Listado.objects.count()})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    return Response({"assets": [], "total": 0})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    return Response({"pagos": [], "total": 0})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_eliminados(request):
    qs = Agent.objects.filter(eliminado_en__isnull=False).order_by('-eliminado_en')
    data = [{"id": a.id, "email": a.email, "nombre": a.nombre,
             "eliminado_en": a.eliminado_en.isoformat()} for a in qs]
    return Response({"usuarios": data})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_restaurar(request, pk):
    try:
        a = Agent.objects.get(id=pk)
        a.eliminado_en = None
        a.is_active = True
        a.save()
        return Response({"success": True})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)


@api_view(['POST', 'DELETE'])
@permission_classes([AllowAny])
def admin_usuario_eliminar(request, pk):
    from api.views_admin import admin_usuario_eliminar as _v
    return _v(request._request, user_id=pk)

@api_view(['PUT'])
@permission_classes([AllowAny])
def admin_usuario_cambiar_plan(request, pk):
    try:
        a = Agent.objects.get(id=pk)
        a.plan_nombre = request.data.get('plan', a.plan_nombre)
        a.plan_activo = True
        a.save()
        return Response({"success": True, "plan": a.plan_nombre})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_enviar_email(request, pk):
    try:
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        a = Agent.objects.get(id=pk)
        asunto = request.data.get('asunto', 'Mensaje de LeadBook')
        mensaje = request.data.get('mensaje', '')
        send_mail(asunto, mensaje, django_settings.DEFAULT_FROM_EMAIL, [a.email], fail_silently=True)
        return Response({"success": True})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)


# ── Bundle views (proxy al views_admin de api) ─────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_list(request):
    from api.views_admin import admin_bundles_list as _v
    return _v(request._request)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_crear(request):
    from api.views_admin import admin_bundles_crear as _v
    return _v(request._request)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_stats(request):
    from api.views_admin import admin_bundles_stats as _v
    return _v(request._request)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_bundles_detail(request, bundle_id):
    from api.views_admin import admin_bundles_detail as _v
    return _v(request._request, bundle_id=bundle_id)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_asignar(request, bundle_id):
    from api.views_admin import admin_bundles_asignar as _v
    return _v(request._request, bundle_id=bundle_id)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_liberar(request, bundle_id):
    from api.views_admin import admin_bundles_liberar as _v
    return _v(request._request, bundle_id=bundle_id)
