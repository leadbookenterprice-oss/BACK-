import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, Suscripcion, Plan

try:
    u = Agent.objects.get(email='charlysanmartin20@gmail.com')
    s = Suscripcion.objects.filter(agente=u).first()
    print(f"USUARIO: {u.email}")
    print(f"PLAN AGENTE (plan_nombre): {u.plan_nombre}")
    print(f"PLAN SUSCRIPCION (relación): {s.plan.nombre if s and s.plan else 'Sin plan'}")
    print(f"MP STATUS: {s.mp_status if s else 'Sin suscripcion'}")
    print(f"AI USED: {s.ai_used if s else '-'}")
    print("\nTODOS LOS PLANES EN DB:")
    for p in Plan.objects.all():
        print(f" - {p.nombre} (ID: {p.id}): {p.precio_usd} USD | Propiedades: {p.properties_per_month}")
except Exception as e:
    print(f"ERROR: {e}")
