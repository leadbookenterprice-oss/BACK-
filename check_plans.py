import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, Suscripcion, Plan

try:
    print(f"Total Agentes en DB: {Agent.objects.count()}")
    print(f"Total Suscripciones en DB: {Suscripcion.objects.count()}")
    print("\nTODOS LOS PLANES EN DB:")
    for p in Plan.objects.all():
        print(f" - {p.nombre.upper()} (ID: {p.id}): Mensual ARS {p.precio_ars_mensual} | Anual ARS {p.precio_ars_anual} | Listados: {p.listados_por_mes} | Video gens: {p.video_generaciones}")
except Exception as e:
    print(f"ERROR: {e}")
