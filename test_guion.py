import requests, json, time

login = requests.post('http://127.0.0.1:8000/api/auth/login/',
    json={'email': 'ooaipi4@gmail.com', 'password': 'test123'})
token = login.json().get('access')
print('LOGIN STATUS:', login.status_code)

h = {'Authorization': 'Bearer ' + token}
body = {
    'tipoPropiedad': 'Casa', 'ciudad': 'Mercedes Bs As',
    'precio': '90000', 'moneda': 'USD', 'operacion': 'Venta',
    'recamaras': '3', 'banos': '2', 'tipoVideo': 'reel'
}

t0 = time.time()
res = requests.post('http://127.0.0.1:8000/api/generar-guion/',
    json=body, headers=h)
elapsed = round(time.time() - t0, 2)

print('STATUS:', res.status_code)
print('TIEMPO:', elapsed, 'segundos')

try:
    data = res.json()
    escenas = data.get('escenas', [])
    print('ESCENAS:', len(escenas))
    for i, e in enumerate(escenas, 1):
        nombre = e.get('nombre', '?')
        icono  = e.get('icono', '')
        texto  = e.get('texto', '')[:70]
        print(f'  [{i}] {nombre} {icono}: {texto}...')
    print()
    ok_status  = res.status_code == 200
    ok_tiempo  = elapsed < 3
    ok_escenas = len(escenas) == 4
    if ok_status and ok_tiempo and ok_escenas:
        print('OK TODAS LAS TAREAS: status=200, tiempo<3s, escenas=4')
    else:
        print('FALLO:',
              '' if ok_status  else f'status={res.status_code}',
              '' if ok_tiempo  else f'tiempo={elapsed}s (>= 3)',
              '' if ok_escenas else f'escenas={len(escenas)} (esperado 4)')
except Exception as ex:
    print('ERROR parseando response:', ex)
    print('RAW:', res.text[:500])
