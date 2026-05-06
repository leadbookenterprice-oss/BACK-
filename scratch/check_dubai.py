import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, Listado

email = 'bookingcharlyza@gmail.com'
user = Agent.objects.filter(email=email).first()

if not user:
    print(f"Error: User {email} not found")
else:
    print(f"User ID: {user.id}")
    listados = Listado.objects.filter(agente=user)
    print(f"Listados count: {listados.count()}")
    for l in listados:
        print("-" * 50)
        print(f"ID: {l.id}")
        print(f"Title: {l.titulo}")
        print(f"Tipo Propiedad: {l.tipo_propiedad}")
        print(f"Datos: {json.dumps(l.datos, indent=2)}")
        print(f"Video Status: {l.video_status}")
