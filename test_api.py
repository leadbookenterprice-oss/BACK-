import requests
import json

def test_user(email, password):
    print(f"\n{'='*10} Probando: {email} {'='*10}")
    res = requests.post("http://127.0.0.1:8000/api/auth/login/", json={"email": email, "password": password})
    if res.status_code != 200:
        print(f"[ERROR Login] {res.status_code}: {res.text}")
        return
        
    token = res.json().get("access")
    headers = {"Authorization": f"Bearer {token}"}
    print("Login: [OK 200]")
    
    endpoints = [
        ("[PUT] Onboarding", "http://127.0.0.1:8000/api/auth/onboarding/", lambda: requests.put("http://127.0.0.1:8000/api/auth/onboarding/", json={"nombre_inmobiliaria":"Test","nicho":"inmobiliaria","pais":"Argentina"}, headers=headers)),
        ("[GET] Perfil", "http://127.0.0.1:8000/api/auth/perfil/", lambda: requests.get("http://127.0.0.1:8000/api/auth/perfil/", headers=headers)),
        ("[GET] Dashboard", "http://127.0.0.1:8000/api/dashboard/", lambda: requests.get("http://127.0.0.1:8000/api/dashboard/", headers=headers)),
        ("[GET] Admin Metricas", "http://127.0.0.1:8000/api/admin/metricas/", lambda: requests.get("http://127.0.0.1:8000/api/admin/metricas/", headers=headers)),
        ("[GET] Admin Usuarios", "http://127.0.0.1:8000/api/admin/usuarios/", lambda: requests.get("http://127.0.0.1:8000/api/admin/usuarios/", headers=headers)),
        ("[POST] Instagram", "http://127.0.0.1:8000/api/publicar-instagram/", lambda: requests.post("http://127.0.0.1:8000/api/publicar-instagram/", json={"imagen_url":"http://test.com/img.jpg","caption":"test","tipo":"post"}, headers=headers)),
        ("[GET] Video Status", "http://127.0.0.1:8000/api/video-status/1/", lambda: requests.get("http://127.0.0.1:8000/api/video-status/1/", headers=headers)),
    ]
    
    for name, url, func in endpoints:
        try:
            res = func()
            if len(res.text) > 300:
                 print(f"{name}: [{res.status_code}] OK (Payload size: {len(res.text)})")
            else:
                 print(f"{name}: [{res.status_code}] {res.text.strip()}")
        except Exception as e:
            print(f"{name}: [FAIL] {str(e)}")
            
test_user("Charlyadmin@gmail.com", "Elcharlesx143")
test_user("Atilioadmin@gmail.com", "Atiliusx4321")
