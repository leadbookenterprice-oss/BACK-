from google import genai
from django.conf import settings
from groq import Groq
import logging
import time
import requests
import os
from api.tracking import track_api_call

logger = logging.getLogger(__name__)

@track_api_call(service='gemini')
def call_gemini_api(prompt: str, agente=None, **kwargs) -> str:
    if agente is not None:
        try:
            from api.pool_manager import get_api_key
            key = get_api_key(agente, 'gemini') or settings.GEMINI_API_KEY
        except Exception:
            key = settings.GEMINI_API_KEY
    else:
        key = settings.GEMINI_API_KEY
    print(f"[DEBUG] Gemini Key: {key[:10] if key else 'N/A'}... | Model: gemini-2.0-flash-lite")
    client = genai.Client(api_key=key)
    system_prompt = kwargs.get('system_prompt', '')
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite',
        contents=full_prompt,
    )
    return response.text

def call_groq_api(prompt: str, **kwargs) -> str:
    """
    Llama a Groq. Usa modelos soportados (llama3-8b-8192 fue decomisionado).
    Permite override de modelo por kwargs['model'].
    """
    key = settings.GROQ_API_KEY or os.environ.get('GROQ_API_KEY', '')
    if not key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    client = Groq(api_key=key)
    system_prompt = kwargs.get('system_prompt', '')
    model = kwargs.get('model') or 'llama-3.1-8b-instant'

    # Lista de fallback para robustez ante deprecaciones
    modelos_fallback = [
        model,
        'llama-3.3-70b-versatile',
        'llama-3.1-8b-instant',
        'llama3-groq-8b-8192-tool-use-preview',
    ]
    vistos = set()
    last_err = None
    for mdl in modelos_fallback:
        if mdl in vistos:
            continue
        vistos.add(mdl)
        try:
            completion = client.chat.completions.create(
                model=mdl,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return completion.choices[0].message.content
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            # Si es model_decommissioned u otro error de modelo, probamos el siguiente
            if 'decommissioned' in msg or 'model' in msg:
                logger.warning(f"Groq model '{mdl}' falló: {e}. Probando siguiente.")
                continue
            raise
    raise RuntimeError(f"Groq sin modelos disponibles: {last_err}")

def smart_call(prompt: str, retries=3, agente=None, **kwargs) -> str:
    import os
    for attempt in range(retries):
        try:
            # Intenta Gemini primero
            if os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None):
                result = call_gemini_api(prompt, agente=agente, **kwargs)
                if result:
                    return result
        except Exception as e:
            print(f"Gemini attempt {attempt+1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(2)  # espera antes de reintentar
                continue
        
        try:
            # Intenta Groq si Gemini falla
            if os.environ.get('GROQ_API_KEY') or getattr(settings, 'GROQ_API_KEY', None):
                result = call_groq_api(prompt, **kwargs)
                if result:
                    return result
        except Exception as e:
            print(f"Groq attempt {attempt+1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
        
        break
    
    return None  # fallback local manejará esto

@track_api_call(service='elevenlabs')
def call_elevenlabs_api(text: str, agente=None, voz='femenina') -> bytes:
    """Genera audio MP3 usando ElevenLabs y el Pool de APIs."""
    if agente is not None:
        try:
            from api.pool_manager import get_api_key
            key = get_api_key(agente, 'elevenlabs') or getattr(settings, 'ELEVENLABS_API_KEY', '')
        except Exception:
            key = getattr(settings, 'ELEVENLABS_API_KEY', '')
    else:
        key = getattr(settings, 'ELEVENLABS_API_KEY', '')

    if not key:
        print("[ERROR] No hay ElevenLabs API Key disponible.")
        return None

    # Voice selection
    if voz == 'masculina':
        voice_id = "pNInz6obpgnuMvHLW6m8" # Daniel (Spanish)
    else:
        voice_id = "EXAVITQu4vr4xnSDxMaL" # Bella (Default Femenina)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return response.content
        else:
            print(f"[ERROR] ElevenLabs API failed ({response.status_code}): {response.text}")
            if agente and response.status_code in [401, 429]:
                 from api.pool_manager import marcar_agotada
                 marcar_agotada(agente, 'elevenlabs')
            return None
    except Exception as e:
        print(f"[ERROR] Exception in ElevenLabs call: {str(e)}")
        return None
