import requests, json, time, os, sys, django

# Setup Django for DB access
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
sys.path.insert(0, os.getcwd())
django.setup()

from api.models import Agent
from rest_framework_simplejwt.tokens import RefreshToken

# Get user and token
user = Agent.objects.filter(is_active=True).first()
if not user:
    print("NO USERS FOUND")
    exit(1)
    
token = str(RefreshToken.for_user(user).access_token)
h = {'Authorization': 'Bearer ' + token}
body = {
  'tipoPropiedad': 'Casa', 'ciudad': 'Mercedes Bs As',
  'precio': '90000', 'moneda': 'USD', 'operacion': 'Venta',
  'recamaras': '3', 'banos': '2', 'tipoVideo': 'reel'
}

print(f"Testing with user: {user.email}")
t0 = time.time()
try:
    res = requests.post('http://127.0.0.1:8000/api/generar-guion/', 
      json=body, headers=h, timeout=10)
    elapsed = round(time.time()-t0, 2)
    print('STATUS:', res.status_code)
    print('TIEMPO:', elapsed, 'seg')
    
    data = res.json()
    escenas = data.get('escenas', [])
    print('ESCENAS:', len(escenas))
    print('TIPO_VIDEO:', data.get('tipo_video'))
    
    if res.status_code == 200 and elapsed < 2 and len(escenas) == 4:
        print("\n✅ TEST PASSED: < 2s response and 4 scenes found.")
    else:
        print("\n❌ TEST FAILED: Check latency or scene count.")
        
except Exception as e:
    print('ERROR:', e)
