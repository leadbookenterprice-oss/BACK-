import os, sys, django, time, json
from django.test import RequestFactory

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
sys.path.insert(0, os.getcwd())
django.setup()

from api.views import generar_guion
from api.models import Agent

# Setup Request
user = Agent.objects.filter(is_active=True).first()
factory = RequestFactory()
data = {
    'tipoPropiedad': 'Casa', 
    'ciudad': 'Mercedes Bs As',
    'precio': '90000', 
    'moneda': 'USD', 
    'operacion': 'Venta',
    'recamaras': '3', 
    'banos': '2', 
    'tipoVideo': 'reel'
}

request = factory.post('/api/generar-guion/', data=data, content_type='application/json')
request.user = user

print(f"Testing internally with user: {user.email}")
t0 = time.time()
response = generar_guion(request)
elapsed = round(time.time() - t0, 3)

print("------------------------------------------------")
print(f"STATUS    : {response.status_code}")
print(f"TIEMPO    : {elapsed} segundos")
print(f"ESCENAS   : {len(response.data.get('escenas', []))}")
print(f"TIPO VIDEO: {response.data.get('tipo_video')}")
print("------------------------------------------------")

for i, scene in enumerate(response.data.get('escenas', []), 1):
    nombre = scene.get('nombre', '?')
    icono  = scene.get('icono', '')
    texto  = scene.get('texto', '')[:60]
    print(f"  [{i}] {nombre} ({icono}): {texto}...")

if response.status_code == 200 and elapsed < 2 and len(response.data.get('escenas', [])) == 4:
    print("\n✅ INTERNAL VERIFICATION PASSED: Response < 2s and exactly 4 scenes.")
else:
    print("\n❌ INTERNAL VERIFICATION FAILED: Review results above.")
