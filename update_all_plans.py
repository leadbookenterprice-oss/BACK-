import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent

updated = Agent.objects.filter(plan_nombre__in=['pro', 'starter', 'premium']).update(
    plan_nombre='free',
    plan_activo=True,
    plan_seleccionado=True
)
print(f'Usuarios actualizados a free: {updated}')
