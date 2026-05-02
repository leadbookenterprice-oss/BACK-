import requests
import base64
import json

base_url = "http://localhost:8000"

# 1x1 black png in base64
dummy_img = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

payload = {
    "operacion": "Venta",
    "tipoPropiedad": "Casa",
    "ciudad": "Miami",
    "precio": "500000",
    "portadaUrl": f"data:image/png;base64,{dummy_img}",
    "fotosRecorrido": [],
    "agenteNombre": "Juan",
    "agenciaNombre": "Agency"
}

def clean_output(resp):
    try:
        data = resp.json()
        if "url" in data and len(data["url"]) > 100:
            data["url"] = data["url"][:50] + "...(truncated)"
        return json.dumps(data, indent=2)
    except:
        return resp.text

print("Testing /api/generar-imagen-post/")
res = requests.post(f"{base_url}/api/generar-imagen-post/", json=payload)
print(f"Status: {res.status_code}")
print(clean_output(res))
print("-" * 50)

print("Testing /api/generar-imagen-story/")
res = requests.post(f"{base_url}/api/generar-imagen-story/", json=payload)
print(f"Status: {res.status_code}")
print(clean_output(res))
print("-" * 50)

print("Testing /api/generar-email/")
res = requests.post(f"{base_url}/api/generar-email/", json=payload)
print(f"Status: {res.status_code}")
print(clean_output(res))
print("-" * 50)

print("Testing /api/generar-pdf/")
res = requests.post(f"{base_url}/api/generar-pdf/", json=payload)
print(f"Status: {res.status_code}")
try:
    print(res.json())
except:
    print("Not JSON")
print("-" * 50)
