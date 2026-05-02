from django.utils import timezone

LIMITES = {
    'free':     {'properties': 10, 'ai': 20, 'images': 15, 'videos': 1},
    'starter':  {'properties': 40, 'ai': 80, 'images': 60, 'videos': 5},
    'pro':      {'properties': 150,'ai': 300,'images': 200,'videos': 20},
    'scale':    {'properties': 999999,'ai': 999999,'images': 999999,'videos': 60},
    'business': {'properties': 999999,'ai': 999999,'images': 999999,'videos': 999999},
}

def get_limites(agente):
    plan = getattr(agente, 'plan_nombre', 'free') or 'free'
    return LIMITES.get(plan, LIMITES['free'])

def puede_generar(agente, tipo):
    from api.models import Listado, UsageLog
    limites = get_limites(agente)
    from django.utils import timezone
    from datetime import timedelta
    ahora = timezone.now()
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    if tipo == 'property':
        usado = Listado.objects.filter(
            agente=agente, creado_en__gte=inicio_mes).count()
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
