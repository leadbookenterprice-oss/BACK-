"""
Test directo de generar-guion usando Django ORM para el token.
Ejecutar: python test_guion_direct.py
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

import requests, time

EMAIL = 'charlysanmartin20@gmail.com'
PASSWORD = 'test123'
BASE = 'http://127.0.0.1:8000'

# Login HTTP real
print(f"Haciendo login con: {EMAIL}")
login_res = requests.post(f'{BASE}/api/auth/login/', json={'email': EMAIL, 'password': PASSWORD}, timeout=5)
print(f"LOGIN STATUS: {login_res.status_code}")
if login_res.status_code != 200:
    print(f"ERROR login: {login_res.text[:300]}")
    import sys; sys.exit(1)

token = login_res.json().get('access')
print(f"Token: {token[:40]}...")

headers = {'Authorization': f'Bearer {token}'}
body = {
    'tipoPropiedad': 'Casa',
    'ciudad': 'Mercedes Bs As',
    'precio': '90000',
    'moneda': 'USD',
    'operacion': 'Venta',
    'recamaras': '3',
    'banos': '2',
    'tipoVideo': 'reel'
}

print("\n--- TEST generar-guion ---")
t0 = time.time()
res = requests.post(
    'http://127.0.0.1:8000/api/generar-guion/',
    json=body,
    headers=headers,
    timeout=10
)
elapsed = round(time.time() - t0, 2)

print(f"STATUS : {res.status_code}")
print(f"TIEMPO : {elapsed} segundos")

try:
    data = res.json()
    escenas = data.get('escenas', [])
    print(f"ESCENAS: {len(escenas)}")
    for i, e in enumerate(escenas, 1):
        nombre = e.get('nombre', '?')
        icono  = e.get('icono', '')
        texto  = e.get('texto', '')[:75]
        print(f"  [{i}] {nombre} {icono}: {texto}...")

    print()
    ok_status  = res.status_code == 200
    ok_tiempo  = elapsed < 3
    ok_escenas = len(escenas) == 4

    if ok_status and ok_tiempo and ok_escenas:
        print("✅ TODAS LAS TAREAS OK: status=200, tiempo<3s, escenas=4")
    else:
        fallos = []
        if not ok_status:  fallos.append(f"status={res.status_code} (esperado 200)")
        if not ok_tiempo:  fallos.append(f"tiempo={elapsed}s (esperado <3s)")
        if not ok_escenas: fallos.append(f"escenas={len(escenas)} (esperado 4)")
        print("❌ FALLO:", " | ".join(fallos))

except Exception as ex:
    print(f"ERROR parseando response: {ex}")
    print(f"RAW: {res.text[:500]}")
