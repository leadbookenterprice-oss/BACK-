from django.utils import timezone

TRIAL_EXPIRED_CODE = 'trial_expired'
TRIAL_EXPIRED_MESSAGE = 'Tu prueba Starter expiro. Para seguir usando LeadBook, contactanos o compra un plan.'

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
