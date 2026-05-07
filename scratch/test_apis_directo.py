"""
Prueba directa de APIs externas (sin Django) para confirmar
que las keys cargadas en .env son válidas.
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "subzero_core.settings")

import django
django.setup()

from django.conf import settings
import requests


def banner(msg):
    print("\n" + "=" * 60)
    print(f"  {msg}")
    print("=" * 60)


banner("Keys cargadas desde .env")
print("GEMINI_API_KEY:     ", (settings.GEMINI_API_KEY[:12] + "...") if settings.GEMINI_API_KEY else "(vacío)")
print("GROQ_API_KEY:       ", (settings.GROQ_API_KEY[:12] + "...") if settings.GROQ_API_KEY else "(vacío)")
print("ELEVENLABS_API_KEY: ", (settings.ELEVENLABS_API_KEY[:12] + "...") if settings.ELEVENLABS_API_KEY else "(vacío)")
print("UPLOADPOST_API_KEY: ", (settings.UPLOADPOST_API_KEY[:12] + "...") if settings.UPLOADPOST_API_KEY else "(vacío)")
print("EMAIL_HOST_USER:    ", settings.EMAIL_HOST_USER or "(vacío)")
print("EMAIL_BACKEND:      ", settings.EMAIL_BACKEND)

# --- Gemini ---
banner("Gemini (gemini-2.5-flash-lite)")
try:
    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents='Respondé con "OK" si me estás leyendo.',
    )
    print("Respuesta:", resp.text[:100])
except Exception as e:
    print("ERROR:", type(e).__name__, e)

# --- Groq ---
banner("Groq (llama-3.1-8b-instant)")
try:
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    comp = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": 'Respondé "OK" si me lees.'}],
    )
    print("Respuesta:", comp.choices[0].message.content[:100])
except Exception as e:
    print("ERROR:", type(e).__name__, e)

# --- ElevenLabs (solo chequea la key con /v1/voices, no genera audio) ---
banner("ElevenLabs (GET /v1/voices)")
try:
    r = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
        timeout=15,
    )
    print("Status:", r.status_code)
    if r.status_code == 200:
        voices = r.json().get('voices', [])
        print(f"Voces disponibles: {len(voices)} (mostrando primeras 3)")
        for v in voices[:3]:
            print(f"  - {v.get('name')} ({v.get('voice_id')})")
    else:
        print("Body:", r.text[:200])
except Exception as e:
    print("ERROR:", type(e).__name__, e)

# --- Upload Post ---
banner("Upload Post (GET /api/uploadposts/users)")
try:
    r = requests.get(
        "https://api.upload-post.com/api/uploadposts/users",
        headers={"Authorization": f"Apikey {settings.UPLOADPOST_API_KEY}"},
        timeout=15,
    )
    print("Status:", r.status_code)
    print("Body (primeros 300 chars):", r.text[:300])
except Exception as e:
    print("ERROR:", type(e).__name__, e)

banner("FIN")
