import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, Listado
from api.services.video_service import generar_video_listado

agent, created = Agent.objects.get_or_create(
    email="test_video_agent@test.com",
    defaults={"nombre": "Video Tester"}
)

listado = Listado.objects.create(
    agente=agent,
    titulo="Casa Espectacular",
    tipo_propiedad="Casa",
    ciudad="Miami",
    precio="500000",
    datos={
        "portadaUrl": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?ixlib=rb-4.0.3&w=1080&h=1920&fit=crop",
        "fotosRecorrido": [
            "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?ixlib=rb-4.0.3&w=1080&h=1920&fit=crop",
            "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?ixlib=rb-4.0.3&w=1080&h=1920&fit=crop"
        ]
    }
)

print(f"--- Prueba de Remotion ---")
print(f"Listado creado ID: {listado.id}. Renderizando...")
success = generar_video_listado(listado.id)

listado.refresh_from_db()
print(f"\n--- Resultados ---")
print(f"Exito del script local: {success}")
print(f"Status del Listado: {listado.video_status}")
print(f"URL del Listado: {listado.video_url}")
