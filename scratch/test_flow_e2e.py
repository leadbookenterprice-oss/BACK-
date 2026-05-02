"""
Test end-to-end del backend LeadBook:
- OTP send + verify
- Registro usando OTP
- Generación de guión y listado con Gemini/Groq
Corre con:
    python scratch/test_flow_e2e.py
"""
import os
import sys
import django
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "subzero_core.settings")
django.setup()

import json
from django.test import Client
from django.utils import timezone
from datetime import timedelta
from api.models import Agent, OTPCode


def banner(msg):
    print("\n" + "=" * 60)
    print(f"  {msg}")
    print("=" * 60)


def run():
    c = Client()

    email = "test_flow@leadbook.local"
    password = "MiPass123!Seguro"

    # Limpieza
    Agent.objects.filter(email=email).delete()
    OTPCode.objects.filter(email=email).delete()

    # === 1) Send OTP ===
    banner("1) POST /api/v1/auth/send-otp/")
    r = c.post("/api/v1/auth/send-otp/", data={"email": email}, content_type="application/json")
    print("Status:", r.status_code, "Body:", r.content.decode()[:200])
    assert r.status_code == 200, "send_otp falló"

    # Leemos el código generado desde DB (en real flow llega por email;
    # como usamos console backend para dev, lo sacamos de DB para testear)
    otp_row = OTPCode.objects.filter(email=email).order_by("-created_at").first()
    assert otp_row, "No se creó OTPCode"
    # Para el test, forzamos un código conocido
    test_code = "123456"
    otp_row.code_hash = OTPCode.hash_code(test_code)
    otp_row.verified = False
    otp_row.attempts = 0
    otp_row.expires_at = timezone.now() + timedelta(minutes=10)
    otp_row.save()
    print(f"OTP inyectado para test: {test_code}")

    # === 2) Verify OTP ===
    banner("2) POST /api/v1/auth/verify-otp/")
    r = c.post(
        "/api/v1/auth/verify-otp/",
        data={"email": email, "code": test_code},
        content_type="application/json",
    )
    print("Status:", r.status_code, "Body:", r.content.decode()[:200])
    assert r.status_code == 200, "verify_otp falló"

    # === 3) Register ===
    banner("3) POST /api/v1/auth/register/")
    payload = {
        "email": email,
        "password": password,
        "nombre": "Test Flow",
        "telefono": "+549111111111",
        "agencia": "LeadBook Test",
    }
    r = c.post("/api/v1/auth/register/", data=payload, content_type="application/json")
    print("Status:", r.status_code, "Body:", r.content.decode()[:200])
    assert r.status_code == 201, "Register falló"
    tokens = r.json()
    access = tokens["access"]
    print("Access token OK (len):", len(access))

    # === 4) Login ===
    banner("4) POST /api/v1/auth/login/")
    r = c.post(
        "/api/v1/auth/login/",
        data={"email": email, "password": password},
        content_type="application/json",
    )
    print("Status:", r.status_code, "Body:", r.content.decode()[:200])
    assert r.status_code == 200, "Login falló"

    # === 5) Generar guion (usa Gemini/Groq si hay keys, sino fallback local) ===
    banner("5) POST /api/v1/generar-guion/ (IA o fallback local)")
    r = c.post(
        "/api/v1/generar-guion/",
        data=json.dumps({
            "tipoVideo": "reel",
            "tipoPropiedad": "Departamento",
            "ciudad": "Buenos Aires",
            "operacion": "Venta",
            "moneda": "USD",
            "precio": "150000",
            "recamaras": "2",
            "banos": "1",
            "superficieCubierta": "65",
        }),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    print("Status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("Tipo video:", data.get("tipo_video"))
        print("Escenas:", len(data.get("escenas", [])))
        for i, esc in enumerate(data.get("escenas", [])[:2]):
            print(f"  - Escena {i+1}: {esc.get('nombre')} -> {esc.get('texto', '')[:80]}...")
    else:
        print("Body:", r.content.decode()[:300])

    # === 6) Generar listado (Groq) ===
    banner("6) POST /api/v1/generar-listado/ (Groq)")
    r = c.post(
        "/api/v1/generar-listado/",
        data=json.dumps({"prompt": "Depto 2 ambientes en Palermo a estrenar"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    print("Status:", r.status_code)
    if r.status_code == 200:
        txt = r.json().get("generated_text", "")
        print("Respuesta (primeros 200 chars):", (txt or "")[:200])
    else:
        print("Body:", r.content.decode()[:300])

    banner("TODO OK")


if __name__ == "__main__":
    run()
