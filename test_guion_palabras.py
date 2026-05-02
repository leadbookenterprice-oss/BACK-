import requests, json, time, sys

# Set encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

login = requests.post('http://127.0.0.1:8000/api/auth/login/', 
  json={'email': 'charlysanmartin20@gmail.com', 'password': 'test123'})
token = login.json().get('access')
h = {'Authorization': 'Bearer ' + token}

def contar_palabras(texto):
    return len(texto.split())

for tipo_video in ['reel', 'tour']:
    print(f"\n{'='*50}")
    print(f"TIPO VIDEO: {tipo_video.upper()}")
    print(f"{'='*50}")
    
    body = {
        'tipoPropiedad': 'Casa', 'ciudad': 'Palermo Buenos Aires',
        'precio': '180000', 'moneda': 'USD', 'operacion': 'Venta',
        'recamaras': '3', 'banos': '2', 'superficieCubierta': '120',
        'tipoVideo': tipo_video
    }
    
    t0 = time.time()
    res = requests.post('http://127.0.0.1:8000/api/generar-guion/', json=body, headers=h)
    elapsed = round(time.time()-t0, 2)
    
    data = res.json()
    escenas = data.get('escenas', [])
    total_palabras = 0
    
    for i, e in enumerate(escenas, 1):
        texto = e.get('texto', '')
        palabras = contar_palabras(texto)
        total_palabras += palabras
        # Print without emojis to avoid console issues if wrap fails
        nombre = e.get('nombre','')
        print(f"  [{i}] {nombre}: {palabras} palabras")
        print(f"      {texto[:100]}...")
    
    print(f"\n  TOTAL PALABRAS: {total_palabras}")
    print(f"  TIEMPO: {elapsed}s")
    rango = "100-150" if tipo_video == 'reel' else "200-300"
    print(f"  RANGO ESPERADO: {rango} palabras")
