import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent

email = 'admin@leadbook.io'
password = 'LeadBook2025!'

if not Agent.objects.filter(email=email).exists():
    admin = Agent.objects.create_superuser(email=email, password=password, nombre='Admin LeadBook')
    print(f"Superusuario creado: {admin.email} | is_staff={admin.is_staff} | is_superuser={admin.is_superuser}")
else:
    admin = Agent.objects.get(email=email)
    admin.is_staff = True
    admin.is_superuser = True
    admin.set_password(password)
    admin.save()
    print(f"Superusuario ya existía, credenciales actualizadas: {admin.email}")
