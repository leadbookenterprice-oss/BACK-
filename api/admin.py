"""
admin_panel/views.py — LeadBook v2.0
Corregido para el nuevo schema:
- APIKey.servicio es FK a Servicio (no string) → usar servicio__nombre para filtrar
- APIKey.assigned_to eliminado → usar UserAPIAssignment
- APIKey.daily_limit → google_daily_limit
- APIKey.created_at → creado_en
- AdminAlert: type→tipo, severity→severidad, message→mensaje, created_at→creado_en
- APIRequestLog: service→servicio__nombre, created_at→creado_en
- Bundles eliminados → reemplazados con lógica v2
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
from api.models import (
    Agent, APIKey, APIRequestLog, AdminAlert, UserBanRecord,
    Listado, Plan, Servicio, UserAPIAssignment, UserAPIQuota
)
from api.services.pool_service import APIPoolService
from decouple import config
from django.conf import settings
from django.utils.crypto import constant_time_compare
from admin_panel.auth import is_admin_request

ADMIN_KEY = config('ADMIN_KEY', default='')


def _check_admin(request):
    return is_admin_request(request)


def _mask_secret(value, head=4, tail=4):
    value = str(value or '')
    if not value:
        return ''
    if len(value) <= head + tail:
        return '*' * len(value)
    return f'{value[:head]}...{value[-tail:]}'


# ══════════════════════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats_v2(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)

    total_users  = Agent.objects.filter(eliminado_en__isnull=True).count()
    free_users   = Agent.objects.filter(
        plan_nombre='starter',
        free_trial_ends_at__isnull=False,
        eliminado_en__isnull=True,
    ).count()
    paid_users   = total_users - free_users
    active_apis  = APIKey.objects.filter(status='available').count()
    pending_alerts = AdminAlert.objects.filter(is_read=False).count()

    requests_today = 0
    requests_month = 0
    try:
        requests_today = APIRequestLog.objects.filter(creado_en__date=hoy).count()
        requests_month = APIRequestLog.objects.filter(creado_en__date__gte=inicio_mes).count()
    except Exception:
        pass

    # Últimos 7 días
    history = []
    for i in range(6, -1, -1):
        day = hoy - timedelta(days=i)
        try:
            cnt = APIRequestLog.objects.filter(creado_en__date=day).count()
        except Exception:
            cnt = 0
        history.append({'date': day.strftime('%d/%m'), 'count': cnt})

    # Uso por servicio
    service_usage = []
    try:
        service_usage = list(
            APIRequestLog.objects
            .filter(creado_en__date__gte=inicio_mes)
            .values('servicio__nombre')
            .annotate(value=Count('id'))
            .order_by('-value')[:5]
        )
        for s in service_usage:
            s['service'] = s.pop('servicio__nombre', '')
    except Exception:
        pass

    # Distribución de planes
    plan_dist = {}
    for row in Agent.objects.filter(eliminado_en__isnull=True).values('plan_nombre').annotate(total=Count('id')):
        plan_dist[row['plan_nombre'] or 'starter'] = row['total']

    # Top usuarios hoy
    top_users = []
    try:
        top_users = list(
            APIRequestLog.objects.filter(creado_en__date=hoy)
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
            'totalUsers':     total_users,
            'freeUsers':      free_users,
            'paidUsers':      paid_users,
            'activeApis':     active_apis,
            'pendingAlerts':  pending_alerts,
            'requestsToday':  requests_today,
            'requestsMonth':  requests_month,
        },
        'charts': {
            'requests_history': history,
            'service_usage':    service_usage,
        },
        'top_users':         top_users,
        # Campos planos para compatibilidad con frontend
        'total_users':       total_users,
        'free_users':        free_users,
        'paid_users':        paid_users,
        'requests_today':    requests_today,
        'requests_month':    requests_month,
        'usuarios_por_plan': plan_dist,
    })


# ══════════════════════════════════════════════════════════════════════════════
# API KEYS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_api_keys_list(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    service       = request.query_params.get('service') or request.query_params.get('servicio')
    status_filter = request.query_params.get('status')

    keys = APIKey.objects.select_related('servicio').order_by('-creado_en')
    if service:
        keys = keys.filter(servicio__nombre=service)
    if status_filter:
        keys = keys.filter(status=status_filter)

    data = []
    for k in keys:
        # Buscar asignación activa en UserAPIAssignment
        asig = UserAPIAssignment.objects.filter(
            apikey=k, activo=True, is_primary=True
        ).select_related('user').first()

        data.append({
            'id':               k.id,
            'servicio':         k.servicio.nombre,
            'service':          k.servicio.nombre,
            'status':           k.status,
            'api_key':          _mask_secret(k.api_key),
            'key_masked':       _mask_secret(k.api_key),
            'label':            k.label,
            'assigned_to':      asig.user.email if asig else None,
            'assigned_to_email':asig.user.email if asig else None,
            'assigned_to_id':   asig.user.id if asig else None,
            'assigned_to_nombre':asig.user.nombre if asig else None,
            'daily_limit':      k.google_daily_limit,
            'requests_today':   k.requests_today,
            'last_health_status': k.last_health_status,
            'error_count':      k.error_count,
            'creado_en':        k.creado_en.isoformat() if k.creado_en else None,
        })
    return Response(data)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_create(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    servicio_nombre = request.data.get('service') or request.data.get('servicio')
    api_key_str     = request.data.get('api_key')
    limit           = request.data.get('daily_limit', 1500)
    label_str       = request.data.get('label')

    if not servicio_nombre or not api_key_str:
        return Response({'error': 'Faltan datos: service y api_key son requeridos'}, status=400)

    servicio = Servicio.objects.filter(nombre=servicio_nombre.lower()).first()
    if not servicio:
        return Response({'error': f'Servicio "{servicio_nombre}" no encontrado. Servicios disponibles: {list(Servicio.objects.values_list("nombre", flat=True))}'}, status=400)

    key = APIKey.objects.create(
        servicio=servicio,
        api_key=api_key_str,
        google_daily_limit=limit,
        label=label_str,
        status='available'
    )
    return Response({'id': key.id, 'status': 'created', 'servicio': servicio.nombre}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_bulk_create(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    keys_data = request.data.get('keys', [])
    if not keys_data:
        return Response({'error': 'No se enviaron keys'}, status=400)

    new_keys = []
    errores  = []

    for data in keys_data:
        servicio_nombre = data.get('service') or data.get('servicio')
        api_key_str     = data.get('api_key') or data.get('key')
        limit           = data.get('daily_limit', 1500)
        label_str       = data.get('label')

        if not servicio_nombre or not api_key_str:
            errores.append({'data': data, 'error': 'Faltan service o api_key'})
            continue

        servicio = Servicio.objects.filter(nombre=servicio_nombre.lower()).first()
        if not servicio:
            errores.append({'data': data, 'error': f'Servicio "{servicio_nombre}" no existe'})
            continue

        if not APIKey.objects.filter(api_key=api_key_str, servicio=servicio).exists():
            new_keys.append(APIKey(
                servicio=servicio,
                api_key=api_key_str,
                google_daily_limit=limit,
                label=label_str,
                status='available'
            ))

    counts = {}
    if new_keys:
        APIKey.objects.bulk_create(new_keys)
        for k in new_keys:
            nombre = k.servicio.nombre
            counts[nombre] = counts.get(nombre, 0) + 1

    return Response({
        'status':            'created',
        'count':             len(new_keys),
        'counts_by_service': counts,
        'ignored':           len(keys_data) - len(new_keys) - len(errores),
        'errores':           errores,
    }, status=201)


@api_view(['PATCH', 'DELETE', 'POST'])
@permission_classes([AllowAny])
def admin_api_keys_detail(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        key = APIKey.objects.select_related('servicio').get(pk=pk)
    except APIKey.DoesNotExist:
        return Response(status=404)

    if request.method == 'POST':
        path = request.path
        if path.endswith('/liberar/'):
            # Desactivar asignaciones activas de esta key
            UserAPIAssignment.objects.filter(apikey=key, activo=True).update(activo=False)
            key.status = 'available'
            key.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'released'})

        elif path.endswith('/reactivar/'):
            key.status = 'available'
            key.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'reactivated'})

        elif path.endswith('/reset/'):
            key.requests_today      = 0
            key.requests_this_month = 0
            key.error_count         = 0
            if key.status == 'exhausted':
                tiene_asig = UserAPIAssignment.objects.filter(apikey=key, activo=True).exists()
                key.status = 'assigned' if tiene_asig else 'available'
            key.save()
            return Response({'status': 'reset'})

        return Response({'error': 'Acción POST desconocida'}, status=400)

    if request.method == 'DELETE':
        # Liberar asignaciones antes de borrar
        UserAPIAssignment.objects.filter(apikey=key).update(activo=False)
        key.delete()
        return Response(status=204)

    # PATCH
    if 'status' in request.data:
        key.status = request.data['status']
    if 'daily_limit' in request.data:
        key.google_daily_limit = request.data['daily_limit']
    if 'notes' in request.data:
        key.notes = request.data['notes']
    if 'label' in request.data:
        key.label = request.data['label']
    key.save()
    return Response({'id': key.id, 'status': key.status})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_test(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        key = APIKey.objects.select_related('servicio').get(pk=pk)
    except APIKey.DoesNotExist:
        return Response(status=404)

    import requests as req
    is_healthy = False
    error      = None
    servicio_nombre = key.servicio.nombre

    try:
        if servicio_nombre == 'gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={key.api_key}"
            res = req.post(url, json={'contents': [{'parts': [{'text': 'hello'}]}]}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
        elif servicio_nombre == 'elevenlabs':
            res = req.get('https://api.elevenlabs.io/v1/voices',
                          headers={'xi-api-key': key.api_key}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
        elif servicio_nombre == 'uploadpost':
            res = req.get('https://api.upload-post.com/api/uploadposts/users',
                          headers={'Authorization': f'Apikey {key.api_key}'}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
    except Exception as e:
        error = str(e)

    key.last_health_status = is_healthy
    key.last_health_check  = timezone.now()
    if not is_healthy:
        key.error_count += 1
    key.save(update_fields=['last_health_status', 'last_health_check', 'error_count', 'updated_at'])

    return Response({'healthy': is_healthy, 'error': error})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_reassign(request, pk):
    """Reasigna la key a otro usuario del pool."""
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        key = APIKey.objects.select_related('servicio').get(pk=pk)
    except APIKey.DoesNotExist:
        return Response(status=404)

    asig = UserAPIAssignment.objects.filter(apikey=key, activo=True).select_related('user').first()
    if not asig:
        return Response({'error': 'Key no está asignada a ningún usuario'}, status=400)

    # Reparar usando pool_service
    repaired = APIPoolService.repair_user_apis(asig.user)
    return Response({'repaired_services': repaired})


# ══════════════════════════════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_users_list(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    users = Agent.objects.filter(eliminado_en__isnull=True).order_by('-fecha_registro')[:100]
    data = []
    for u in users:
        data.append({
            'id':           u.id,
            'email':        u.email,
            'nombre':       u.nombre,
            'logo_url':     u.logo_url,
            'plan':         u.plan_nombre,
            'is_active':    u.is_active,
            'is_suspended': not u.is_active,
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_users_detail(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response(status=404)

    # APIs asignadas via UserAPIAssignment
    assignments = UserAPIAssignment.objects.filter(
        user=u, activo=True
    ).select_related('apikey', 'servicio')

    keys = [{
        'id':           a.apikey.id,
        'servicio':     a.servicio.nombre,
        'status':       a.apikey.status,
        'requests_today': a.apikey.requests_today,
        'daily_limit':  a.apikey.google_daily_limit,
        'is_primary':   a.is_primary,
    } for a in assignments]

    # Quota real del usuario
    quotas = UserAPIQuota.objects.filter(user=u).select_related('servicio')
    quota_data = [{
        'servicio':         q.servicio.nombre,
        'requests_today':   q.requests_today,
        'user_daily_limit': q.user_daily_limit,
        'is_blocked':       q.is_blocked,
    } for q in quotas]

    logs = list(
        APIRequestLog.objects.filter(user=u)
        .select_related('servicio')
        .order_by('-creado_en')
        .values('servicio__nombre', 'endpoint', 'success', 'creado_en')[:50]
    )
    for l in logs:
        l['service'] = l.pop('servicio__nombre', '')
        l['created_at'] = l.pop('creado_en', None)

    is_online = False
    if u.last_login:
        is_online = (timezone.now() - u.last_login).total_seconds() < 300

    return Response({
        'id':                 u.id,
        'email':              u.email,
        'nombre':             u.nombre,
        'logo_url':           u.logo_url,
        'telefono':           u.telefono,
        'agencia':            u.agencia,
        'nombre_inmobiliaria':u.nombre_inmobiliaria,
        'nicho':              u.nicho,
        'pais':               u.pais,
        'plan':               u.plan_nombre,
        'fecha_registro':     u.fecha_registro,
        'last_login':         u.last_login,
        'is_online':          is_online,
        'is_active':          u.is_active,
        'keys':               keys,
        'quotas':             quota_data,
        'recent_logs':        logs,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_user_info_general(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response(status=404)

    is_online = False
    if u.last_login:
        is_online = (timezone.now() - u.last_login).total_seconds() < 300

    return Response({
        'nombre':           u.nombre,
        'nombre_negocio':   u.nombre_inmobiliaria,
        'telefono':         u.telefono,
        'email':            u.email,
        'is_online':        is_online,
        'ultima_conexion':  u.last_login,
        'fecha_registro':   u.fecha_registro,
        'agencia':          u.agencia,
        'nicho':            u.nicho,
        'pais':             u.pais,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_user_api_pool(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist:
        return Response(status=404)

    assignments = UserAPIAssignment.objects.filter(
        user=u, activo=True
    ).select_related('apikey', 'servicio')

    # Quotas reales del usuario
    quotas = {
        q.servicio.nombre: q
        for q in UserAPIQuota.objects.filter(user=u).select_related('servicio')
    }

    data = []
    for a in assignments:
        svc_nombre = a.servicio.nombre
        quota      = quotas.get(svc_nombre)
        data.append({
            'id':               a.apikey.id,
            'servicio':         svc_nombre,
            'status':           a.apikey.status,
            'is_primary':       a.is_primary,
            'requests_today':   quota.requests_today if quota else 0,
            'daily_limit':      quota.user_daily_limit if quota else a.apikey.google_daily_limit,
            'is_blocked':       quota.is_blocked if quota else False,
            'last_used':        a.apikey.last_used_at,
        })
    return Response(data)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_users_hard_delete(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        u = Agent.objects.get(pk=pk)
        APIPoolService.release_keys_from_user(u)
        AdminAlert.objects.create(
            tipo='assign_failed',
            severidad='info',
            titulo='Usuario eliminado y APIs liberadas',
            mensaje=f'El usuario {u.email} fue eliminado. Sus keys volvieron al pool.',
            related_user=u,
        )
        u.delete()
        return Response({'status': 'deleted_permanently'}, status=200)
    except Agent.DoesNotExist:
        return Response(status=404)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_users_ban(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        u = Agent.objects.get(pk=pk)
        reason = request.data.get('reason', 'Sin razón provista')

        UserBanRecord.objects.create(
            user=u,
            banned_by=request.user if request.user.is_authenticated else None,
            reason=reason,
        )
        u.is_active = False
        u.save()
        APIPoolService.release_keys_from_user(u)

        from api.models import BannedEmail, BannedIP
        BannedEmail.objects.get_or_create(email=u.email, defaults={'reason': reason})
        if u.last_login_ip:
            BannedIP.objects.get_or_create(ip_address=u.last_login_ip, defaults={'reason': reason})

        return Response({
            'status':    'banned_permanently',
            'email':     u.email,
            'ip_banned': bool(u.last_login_ip),
        })
    except Agent.DoesNotExist:
        return Response(status=404)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_users_unban(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        u = Agent.objects.get(pk=pk)
        UserBanRecord.objects.filter(user=u, is_active=True).update(is_active=False)
        u.is_active = True
        u.save()
        APIPoolService.assign_keys_to_user(u)
        return Response({'status': 'unbanned'})
    except Agent.DoesNotExist:
        return Response(status=404)


# ══════════════════════════════════════════════════════════════════════════════
# REQUESTS / LOGS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_requests_list(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    logs = (APIRequestLog.objects
            .select_related('user', 'servicio')
            .order_by('-creado_en')[:100])
    data = [{
        'id':       l.id,
        'user':     l.user.email if l.user else None,
        'service':  l.servicio.nombre if l.servicio else None,
        'endpoint': l.endpoint,
        'success':  l.success,
        'time_ms':  l.response_time_ms,
        'created_at': l.creado_en,
    } for l in logs]
    return Response(data)


# ══════════════════════════════════════════════════════════════════════════════
# ALERTAS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET', 'PATCH'])
@permission_classes([AllowAny])
def admin_alerts_list(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    if request.method == 'GET':
        alerts = AdminAlert.objects.order_by('-creado_en')[:50]
        data = list(alerts.values(
            'id', 'tipo', 'severidad', 'titulo', 'mensaje', 'creado_en', 'is_read'
        ))
        # Aliases para compatibilidad con frontend
        for a in data:
            a['type']       = a.get('tipo')
            a['severity']   = a.get('severidad')
            a['title']      = a.get('titulo')
            a['message']    = a.get('mensaje')
            a['created_at'] = a.get('creado_en')
            a['timestamp']  = a.get('creado_en')
        return Response(data)
    else:
        ids = request.data.get('ids', [])
        AdminAlert.objects.filter(id__in=ids).update(is_read=True)
        return Response({'status': 'updated'})


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_analytics_timeseries(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'data': 'Time series analytics — próximamente'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_analytics_top(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'data': 'Top analytics — próximamente'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_health_status(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    total   = APIKey.objects.count()
    healthy = APIKey.objects.filter(last_health_status=True).count()
    return Response({
        'healthy_percentage': (healthy / total * 100) if total > 0 else 0,
        'total_keys':         total,
        'healthy_keys':       healthy,
    })


# ══════════════════════════════════════════════════════════════════════════════
# ACCIONES UTILITARIAS
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_health_check_trigger(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    from api.tasks import health_check_all_keys
    try:
        health_check_all_keys.delay()
    except Exception:
        health_check_all_keys()
    return Response({'success': True, 'message': 'Health check disparado'})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_alert_read(request, alert_id):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        alert = AdminAlert.objects.get(id=alert_id)
        alert.is_read = True
        alert.save()
        return Response({'success': True})
    except AdminAlert.DoesNotExist:
        return Response({'error': 'Alerta no encontrada'}, status=404)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    qs   = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    data = [{
        'id':           l.id,
        'titulo':       l.titulo,
        'ciudad':       l.ciudad,
        'agente':       l.agente.email,
        'video_status': l.video_status,
        'creado_en':    l.creado_en.isoformat(),
    } for l in qs]
    return Response({'listados': data, 'total': Listado.objects.count()})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'assets': [], 'total': 0})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    from api.models import Pago
    pagos = Pago.objects.select_related('user').order_by('-creado_en')[:100]
    data = [{
        'id':            p.id,
        'user':          p.user.email if p.user else 'Usuario eliminado',
        'tipo':          p.tipo,
        'monto':         float(p.monto),
        'moneda':        p.moneda,
        'mp_status':     p.mp_status,
        'mp_payment_id': p.mp_payment_id,
        'creado_en':     p.creado_en.isoformat(),
    } for p in pagos]
    return Response({'pagos': data, 'total': Pago.objects.count()})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_eliminados(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    qs = Agent.objects.filter(eliminado_en__isnull=False).order_by('-eliminado_en')
    data = [{
        'id':          a.id,
        'email':       a.email,
        'nombre':      a.nombre,
        'eliminado_en':a.eliminado_en.isoformat(),
    } for a in qs]
    return Response({'usuarios': data})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_restaurar(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        a = Agent.objects.get(id=pk)
        a.eliminado_en = None
        a.is_active    = True
        a.save()
        return Response({'success': True})
    except Agent.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)


@api_view(['POST', 'DELETE'])
@permission_classes([AllowAny])
def admin_usuario_eliminar(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        a = Agent.objects.get(id=pk)
        a.soft_delete()
        APIPoolService.release_keys_from_user(a)
        return Response({'success': True})
    except Agent.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)


@api_view(['PUT'])
@permission_classes([AllowAny])
def admin_usuario_cambiar_plan(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        a = Agent.objects.get(id=pk)
        nuevo_plan = request.data.get('plan', a.plan_nombre)
        if nuevo_plan not in ['starter', 'pro', 'scale', 'business']:
            return Response({'error': 'Plan invalido'}, status=400)
        a.plan_nombre = nuevo_plan
        a.plan_activo = True
        a.plan_seleccionado = True
        a.free_trial_started_at = None
        a.free_trial_ends_at = None
        a.save(update_fields=[
            'plan_nombre', 'plan_activo', 'plan_seleccionado',
            'free_trial_started_at', 'free_trial_ends_at', 'updated_at',
        ])
        # Recalcular quotas automáticamente via signal en models.py
        return Response({'success': True, 'plan': a.plan_nombre})
    except Agent.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_enviar_email(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    try:
        from django.core.mail import send_mail
        from django.conf import settings as django_settings
        a       = Agent.objects.get(id=pk)
        asunto  = request.data.get('asunto', 'Mensaje de LeadBook')
        mensaje = request.data.get('mensaje', '')
        send_mail(asunto, mensaje, django_settings.DEFAULT_FROM_EMAIL, [a.email], fail_silently=True)
        return Response({'success': True})
    except Agent.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)


# ══════════════════════════════════════════════════════════════════════════════
# BUNDLES → reemplazados por UserAPIAssignment en v2
# Estos endpoints ya no gestionan bundles sino asignaciones directas
# ══════════════════════════════════════════════════════════════════════════════

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_list(request):
    """v2: devuelve stats del pool de asignaciones."""
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    stats = APIPoolService.get_bundle_stats()
    return Response(stats)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_crear(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'En v2.0 no hay bundles. Las asignaciones se hacen por servicio individual via /admin/users/<id>/add-extra/'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_stats(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response(APIPoolService.get_bundle_stats())


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_bundles_detail(request, bundle_id):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Bundles eliminados en v2.0'}, status=410)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_asignar(request, bundle_id):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Bundles eliminados en v2.0. Usar /admin/users/<id>/add-extra/'}, status=410)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_liberar(request, bundle_id):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Bundles eliminados en v2.0'}, status=410)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_auto_repair(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    user_ids = request.data.get('user_ids', [])
    if user_ids:
        users = Agent.objects.filter(id__in=user_ids, is_active=True)
    else:
        users = Agent.objects.filter(is_active=True, eliminado_en__isnull=True)

    fixed   = 0
    details = []
    for user in users:
        repaired = APIPoolService.repair_user_apis(user)
        if repaired:
            fixed += 1
            details.append({'email': user.email, 'repaired': repaired})

    return Response({'status': 'success', 'fixed_count': fixed, 'details': details})
