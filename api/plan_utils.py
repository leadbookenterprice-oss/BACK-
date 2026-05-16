from django.utils import timezone

LIMITES = {
    'free':     {'properties': 1200, 'ai': 1200, 'images': 1200, 'videos': 33, 'auto_posts': 10},
    'starter':  {'properties': 1200, 'ai': 1200, 'images': 1200, 'videos': 33, 'auto_posts': 10},
    'pro':      {'properties': 3600, 'ai': 3600, 'images': 3600, 'videos': 100, 'auto_posts': None},
    'scale':    {'properties': 999999, 'ai': 999999, 'images': 999999, 'videos': 165, 'auto_posts': None},
    'business': {'properties': 999999, 'ai': 999999, 'images': 999999, 'videos': 999999, 'auto_posts': None},
}

def get_limites(agente):
    plan = getattr(agente, 'plan_nombre', 'free') or 'free'
    return LIMITES.get(plan, LIMITES['free'])

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
