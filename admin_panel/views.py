# admin_panel/views.py — LeadBook v2.0 COMPLETO
# REEMPLAZA TODO el contenido actual del archivo
# Schema v2: servicio es FK, no string. No existe assigned_to en APIKey.

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from datetime import timedelta
from api.models import (
    Agent, APIKey, APIRequestLog, AdminAlert, UserBanRecord,
    Listado, Servicio, UserAPIAssignment, UserAPIQuota
)
from api.services.pool_service import APIPoolService
from decouple import config
from django.utils.crypto import constant_time_compare

ADMIN_KEY = config('ADMIN_KEY', default='')


def _service_defaults(nombre):
    descripcion = {
        'gemini': 'Google Gemini',
        'elevenlabs': 'ElevenLabs',
        'uploadpost': 'UploadPost',
        'groq': 'Groq',
        'nvidia': 'NVIDIA',
    }.get(nombre, nombre.title())
    return {
        'descripcion': descripcion,
        'activo': True,
        'default_daily_limit': 1500,
        'extra_increment': 10 if nombre == 'uploadpost' else 1500,
    }


def _get_or_create_service(nombre):
    normalized = str(nombre or '').strip().lower()
    if not normalized:
        return None
    servicio = Servicio.objects.filter(nombre__iexact=normalized).first()
    if servicio:
        return servicio
    servicio, _ = Servicio.objects.get_or_create(
        nombre=normalized,
        defaults=_service_defaults(normalized),
    )
    return servicio


def _check_admin(request):
    supplied_key = request.headers.get('X-Admin-Key', '')
    if ADMIN_KEY and supplied_key and constant_time_compare(supplied_key, ADMIN_KEY):
        return True
    return request.user and request.user.is_authenticated and request.user.is_staff


def _get_cfg(clave, default=None):
    from api.models import ConfiguracionSistema
    cfg, _ = ConfiguracionSistema.objects.get_or_create(
        clave=clave, defaults={'datos': default or []}
    )
    return cfg


# ── STATS ─────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats_v2(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)
    total_users = Agent.objects.filter(eliminado_en__isnull=True).count()
    free_users  = Agent.objects.filter(plan_nombre='free', eliminado_en__isnull=True).count()
    paid_users  = total_users - free_users
    active_apis = APIKey.objects.filter(status='available').count()
    pending_alerts = AdminAlert.objects.filter(is_read=False).count()
    requests_today = requests_month = 0
    try:
        requests_today = APIRequestLog.objects.filter(creado_en__date=hoy).count()
        requests_month = APIRequestLog.objects.filter(creado_en__date__gte=inicio_mes).count()
    except Exception:
        pass
    history = []
    for i in range(6, -1, -1):
        day = hoy - timedelta(days=i)
        try: cnt = APIRequestLog.objects.filter(creado_en__date=day).count()
        except Exception: cnt = 0
        history.append({'date': day.strftime('%d/%m'), 'count': cnt})
    plan_dist = {}
    for row in Agent.objects.filter(eliminado_en__isnull=True).values('plan_nombre').annotate(total=Count('id')):
        plan_dist[row['plan_nombre'] or 'free'] = row['total']
    return Response({
        'stats': {'totalUsers': total_users, 'freeUsers': free_users, 'paidUsers': paid_users,
                  'activeApis': active_apis, 'pendingAlerts': pending_alerts,
                  'requestsToday': requests_today, 'requestsMonth': requests_month},
        'charts': {'requests_history': history, 'service_usage': []},
        'top_users': [],
        'total_users': total_users, 'free_users': free_users, 'paid_users': paid_users,
        'requests_today': requests_today, 'requests_month': requests_month,
        'usuarios_por_plan': plan_dist,
    })


# ── API KEYS POOL ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_api_keys_list(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    service       = request.query_params.get('service') or request.query_params.get('servicio')
    status_filter = request.query_params.get('status')
    keys = APIKey.objects.select_related('servicio').order_by('-creado_en')
    if service:
        keys = keys.filter(servicio__nombre__iexact=service)
    if status_filter:
        keys = keys.filter(status=status_filter)
    data = []
    for k in keys:
        asig = UserAPIAssignment.objects.filter(
            apikey=k, activo=True
        ).select_related('user', 'servicio', 'pago').first()
        quota = None
        comprada_en = None
        if asig:
            quota = UserAPIQuota.objects.filter(user=asig.user, servicio=asig.servicio).first()
            if asig.pago:
                comprada_en = asig.pago.procesado_en or asig.pago.creado_en
            comprada_en = comprada_en or asig.assigned_at
        data.append({
            'id': k.id, 'servicio': k.servicio.nombre, 'service': k.servicio.nombre,
            'status': k.status, 'api_key': k.api_key,
            'key_masked': k.api_key[:10] + '...' if k.api_key else '',
            'label': k.label,
            'is_primary': asig.is_primary if asig else True,
            'usuario_id': asig.user.id if asig else None,
            'usuario_actual': asig.user.nombre if asig else None,
            'assigned_to': asig.user.email if asig else None,
            'assigned_to_email': asig.user.email if asig else None,
            'assigned_to_id': asig.user.id if asig else None,
            'assigned_to_nombre': asig.user.nombre if asig else None,
            'daily_limit': k.google_daily_limit,
            'requests_today': k.requests_today,
            'quota_requests_today': quota.requests_today if quota else 0,
            'user_daily_limit': quota.user_daily_limit if quota else None,
            'is_blocked': quota.is_blocked if quota else False,
            'assigned_at': asig.assigned_at.isoformat() if asig and asig.assigned_at else None,
            'comprada_en': comprada_en.isoformat() if comprada_en else None,
            'pago_id': asig.pago.id if asig and asig.pago else None,
            'mp_payment_id': asig.pago.mp_payment_id if asig and asig.pago else None,
            'last_health_status': k.last_health_status,
            'error_count': k.error_count,
            'creado_en': k.creado_en.isoformat() if k.creado_en else None,
        })
    return Response(data)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_create(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    servicio_nombre = (request.data.get('service') or request.data.get('servicio') or '').strip().lower()
    api_key_str = str(request.data.get('api_key') or '').strip()
    limit = request.data.get('daily_limit', 1500)
    label_str = request.data.get('label', '')
    if not servicio_nombre or not api_key_str:
        return Response({'error': 'service y api_key son requeridos'}, status=400)
    servicio = _get_or_create_service(servicio_nombre)
    if not servicio:
        disponibles = list(Servicio.objects.values_list('nombre', flat=True))
        return Response({'error': f'Servicio "{servicio_nombre}" no existe. Disponibles: {disponibles}'}, status=400)
    key = APIKey.objects.create(servicio=servicio, api_key=api_key_str,
                                google_daily_limit=limit, label=label_str, status='available')
    return Response({'id': key.id, 'status': 'created', 'servicio': servicio.nombre}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_bulk_create(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    keys_data = request.data.get('keys', [])
    if not isinstance(keys_data, list) or not keys_data:
        return Response({'error': 'No se enviaron keys'}, status=400)

    def normalize_key(value):
        return str(value or '').replace('\ufeff', '').replace('\u200b', '').strip().strip('"\'')

    candidates = []
    errores = []
    seen_in_request = set()
    duplicates_in_request = 0
    service_cache = {}

    for index, data in enumerate(keys_data, start=1):
        if not isinstance(data, dict):
            errores.append({'line': index, 'error': 'Formato inválido'})
            continue

        servicio_nombre = str(data.get('service') or data.get('servicio') or '').strip().lower()
        api_key_str = normalize_key(data.get('api_key') or data.get('key'))
        label_str = str(data.get('label') or '').strip()

        try:
            limit = int(data.get('daily_limit') or 1500)
        except (TypeError, ValueError):
            limit = 1500

        if not servicio_nombre or not api_key_str:
            errores.append({'line': index, 'error': 'Faltan service o api_key'})
            continue

        servicio = service_cache.get(servicio_nombre)
        if servicio is None:
            servicio = _get_or_create_service(servicio_nombre)
            service_cache[servicio_nombre] = servicio

        if not servicio:
            errores.append({'line': index, 'error': f'Servicio "{servicio_nombre}" no existe'})
            continue

        pair = (servicio.id, api_key_str)
        if pair in seen_in_request:
            duplicates_in_request += 1
            continue

        seen_in_request.add(pair)
        candidates.append({
            'servicio': servicio,
            'api_key': api_key_str,
            'daily_limit': limit,
            'label': label_str,
        })

    existing_pairs = set()
    keys_by_service = {}
    for servicio_id, api_key_str in seen_in_request:
        keys_by_service.setdefault(servicio_id, set()).add(api_key_str)

    for servicio_id, api_keys in keys_by_service.items():
        existing_pairs.update(
            (servicio_id, key)
            for key in APIKey.objects.filter(servicio_id=servicio_id, api_key__in=api_keys).values_list('api_key', flat=True)
        )

    new_keys = [
        APIKey(
            servicio=item['servicio'],
            api_key=item['api_key'],
            google_daily_limit=item['daily_limit'],
            label=item['label'],
            status='available',
        )
        for item in candidates
        if (item['servicio'].id, item['api_key']) not in existing_pairs
    ]

    counts = {}
    duplicates_deleted = 0
    duplicates_protected = 0

    with transaction.atomic():
        if new_keys:
            APIKey.objects.bulk_create(new_keys)
            for k in new_keys:
                nombre = k.servicio.nombre
                counts[nombre] = counts.get(nombre, 0) + 1

        # Limpieza segura: solo elimina duplicados sin asignaciones ni logs históricos.
        for servicio_id, api_key_str in seen_in_request:
            duplicates = list(
                APIKey.objects.filter(servicio_id=servicio_id, api_key=api_key_str)
                .order_by('creado_en', 'id')
            )
            if len(duplicates) <= 1:
                continue

            duplicate_ids = [key.id for key in duplicates]
            linked_ids = set(UserAPIAssignment.objects.filter(apikey_id__in=duplicate_ids).values_list('apikey_id', flat=True))
            linked_ids.update(APIRequestLog.objects.filter(api_key_id__in=duplicate_ids).values_list('api_key_id', flat=True))
            keep = next((key for key in duplicates if key.id in linked_ids), duplicates[0])
            delete_ids = [key.id for key in duplicates if key.id != keep.id and key.id not in linked_ids]
            duplicates_protected += sum(1 for key in duplicates if key.id != keep.id and key.id in linked_ids)

            if delete_ids:
                APIKey.objects.filter(id__in=delete_ids).delete()
                duplicates_deleted += len(delete_ids)

    duplicates_existing = len(existing_pairs)
    ignored = duplicates_in_request + duplicates_existing + len(errores)

    return Response({
        'status': 'created',
        'received': len(keys_data),
        'valid_unique': len(candidates),
        'count': len(new_keys),
        'created': len(new_keys),
        'counts_by_service': counts,
        'ignored': ignored,
        'duplicates_in_request': duplicates_in_request,
        'duplicates_existing': duplicates_existing,
        'duplicates_deleted': duplicates_deleted,
        'duplicates_protected': duplicates_protected,
        'errores': errores,
    }, status=201)


@api_view(['PATCH', 'DELETE', 'POST'])
@permission_classes([AllowAny])
def admin_api_keys_detail(request, pk):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)
    try: key = APIKey.objects.select_related('servicio').get(pk=pk)
    except APIKey.DoesNotExist: return Response(status=404)

    def reset_related_quotas():
        assignments = UserAPIAssignment.objects.filter(
            apikey=key, activo=True
        ).select_related('user', 'servicio')
        for asig in assignments:
            quota = UserAPIQuota.objects.filter(user=asig.user, servicio=asig.servicio).first()
            if quota:
                quota.requests_today = 0
                quota.is_blocked = False
                quota.blocked_reason = None
                quota.save(update_fields=['requests_today', 'is_blocked', 'blocked_reason', 'updated_at'])

    if request.method == 'POST':
        path = request.path
        if path.endswith('/liberar/'):
            UserAPIAssignment.objects.filter(apikey=key, activo=True).update(activo=False)
            key.status = 'available'; key.save(update_fields=['status', 'updated_at'])
            return Response({'status': 'released'})
        elif path.endswith('/reactivar/'):
            key.requests_today = 0; key.requests_this_month = 0; key.error_count = 0
            key.status = 'assigned' if UserAPIAssignment.objects.filter(apikey=key, activo=True).exists() else 'available'
            key.save(update_fields=['status', 'requests_today', 'requests_this_month', 'error_count', 'updated_at'])
            reset_related_quotas()
            return Response({'status': 'reactivated'})
        elif path.endswith('/reset/'):
            key.requests_today = 0; key.requests_this_month = 0; key.error_count = 0
            if key.status == 'exhausted':
                key.status = 'assigned' if UserAPIAssignment.objects.filter(apikey=key, activo=True).exists() else 'available'
            key.save()
            reset_related_quotas()
            return Response({'status': 'reset'})
        return Response({'error': 'Accion desconocida'}, status=400)
    if request.method == 'DELETE':
        UserAPIAssignment.objects.filter(apikey=key).update(activo=False)
        key.delete(); return Response(status=204)
    if 'status'      in request.data: key.status             = request.data['status']
    if 'daily_limit' in request.data: key.google_daily_limit = request.data['daily_limit']
    if 'notes'       in request.data: key.notes              = request.data['notes']
    if 'label'       in request.data: key.label              = request.data['label']
    key.save(); return Response({'id': key.id, 'status': key.status})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_test(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: key = APIKey.objects.select_related('servicio').get(pk=pk)
    except APIKey.DoesNotExist: return Response(status=404)
    import requests as req
    is_healthy = False; error = None
    svc = key.servicio.nombre
    try:
        if svc == 'gemini':
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={key.api_key}"
            res = req.post(url, json={'contents': [{'parts': [{'text': 'hello'}]}]}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
        elif svc == 'elevenlabs':
            res = req.get('https://api.elevenlabs.io/v1/voices', headers={'xi-api-key': key.api_key}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
        elif svc == 'uploadpost':
            res = req.get('https://api.upload-post.com/api/uploadposts/users', headers={'Authorization': f'Apikey {key.api_key}'}, timeout=5)
            is_healthy = res.status_code == 200
            if not is_healthy: error = res.text
    except Exception as e: error = str(e)
    key.last_health_status = is_healthy; key.last_health_check = timezone.now()
    if not is_healthy: key.error_count += 1
    key.save(update_fields=['last_health_status', 'last_health_check', 'error_count', 'updated_at'])
    return Response({'healthy': is_healthy, 'error': error})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_api_keys_reassign(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: key = APIKey.objects.select_related('servicio').get(pk=pk)
    except APIKey.DoesNotExist: return Response(status=404)
    asig = UserAPIAssignment.objects.filter(apikey=key, activo=True).select_related('user').first()
    if not asig: return Response({'error': 'Key no asignada'}, status=400)
    repaired = APIPoolService.repair_user_apis(asig.user)
    return Response({'repaired_services': repaired})


@api_view(['PUT'])
@permission_classes([AllowAny])
def admin_pool_key_actualizar(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: key = APIKey.objects.get(pk=pk)
    except APIKey.DoesNotExist: return Response(status=404)
    if 'status'      in request.data: key.status             = request.data['status']
    if 'daily_limit' in request.data: key.google_daily_limit = request.data['daily_limit']
    if 'label'       in request.data: key.label              = request.data['label']
    if 'notes'       in request.data: key.notes              = request.data['notes']
    key.save(); return Response({'ok': True, 'id': key.id})


@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_pool_key_eliminar(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: key = APIKey.objects.get(pk=pk)
    except APIKey.DoesNotExist: return Response(status=404)
    UserAPIAssignment.objects.filter(apikey=key).update(activo=False)
    key.delete(); return Response({'ok': True})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_pool_key_toggle(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: key = APIKey.objects.get(pk=pk)
    except APIKey.DoesNotExist: return Response(status=404)
    key.status = 'available' if key.status == 'disabled' else 'disabled'
    key.save(update_fields=['status', 'updated_at']); return Response({'ok': True, 'status': key.status})


# ── GLOBAL KEYS ───────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_global_keys_list(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response(_get_cfg('global_keys').datos or [])


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_global_keys_upsert(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    servicio = request.data.get('servicio', '').lower()
    api_key  = request.data.get('api_key', '')
    label    = request.data.get('label', '')
    if not servicio or not api_key: return Response({'error': 'servicio y api_key requeridos'}, status=400)
    cfg = _get_cfg('global_keys'); keys = cfg.datos or []; found = False
    for k in keys:
        if k.get('servicio') == servicio:
            k.update({'api_key': api_key, 'label': label, 'activo': True}); found = True; break
    if not found:
        import time
        keys.append({'id': int(time.time()), 'servicio': servicio, 'api_key': api_key, 'label': label, 'activo': True})
    cfg.datos = keys; cfg.save(); return Response({'ok': True})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_global_key_toggle(request, key_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    cfg = _get_cfg('global_keys')
    for k in (cfg.datos or []):
        if k.get('id') == key_id:
            k['activo'] = not k.get('activo', True); cfg.save()
            return Response({'ok': True, 'activo': k['activo']})
    return Response({'error': 'No encontrado'}, status=404)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_global_key_eliminar(request, key_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    cfg = _get_cfg('global_keys'); keys = cfg.datos or []
    nuevas = [k for k in keys if k.get('id') != key_id]
    if len(nuevas) == len(keys): return Response({'error': 'No encontrado'}, status=404)
    cfg.datos = nuevas; cfg.save(); return Response({'ok': True})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_global_key_reset(request, key_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    cfg = _get_cfg('global_keys')
    for k in (cfg.datos or []):
        if k.get('id') == key_id:
            k.update({'requests_today': 0, 'requests_this_month': 0}); cfg.save()
            return Response({'ok': True})
    return Response({'error': 'No encontrado'}, status=404)


# ── USUARIOS ──────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_users_list(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    users = Agent.objects.filter(eliminado_en__isnull=True).order_by('-fecha_registro')[:100]
    return Response([{'id': u.id, 'email': u.email, 'nombre': u.nombre, 'logo_url': u.logo_url,
                      'plan': u.plan_nombre, 'is_active': u.is_active, 'is_suspended': not u.is_active} for u in users])


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_users_detail(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response(status=404)
    assignments = UserAPIAssignment.objects.filter(user=u, activo=True).select_related('apikey', 'servicio')
    keys = [{'id': a.apikey.id, 'servicio': a.servicio.nombre, 'status': a.apikey.status,
             'api_key': a.apikey.api_key[:8] + '...' if a.apikey.api_key else '—',
             'requests_today': a.apikey.requests_today, 'daily_limit': a.apikey.google_daily_limit,
             'is_primary': a.is_primary} for a in assignments]
    quotas = [{'servicio': q.servicio.nombre, 'requests_today': q.requests_today,
               'user_daily_limit': q.user_daily_limit, 'is_blocked': q.is_blocked}
              for q in UserAPIQuota.objects.filter(user=u).select_related('servicio')]
    logs = list(APIRequestLog.objects.filter(user=u).select_related('servicio')
                .order_by('-creado_en').values('servicio__nombre', 'endpoint', 'success', 'creado_en')[:20])
    for l in logs: l['service'] = l.pop('servicio__nombre', ''); l['created_at'] = l.pop('creado_en', None)
    is_online = bool(u.last_login and (timezone.now() - u.last_login).total_seconds() < 300)
    return Response({'id': u.id, 'email': u.email, 'nombre': u.nombre, 'logo_url': u.logo_url,
                     'telefono': u.telefono, 'agencia': u.agencia, 'nombre_inmobiliaria': u.nombre_inmobiliaria,
                     'nicho': u.nicho, 'pais': u.pais, 'plan': u.plan_nombre,
                     'fecha_registro': u.fecha_registro, 'last_login': u.last_login,
                     'is_online': is_online, 'is_active': u.is_active,
                     'keys': keys, 'quotas': quotas, 'recent_logs': logs})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_user_info_general(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response(status=404)
    is_online = bool(u.last_login and (timezone.now() - u.last_login).total_seconds() < 300)
    return Response({'nombre': u.nombre, 'nombre_negocio': u.nombre_inmobiliaria, 'telefono': u.telefono,
                     'email': u.email, 'is_online': is_online, 'ultima_conexion': u.last_login,
                     'fecha_registro': u.fecha_registro, 'agencia': u.agencia, 'nicho': u.nicho, 'pais': u.pais})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_user_api_pool(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response(status=404)
    assignments = UserAPIAssignment.objects.filter(user=u, activo=True).select_related('apikey', 'servicio')
    quotas = {q.servicio.nombre: q for q in UserAPIQuota.objects.filter(user=u).select_related('servicio')}
    data = []
    for a in assignments:
        svc = a.servicio.nombre; q = quotas.get(svc)
        data.append({'id': a.apikey.id, 'servicio': svc, 'status': a.apikey.status,
                     'is_primary': a.is_primary,
                     'requests_today': q.requests_today if q else 0,
                     'daily_limit': q.user_daily_limit if q else a.apikey.google_daily_limit,
                     'is_blocked': q.is_blocked if q else False, 'last_used': a.apikey.last_used_at})
    return Response(data)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_users_hard_delete(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response(status=404)
    APIPoolService.release_keys_from_user(u)
    AdminAlert.objects.create(tipo='assign_failed', severidad='info',
                               titulo='Usuario eliminado', mensaje=f'{u.email} eliminado. Keys liberadas.', related_user=u)
    u.delete(); return Response({'status': 'deleted_permanently'})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_users_ban(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response(status=404)
    reason = request.data.get('reason', 'Sin razon')
    UserBanRecord.objects.create(user=u, banned_by=request.user if request.user.is_authenticated else None, reason=reason)
    u.is_active = False; u.save()
    APIPoolService.release_keys_from_user(u)
    from api.models import BannedEmail, BannedIP
    BannedEmail.objects.get_or_create(email=u.email, defaults={'reason': reason})
    if u.last_login_ip: BannedIP.objects.get_or_create(ip_address=u.last_login_ip, defaults={'reason': reason})
    return Response({'status': 'banned_permanently', 'email': u.email, 'ip_banned': bool(u.last_login_ip)})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_users_unban(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: u = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response(status=404)
    UserBanRecord.objects.filter(user=u, is_active=True).update(is_active=False)
    u.is_active = True; u.save()
    APIPoolService.assign_keys_to_user(u)
    return Response({'status': 'unbanned'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_eliminados(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    qs = Agent.objects.filter(eliminado_en__isnull=False).order_by('-eliminado_en')
    return Response([{'id': a.id, 'email': a.email, 'nombre': a.nombre,
                      'eliminado_en': a.eliminado_en.isoformat()} for a in qs])


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_restaurar(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: a = Agent.objects.get(id=pk)
    except Agent.DoesNotExist: return Response({'error': 'No encontrado'}, status=404)
    a.eliminado_en = None; a.is_active = True; a.save()
    return Response({'success': True})


@api_view(['POST', 'DELETE'])
@permission_classes([AllowAny])
def admin_usuario_eliminar(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: a = Agent.objects.get(id=pk)
    except Agent.DoesNotExist: return Response({'error': 'No encontrado'}, status=404)
    a.soft_delete(); APIPoolService.release_keys_from_user(a)
    return Response({'success': True})


@api_view(['PUT', 'POST'])
@permission_classes([AllowAny])
def admin_usuario_cambiar_plan(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try: a = Agent.objects.get(id=pk)
    except Agent.DoesNotExist: return Response({'error': 'No encontrado'}, status=404)
    a.plan_nombre = request.data.get('plan', a.plan_nombre); a.plan_activo = True; a.save()
    return Response({'success': True, 'plan': a.plan_nombre})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_enviar_email(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try:
        from django.core.mail import send_mail
        from django.conf import settings as dj_settings
        a = Agent.objects.get(id=pk)
        send_mail(request.data.get('asunto', 'Mensaje de LeadBook'),
                  request.data.get('mensaje', ''), dj_settings.DEFAULT_FROM_EMAIL, [a.email], fail_silently=True)
        return Response({'success': True})
    except Agent.DoesNotExist: return Response({'error': 'No encontrado'}, status=404)


# ── LOGS / ALERTAS ────────────────────────────────────────────────────────────

@api_view(['GET', 'PATCH'])
@permission_classes([AllowAny])
def admin_alerts_list(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    if request.method == 'GET':
        alerts = AdminAlert.objects.order_by('-creado_en')[:50]
        data = list(alerts.values('id', 'tipo', 'severidad', 'titulo', 'mensaje', 'creado_en', 'is_read'))
        for a in data:
            a['type'] = a.get('tipo'); a['severity'] = a.get('severidad')
            a['title'] = a.get('titulo'); a['message'] = a.get('mensaje'); a['created_at'] = a.get('creado_en'); a['timestamp'] = a.get('creado_en')
        return Response(data)
    AdminAlert.objects.filter(id__in=request.data.get('ids', [])).update(is_read=True)
    return Response({'status': 'updated'})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_alert_read(request, alert_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    try:
        alert = AdminAlert.objects.get(id=alert_id); alert.is_read = True; alert.save()
        return Response({'success': True})
    except AdminAlert.DoesNotExist: return Response({'error': 'No encontrada'}, status=404)


# ── CONTENIDO ─────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    qs = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    return Response({'listados': [{'id': l.id, 'titulo': l.titulo, 'ciudad': l.ciudad,
                                   'agente': l.agente.email, 'video_status': l.video_status,
                                   'creado_en': l.creado_en.isoformat()} for l in qs],
                     'total': Listado.objects.count()})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'assets': [], 'total': 0})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    from api.models import Pago
    pagos = Pago.objects.select_related('user').order_by('-creado_en')[:100]
    return Response({'pagos': [{'id': p.id, 'user': p.user.email if p.user else 'Eliminado',
                                'tipo': p.tipo, 'monto': float(p.monto), 'moneda': p.moneda,
                                'mp_status': p.mp_status, 'creado_en': p.creado_en.isoformat()} for p in pagos],
                     'total': Pago.objects.count()})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_analytics_timeseries(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'data': 'proximamente'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_analytics_top(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'data': 'proximamente'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_health_status(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    total = APIKey.objects.count(); healthy = APIKey.objects.filter(last_health_status=True).count()
    return Response({'healthy_percentage': (healthy / total * 100) if total else 0,
                     'total_keys': total, 'healthy_keys': healthy})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_health_check_trigger(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    from api.tasks import health_check_all_keys
    try: health_check_all_keys.delay()
    except Exception: health_check_all_keys()
    return Response({'success': True})


# ── BUNDLES (deprecated stubs) ────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_list(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response(APIPoolService.get_bundle_stats())

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_crear(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Deprecated en v2.0'})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_stats(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response(APIPoolService.get_bundle_stats())

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_bundles_detail(request, bundle_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Deprecated'}, status=410)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_asignar(request, bundle_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Deprecated'}, status=410)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_liberar(request, bundle_id):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    return Response({'info': 'Deprecated'}, status=410)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_auto_repair(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    user_ids = request.data.get('user_ids', [])
    users = Agent.objects.filter(id__in=user_ids, is_active=True) if user_ids \
            else Agent.objects.filter(is_active=True, eliminado_en__isnull=True)
    fixed = 0; details = []
    for user in users:
        repaired = APIPoolService.repair_user_apis(user)
        if repaired: fixed += 1; details.append({'email': user.email, 'repaired': repaired})
    return Response({'status': 'success', 'fixed_count': fixed, 'details': details})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_requests_list(request):
    if not _check_admin(request):
        return Response({'error': 'Forbidden'}, status=403)

    limit = int(request.GET.get('limit', 200))
    servicio = request.GET.get('servicio', '')
    success_filter = request.GET.get('exitoso', '')

    qs = APIRequestLog.objects.select_related('user', 'servicio').order_by('-creado_en')

    if servicio:
        qs = qs.filter(servicio__nombre__iexact=servicio)
    if success_filter == 'true':
        qs = qs.filter(success=True)
    elif success_filter == 'false':
        qs = qs.filter(success=False)

    logs = []
    for log in qs[:limit]:
        logs.append({
            'id': log.id,
            'timestamp': log.creado_en.isoformat(),
            'user_email': log.user.email if log.user else None,
            'servicio': log.servicio.nombre if log.servicio else None,
            'action': log.endpoint or '',
            'success': log.success,
            'response_time': log.response_time_ms,
            'request_body': None,
            'error_message': log.error_message if not log.success else None,
        })

    return Response({'logs': logs, 'total': len(logs)})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_add_extra_api(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    from api.models import Agent
    try: user = Agent.objects.get(pk=pk)
    except Agent.DoesNotExist: return Response({'error': 'Usuario no encontrado'}, status=404)
    servicio_nombre = request.data.get('servicio', 'gemini').lower()
    added = APIPoolService.add_extra_key(user, servicio_nombre)
    if added:
        return Response({'ok': True, 'mensaje': f'API extra de {servicio_nombre} asignada'})
    return Response({'error': 'No hay keys disponibles en el pool'}, status=400)
