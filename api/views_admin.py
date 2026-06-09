# api/views_admin.py — LeadBook v2.0
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from decouple import config
from django.conf import settings
from django.db import transaction
from django.utils.crypto import constant_time_compare
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Count, Sum, Q
import cloudinary.uploader
import requests
from .models import (
    Agent, Listado, Plan, APIKey, AdminAlert, Servicio, 
    UserAPIAssignment, UserAPIQuota, VideoMusic, VideoSFX, ConfiguracionSistema,
    AccessCode, ContentGenerationRun, CerebrasUsageLog
)
from api.services.pool_service import SERVICE_DEFAULTS
from api.services.api_usage_monitor import build_api_usage_logs, build_api_usage_summary
from api.services.ai_router import build_ai_root_payload, save_ai_root_config, test_ai_root
from admin_panel.auth import is_admin_request

ADMIN_KEY = config('ADMIN_KEY', default='')

ROOT_LLM_SERVICES = {
    'gemini',
    'cerebras',
    'groq',
    'nvidia',
    'nim',
    'openrouter',
    'huggingface',
    'mistral',
    'cohere',
    'sambanova',
    'deepseek',
    'cloudflare_workers_ai',
    'github_models',
}
ASSIGNABLE_SERVICES = {'uploadpost', 'elevenlabs'}
ENVIRONMENT_SERVICES = {'cloudinary'}
ADMIN_POOL_SERVICES = ROOT_LLM_SERVICES | ASSIGNABLE_SERVICES

def _is_staff_check(request):
    return is_admin_request(request)


def _mask_secret(value, head=4, tail=4):
    value = str(value or '')
    if not value:
        return ''
    if len(value) <= head + tail:
        return '*' * len(value)
    return f'{value[:head]}...{value[-tail:]}'


def _normalize_api_key_value(value):
    return str(value or '').strip()


def _normalize_service_name(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'nvidia_nim', 'nim'}:
        return 'nvidia'
    return normalized


def _service_category(service_name):
    normalized = _normalize_service_name(service_name)
    if normalized in ROOT_LLM_SERVICES:
        return 'root_llm'
    if normalized in ASSIGNABLE_SERVICES:
        return 'assignable'
    if normalized in ENVIRONMENT_SERVICES:
        return 'environment'
    return 'other'


def _pool_service_allowed(service_name):
    return _normalize_service_name(service_name) in ADMIN_POOL_SERVICES


def _allowed_pool_services_for_category(category):
    normalized = str(category or '').strip().lower()
    if normalized in {'root_llm', 'root', 'llm'}:
        return ROOT_LLM_SERVICES
    if normalized in {'assignable', 'assignment', 'asignacion', 'asignables'}:
        return ASSIGNABLE_SERVICES
    return ADMIN_POOL_SERVICES


def _service_defaults(nombre):
    service_defaults = SERVICE_DEFAULTS.get(nombre)
    if service_defaults:
        return {
            'descripcion': service_defaults['descripcion'],
            'activo': True,
            'default_daily_limit': service_defaults['default_daily_limit'],
            'default_monthly_limit': service_defaults['default_monthly_limit'],
            'extra_increment': service_defaults['extra_increment'],
        }

    descripcion = {
        'gemini': 'Google Gemini AI Studio',
        'elevenlabs': 'ElevenLabs',
        'uploadpost': 'UploadPost',
        'groq': 'Groq',
        'nvidia': 'NVIDIA NIM',
        'cerebras': 'Cerebras',
    }.get(nombre, nombre.title())
    return {
        'descripcion': descripcion,
        'activo': True,
        'default_daily_limit': 1000000 if nombre == 'cerebras' else (1500 if nombre in {'gemini', 'elevenlabs'} else (999999 if nombre == 'uploadpost' else 1500)),
        'default_monthly_limit': 10 if nombre == 'uploadpost' else None,
        'extra_increment': 1000000 if nombre == 'cerebras' else (10 if nombre == 'uploadpost' else 1500),
    }


def _get_or_create_service(nombre):
    normalized = _normalize_service_name(nombre)
    if not normalized:
        return None
    servicio = Servicio.objects.filter(nombre__iexact=normalized).first()
    if servicio:
        return servicio
    servicio, _ = Servicio.objects.get_or_create(nombre=normalized, defaults=_service_defaults(normalized))
    return servicio


ELEVENLABS_MONTHLY_DEFAULT = 10000


def _key_window_usage(key):
    service_name = _normalize_service_name(getattr(getattr(key, 'servicio', None), 'nombre', ''))
    if service_name == 'cerebras':
        limit = key.google_daily_limit or 1000000
        if limit < 100000:
            limit = 1000000
        return {
            'service': service_name,
            'usage': int(key.slot_tokens_today or 0),
            'limit': int(limit or 0),
            'unit': 'tokens',
            'window': 'day',
        }
    if service_name == 'elevenlabs':
        limit = key.google_monthly_limit or ELEVENLABS_MONTHLY_DEFAULT
        usage = key.requests_this_month or 0
        unit = 'characters'
        window = 'month'
    else:
        limit = key.google_daily_limit or 1500
        usage = key.requests_today or 0
        unit = 'requests'
        window = 'day'
    return {
        'service': service_name,
        'usage': int(usage or 0),
        'limit': int(limit or 0),
        'unit': unit,
        'window': window,
    }


def _api_key_has_history(key):
    if UserAPIAssignment.objects.filter(apikey=key).exists():
        return True
    if key.logs.exists():
        return True
    counters = [key.requests_today, key.requests_this_month, key.total_requests, key.error_count]
    return bool(key.last_used_at or any(int(value or 0) > 0 for value in counters))


def _key_assignment_stats(key):
    service_name = _normalize_service_name(getattr(getattr(key, 'servicio', None), 'nombre', ''))
    if service_name in ASSIGNABLE_SERVICES:
        assignments = UserAPIAssignment.objects.filter(
            apikey=key,
            activo=True,
            servicio__nombre__iexact=service_name,
        ).select_related('user')
        users = [a.user for a in assignments if a.user_id]
        return {
            'assigned_count': len(users),
            'shared_capacity': 1,
            'shared_available_slots': max(0, 1 - len(users)),
            'sharing_mode': f'{service_name}_per_user',
            'assigned_users': [
                {'id': user.id, 'email': user.email, 'plan': getattr(user, 'plan_nombre', '')}
                for user in users[:12]
            ],
        }
    shared_capacity = 1
    return {
        'assigned_count': 0,
        'shared_capacity': shared_capacity,
        'shared_available_slots': shared_capacity,
        'sharing_mode': 'leadbook_pool',
        'assigned_users': [],
    }


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
    
    # Solo clientes reales; el dashboard admin usa sesión firmada, no un Agent staff.
    usuarios = Agent.objects.filter(is_staff=False, is_superuser=False).order_by('-fecha_registro')
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


@api_view(['GET', 'PUT'])
@permission_classes([AllowAny])
def admin_ai_root(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        return Response(build_ai_root_payload())

    provider = request.data.get('provider')
    model = request.data.get('model')
    try:
        save_ai_root_config(
            provider,
            model,
            updated_by=getattr(request.user, 'email', '') or 'admin',
        )
    except ValueError as exc:
        payload = build_ai_root_payload()
        payload.update({
            'error': 'ai_root_unavailable',
            'message': str(exc),
        })
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)

    payload = build_ai_root_payload()
    payload['saved'] = True
    return Response(payload)


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_ai_root_test(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        result = test_ai_root(
            provider=request.data.get('provider'),
            model=request.data.get('model'),
            prompt=request.data.get('prompt'),
        )
    except ValueError as exc:
        return Response(
            {'error': 'ai_root_unavailable', 'message': str(exc), **build_ai_root_payload()},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        return Response(
            {'error': 'ai_root_test_failed', 'message': str(exc), **build_ai_root_payload()},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(result)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_apikeys_pool(request):
    """
    Lista el pool de llaves agrupado por servicio.
    v2: usa la relación con Servicio y permite root LLM + asignables.
    """
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    servicio_filter = _normalize_service_name(request.query_params.get('servicio') or request.query_params.get('service'))
    category_filter = request.query_params.get('category') or request.query_params.get('categoria')
    keys = APIKey.objects.all().select_related('servicio', 'slot_locked_by', 'slot_locked_listado').order_by('servicio__nombre', '-total_requests', '-requests_today', '-slot_tokens_today', '-creado_en')
    if servicio_filter:
        if servicio_filter in ENVIRONMENT_SERVICES:
            return Response({
                'error': 'cloudinary_uses_dedicated_endpoints',
                'message': 'Cloudinary se administra desde /api/admin/cloudinary/...',
                'keys': [],
            }, status=status.HTTP_400_BAD_REQUEST)
        if not _pool_service_allowed(servicio_filter):
            return Response({'keys': []})
        keys = keys.filter(servicio__nombre__iexact=servicio_filter)
    else:
        keys = keys.filter(servicio__nombre__in=_allowed_pool_services_for_category(category_filter))
    
    data = []
    for k in keys:
        service_name = _normalize_service_name(k.servicio.nombre if k.servicio_id else '')
        usage = _key_window_usage(k)
        limite = usage['limit']
        consumo = usage['usage']
        porcentaje = min(100, int((consumo / limite) * 100)) if limite else 0
        
        # Encontrar quién la tiene asignada cuando el servicio es por usuario.
        assignment_stats = _key_assignment_stats(k)
        asig_primaria = None
        if service_name in ASSIGNABLE_SERVICES:
            asig_primaria = (
                UserAPIAssignment.objects
                .filter(apikey=k, activo=True, servicio__nombre__iexact=service_name)
                .select_related('user')
                .order_by('-is_primary', 'assigned_at')
                .first()
            )
        status_value = k.status
        if k.status == 'assigned' and service_name not in ASSIGNABLE_SERVICES:
            status_value = 'in_use'
        active_generation_run = None
        recent_cerebras_log = None
        if service_name == 'cerebras':
            active_generation_run = (
                ContentGenerationRun.objects
                .filter(api_key=k, status__in=['pending', 'running', 'waiting_slot', 'waiting_rate_limit'])
                .select_related('user', 'listado')
                .order_by('-started_at')
                .first()
            )
            recent_cerebras_log = (
                CerebrasUsageLog.objects
                .filter(api_key=k)
                .order_by('-creado_en', '-id')
                .first()
            )

        data.append({
            'id': k.id,
            'servicio': service_name,
            'service': service_name,
            'category': _service_category(service_name),
            'label': k.label or _mask_secret(k.api_key),
            'api_key_masked': _mask_secret(k.api_key),
            'key_masked': _mask_secret(k.api_key),
            'status': status_value,
            'consumo_hoy': consumo,
            'limite_hoy': limite,
            'consumo_mes': k.requests_this_month or 0,
            'limite_mes': k.google_monthly_limit,
            'usage_unit': usage['unit'],
            'usage_window': usage['window'],
            'usage_current': consumo,
            'usage_limit': limite,
            'porcentaje': porcentaje,
            'error_count': k.error_count,
            'asignada_a': asig_primaria.user.email if asig_primaria else None,
            'assigned_to_email': asig_primaria.user.email if asig_primaria else None,
            'assigned_to_id': asig_primaria.user.id if asig_primaria else None,
            'extras_count': 0,
            'assigned_users_count': assignment_stats['assigned_count'],
            'shared_capacity': assignment_stats['shared_capacity'],
            'shared_available_slots': assignment_stats['shared_available_slots'],
            'sharing_mode': assignment_stats['sharing_mode'],
            'assigned_users': assignment_stats['assigned_users'],
            'slot_locked_by_id': k.slot_locked_by_id,
            'slot_locked_by_email': k.slot_locked_by.email if k.slot_locked_by_id and k.slot_locked_by else None,
            'slot_locked_listado_id': k.slot_locked_listado_id,
            'slot_locked_until': k.slot_locked_until,
            'slot_tokens_today': k.slot_tokens_today or 0,
            'slot_tokens_limit': (k.google_daily_limit if (k.google_daily_limit or 0) >= 100000 else 1000000),
            'slot_last_error': k.slot_last_error or '',
            'slot_last_rate_limit_headers': k.slot_last_rate_limit_headers or {},
            'slot_last_rate_limit_at': k.slot_last_rate_limit_at,
            'active_generation_run_id': active_generation_run.id if active_generation_run else None,
            'active_generation_run_status': active_generation_run.status if active_generation_run else None,
            'active_generation_run_step': active_generation_run.current_step if active_generation_run else None,
            'active_generation_run_user_email': active_generation_run.user.email if active_generation_run and active_generation_run.user_id else None,
            'active_generation_run_listado_id': active_generation_run.listado_id if active_generation_run else None,
            'last_cerebras_log': {
                'id': recent_cerebras_log.id,
                'task': recent_cerebras_log.task,
                'model': recent_cerebras_log.model,
                'status_code': recent_cerebras_log.status_code,
                'success': recent_cerebras_log.success,
                'estimated_tokens': recent_cerebras_log.estimated_tokens,
                'actual_tokens': recent_cerebras_log.actual_tokens,
                'charged_tokens': recent_cerebras_log.charged_tokens,
                'retry_after_seconds': recent_cerebras_log.retry_after_seconds,
                'creado_en': recent_cerebras_log.creado_en,
            } if recent_cerebras_log else None,
        })
    
    return Response({'keys': data})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_cerebras_usage_logs(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        limit = max(1, min(int(request.query_params.get('limit', 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    qs = (
        CerebrasUsageLog.objects
        .select_related('api_key', 'user', 'listado', 'run', 'step')
        .order_by('-creado_en', '-id')
    )
    api_key_id = request.query_params.get('api_key_id') or request.query_params.get('key_id')
    run_id = request.query_params.get('run_id')
    listado_id = request.query_params.get('listado_id')
    user_id = request.query_params.get('user_id')
    success = request.query_params.get('success')

    if api_key_id:
        qs = qs.filter(api_key_id=api_key_id)
    if run_id:
        qs = qs.filter(run_id=run_id)
    if listado_id:
        qs = qs.filter(listado_id=listado_id)
    if user_id:
        qs = qs.filter(user_id=user_id)
    if str(success).lower() in {'true', '1', 'false', '0'}:
        qs = qs.filter(success=str(success).lower() in {'true', '1'})

    logs = []
    for item in qs[:limit]:
        logs.append({
            'id': item.id,
            'api_key_id': item.api_key_id,
            'api_key_label': item.api_key.label if item.api_key_id and item.api_key else None,
            'user_id': item.user_id,
            'user_email': item.user.email if item.user_id and item.user else None,
            'listado_id': item.listado_id,
            'run_id': item.run_id,
            'run_status': item.run.status if item.run_id and item.run else None,
            'step': item.step.step if item.step_id and item.step else None,
            'model': item.model,
            'task': item.task,
            'status_code': item.status_code,
            'success': item.success,
            'estimated_tokens': item.estimated_tokens,
            'actual_tokens': item.actual_tokens,
            'charged_tokens': item.charged_tokens,
            'response_time_ms': item.response_time_ms,
            'rate_limit_headers': item.rate_limit_headers or {},
            'retry_after_seconds': item.retry_after_seconds,
            'error_message': item.error_message or '',
            'creado_en': item.creado_en,
        })

    return Response({'logs': logs, 'count': len(logs)})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_api_usage_summary(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    create_alerts = str(request.query_params.get('alerts', '1')).strip().lower() not in {'0', 'false', 'no'}
    payload = build_api_usage_summary(
        service=request.query_params.get('service') or request.query_params.get('servicio'),
        create_alerts=create_alerts,
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_api_usage_logs(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    payload = build_api_usage_logs(
        service=request.query_params.get('service') or request.query_params.get('servicio'),
        api_key_id=request.query_params.get('api_key_id') or request.query_params.get('key_id'),
        user_id=request.query_params.get('user_id'),
        success=request.query_params.get('success'),
        limit=request.query_params.get('limit', 100),
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_api_usage_key_detail(request, key_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    key = APIKey.objects.filter(pk=key_id).select_related('servicio').first()
    if not key:
        return Response({'error': 'API key no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    summary = build_api_usage_summary(
        service=key.servicio.nombre if key.servicio_id else None,
        create_alerts=str(request.query_params.get('alerts', '1')).strip().lower() not in {'0', 'false', 'no'},
    )
    key_payload = next((item for item in summary.get('keys', []) if item.get('id') == key.id), None)
    logs = build_api_usage_logs(
        service=key.servicio.nombre if key.servicio_id else None,
        api_key_id=key.id,
        success=request.query_params.get('success'),
        limit=request.query_params.get('limit', 100),
    )
    return Response({
        'generated_at': summary.get('generated_at'),
        'key': key_payload,
        'logs': logs.get('logs', []),
        'logs_count': logs.get('count', 0),
    })


@api_view(['POST'])
def admin_apikeys_pool_crear(request):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    svc_name = _normalize_service_name(request.data.get('servicio') or request.data.get('service'))
    key_val = _normalize_api_key_value(request.data.get('api_key') or request.data.get('key'))
    if not svc_name or not key_val:
        return Response({'error': 'Faltan servicio/api_key'}, status=400)
    if svc_name in ENVIRONMENT_SERVICES:
        return Response({
            'error': 'cloudinary_uses_dedicated_endpoints',
            'message': 'Cloudinary se administra desde /api/admin/cloudinary/...',
        }, status=400)
    if not _pool_service_allowed(svc_name):
        return Response({'error': 'Servicio no soportado en pool admin'}, status=400)

    svc = _get_or_create_service(svc_name)
    if not svc:
        return Response({'error': 'Servicio invalido'}, status=400)
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

        service_name = _normalize_service_name(svc.nombre)
        try:
            daily_limit = int(request.data.get('daily_limit') or svc.default_daily_limit or 1500)
        except (TypeError, ValueError):
            daily_limit = svc.default_daily_limit or 1500
        monthly_limit = request.data.get(
            'monthly_limit',
            svc.default_monthly_limit if svc.default_monthly_limit is not None else (ELEVENLABS_MONTHLY_DEFAULT if service_name == 'elevenlabs' else None),
        )
        try:
            monthly_limit = int(monthly_limit) if monthly_limit is not None else None
        except (TypeError, ValueError):
            monthly_limit = svc.default_monthly_limit if svc.default_monthly_limit is not None else None

        k = APIKey.objects.create(
            servicio=svc,
            api_key=key_val,
            label=request.data.get('label'),
            google_daily_limit=daily_limit,
            google_monthly_limit=monthly_limit,
            status='available',
        )
    return Response({'id': k.id, 'service': service_name, 'category': _service_category(service_name), 'status': 'created', **cleanup}, status=201)

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
            if service_name in ENVIRONMENT_SERVICES:
                errors.append({'index': index, 'service': service_name, 'error': 'Cloudinary usa endpoints dedicados'})
                continue
            if not _pool_service_allowed(service_name):
                errors.append({'index': index, 'service': service_name, 'error': 'Servicio no soportado en pool admin'})
                continue

            servicio = _get_or_create_service(service_name)
            if not servicio:
                errors.append({'index': index, 'service': service_name, 'error': f'Servicio "{service_name}" no existe'})
                continue
            monthly_limit = data.get(
                'monthly_limit',
                servicio.default_monthly_limit if servicio.default_monthly_limit is not None else (ELEVENLABS_MONTHLY_DEFAULT if service_name == 'elevenlabs' else None),
            )
            try:
                monthly_limit = int(monthly_limit) if monthly_limit is not None else None
            except (TypeError, ValueError):
                monthly_limit = servicio.default_monthly_limit if servicio.default_monthly_limit is not None else None
            try:
                limit = int(limit or servicio.default_daily_limit or 1500)
            except (TypeError, ValueError):
                limit = servicio.default_daily_limit or 1500

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
                google_monthly_limit=monthly_limit,
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
    k = (
        APIKey.objects
        .filter(pk=pk)
        .exclude(servicio__nombre__iexact='cloudinary')
        .select_related('servicio')
        .first()
    )
    if not k:
        return Response({'error': 'API key no encontrada en pool admin'}, status=status.HTTP_404_NOT_FOUND)
    service_name = _normalize_service_name(k.servicio.nombre if k.servicio_id else '')
    if request.method == 'GET':
        return Response({
            'id': k.id,
            'service': service_name,
            'servicio': service_name,
            'category': _service_category(service_name),
            'key': _mask_secret(k.api_key),
            'key_masked': _mask_secret(k.api_key),
            'api_key_masked': _mask_secret(k.api_key),
            'status': k.status,
            'label': k.label or '',
            'daily_limit': k.google_daily_limit,
            'monthly_limit': k.google_monthly_limit,
        })
    elif request.method == 'PUT':
        label = request.data.get('label')
        if label is not None:
            k.label = str(label).strip()
        if 'daily_limit' in request.data:
            try:
                k.google_daily_limit = int(request.data.get('daily_limit') or k.google_daily_limit or 999999)
            except (TypeError, ValueError):
                return Response({'error': 'daily_limit invalido'}, status=status.HTTP_400_BAD_REQUEST)
        if 'monthly_limit' in request.data:
            raw_monthly = request.data.get('monthly_limit')
            try:
                k.google_monthly_limit = int(raw_monthly) if raw_monthly not in {None, ''} else None
            except (TypeError, ValueError):
                return Response({'error': 'monthly_limit invalido'}, status=status.HTTP_400_BAD_REQUEST)
        k.save(update_fields=['label', 'google_daily_limit', 'google_monthly_limit', 'updated_at'])
        return Response({'ok': True})
    elif request.method == 'DELETE':
        k.delete()
        return Response({'ok': True})


def _admin_key_test_request(service_name, api_key):
    service_name = _normalize_service_name(service_name)
    timeout = 12
    if service_name == 'elevenlabs':
        return requests.get(
            'https://api.elevenlabs.io/v1/user/subscription',
            headers={'xi-api-key': api_key},
            timeout=timeout,
        )
    if service_name == 'uploadpost':
        return requests.get(
            'https://api.upload-post.com/api/uploadposts/users',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'gemini':
        return requests.get(
            'https://generativelanguage.googleapis.com/v1beta/models',
            params={'key': api_key},
            timeout=timeout,
        )
    if service_name == 'cerebras':
        return requests.get(
            'https://api.cerebras.ai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'groq':
        return requests.get(
            'https://api.groq.com/openai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'nvidia':
        return requests.get(
            'https://integrate.api.nvidia.com/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'openrouter':
        return requests.get(
            'https://openrouter.ai/api/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'huggingface':
        return requests.get(
            'https://huggingface.co/api/whoami-v2',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'mistral':
        return requests.get(
            'https://api.mistral.ai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'cohere':
        return requests.get(
            'https://api.cohere.ai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'sambanova':
        return requests.get(
            'https://api.sambanova.ai/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'deepseek':
        return requests.get(
            'https://api.deepseek.com/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    if service_name == 'github_models':
        return requests.get(
            'https://models.inference.ai.azure.com/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=timeout,
        )
    raise ValueError('test_not_supported')


@api_view(['POST'])
def admin_apikeys_pool_test(request, pk):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)

    key = (
        APIKey.objects
        .filter(pk=pk)
        .exclude(servicio__nombre__iexact='cloudinary')
        .select_related('servicio')
        .first()
    )
    if not key:
        return Response({'error': 'API key no encontrada en pool admin'}, status=status.HTTP_404_NOT_FOUND)

    service_name = _normalize_service_name(key.servicio.nombre if key.servicio_id else '')
    if service_name in ENVIRONMENT_SERVICES:
        return Response({'error': 'cloudinary_uses_dedicated_endpoints'}, status=status.HTTP_400_BAD_REQUEST)
    if not _pool_service_allowed(service_name):
        return Response({'error': 'test_not_supported'}, status=status.HTTP_400_BAD_REQUEST)

    started = now()
    try:
        response = _admin_key_test_request(service_name, key.api_key)
        elapsed_ms = int((now() - started).total_seconds() * 1000)
        ok = 200 <= response.status_code < 300
        if ok:
            technical_status = 'OK'
            if key.status in {'dead', 'exhausted'}:
                key.status = 'available'
            key.last_health_status = True
            key.slot_last_error = ''
        elif response.status_code in {401, 403}:
            technical_status = 'INVALIDA'
            key.status = 'dead'
            key.error_count = (key.error_count or 0) + 1
            key.last_health_status = False
            key.slot_last_error = f'Test {service_name} invalido: HTTP {response.status_code}'
        elif response.status_code == 429:
            technical_status = 'RATE_LIMITED'
            key.status = 'exhausted'
            key.error_count = (key.error_count or 0) + 1
            key.last_health_status = False
            key.slot_last_error = 'Rate limit temporal o cuota agotada durante test'
        else:
            technical_status = 'ERROR_TEMPORAL'
            key.error_count = (key.error_count or 0) + 1
            key.last_health_status = False
            key.slot_last_error = f'Test {service_name} fallo: HTTP {response.status_code}'
        key.last_health_check = now()
        key.save(update_fields=['status', 'error_count', 'last_health_check', 'last_health_status', 'slot_last_error', 'updated_at'])
        return Response({
            'id': key.id,
            'service': service_name,
            'category': _service_category(service_name),
            'status': technical_status,
            'health_ok': ok,
            'status_code': response.status_code,
            'response_time_ms': elapsed_ms,
            'error': None if ok else (response.text or '')[:500],
            'message': 'Key operativa' if ok else 'El test no pudo validar la key',
        }, status=200 if ok else status.HTTP_502_BAD_GATEWAY)
    except ValueError as exc:
        return Response({'error': str(exc), 'service': service_name}, status=status.HTTP_400_BAD_REQUEST)
    except requests.RequestException as exc:
        key.error_count = (key.error_count or 0) + 1
        key.last_health_check = now()
        key.last_health_status = False
        key.slot_last_error = str(exc)[:1000]
        key.save(update_fields=['error_count', 'last_health_check', 'last_health_status', 'slot_last_error', 'updated_at'])
        return Response({
            'id': key.id,
            'service': service_name,
            'category': _service_category(service_name),
            'status': 'ERROR_TEMPORAL',
            'health_ok': False,
            'error': str(exc),
        }, status=status.HTTP_502_BAD_GATEWAY)


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
    """Deprecated: solo UploadPost tiene asignacion por usuario."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({
        'ok': False,
        'disabled': True,
        'message': 'Las API keys de IA son internas de LeadBook. Solo UploadPost se asigna por usuario.',
    }, status=status.HTTP_410_GONE)

@api_view(['POST'])
def admin_apikeys_auto_repair(request):
    """Deprecated: no hay auto-repair de APIs de IA por usuario."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    return Response({
        'status': 'disabled',
        'disabled': True,
        'fixed_count': 0,
        'message': 'El pool de IA es interno de LeadBook. UploadPost se asigna automaticamente cuando el usuario lo necesita.',
    })

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

    image_value = request.data.get('image') or request.data.get('url')
    if not image_value:
        return Response({'error': 'Falta image o url'}, status=400)

    resolved_url = str(image_value).strip()
    if resolved_url.startswith('data:') or resolved_url.startswith('http'):
        try:
            uploaded = cloudinary.uploader.upload(
                resolved_url,
                folder='leadbook/branding',
                public_id='watermark',
                overwrite=True,
                resource_type='image',
            )
            resolved_url = uploaded.get('secure_url') or uploaded.get('url') or resolved_url
        except Exception as exc:
            return Response({'error': f'No se pudo subir la marca de agua: {exc}'}, status=400)

    config_obj.datos = {'url': resolved_url}
    config_obj.valor = resolved_url
    config_obj.save(update_fields=['datos', 'valor', 'actualizado_en'])
    return Response({'ok': True, 'url': resolved_url})

# --- Más endpoints ---
@api_view(['POST'])
def admin_usuario_eliminar(request, user_id):
    if not _is_staff_check(request): return Response({'error': 'Forbidden'}, status=403)
    try:
        u = Agent.objects.get(id=user_id)
        _blacklist_user_refresh_tokens(u)
        revoked_user_id = u.id
        u.soft_delete()
        transaction.on_commit(lambda: _emit_account_revoked_event(revoked_user_id, None))
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
