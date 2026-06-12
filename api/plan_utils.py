from django.utils import timezone
from datetime import timedelta

TRIAL_EXPIRED_CODE = 'trial_expired'
TRIAL_EXPIRED_MESSAGE = 'Tu prueba Starter expiro. Para seguir usando LeadBook, contactanos o compra un plan.'
PRO_FEATURE_PLANS = {'pro', 'scale', 'business'}
STARTER_DAILY_LISTING_LIMIT = 2
STARTER_DAILY_LISTING_PLANS = {'free', 'starter'}
CONTENT_PACK_REQUIRED_FORMATS = ('pdf', 'post', 'story', 'carrusel', 'email')
PROPERTY_USAGE_COUNTED_AT_KEY = 'property_usage_counted_at'
PROPERTY_USAGE_COUNTED_RUN_ID_KEY = 'property_usage_generation_run_id'

LIMITES = {
    # Alias legacy: las cuentas nuevas con codigo usan starter.
    'free':     {'properties': 1200, 'ai': 1200, 'images': 1200, 'videos': 33, 'auto_posts': 10},
    'starter':  {'properties': 1200, 'ai': 1200, 'images': 1200, 'videos': 33, 'auto_posts': 10},
    'pro':      {'properties': 3600, 'ai': 3600, 'images': 3600, 'videos': 100, 'auto_posts': None},
    'scale':    {'properties': 999999, 'ai': 999999, 'images': 999999, 'videos': 165, 'auto_posts': None},
    'business': {'properties': 999999, 'ai': 999999, 'images': 999999, 'videos': 999999, 'auto_posts': None},
}

def get_limites(agente):
    plan = getattr(agente, 'plan_nombre', 'starter') or 'starter'
    return LIMITES.get(plan, LIMITES['starter'])

def get_plan_name(agente):
    return str(getattr(agente, 'plan_nombre', '') or 'starter').strip().lower()

def get_daily_listing_limit(agente):
    plan = get_plan_name(agente)
    if plan in STARTER_DAILY_LISTING_PLANS:
        return STARTER_DAILY_LISTING_LIMIT
    return None

def get_daily_listing_usage(agente):
    from api.models import UsageLog
    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return UsageLog.objects.filter(agent=agente, tipo='property', fecha__gte=start_of_day).count()

def get_daily_listing_quota(agente):
    limit = get_daily_listing_limit(agente)
    used = get_daily_listing_usage(agente) if limit is not None else 0
    remaining = None if limit is None else max(0, limit - used)
    return {
        'applies': limit is not None,
        'plan': get_plan_name(agente),
        'used': used,
        'limit': limit,
        'remaining': remaining,
        'exhausted': bool(limit is not None and used >= limit),
        'window': 'day',
        'excludes_video': True,
    }

def build_daily_listing_limit_payload(agente):
    quota = get_daily_listing_quota(agente)
    return {
        'error': 'daily_listing_limit_reached',
        'code': 'daily_listing_limit_reached',
        'mensaje': 'Alcanzaste el limite diario de 2 listados del plan Starter. El video se maneja con limites separados.',
        'quota': quota,
        'usados': quota['used'],
        'limite': quota['limit'],
        'excludes_video': True,
    }

def puede_crear_listado_hoy(agente):
    quota = get_daily_listing_quota(agente)
    return not quota['exhausted'], quota

# Weekly listing and video limits for free/starter users
FREE_WEEKLY_LISTING_LIMIT = 10
FREE_WEEKLY_VIDEO_LIMIT = 1

def get_week_start():
    now = timezone.now()
    # Monday is the start of the week
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)

def get_weekly_listing_usage(agente):
    from api.models import UsageLog
    week_start = get_week_start()
    return UsageLog.objects.filter(agent=agente, tipo='property', fecha__gte=week_start).count()

def get_weekly_listing_limit(agente):
    plan = get_plan_name(agente)
    if plan in STARTER_DAILY_LISTING_PLANS:
        return FREE_WEEKLY_LISTING_LIMIT
    return None

def get_weekly_listing_quota(agente):
    limit = get_weekly_listing_limit(agente)
    used = get_weekly_listing_usage(agente) if limit is not None else 0
    remaining = None if limit is None else max(0, limit - used)
    return {
        'applies': limit is not None,
        'plan': get_plan_name(agente),
        'used': used,
        'limit': limit,
        'remaining': remaining,
        'exhausted': bool(limit is not None and used >= limit),
        'window': 'week',
    }

def build_weekly_listing_limit_payload(agente):
    quota = get_weekly_listing_quota(agente)
    return {
        'error': 'weekly_listing_limit_reached',
        'code': 'weekly_listing_limit_reached',
        'mensaje': 'Alcanzaste el limite semanal de 10 listados del plan Starter.',
        'quota': quota,
        'usados': quota['used'],
        'limite': quota['limit'],
    }

def get_weekly_video_usage(agente):
    from api.models import UsageLog
    week_start = get_week_start()
    return UsageLog.objects.filter(agent=agente, tipo='video', fecha__gte=week_start).count()

def get_weekly_video_limit(agente):
    plan = get_plan_name(agente)
    if plan in STARTER_DAILY_LISTING_PLANS:
        return FREE_WEEKLY_VIDEO_LIMIT
    return None

def get_weekly_video_quota(agente):
    limit = get_weekly_video_limit(agente)
    used = get_weekly_video_usage(agente) if limit is not None else 0
    remaining = None if limit is None else max(0, limit - used)
    return {
        'applies': limit is not None,
        'plan': get_plan_name(agente),
        'used': used,
        'limit': limit,
        'remaining': remaining,
        'exhausted': bool(limit is not None and used >= limit),
        'window': 'week',
    }

def build_weekly_video_limit_payload(agente):
    quota = get_weekly_video_quota(agente)
    return {
        'error': 'weekly_video_limit_reached',
        'code': 'weekly_video_limit_reached',
        'mensaje': 'Alcanzaste el limite semanal de 1 video del plan Starter.',
        'quota': quota,
        'usados': quota['used'],
        'limite': quota['limit'],
    }


def has_pro_feature_access(agente):
    if getattr(agente, 'is_staff', False):
        return True
    return get_plan_name(agente) in PRO_FEATURE_PLANS

def get_pro_feature_block_payload(agente, feature='crm'):
    if has_pro_feature_access(agente):
        return None
    return {
        'code': 'crm_plan_required',
        'error': 'crm_plan_required',
        'message': 'Esta herramienta esta disponible desde el Plan Pro.',
        'required_plan': 'pro',
        'feature': feature,
    }

def get_free_trial_status(agente):
    now = timezone.now()
    started_at = getattr(agente, 'free_trial_started_at', None)
    ends_at = getattr(agente, 'free_trial_ends_at', None)
    has_trial = bool(ends_at)
    seconds_left = None
    expired = False

    if has_trial:
        seconds_left = max(0, int((ends_at - now).total_seconds()))
        expired = seconds_left <= 0
        if expired and getattr(agente, 'plan_activo', True):
            agente.plan_activo = False
            agente.save(update_fields=['plan_activo', 'updated_at'])

    return {
        'is_free_trial': has_trial,
        'trial_started_at': started_at,
        'trial_ends_at': ends_at,
        'trial_seconds_left': seconds_left,
        'trial_expired': expired,
    }

def get_plan_block_payload(agente):
    if not agente or not getattr(agente, 'is_authenticated', False):
        return None
    if getattr(agente, 'is_staff', False):
        return None

    trial = get_free_trial_status(agente)
    if trial['trial_expired']:
        return {
            'code': TRIAL_EXPIRED_CODE,
            'error': TRIAL_EXPIRED_CODE,
            'message': TRIAL_EXPIRED_MESSAGE,
            'trial_expired': True,
            'trial_ends_at': trial['trial_ends_at'],
            'contact_whatsapp': '+542324581770',
        }

    if not getattr(agente, 'plan_activo', True):
        return {
            'code': 'plan_inactive',
            'error': 'plan_inactive',
            'message': 'Tu plan no esta activo. Contactanos o compra un plan para seguir usando LeadBook.',
            'trial_expired': False,
            'contact_whatsapp': '+542324581770',
        }

    return None

def puede_generar(agente, tipo):
    from api.models import UsageLog
    limites = get_limites(agente)
    from django.utils import timezone
from datetime import timedelta
    ahora = timezone.now()
    
    if tipo == 'property':
        usado = UsageLog.objects.filter(
            agent=agente,
            tipo='property',
            fecha__year=ahora.year,
            fecha__month=ahora.month
        ).count()
        return usado < limites['properties']
    
    if tipo in ['ai', 'image', 'video']:
        limite_key = 'images' if tipo == 'image' else 'videos' if tipo == 'video' else 'ai'
        usado = UsageLog.objects.filter(
            agent=agente, 
            tipo=tipo, 
            fecha__year=ahora.year, 
            fecha__month=ahora.month
        ).count()
        return usado < limites[limite_key]
    
    return True

def incrementar_uso(agente, tipo):
    pass

def registrar_uso(agent, tipo):
    from api.models import UsageLog
    UsageLog.objects.create(agent=agent, tipo=tipo)

def _has_text(value):
    return isinstance(value, str) and bool(value.strip())

def _first_dict(*values):
    for value in values:
        if isinstance(value, dict):
            return value
    return {}

def _has_nonempty_sequence(value):
    return isinstance(value, (list, tuple)) and any(item for item in value)

def _has_served_content(format_id, value):
    if not isinstance(value, dict):
        return False

    if format_id == 'pdf':
        return _has_text(value.get('url')) or _has_text(value.get('pdf_url'))
    if format_id in {'post', 'story'}:
        return any(_has_text(value.get(key)) for key in ('url', 'image_url', 'secure_url'))
    if format_id == 'carrusel':
        return (
            _has_nonempty_sequence(value.get('slides'))
            or _has_nonempty_sequence(value.get('images'))
            or any(_has_text(value.get(key)) for key in ('url', 'image_url', 'secure_url'))
        )
    if format_id == 'email':
        return _has_text(value.get('html')) or _has_text(value.get('url'))
    return False

def listing_content_pack_ready(datos_extra):
    datos = datos_extra if isinstance(datos_extra, dict) else {}
    resultados = _first_dict(datos.get('resultados'))
    return all(_has_served_content(format_id, resultados.get(format_id)) for format_id in CONTENT_PACK_REQUIRED_FORMATS)

def registrar_uso_listado_si_completo(listado, *, generation_run_id=None):
    if not listado or not getattr(listado, 'pk', None):
        return False

    from django.db import transaction
    from api.models import Listado, UsageLog

    with transaction.atomic():
        locked = Listado.objects.select_for_update().select_related('agente').get(pk=listado.pk)
        datos_extra = locked.datos_extra if isinstance(locked.datos_extra, dict) else {}
        if datos_extra.get(PROPERTY_USAGE_COUNTED_AT_KEY):
            return False
        if not listing_content_pack_ready(datos_extra):
            return False

        UsageLog.objects.create(agent=locked.agente, tipo='property')
        datos_extra[PROPERTY_USAGE_COUNTED_AT_KEY] = timezone.now().isoformat()
        if generation_run_id:
            datos_extra[PROPERTY_USAGE_COUNTED_RUN_ID_KEY] = int(generation_run_id)
        locked.datos_extra = datos_extra
        locked.save(update_fields=['datos_extra'])
        return True
