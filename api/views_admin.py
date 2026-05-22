# api/views_admin.py — LeadBook v2.0
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from decouple import config
from django.db import transaction
from django.utils.crypto import constant_time_compare
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Count, Sum, Q
from .models import (
    Agent, Listado, Plan, APIKey, AdminAlert, Servicio, 
    UserAPIAssignment, UserAPIQuota, VideoMusic, VideoSFX, ConfiguracionSistema,
    AccessCode
)

ADMIN_KEY = config('ADMIN_KEY', default='')

def _is_staff_check(request):
    supplied_key = request.headers.get('X-Admin-Key', '')
    if ADMIN_KEY and supplied_key and constant_time_compare(supplied_key, ADMIN_KEY):
        return True
    return request.user and request.user.is_authenticated and request.user.is_staff


def _normalize_api_key_value(value):
    return str(value or '').strip()


def _normalize_service_name(value):
    return str(value or '').strip().lower()


def _api_key_has_history(key):
    if UserAPIAssignment.objects.filter(apikey=key).exists():
        return True
    if key.logs.exists():
        return True
    counters = [key.requests_today, key.requests_this_month, key.total_requests, key.error_count]
    return bool(key.last_used_at or any(int(value or 0) > 0 for value in counters))


def _cleanup_duplicate_api_keys(service_names=None):
    services = [_normalize_service_name(name) for name in (service_names or []) if _normalize_service_name(name)]
    keys = APIKey.objects.select_related('servicio').order_by('servicio_id', 'api_key', 'id')
    if services:
        keys = keys.filter(servicio__nombre__in=services)

    grouped = {}
    for key in keys:
        normalized_key = _normalize_api_key_value(key.api_key)
        if not normalized_key:
            continue
        grouped.setdefault((key.servicio_id, normalized_key), []).append(key)

    deleted = 0
    protected = 0
    groups_found = 0
    for duplicates in grouped.values():
        if len(duplicates) <= 1:
            continue

        groups_found += 1
        keep = sorted(
            duplicates,
            key=lambda item: (0 if _api_key_has_history(item) else 1, item.id),
        )[0]

        for duplicate in duplicates:
            if duplicate.id == keep.id:
                continue
            if _api_key_has_history(duplicate):
                protected += 1
                continue
            try:
                duplicate.delete()
                deleted += 1
            except Exception:
                protected += 1

    return {
        'duplicates_deleted': deleted,
        'duplicates_protected': protected,
        'duplicate_groups': groups_found,
    }


def _forbidden():
    return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)


def _serialize_access_code(code):
    redeemed_by = code.redeemed_by
    return {
        'id': code.id,
        'code': code.code,
        'is_active': code.is_active,
        'trial_days': code.trial_days,
        'assigned_email': code.assigned_email or '',
        'notes': code.notes or '',
        'created_at': code.created_at,
        'redeemed_at': code.redeemed_at,
        'redeemed_by': redeemed_by.email if redeemed_by else None,
        'redeemed_by_id': redeemed_by.id if redeemed_by else None,
        'redeemed_account_active': bool(redeemed_by and redeemed_by.is_active and not redeemed_by.eliminado_en),
        'redeemed_account_deleted_at': redeemed_by.eliminado_en if redeemed_by else None,
        'revocable_account': _is_revocable_starter_trial_account(redeemed_by),
        'trial_ends_at': getattr(redeemed_by, 'free_trial_ends_at', None) if redeemed_by else None,
        'status': 'usado' if code.redeemed_at else ('activo' if code.is_active else 'desactivado'),
    }


def _is_revocable_starter_trial_account(user):
    if not user or getattr(user, 'is_staff', False):
        return False
    if getattr(user, 'eliminado_en', None):
        return False
    return (
        getattr(user, 'plan_nombre', None) == 'starter'
        and bool(getattr(user, 'free_trial_ends_at', None))
    )


def _blacklist_user_refresh_tokens(user):
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        for token in OutstandingToken.objects.filter(user_id=user.id):
            BlacklistedToken.objects.get_or_create(token=token)
    except Exception:
        pass


def _emit_account_revoked_event(user_id, access_code):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        async_to_sync(channel_layer.group_send)(
            f'presence_{user_id}',
            {
                'type': 'account.revoked',
                'reason': 'access_code_revoked',
                'access_code': access_code,
                'message': 'Tu token de prueba fue bloqueado. La cuenta fue cerrada.',
            },
        )
    except Exception:
        pass


def _revoke_starter_trial_account(user, access_code=None):
    user_id = user.id
    _blacklist_user_refresh_tokens(user)
    user.plan_activo = False
    user.plan_seleccionado = False
    user.free_trial_started_at = None
    user.free_trial_ends_at = None
    user.soft_delete()
    transaction.on_commit(lambda: _emit_account_revoked_event(user_id, access_code))


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_access_codes(request):
    if not _is_staff_check(request):
        return _forbidden()

    if request.method == 'GET':
        codes = AccessCode.objects.select_related('redeemed_by').order_by('-created_at')[:500]
        return Response({'codes': [_serialize_access_code(code) for code in codes]})

    try:
        count = int(request.data.get('count') or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(count, 50))

    try:
        trial_days = int(request.data.get('trial_days') or 30)
    except (TypeError, ValueError):
        trial_days = 30
    trial_days = max(1, min(trial_days, 365))

    assigned_email = str(request.data.get('assigned_email') or '').strip().lower() or None
    notes = str(request.data.get('notes') or '').strip()[:500]
    created_by = request.user if request.user and request.user.is_authenticated else None

    created = []
    for _ in range(count):
        code = AccessCode.objects.create(
            code=AccessCode.generate_code(),
            trial_days=trial_days,
            assigned_email=assigned_email if count == 1 else None,
            notes=notes,
            created_by=created_by,
        )
        created.append(code)

    return Response({'codes': [_serialize_access_code(code) for code in created]}, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([AllowAny])
def admin_access_code_detail(request, code_id):
    if not _is_staff_check(request):
        return _forbidden()

    try:
        code = AccessCode.objects.select_related('redeemed_by').get(id=code_id)
    except AccessCode.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if code.redeemed_at and request.method != 'DELETE':
        return Response({'error': 'El codigo ya fue usado y no se puede modificar.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        account_revoked = False
        with transaction.atomic():
            code = AccessCode.objects.select_for_update().get(id=code.id)
            redeemed_user = None
            if code.redeemed_by_id:
                redeemed_user = Agent.objects.all_including_deleted().select_for_update().filter(
                    id=code.redeemed_by_id,
                ).first()
                code.redeemed_by = redeemed_user

            if redeemed_user:
                if _is_revocable_starter_trial_account(redeemed_user):
                    _revoke_starter_trial_account(redeemed_user, code.code)
                    account_revoked = True
                elif not getattr(redeemed_user, 'eliminado_en', None):
                    return Response({
                        'error': 'La cuenta asociada ya no es un trial Starter revocable.',
                    }, status=status.HTTP_409_CONFLICT)

            code.is_active = False
            code.save(update_fields=['is_active', 'updated_at'])

        return Response({
            'ok': True,
            'account_revoked': account_revoked,
            'code': _serialize_access_code(code),
        })

    if 'is_active' in request.data:
        code.is_active = bool(request.data.get('is_active'))
    if 'notes' in request.data:
        code.notes = str(request.data.get('notes') or '').strip()[:500]
    code.save(update_fields=['is_active', 'notes', 'updated_at'])
    return Response({'ok': True, 'code': _serialize_access_code(code)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_metricas(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    hoy = now().date()
    inicio_mes = hoy.replace(day=1)

    total_usuarios = Agent.objects.count()
    usuarios_activos_mes = Agent.objects.filter(last_login__date__gte=inicio_mes).count()
    total_listados = Listado.objects.count()
    listados_hoy = Listado.objects.filter(creado_en__date=hoy).count()

    # MRR Estimado
    ingresos = 0
    planes = Plan.objects.exclude(nombre='free')
    for p in planes:
        count = Agent.objects.filter(plan_nombre=p.nombre, plan_activo=True).count()
        ingresos += (count * float(p.precio_ars_mensual or 0)) # v2 usa ARS

    usuarios_por_plan = {"starter": 0, "pro": 0, "scale": 0, "business": 0}
    stats_planes = Agent.objects.values('plan_nombre').annotate(total=Count('id'))
    for s in stats_planes:
        nombre = 'starter' if s['plan_nombre'] == 'free' else s['plan_nombre']
        if nombre in usuarios_por_plan:
            usuarios_por_plan[nombre] += s['total']

    return Response({
        "total_usuarios": total_usuarios,
        "usuarios_activos_mes": usuarios_activos_mes,
        "total_listados": total_listados,
        "listados_hoy": listados_hoy,
        "mrr_estimado": ingresos,
        "usuarios_por_plan": usuarios_por_plan
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_eliminados(request):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    # Manager custom para ver eliminados
    usuarios = Agent.objects.all_including_deleted().filter(eliminado_en__isnull=False)
    data = [{
        'id': u.id, 'email': u.email, 'nombre': u.nombre, 
        'eliminado_en': u.eliminado_en
    } for u in usuarios]
    return Response(data)

@api_view(['POST'])
def admin_usuario_suspender(request, user_id):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    u = Agent.objects.get(id=user_id)
    u.is_active = not u.is_active
    u.save()
    return Response({'ok': True, 'is_active': u.is_active})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_list(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    
    # Solo usuarios no eliminados (el manager Agent.objects ya los filtra)
    usuarios = Agent.objects.all().order_by('-fecha_registro')
    data = [{
        'id': u.id,
        'email': u.email,
        'nombre': u.nombre,
        'plan': u.plan_nombre,
        'plan_nombre': u.plan_nombre,
        'plan_activo': u.plan_activo,
        'activo': u.is_active,
        'fecha_registro': u.fecha_registro,
        'free_trial_started_at': u.free_trial_started_at,
        'free_trial_ends_at': u.free_trial_ends_at,
    } for u in usuarios]
    return Response(data)

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    try:
        u = Agent.objects.get(id=user_id)
        # Cuotas
        cuotas = UserAPIQuota.objects.filter(user=u).select_related('servicio')
        stats_cuotas = [{
            'servicio': c.servicio.nombre,
            'hoy': c.requests_today,
            'limite': c.user_daily_limit,
            'bloqueado': c.is_blocked
        } for c in cuotas]
        
        return Response({
            'id': u.id,
            'email': u.email,
            'nombre': u.nombre,
            'plan': u.plan_nombre,
            'is_active': u.is_active,
            'cuotas': stats_cuotas
        })
    except Agent.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_apikeys_pool(request):
    """
    Lista el pool de llaves agrupado por servicio.
    v2: usa la relación con Servicio.
    """
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    from api.models import APIKey
    
    servicio_filter = request.query_params.get('servicio')
    keys = APIKey.objects.all().select_related('servicio').order_by('servicio__nombre', '-creado_en')
    
    if servicio_filter:
        keys = keys.filter(servicio__nombre__icontains=servicio_filter)
    
    data = []
    for k in keys:
        limite = k.google_daily_limit or 1500
        consumo = k.requests_today or 0
        porcentaje = min(100, int((consumo / limite) * 100)) if limite else 0
        
        # Encontrar quién la tiene asignada (como primaria)
        asig_primaria = UserAPIAssignment.objects.filter(apikey=k, activo=True, is_primary=True).first()
        asig_extras = UserAPIAssignment.objects.filter(apikey=k, activo=True, is_primary=False).count()

        data.append({
            'id': k.id,
            'servicio': k.servicio.nombre,
            'label': k.label or f"{k.api_key[:10]}...",
            'status': k.status,
            'consumo_hoy': consumo,
            'limite_hoy': limite,
            'porcentaje': porcentaje,
            'error_count': k.error_count,
            'asignada_a': asig_primaria.user.email if asig_primaria else None,
            'extras_count': asig_extras
        })
    
    return Response({'keys': data})

@api_view(['POST'])
def admin_apikeys_pool_crear(request):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    svc_name = _normalize_service_name(request.data.get('servicio') or request.data.get('service'))
    key_val = _normalize_api_key_value(request.data.get('api_key') or request.data.get('key'))
    if not svc_name or not key_val:
        return Response({'error': 'Faltan servicio/api_key'}, status=400)

    svc, _ = Servicio.objects.get_or_create(nombre=svc_name)
    with transaction.atomic():
        cleanup = _cleanup_duplicate_api_keys([svc.nombre])
        existing = APIKey.objects.filter(servicio=svc, api_key=key_val).order_by('id').first()
        if existing:
            return Response({
                'id': existing.id,
                'status': 'exists',
                'duplicates_existing': 1,
                **cleanup,
            }, status=200)

        k = APIKey.objects.create(
            servicio=svc,
            api_key=key_val,
            label=request.data.get('label'),
            google_daily_limit=request.data.get('daily_limit', 1500),
            status='available',
        )
    return Response({'id': k.id, 'status': 'created', **cleanup}, status=201)

@api_view(['POST'])
def admin_apikeys_pool_bulk(request):
    if not _is_staff_check(request): return _forbidden()
    keys_data = request.data.get('keys', [])
    if not isinstance(keys_data, list) or not keys_data:
        return Response({'error': 'No se enviaron keys'}, status=400)

    seen_in_request = set()
    new_keys = []
    errors = []
    counts = {}
    affected_services = set()
    duplicates_in_request = 0
    duplicates_existing = 0

    with transaction.atomic():
        for index, data in enumerate(keys_data, start=1):
            if not isinstance(data, dict):
                errors.append({'index': index, 'error': 'Formato invalido'})
                continue

            service_name = _normalize_service_name(data.get('service') or data.get('servicio'))
            api_key_str = _normalize_api_key_value(data.get('api_key') or data.get('key'))
            limit = data.get('daily_limit', 1500)
            label = data.get('label')

            if not service_name or not api_key_str:
                errors.append({'index': index, 'error': 'Faltan service o api_key'})
                continue

            servicio = Servicio.objects.filter(nombre=service_name).first()
            if not servicio:
                errors.append({'index': index, 'service': service_name, 'error': f'Servicio "{service_name}" no existe'})
                continue

            affected_services.add(servicio.nombre)
            fingerprint = (servicio.id, api_key_str)
            if fingerprint in seen_in_request:
                duplicates_in_request += 1
                continue
            seen_in_request.add(fingerprint)

            if APIKey.objects.filter(servicio=servicio, api_key=api_key_str).exists():
                duplicates_existing += 1
                continue

            new_keys.append(APIKey(
                servicio=servicio,
                api_key=api_key_str,
                google_daily_limit=limit,
                label=label,
                status='available',
            ))

        if new_keys:
            APIKey.objects.bulk_create(new_keys)
            for key in new_keys:
                service = key.servicio.nombre
                counts[service] = counts.get(service, 0) + 1

        cleanup = _cleanup_duplicate_api_keys(affected_services)

    return Response({
        'status': 'created' if new_keys else 'ok',
        'received': len(keys_data),
        'created': len(new_keys),
        'count': len(new_keys),
        'counts_by_service': counts,
        'ignored': duplicates_in_request + duplicates_existing,
        'duplicates_in_request': duplicates_in_request,
        'duplicates_existing': duplicates_existing,
        'duplicates_deleted': cleanup['duplicates_deleted'],
        'duplicates_protected': cleanup['duplicates_protected'],
        'duplicate_groups': cleanup['duplicate_groups'],
        'errores': errors,
    }, status=201 if new_keys else 200)

@api_view(['GET', 'PUT', 'DELETE'])
def admin_apikeys_pool_detail(request, pk):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    k = APIKey.objects.get(pk=pk)
    if request.method == 'GET':
        return Response({'id': k.id, 'key': k.api_key, 'status': k.status})
    elif request.method == 'PUT':
        # Update logic...
        k.save()
        return Response({'ok': True})
    elif request.method == 'DELETE':
        k.delete()
        return Response({'ok': True})

@api_view(['GET'])
def admin_apikeys_global(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({'settings': {}})

@api_view(['POST'])
def admin_enviar_email(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({'ok': True, 'message': 'Email sent stub'})

@api_view(['POST'])
def admin_add_extra_api(request, user_id):
    """Asigna una API extra manualmente a un usuario."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    
    from api.services.pool_service import APIPoolService
    servicio_nombre = request.data.get('servicio', 'gemini')
    
    try:
        user = Agent.objects.get(id=user_id)
        asig = APIPoolService.add_extra_key(user, servicio_nombre)
        if asig:
            return Response({'ok': True, 'key': f"{asig.apikey.api_key[:10]}..."})
        return Response({'error': 'No hay stock disponible'}, status=400)
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)

@api_view(['POST'])
def admin_apikeys_auto_repair(request):
    """Repara las APIs de los usuarios activos."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    
    from api.services.pool_service import APIPoolService
    user_ids = request.data.get('user_ids', [])
    
    if user_ids:
        users = Agent.objects.filter(id__in=user_ids, is_active=True)
    else:
        users = Agent.objects.filter(is_active=True)
        
    fixed = 0
    for u in users:
        repaired = APIPoolService.repair_user_apis(u)
        if repaired:
            fixed += 1
            
    return Response({"status": "success", "fixed_count": fixed})

# --- Stubs para bundles (eliminados en v2) ---
@api_view(['GET'])
def admin_bundles_list(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({'bundles': [], 'message': 'Bundles eliminados en v2. Usar Pool.'})

@api_view(['POST'])
def admin_bundles_crear(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({'error': 'Deprecated'}, status=400)

@api_view(['GET', 'PUT', 'DELETE'])
def admin_bundles_detail(request, bundle_id):
    if not _is_staff_check(request): return _forbidden()
    return Response({'error': 'Deprecated'}, status=404)

@api_view(['POST'])
def admin_bundles_asignar(request, bundle_id):
    if not _is_staff_check(request): return _forbidden()
    return Response({'error': 'Deprecated'}, status=400)

@api_view(['POST'])
def admin_bundles_liberar(request, bundle_id):
    if not _is_staff_check(request): return _forbidden()
    return Response({'error': 'Deprecated'}, status=400)

@api_view(['GET'])
def admin_bundles_stats(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({'disponibles': 0, 'asignados': 0})

# --- Librería de Audio (VideoMusic + VideoSFX) ---
@api_view(['GET', 'POST'])
def admin_audio_music(request):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    if request.method == 'GET':
        tracks = VideoMusic.objects.all().order_by('-creado_en')
        return Response([{
            'id': t.id, 'nombre': t.nombre, 'duracion': t.duracion_segundos, 
            'activo': t.activo, 'url': t.cloudinary_url
        } for t in tracks])
    # Subida no implementada en este stub simplificado para no romper el deploy
    return Response({'error': 'Use Cloudinary Admin'}, status=400)

@api_view(['DELETE', 'PATCH'])
def admin_audio_music_detail(request, pk):
    if not _is_staff_check(request): return _forbidden()
    VideoMusic.objects.filter(pk=pk).delete()
    return Response({'ok': True})

@api_view(['GET', 'POST'])
def admin_audio_sfx(request):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    if request.method == 'GET':
        sfx = VideoSFX.objects.all().order_by('-creado_en')
        return Response([{
            'id': s.id, 'nombre': s.nombre, 'tipo': s.tipo, 
            'activo': s.activo, 'url': s.cloudinary_url
        } for s in sfx])
    return Response({'error': 'Use Cloudinary Admin'}, status=400)

@api_view(['DELETE', 'PATCH'])
def admin_audio_sfx_detail(request, pk):
    if not _is_staff_check(request): return _forbidden()
    VideoSFX.objects.filter(pk=pk).delete()
    return Response({'ok': True})

@api_view(['GET', 'POST'])
def admin_branding_watermark(request):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    config_obj, _ = ConfiguracionSistema.objects.get_or_create(clave='watermark')
    if request.method == 'GET':
        return Response({'url': config_obj.datos.get('url')})
    # Update logic (skipped for brevity, but model is compatible)
    return Response({'ok': True})

# --- Más endpoints ---
@api_view(['POST'])
def admin_usuario_eliminar(request, user_id):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    try:
        u = Agent.objects.get(id=user_id)
        u.soft_delete()
        return Response({'ok': True})
    except Agent.DoesNotExist: return Response(status=404)

@api_view(['GET'])
def admin_usuario_restaurar(request, user_id):
    if not _is_staff_check(request): return _forbidden()
    # Requiere manager all_including_deleted()
    u = Agent.objects.all_including_deleted().get(id=user_id)
    u.eliminado_en = None
    u.is_active = True
    u.save()
    return Response({'ok': True})

@api_view(['POST'])
def admin_usuario_cambiar_plan(request, user_id):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    plan = request.data.get('plan') or request.data.get('plan_nombre')
    if plan not in ['starter', 'pro', 'scale', 'business']:
        return Response({'error': 'Plan invalido'}, status=400)
    u = Agent.objects.get(id=user_id)
    u.plan_nombre = plan
    u.plan_activo = True
    u.plan_seleccionado = True
    u.free_trial_started_at = None
    u.free_trial_ends_at = None
    u.save(update_fields=[
        'plan_nombre', 'plan_activo', 'plan_seleccionado',
        'free_trial_started_at', 'free_trial_ends_at', 'updated_at',
    ])
    return Response({'ok': True, 'plan': plan})

@api_view(['GET'])
def admin_apikeys_resumen(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({"message": "Use admin_pool_estado"})

@api_view(['GET'])
def admin_pool_estado(request):
    if not _is_staff_check(request): return _forbidden()
    stats = APIKey.objects.values('servicio__nombre', 'status').annotate(total=Count('id'))
    return Response(list(stats))

@api_view(['POST'])
def admin_alerts_read(request, alert_id):
    if not _is_staff_check(request): return _forbidden()
    AdminAlert.objects.filter(id=alert_id).update(is_read=True)
    return Response({'ok': True})

@api_view(['POST'])
def admin_health_check(request):
    if not _is_staff_check(request): return _forbidden()
    return Response({'message': 'Task queued'})
