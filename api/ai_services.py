from google import genai
from django.conf import settings
from groq import Groq
import logging
import time
import requests
import os
import random
import re
from api.tracking import track_api_call

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates_pdf')

TEMPLATE_COLORES = {
    'template_dubai_night.html': {
        'primario': '#1a0a2e',
        'secundario': '#2d1b4e', 
        'acento': '#c9a84c',
    },
    'template_beverly_hills.html': {
        'primario': '#2c3e50',
        'secundario': '#34495e',
        'acento': '#e8c547',
    },
    'template_manhattan.html': {
        'primario': '#111111',
        'secundario': '#1a1a1a',
        'acento': '#e63946',
    },
    'template_mediterraneo.html': {
        'primario': '#6b4423',
        'secundario': '#8b5e3c',
        'acento': '#c17f3a',
    },
    'template_tech_modern.html': {
        'primario': '#0d47a1',
        'secundario': '#1565c0',
        'acento': '#00e5ff',
    },
}

def generar_html_desde_template(context, agente):
    """
    Genera HTML usando un template prediseñado.
    Gemini solo elige los colores según el estilo de la propiedad.
    """
    print(f"[Template DEBUG] context keys: {list(context.keys())}")
    print(f"[Template DEBUG] portada_url raw: {repr(context.get('portada_url', 'NO EXISTE'))}")
    print(f"[Template DEBUG] portadaUrl raw: {repr(context.get('portadaUrl', 'NO EXISTE'))}")
    
    # 1. Elegir template al azar
    templates = list(TEMPLATE_COLORES.keys())
    template_elegido = random.choice(templates)
    
    # 2. Leer el template
    template_path = os.path.join(TEMPLATES_DIR, template_elegido)
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 3. Aplicar colores del template
    colores = TEMPLATE_COLORES[template_elegido]
    html = html.replace('{{COLOR_PRIMARIO}}', colores['primario'])
    html = html.replace('{{COLOR_SECUNDARIO}}', colores['secundario'])
    html = html.replace('{{COLOR_ACENTO}}', colores['acento'])
    
    # 4. Reemplazar datos de la propiedad
    html = html.replace('{{TITULO}}', str(context.get('tipo_propiedad', '') + ' en ' + context.get('ciudad', '')))
    precio_str = f"{context.get('moneda', '$')} {context.get('precio', '')}"
    html = html.replace('{{PRECIO}}', precio_str)
    html = html.replace('{{CIUDAD}}', str(context.get('ciudad', '')))
    html = html.replace('{{OPERACION}}', str(context.get('operacion', 'VENTA')).upper())
    html = html.replace('{{DESCRIPCION}}', str(context.get('descripcion', '')))
    html = html.replace('{{RECAMARAS}}', str(context.get('recamaras', 'N/A')))
    html = html.replace('{{BANOS}}', str(context.get('banos', 'N/A')))
    html = html.replace('{{SUPERFICIE_TOTAL}}', str(context.get('superficie_total', 'N/A')))
    html = html.replace('{{SUPERFICIE_CUBIERTA}}', str(context.get('superficie_cubierta', 'N/A')))
    html = html.replace('{{ESTACIONAMIENTOS}}', str(context.get('estacionamientos', 'N/A')))
    html = html.replace('{{AGENTE_NOMBRE}}', str(context.get('agente_nombre', '')))
    html = html.replace('{{AGENTE_TELEFONO}}', str(context.get('agente_telefono', '')))
    html = html.replace('{{AGENTE_EMAIL}}', str(context.get('agente_email', '')))
    html = html.replace('{{AGENCIA_NOMBRE}}', str(context.get('agencia_nombre', '')))
    
    # 5. Logo de agencia
    logo_url = context.get('logo_url_raw', '')
    if logo_url:
        html = html.replace('{{#if LOGO_AGENCIA}}', '')
        html = html.replace('{{/if}}', '')
        html = html.replace('{{LOGO_AGENCIA}}', logo_url)
    else:
        # Eliminar bloque condicional del logo, dejar solo el texto
        html = re.sub(r'\{\{#if LOGO_AGENCIA\}\}.*?\{\{else\}\}', '', html, flags=re.DOTALL)
        html = re.sub(r'\{\{/if\}\}', '', html)
    
    # 6. QR en base64 — CRÍTICO: reemplazar antes de cualquier otra cosa
    qr_code = context.get('qr_code', '')
    print(f"[Template] QR code presente: {bool(qr_code)}, largo: {len(str(qr_code))}")
    if qr_code:
        html = html.replace('{{#if QR_CODE}}', '')
        html = re.sub(r'\{\{/if\}\}', '', html)
        html = html.replace('{{QR_CODE}}', qr_code)
    else:
        html = re.sub(r'\{\{#if QR_CODE\}\}.*?\{\{/if\}\}', '', html, flags=re.DOTALL)
    
    # 7. Foto de portada
    portada_val = context.get('portada_url', '')
    if isinstance(portada_val, dict) and 'public_id' in portada_val:
        from api.services.almacenamiento import AlmacenamientoCloudinary
        portada_url = AlmacenamientoCloudinary.obtener_url_foto(portada_val)
    else:
        portada_url = str(portada_val)
        
    import re as re_module
    portada_url = re_module.sub(r's--[^/]+--/', '', portada_url)
    
    if not portada_url or not portada_url.startswith('http'):
        fotos = context.get('fotos_recorrido_raw', [])
        if fotos:
            primera = fotos[0]
            if isinstance(primera, dict):
                from api.services.almacenamiento import AlmacenamientoCloudinary
                portada_url = AlmacenamientoCloudinary.obtener_url_foto(primera)
                portada_url = re_module.sub(r's--[^/]+--/', '', portada_url)
            else:
                portada_url = str(primera)
                
    print(f"[Template] Portada URL: {portada_url[:80] if portada_url else 'VACÍA'}")
    html = html.replace('{{FOTO_PORTADA}}', portada_url)

    
    # 8. Fotos de galería
    fotos = context.get('fotos_recorrido_raw', [])
    galeria_html = ''
    for i, foto in enumerate(fotos):
        if isinstance(foto, dict) and 'public_id' in foto:
            from api.services.almacenamiento import AlmacenamientoCloudinary
            foto_url = AlmacenamientoCloudinary.obtener_url_foto(foto)
        else:
            foto_url = str(foto)
        if foto_url:
            galeria_html += f'<img class="galeria-foto" src="{foto_url}" alt="Foto {i+1}">\n'

    html = html.replace('{{GALERIA_FOTOS}}', galeria_html)
    
    # 9. Amenidades — generar chips HTML (ANTES DE LIMPIAR)
    amenidades = context.get('amenidades', [])
    print(f"[Template] Amenidades: {amenidades}")
    chips_html = ''.join([f'<span class="amenidad-chip">{a}</span>' for a in amenidades])
    html = html.replace('{{AMENIDADES}}', chips_html)

    # Limpiar cualquier placeholder restante
    html = re.sub(r'\{\{#if [^}]+\}\}', '', html)
    html = re.sub(r'\{\{else\}\}', '', html)
    html = re.sub(r'\{\{/if\}\}', '', html)
    html = re.sub(r'\{\{[^}]+\}\}', '', html)
    
    
    logger.info(f"[HTML Template] Template elegido: {template_elegido}. HTML generado: {len(html)} chars.")
    return html

# Cascada de modelos para generación de contenido premium (Paso 2)
GEMINI_MODELS_CASCADE = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
]

# Cascada Paso 1 — solo texto, rápidos
PASO1_CASCADE = [
    ("groq", "llama-3.3-70b-versatile"),
    ("nim", "moonshotai/kimi-k2-instruct"),
    ("nim", "qwen/qwen3-coder-480b-a35b-instruct"),
    ("nim", "mistralai/mistral-large-3-675b-instruct-2512"),
    ("gemini", "gemini-2.5-flash-lite"),  # último fallback
]

# Cascada Paso 2 — Prioridad Gemini, luego NIM, luego Groq
PASO2_CASCADE = [
    ("gemini", "gemini-2.5-pro"),
    ("gemini", "gemini-2.5-flash"),
    ("gemini", "gemini-3-flash-preview"),
    ("gemini", "gemini-3.1-flash-lite-preview"),
    ("gemini", "gemini-2.5-flash-lite"),
    ("nim", "meta/llama-4-maverick-17b-128e-instruct"),
    ("nim", "mistralai/mistral-large-3-675b-instruct-2512"),
    ("groq", "llama-3.3-70b-versatile"),
]

def _get_nvidia_key():
    from api.models import APIKey
    pool_key = APIKey.objects.filter(servicio='nvidia', status__in=['available', 'active']).first()
    if pool_key:
        return pool_key.api_key
    return settings.NVIDIA_API_KEY

def _get_groq_key():
    from api.models import APIKey
    pool_key = APIKey.objects.filter(servicio='groq', status__in=['available', 'active']).first()
    if pool_key:
        return pool_key.api_key
    return settings.GROQ_API_KEY


# Excepción especial para cuota mensual de Gemini agotada.
# Los views la capturan y devuelven HTTP 429 con mensaje canonico.
class GeminiQuotaExhaustedError(Exception):
    """Cuota mensual/diaria de Gemini agotada. No tiene solución con reintentos."""
    pass

@track_api_call(service='gemini')
def call_gemini_api(prompt: str, agente=None, **kwargs) -> str:
    if agente is not None:
        from api.pool_manager import get_api_key
        key = get_api_key(agente, 'gemini')
        if not key:
            raise Exception("No tienes una API Key de Gemini asignada en el Pool.")
    else:
        key = settings.GEMINI_API_KEY
    print(f"[DEBUG] Gemini Key: {key[:10] if key else 'N/A'}... | Model: gemini-2.5-flash-lite")
    client = genai.Client(api_key=key)
    system_prompt = kwargs.get('system_prompt', '')
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    def _call():
        return client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=full_prompt,
        ).text

    return execute_with_gemini_retry(agente, _call)

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

@track_api_call(service='groq')
def call_groq_html(prompt: str, system_prompt: str = "") -> str:
    """Llama a Groq para generar HTML. Solo texto, sin imágenes."""
    key = _get_groq_key()
    if not key:
        logger.error("No se encontró API Key para Groq")
        return None

    client = Groq(api_key=key)
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error en call_groq_html: {e}")
        return None

@track_api_call(service='nim')
def call_nim_model(prompt: str, model_id: str, imagen_url: str = None) -> str:
    """
    Llama a cualquier modelo de NVIDIA NIM.
    Si imagen_url está presente y el modelo es multimodal, la incluye.
    Endpoint: https://integrate.api.nvidia.com/v1/chat/completions
    """
    from openai import OpenAI
    
    # Obtener key de pool o settings
    key = _get_nvidia_key()
    if not key:
        raise Exception("No hay NVIDIA API Key disponible")
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key
    )
    
    # Modelos multimodales que soportan imágenes
    MULTIMODAL_MODELS = [
        "meta/llama-4-maverick-17b-128e-instruct",
        "microsoft/phi-4-multimodal-instruct", 
        "google/gemma-3-27b-it",
    ]
    
    if imagen_url and model_id in MULTIMODAL_MODELS:
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": imagen_url}}
            ]
        }]
    else:
        # Si el modelo no es multimodal pero tenemos imagen, la inyectamos como texto
        msg_content = prompt
        if imagen_url:
            msg_content = f"Foto de portada (URL): {imagen_url}\n\n{prompt}"
            
        messages = [{"role": "user", "content": msg_content}]
    
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        max_tokens=16384,
        temperature=0.7
    )
    return response.choices[0].message.content

def smart_call(prompt: str, retries=3, agente=None, **kwargs) -> str:
    import os
    import time
    for attempt in range(retries):
        try:
            # Intenta Gemini
            if os.environ.get('GEMINI_API_KEY') or getattr(settings, 'GEMINI_API_KEY', None) or agente is not None:
                result = call_gemini_api(prompt, agente=agente, **kwargs)
                if result:
                    return result
        except Exception as e:
            print(f"Gemini attempt {attempt+1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(2)  # espera antes de reintentar
                continue
        break
    
    return None  # fallback local manejará esto

@track_api_call(service='elevenlabs')
def call_elevenlabs_api(text: str, agente=None, voz='femenina') -> bytes:
    """Genera audio MP3 usando ElevenLabs y el Pool de APIs."""
    if agente is not None:
        from api.pool_manager import get_api_key
        key = get_api_key(agente, 'elevenlabs')
        if not key:
            print("[ERROR] No hay ElevenLabs API Key asignada para el usuario en el Pool.")
            return None
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
                 # Forzar cuota al maximo para que la UI marque 100% consumido
                 try:
                     from api.pool_manager import get_api_key
                     from api.models import APIKey
                     key_str = get_api_key(agente, 'elevenlabs')
                     if key_str:
                         k = APIKey.objects.filter(api_key=key_str).first()
                         if k:
                             k.status = 'exhausted'
                             k.requests_this_month = k.monthly_limit or 10000
                             k.save()
                 except Exception as e:
                     logger.error(f"Error marcando ElevenLabs como agotada: {e}")
                 raise Exception("Llegaste al límite mensual de tu API de Audio (ElevenLabs).")
            return None
    except Exception as e:
        print(f"[ERROR] Exception in ElevenLabs call: {str(e)}")
        return None


def _get_leadbook_watermark_b64():
    """Retorna el logo de LeadBook como data-URL base64 para embed en HTML."""
    import base64
    import os
    logo_path = os.path.join(os.path.dirname(__file__), 'leadbook_logo.png')
    try:
        with open(logo_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _mark_gemini_exhausted(agente, is_monthly=False):
    """Marca la key de Gemini del agente como agotada en la DB."""
    try:
        from api.pool_manager import get_api_key
        from api.models import APIKey
        key_str = get_api_key(agente, 'gemini')
        if key_str:
            k = APIKey.objects.filter(api_key=key_str).first()
            if k:
                k.status = 'exhausted'
                if is_monthly:
                    k.is_monthly_exhausted = True
                k.requests_this_month = k.monthly_limit or 1500
                k.save()
    except Exception as ex:
        logger.error(f"Error marcando Gemini como agotada: {ex}")

def execute_with_gemini_retry(agente, operation, max_retries=3):
    """
    Ejecuta una operación de Gemini con manejo inteligente de errores 429.
    Distingue entre rate limits por minuto y cuota mensual agotada.
    """
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except Exception as e:
            error_msg = str(e).lower()
            original_error_msg = str(e)
            
            if '429' in error_msg or 'quota' in error_msg or 'exhausted' in error_msg:
                # 1. Error mensual/diario (Agotamiento real)
                is_monthly = any(term in original_error_msg for term in [
                    'GenerateRequestsPerDayPerProjectPerModel',
                    'generate_content_free_tier_requests',
                    'limit: 0'
                ])
                
                # 2. Error por minuto (Rate limit)
                is_minute = any(term in original_error_msg for term in [
                    'GenerateContentInputTokensPerModelPerMinute',
                    'GenerateRequestsPerMinutePerProjectPerModel'
                ])
                
                if is_monthly or (not is_minute and '429' not in error_msg): 
                    # Es un agotamiento real de cuota mensual/diaria
                    if agente:
                        _mark_gemini_exhausted(agente, is_monthly=True)
                    raise GeminiQuotaExhaustedError(
                        "Alcanzaste el límite mensual de generación de contenido IA. "
                        "Tu cuota se renueva el próximo mes."
                    )
                    
                if is_minute or '429' in error_msg:
                    # Rate limit temporal por minuto
                    if attempt < max_retries:
                        logger.warning(f"Rate limit de Gemini alcanzado (intento {attempt + 1}/{max_retries}). Esperando 60s...")
                        time.sleep(60)
                        continue
                    else:
                        logger.error("Rate limit de Gemini persistente tras 3 reintentos. Abortando sin marcar agotada.")
                        raise Exception("Servidor de IA ocupado. Por favor, intentá nuevamente en unos minutos.")
            
            # Si no es un error relacionado a cuotas/rate limit, lanzar de inmediato
            raise e


def generar_html_gemini(context, agente):
    """
    Genera una ficha HTML inmobiliaria en DOS pasos:
      Paso 1 - gemini-2.5-flash-lite: genera un prompt creativo de diseño (sin imágenes)
      Paso 2 - Cascada de modelos (2.5 Pro -> 2.5 Flash -> 3 Flash -> ...): genera el HTML final
    """
    import base64
    from google.genai import types
    from django.conf import settings
    from google import genai
    import random

    import time
    print(f"[HTML] ▶ Función iniciada. Usuario: {agente}")
    print(f"[HTML] ▶ Obteniendo API key...")

    try:
        if agente is not None:
            from api.pool_manager import get_api_key
            key = get_api_key(agente, 'gemini')
            if not key:
                logger.error("No hay API Key de Gemini asignada para este usuario en el Pool.")
                return None
        else:
            key = settings.GEMINI_API_KEY
            
        print(f"[HTML] ✅ API key obtenida: {key[:12]}...")

        client = genai.Client(api_key=key)

        # ─── PASO 1: Generar prompt creativo de diseño ───────────────────────────
        # Variantes de estilo para que cada ficha sea visualmente distinta
        style_seeds = [
            "Elegante y minimalista de la Quinta Avenida: tipografía serif editorial para títulos (Playfair Display), mucho espacio negativo, paleta de blancos rotos y carbón, acentos en oro champán.",
            "Modernismo radical de Beverly Hills: tipografía sans-serif geométrica (Montserrat 900), contrastes de alto impacto, secciones con bordes nítidos, paleta monocromática con un color de acento vibrante.",
            "Lujo nocturno de Dubái: fondo deep dark (#0f0f0f), acentos dorados brillantes y bronce, tipografía serif clásica premium (Cinzel), glassmorphism intenso con desenfoque de fondo en todas las cards.",
            "Residencial mediterráneo de la Costa Brava: paleta de colores terracota, arena y azul profundo, tipografía humanista (Lora), sombras suaves y orgánicas, texturas visuales limpias.",
            "Penthouse urbano de Manhattan: tipografía condensada industrial (Bebas Neue), secciones con cortes diagonales dinámicos, paleta de grises metálicos y azul medianoche, estética tecnológica.",
            "Editorial tipo Vogue Real Estate: layout de revista de alta gama, tipografía Bodoni para títulos, interlineado amplio, paleta pastel sofisticada con acentos negros profundos.",
            "Arquitectura contemporánea nórdica: estilo Zen, tipografía Inter con pesos variables, glassmorphism sutil, paleta de maderas claras, grises suaves y blanco nórdico.",
            "Hacienda de lujo mexicana: paleta orgánica (arcilla, bosque, piedra), tipografía serif robusta, iconos artesanales, sombras profundas y layout cálido pero estructurado.",
        ]
        style_hint = random.choice(style_seeds)

        tipo = context.get('tipo_propiedad', 'propiedad')
        operacion = context.get('operacion', 'venta')
        precio = context.get('precio', '')
        moneda = context.get('moneda', 'USD')
        ciudad = context.get('ciudad', '')
        amenidades = ', '.join(context.get('amenidades', [])[:10])
        agente_nombre = context.get('agente_nombre', '')
        agencia_nombre = context.get('agencia_nombre', '')

        prompt_step1 = f"""Sos un director de arte de una agencia de branding de lujo y real estate premium.
        
Tu tarea es generar un PROMPT DE DISEÑO DETALLADO, creativo y técnico para que un desarrollador frontend senior genere el HTML de una landing page inmobiliaria de alto nivel.
El estilo base de esta ficha debe ser: {style_hint} (PERO EXPANDE ESTO CON MUCHO MÁS DETALLE VISUAL Y LUJO).

DATOS DE LA PROPIEDAD:
- Tipo: {tipo} en {operacion}
- Precio: {moneda} {precio}
- Ubicación: {ciudad}
- Amenidades: {amenidades}
- Agencia: {agencia_nombre} | Agente: {agente_nombre}

El prompt que generes debe especificar obligatoriamente:
1. TIPOGRAFÍA (Google Fonts): Elegí una fuente para Títulos (Display/Serif/Sans-Bold) y otra para el Cuerpo de texto. Especificá los 'font-weight' exactos (ej: 300, 700, 900).
2. PALETA DE COLORES (Hex): Definí color Principal, Secundario, Acento (gold, emerald, deep blue, etc), Fondo (no uses blanco puro, buscá off-white o dark mode premium), Texto y Gradientes cinematográficos.
3. EFECTOS VISUALES: Especificá el uso de 'backdrop-filter: blur' para glassmorphism, sombras 'box-shadow' multi-capa, bordes sutiles y overlays oscuros con degradado para legibilidad sobre imágenes.
4. ANIMACIONES CSS: Instruí sobre animaciones de entrada 'fade-in-up', transiciones 'ease-in-out' de 0.3s y efectos hover vivos en botones y chips.
5. DISEÑO DE SECCIONES: Describí cómo deben integrarse visualmente el Hero, la barra de Stats (en bloque sólido o minimalista), las Amenidades (como chips de diseño) y la Galería.

Devolvé SOLO el prompt de diseño técnico (texto plano, sin markdown, sin introducciones). El resultado debe ser una hoja de ruta visual para un programador."""

        print(f"[HTML] ▶ Paso 1 - Armando prompt de diseño...")
        print(f"[HTML] ▶ Paso 1 - Datos enviados: tipo={context.get('tipo_propiedad')}, ciudad={context.get('ciudad')}, amenidades={len(context.get('amenidades', []))} items")
        t1 = time.time()
        
        design_prompt = None
        for provider, model_id in PASO1_CASCADE:
            try:
                print(f"[HTML] ▶ Paso 1 - Intentando con {provider} ({model_id})...")
                if provider == "groq":
                    design_prompt = call_groq_html(prompt_step1)
                elif provider == "nim":
                    design_prompt = call_nim_model(prompt_step1, model_id)
                elif provider == "gemini":
                    def _call_step1():
                        return client.models.generate_content(
                            model=model_id,
                            contents=prompt_step1,
                        ).text.strip()
                    design_prompt = execute_with_gemini_retry(agente, _call_step1)
                
                if design_prompt:
                    print(f"[HTML] ✅ Paso 1 exitoso con {provider} ({model_id})")
                    break
            except Exception as e:
                error_msg = str(e).lower()
                logger.warning(f"[HTML] ⚠️ Paso 1 - {provider} ({model_id}) falló: {e}")
                if "per minute" in error_msg:
                    print(f"[HTML] ⏳ Rate limit por minuto. Esperando 60s...")
                    time.sleep(60)
                continue

        if not design_prompt:
            logger.error("Paso 1 falló con todos los modelos de la cascada.")
            return None

        print(f"[HTML] ✅ Paso 1 finalizado en {time.time()-t1:.2f}s. Largo del prompt: {len(design_prompt)} chars")

        # ─── PASO 2: Generar HTML final ──────────────────────────────────────────
        contents_step2 = []
        portada_url = context.get('portada_url')
        
        # Obtenemos la imagen de portada para Gemini
        try:
            # Si la portada ya es base64, la usamos. Si no, Gemini en el paso 2 la ignorará 
            # (ya que los modelos NIM usan la URL directamente vía call_nim_model)
            if portada_url and (portada_url.startswith('data:image') or portada_url.startswith('https://')):
                # Nota: Si es HTTPS, los modelos NIM la procesan nativamente. 
                # Para Gemini, solo adjuntamos si podemos decodificarla (base64)
                if portada_url.startswith('data:image'):
                    contents_step2.append(types.Part.from_bytes(
                        data=base64.b64decode(portada_url.split(',')[1]),
                        mime_type="image/png"
                    ))
                    print(f"[HTML] ▶ Paso 2 - Imagen de portada (base64) adjunta para Gemini.")
                else:
                    print(f"[HTML] ▶ Paso 2 - Imagen de portada (URL) disponible para modelos NIM.")
        except Exception as e:
            print(f"[HTML] ⚠️ Error procesando imagen de portada para el prompt: {e}")

        # QR embed
        qr_code = context.get('qr_code', '')
        qr_img_tag = f'<img src="data:image/png;base64,{qr_code}" style="width:80px;height:80px;" alt="QR WhatsApp">' if qr_code else ''
        
        # URLs crudas (evitar enviar base64 enorme en el prompt de texto)
        logo_url_str = context.get('agencia_logo_url', '') or context.get('logo_url', '')
        watermark_html = context.get('watermark_html', '')

        fotos_recorrido = context.get('fotos_recorrido_raw', [])
        fotos_limpias = [f for f in fotos_recorrido if not f.startswith('data:')]
        fotos_galeria_str = "\n".join(fotos_limpias[:5])

        prompt_step2 = f"""CRÍTICO: GENERÁ EL HTML COMPLETO DE ARRIBA HACIA ABAJO SIN OMITIR NINGUNA SECCIÓN. 
EL ORDEN ES OBLIGATORIO: 1)head+CSS 2)top-bar 3)hero 4)precio 5)stats 6)descripción 7)amenidades 8)galería 9)footer.
NUNCA CORTES EL HTML A MITAD. SI NO PODÉS COMPLETAR UNA SECCIÓN, DEJÁ UN PLACEHOLDER PERO NO LA OMITAS.

Sos un desarrollador frontend senior especializado en landing pages inmobiliarias de lujo. Tu objetivo es convertir el siguiente prompt de diseño en un sitio web perfecto.

DISEÑO A IMPLEMENTAR (seguilo ESTRICTAMENTE):
{design_prompt}

DATOS DE LA PROPIEDAD:
- Tipo: {context.get('tipo_propiedad')}
- Operación: {context.get('operacion')}
- Precio: {context.get('moneda')} {context.get('precio')}
- Ciudad/Ubicación: {context.get('ciudad')}
- Recámaras: {context.get('recamaras', 'N/A')}
- Baños: {context.get('banos', 'N/A')}
- Superficie Cubierta: {context.get('superficie_cubierta', 'N/A')}
- Superficie Total: {context.get('superficie_total', 'N/A')}
- Estacionamientos: {context.get('estacionamientos', 'N/A')}

DESCRIPCIÓN:
{context.get('descripcion', '')}

AMENIDADES: {', '.join(context.get('amenidades', []))}

DATOS DEL AGENTE:
- Nombre: {context.get('agente_nombre', '')} | Agencia: {context.get('agencia_nombre', '')}
- Teléfono: {context.get('agente_telefono', '')} | Email: {context.get('agente_email', '')}

IMÁGENES:
- Portada: La imagen adjunta binaria o URL es la FOTO DE PORTADA y DEBE ser usada exclusivamente en el Hero Section como imagen de fondo. No uses ninguna URL de galería para el hero.
- Logo Agencia: {logo_url_str if logo_url_str else 'No disponible — omitir sección de logo'}
- Galería (URLs):
{fotos_galeria_str}

GUÍA DE SECCIONES PREMIUM:
1. TOP BAR: Logo alineado, diseño minimalista, sticky.
2. HERO: Altura 500px, centrada, con un gradiente oscuro cinematográfico (bottom-to-top). Título de la propiedad impactante en tipografía Display grande. Badge de operación en color acento. La imagen de fondo DEBE ser la portada.
3. PRECIO: Superpuesto elegantemente sobre el gradiente del hero o en una transición inmediata.
4. STATS BAR: Fondo de color sólido (oscuro o acento). 5 columnas con ICONOS SVG INLINE únicos (house, bed, bath, ruler, car). Números en bold grande, etiquetas en uppercase pequeño.
5. DESCRIPCIÓN: Fondo off-white sutil. Usá comillas decorativas gigantes (opacity 0.1) en color acento al inicio. Interlineado de 1.8 para máxima legibilidad.
6. AMENIDADES: Layout flex-wrap. Chips con bordes redondeados, hover animation (scale 1.05) e ICONOS SVG lógicos para cada una.
7. GALERÍA: Layout de 1 columna (full width). Cada imagen debe ocupar el 100% del ancho disponible con una altura mínima de 400px. Bordes redondeados (12px), box-shadow suave y hover effect de zoom sutil.
8. FOOTER: Fondo oscuro. Avatar del agente circular con borde acento. Botones de contacto funcionales: WhatsApp (https://wa.me/{str(context.get('agente_telefono', '')).replace(' ', '').replace('+', '').replace('-', '')}) y Email (mailto:{context.get('agente_email', '')}). Ambos deben abrirse en nueva pestaña (target="_blank"). QR Code ({qr_img_tag}) bien posicionado. Marca de agua LeadBook: {watermark_html}

REGLAS TÉCNICAS:
- CSS en <style> dentro del <head>.
- Usá variables CSS (:root) para los colores del diseño.
- Importá las Google Fonts especificadas.
- Incluí keyframes para una animación 'fade-in-up' al cargar la página.
- DEVOLVÉ SOLO EL CÓDIGO HTML PURO, sin backticks ni markdown."""

        contents_step2.append(prompt_step2)

        # Prompt alternativo mucho más detallado y estricto para modelos NIM y Groq
        datos_propiedad = f"""
- Tipo: {context.get('tipo_propiedad')}
- Operación: {context.get('operacion')}
- Precio: {context.get('moneda')} {context.get('precio')}
- Ciudad/Ubicación: {context.get('ciudad')}
- Recámaras: {context.get('recamaras', 'N/A')}
- Baños: {context.get('banos', 'N/A')}
- Superficie Cubierta: {context.get('superficie_cubierta', 'N/A')}
- Superficie Total: {context.get('superficie_total', 'N/A')}
- Estacionamientos: {context.get('estacionamientos', 'N/A')}
- Amenidades: {', '.join(context.get('amenidades', []))}
- Descripción: {context.get('descripcion', '')}
- Agente: {context.get('agente_nombre', '')} | {context.get('agente_email', '')} | {context.get('agente_telefono', '')}
- Agencia: {context.get('agencia_nombre', '')}
"""
        
        prompt_step2_nim = f"""Sos un desarrollador frontend senior especializado en sitios inmobiliarios de lujo. 
Tu única tarea es generar código HTML completo, válido y autónomo para una ficha inmobiliaria premium.

CRÍTICO — LEÉ ESTO ANTES DE GENERAR:
- Generá el HTML COMPLETO de arriba hacia abajo sin omitir NINGUNA sección
- El orden es OBLIGATORIO: 1)head+CSS completo 2)top-bar 3)hero con foto 4)precio 5)stats 6)descripción 7)amenidades 8)galería 9)footer con datos agente
- NUNCA uses markdown, NUNCA uses backticks, NUNCA des explicaciones — solo HTML puro
- El CSS tiene que estar COMPLETO en el <head> con variables :root, Google Fonts, animaciones keyframes
- La foto de portada está disponible en esta URL: {portada_url} — usala como background-image del hero
- El hero tiene que tener height: 500px, fondo con la foto y un overlay oscuro degradado

DISEÑO A IMPLEMENTAR:
{design_prompt}

DATOS DE LA PROPIEDAD:
{datos_propiedad}

REGLAS DE DISEÑO PREMIUM:
- Hero: foto full-width 500px con gradiente oscuro cinematográfico bottom-to-top, título y precio superpuestos
- Stats bar: fondo oscuro, 5 columnas con SVG icons únicos, números grandes bold
- Amenidades: chips con hover animation, icons SVG inline
- Galería: cada foto 100% ancho, min-height 400px, border-radius 8px
- Footer: fondo oscuro, datos del agente, QR code
- Tipografía: Google Fonts según el diseño, mínimo 2 fuentes diferentes
- Colores: variables CSS en :root, gradientes en múltiples elementos"""

        print(f"[HTML] ▶ Paso 2 - Iniciando cascada de modelos...")
        t3 = time.time()
        
        html_output = None
        last_error = None
        
        for provider, model_id in PASO2_CASCADE:
            print(f"[HTML] ▶ Paso 2 - Intentando con {provider} ({model_id})...")
            try:
                if provider == "nim":
                    html_output = call_nim_model(prompt_step2_nim, model_id, imagen_url=portada_url)
                elif provider == "groq":
                    p2_modified = f"Foto de portada (URL): {portada_url}\n\n{prompt_step2_nim}"
                    html_output = call_groq_html(p2_modified)
                elif provider == "gemini":
                    def _call_step2():
                        return client.models.generate_content(
                            model=model_id,
                            contents=contents_step2,
                        ).text.strip()
                    html_output = execute_with_gemini_retry(agente, _call_step2)
                
                if html_output:
                    print(f"[HTML] ✅ Paso 2 exitoso con {provider} ({model_id})")
                    break
            except Exception as e:
                error_msg = str(e).lower()
                last_error = e
                logger.warning(f"[HTML] ⚠️ Paso 2 - {provider} ({model_id}) falló: {e}")
                if "per minute" in error_msg:
                    print(f"[HTML] ⏳ Rate limit por minuto. Esperando 60s...")
                    time.sleep(60)
                continue

        if not html_output:
            logger.error(f"Paso 2 falló con todos los modelos disponibles. Último error: {last_error}")
            return None
        
        print(f"[HTML] ✅ Paso 2 - Respuesta recibida en {time.time()-t3:.2f}s. Largo HTML: {len(html_output) if html_output else 0} chars")
        if html_output:
            print(f"[HTML] ▶ Paso 2 - Primeros 200 chars del HTML: {html_output[:200]}")

        # Limpiar posibles backticks si la IA desobedece
        if html_output.startswith('```html'):
            html_output = html_output[7:]
        if html_output.startswith('```'):
            html_output = html_output[3:]
        if html_output.endswith('```'):
            html_output = html_output[:-3]

        logger.info(f"[HTML Gen] Paso 2 completado. HTML generado ({len(html_output)} chars).")
        return html_output.strip()

    except Exception as e:
        print(f"[HTML] ❌ Error en generar_html_gemini: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # execute_with_gemini_retry ya manejó el 429 correctamente
        logger.error(f"Error en generar_html_gemini: {e}")
        return None
