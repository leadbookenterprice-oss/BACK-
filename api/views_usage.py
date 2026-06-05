"""
api/views_usage.py - LeadBook v2.0
Estadisticas de uso de APIs para usuarios y admin.
Las API keys pertenecen al pool interno de LeadBook; los usuarios solo consumen cuota.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from api.models import APIKey, UserAPIQuota
from api.services.pool_service import APIPoolService, ensure_core_services


SERVICIO_MAP = {
    'gemini': {'nombre': 'Generacion de Contenido IA', 'unidad': 'peticiones', 'icono': 'brain'},
    'elevenlabs': {'nombre': 'Voces Neurales', 'unidad': 'caracteres', 'icono': 'mic'},
    'uploadpost': {'nombre': 'Gestor de Redes', 'unidad': 'publicaciones', 'icono': 'share'},
    'cerebras': {'nombre': 'Motor IA Cerebras', 'unidad': 'peticiones IA', 'icono': 'brain'},
}


def _has_pool_capacity(servicio, *, soft_exhaustion=False):
    if str(getattr(servicio, 'nombre', '') or '').strip().lower() == 'uploadpost':
        return APIKey.objects.filter(servicio=servicio, status__in=['available', 'assigned']).exists()
    statuses = ['available', 'in_use', 'exhausted'] if soft_exhaustion else ['available', 'in_use']
    return APIKey.objects.filter(servicio=servicio, status__in=statuses).exists()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mi_uso_apis(request):
    """Devuelve el uso del usuario sin exponer keys asignadas."""
    user = request.user
    ensure_core_services()
    APIPoolService.ensure_user_quotas(user)

    from api.tracking import get_uploadpost_quota, sync_uploadpost_quota_from_sql
    get_uploadpost_quota(user)

    quotas = UserAPIQuota.objects.filter(user=user).select_related('servicio')

    from api.plan_utils import get_daily_listing_quota
    stats = []
    listing_quota = get_daily_listing_quota(user)
    if listing_quota['applies']:
        listing_limit = listing_quota['limit'] or 0
        listing_used = listing_quota['used'] or 0
        stats.append({
            'servicio': 'listados_dia',
            'nombre': 'Listados diarios Starter',
            'icono': 'home',
            'consumido': listing_used,
            'limite': listing_limit,
            'ilimitado': False,
            'limite_label': listing_limit,
            'extras_activos': 0,
            'unidad': 'listados/dia',
            'porcentaje': min(100, int((listing_used / listing_limit) * 100)) if listing_limit else 0,
            'status': 'exhausted' if listing_quota['exhausted'] else 'ok',
            'window': 'day',
            'excludes_video': True,
        })

    for quota in quotas:
        quota.maybe_reset_daily()
        quota.recalcular_limite(plan=user.plan_nombre)
        quota.maybe_reset_monthly()

        svc_name = quota.servicio.nombre
        soft_exhaustion = svc_name in {'gemini', 'elevenlabs'}
        info = SERVICIO_MAP.get(svc_name, {
            'nombre': svc_name.capitalize(),
            'unidad': 'unidades',
            'icono': 'api',
        })

        if svc_name == 'uploadpost':
            quota = sync_uploadpost_quota_from_sql(user, quota)
            limite = quota.user_monthly_limit
            consumido = quota.requests_this_month
            window = 'month'
        else:
            limite = quota.user_daily_limit or 1500
            consumido = quota.requests_today
            window = 'day'

        unlimited = svc_name == 'uploadpost' and limite is None
        pool_available = _has_pool_capacity(quota.servicio, soft_exhaustion=soft_exhaustion)
        exhausted_by_quota = bool(not unlimited and limite and consumido >= limite)
        exhausted_by_pool = not pool_available and not soft_exhaustion

        if quota.is_blocked and not exhausted_by_quota:
            quota.is_blocked = False
            quota.blocked_reason = None
            quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])

        porcentaje = 0 if unlimited else (min(100, int((consumido / limite) * 100)) if limite else 0)
        status_value = 'ok'
        if exhausted_by_quota or exhausted_by_pool or quota.is_blocked:
            status_value = 'exhausted'
            if limite and not unlimited:
                porcentaje = 100

        stats.append({
            'servicio': svc_name,
            'nombre': info['nombre'],
            'icono': info['icono'],
            'consumido': consumido,
            'limite': limite,
            'ilimitado': unlimited,
            'limite_label': 'inf' if unlimited else limite,
            'extras_activos': 0,
            'unidad': info['unidad'],
            'porcentaje': porcentaje,
            'status': status_value,
            'window': window,
            'pool_available': pool_available,
        })

    return Response({'success': True, 'plan': user.plan_nombre, 'stats': stats})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_uso_global(request):
    """Resumen administrativo simple de llaves del pool LeadBook."""
    keys = APIKey.objects.all().select_related('servicio').order_by('servicio__nombre', '-total_requests')

    resultado = []
    for key in keys:
        service = key.servicio.nombre
        if service == 'cerebras':
            limite = key.google_daily_limit or 1000000
            if limite < 100000:
                limite = 1000000
            consumido = key.slot_tokens_today or 0
        elif service == 'elevenlabs':
            limite = key.google_monthly_limit or 10000
            consumido = key.requests_this_month
        else:
            limite = key.google_daily_limit or 1500
            consumido = key.requests_today
        porcentaje = min(100, int((consumido / limite) * 100)) if limite else 0

        resultado.append({
            'id': key.id,
            'servicio': service,
            'label': key.label or f'{key.api_key[:8]}...',
            'empresa': key.empresa,
            'status': key.status,
            'consumido_hoy': consumido,
            'limite_hoy': limite,
            'porcentaje': 100 if key.status == 'exhausted' else porcentaje,
            'total_requests': key.total_requests,
            'error_count': key.error_count,
            'ultima_vez': key.last_used_at,
        })

    return Response({'success': True, 'keys': resultado})
