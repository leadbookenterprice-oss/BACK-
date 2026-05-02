import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, Plan, Suscripcion

# Creacion de planes
planes = [
    { "nombre": "starter", "precio_usd": 0,   "properties_per_month": 10,  "ai_generations": 20,  "image_generations": 10, "video_generations": 0 },
    { "nombre": "pro",     "precio_usd": 29,  "properties_per_month": 50,  "ai_generations": 200, "image_generations": 100,"video_generations": 5, "branding": True },
    { "nombre": "premium", "precio_usd": 79,  "properties_per_month": 999, "ai_generations": 999, "image_generations": 500,"video_generations": 20, "auto_posting": True, "voice_ai": True, "branding": True, "priority_support": True },
]

for p in planes:
    nombre = p.pop('nombre')
    Plan.objects.update_or_create(nombre=nombre, defaults=p)

starter_plan = Plan.objects.get(nombre='starter')

# Asignar a agentes existentes
for agent in Agent.objects.all():
    if not agent.plan_nombre:
        agent.plan_nombre = 'starter'
        agent.save()
    Suscripcion.objects.get_or_create(agente=agent, defaults={'plan': starter_plan})

print("Planes actualizados y asignados exitosamente.")
