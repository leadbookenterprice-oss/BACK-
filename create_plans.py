import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subzero_core.settings')
django.setup()

from api.models import Agent, Plan, Suscripcion

# Creacion de planes
planes = [
    {
        "nombre": "starter",
        "precio_ars_mensual": 24000,
        "precio_ars_anual": 240000,
        "listados_por_mes": 20,
        "ai_generaciones": 50,
        "gemini_daily_limit": 1500,
        "elevenlabs_daily_limit": 1500,
        "uploadpost_daily_limit": 10,
        "video_generaciones": 0,
        "auto_posting": False,
        "voice_ai": False,
        "branding": False,
        "priority_support": False,
        "activo": True
    },
    {
        "nombre": "pro",
        "precio_ars_mensual": 55200,
        "precio_ars_anual": 552000,
        "listados_por_mes": 100,
        "ai_generaciones": 500,
        "gemini_daily_limit": 5000,
        "elevenlabs_daily_limit": 5000,
        "uploadpost_daily_limit": 50,
        "video_generaciones": 5,
        "auto_posting": True,
        "voice_ai": True,
        "branding": True,
        "priority_support": False,
        "activo": True
    },
    {
        "nombre": "scale",
        "precio_ars_mensual": 120000,
        "precio_ars_anual": 1200000,
        "listados_por_mes": 9999,
        "ai_generaciones": 9999,
        "gemini_daily_limit": 10000,
        "elevenlabs_daily_limit": 10000,
        "uploadpost_daily_limit": 999,
        "video_generaciones": 20,
        "auto_posting": True,
        "voice_ai": True,
        "branding": True,
        "priority_support": True,
        "activo": True
    },
    {
        "nombre": "business",
        "precio_ars_mensual": 240000,
        "precio_ars_anual": 2400000,
        "listados_por_mes": 99999,
        "ai_generaciones": 99999,
        "gemini_daily_limit": 50000,
        "elevenlabs_daily_limit": 50000,
        "uploadpost_daily_limit": 9999,
        "video_generaciones": 100,
        "auto_posting": True,
        "voice_ai": True,
        "branding": True,
        "priority_support": True,
        "activo": True
    }
]

for p in planes:
    nombre = p.pop('nombre')
    Plan.objects.update_or_create(nombre=nombre, defaults=p)

print("Planes actualizados en la base de datos exitosamente.")
