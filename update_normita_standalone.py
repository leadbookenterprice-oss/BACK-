import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent

user = Agent.objects.filter(email__icontains='normita').first()
if user:
    print('Usuario encontrado:', user.email)
    print('Plan actual:', user.plan_nombre)
    user.plan_nombre = 'free'
    user.plan_activo = True
    user.plan_seleccionado = True
    user.save()
    print('Plan actualizado a FREE')
else:
    print('Usuario no encontrado')
