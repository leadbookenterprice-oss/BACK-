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
                    # Es un agotamiento real
                    if agente:
                        _mark_gemini_exhausted(agente, is_monthly=True)
                    raise Exception("Llegaste al límite mensual de tu API de Inteligencia Artificial (Gemini).")
                    
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
      Paso 2 - gemini-2.5-flash: usa ese prompt + todas las imágenes para generar el HTML final
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
            "elegante y minimalista, tipografía serif para títulos, mucho espacio en blanco",
            "moderno y bold, tipografía sans-serif geométrica, contrastes fuertes y secciones coloreadas",
            "lujoso y oscuro, fondo oscuro con acentos dorados, tipografía display premium",
            "fresco y mediterráneo, colores tierra y crema, tipografía humanista",
            "urbano y dinámico, tipografía condensada, secciones con bordes diagonales",
            "clásico y confiable, layout tipo revista inmobiliaria, tipografía editorial",
            "tech y contemporáneo, glassmorphism sutil, tipografía Inter con pesos variables",
            "natural y sostenible, paleta verde-madera, tipografía orgánica redondeada",
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

        prompt_step1 = f"""Sos un director de arte especialista en fichas inmobiliarias digitales premium.

Tu tarea es generar un PROMPT DE DISEÑO DETALLADO y creativo para que otro modelo genere el HTML de una ficha inmobiliaria.
El estilo base de esta ficha debe ser: {style_hint}

DATOS DE LA PROPIEDAD:
- Tipo: {tipo} en {operacion}
- Precio: {moneda} {precio}
- Ubicación: {ciudad}
- Amenidades: {amenidades}
- Agencia: {agencia_nombre} | Agente: {agente_nombre}

El prompt debe especificar en detalle:
1. Fuentes de Google Fonts a usar (nombre exacto de la fuente para heading y para body)
2. Paleta de colores exacta (hex codes) — color principal, secundario, acento, fondo, texto
3. Cómo organizar las secciones (top bar, hero, precio, stats, descripción, amenidades, galería, footer)
4. Efectos visuales CSS específicos (gradientes, sombras, bordes, overlays)
5. Estilo de los chips de amenidades (bordes, colores, íconos)
6. Estilo del footer con datos del agente

Devolvé SOLO el prompt de diseño (texto plano, sin markdown, sin explicaciones adicionales).
Sé muy específico con los valores CSS y las fuentes exactas. El resultado debe ser único y diferente cada vez."""

        print(f"[HTML] ▶ Paso 1 - Armando prompt de diseño...")
        print(f"[HTML] ▶ Paso 1 - Datos enviados: tipo={context.get('tipo_propiedad')}, ciudad={context.get('ciudad')}, amenidades={len(context.get('amenidades', []))} items")
        t1 = time.time()
        
        print(f"[HTML] ▶ Paso 1 - Enviando request a gemini-2.5-flash-lite...")
        def _call_step1():
            return client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt_step1,
            ).text.strip()

        design_prompt = execute_with_gemini_retry(agente, _call_step1)
        
        print(f"[HTML] ✅ Paso 1 - Respuesta recibida en {time.time()-t1:.2f}s. Largo: {len(design_prompt) if design_prompt else 0} chars")
        if design_prompt:
            print(f"[HTML] ▶ Paso 1 - Primeros 100 chars: {design_prompt[:100]}")
        else:
            print(f"[HTML] ▶ Paso 1 falló - design_prompt vacío")
            
        logger.info(f"[HTML Gen] Paso 1 completado. Prompt creativo generado ({len(design_prompt)} chars).")

        # ─── PASO 2: Generar HTML final con imágenes ─────────────────────────────
        contents_step2 = []

        print(f"[HTML] ▶ Paso 2 - Preparando imágenes...")
        print(f"[HTML] ▶ Paso 2 - portada_url presente: {bool(context.get('portada_url'))}")
        
        # Helper para agregar imágenes base64 como partes nativas
        def add_image_part(data_url):
            if not data_url:
                return
            try:
                print(f"[HTML] ▶ Paso 2 - Descargando portada...")
                t2 = time.time()
                if data_url.startswith('data:'):
                    header, b64_data = data_url.split(',', 1)
                    mime = header.split(':')[1].split(';')[0]
                    raw_bytes = base64.b64decode(b64_data)
                    contents_step2.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime))
                    print(f"[HTML] ✅ Paso 2 - Portada decodificada (base64) en {time.time()-t2:.2f}s. Tamaño: {len(raw_bytes)} bytes")
                elif data_url.startswith('http'):
                    # URL remota: intentar descargar
                    import requests as req_lib
                    r = req_lib.get(data_url, timeout=8)
                    if r.status_code == 200:
                        mime = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
                        contents_step2.append(types.Part.from_bytes(data=r.content, mime_type=mime))
                        print(f"[HTML] ✅ Paso 2 - Portada descargada en {time.time()-t2:.2f}s. Tamaño: {len(r.content)} bytes")
            except Exception as img_err:
                logger.warning(f"No se pudo procesar imagen para Gemini: {img_err}")

        # Agregar imágenes en orden: SOLO portada va como imagen binaria nativa
        if context.get('portada_url'):
            add_image_part(context['portada_url'])

        # Preparar watermark LeadBook (texto puro para ahorrar tokens)
        watermark_html = '<div style="position:fixed;bottom:16px;right:16px;opacity:0.15;font-family:sans-serif;font-size:11px;color:#888;pointer-events:none;z-index:9999;">Generado con LeadBook</div>'

        # QR embed
        qr_code = context.get('qr_code', '')
        qr_img_tag = f'<img src="data:image/png;base64,{qr_code}" style="width:80px;height:80px;" alt="QR WhatsApp">' if qr_code else ''
        
        # URLs crudas (evitar enviar base64 enorme en el prompt de texto)
        logo_url_str = context.get('logo_url_raw', '')
        fotos_galeria_str = "\n".join(context.get('fotos_recorrido_raw', [])[:5])

        print(f"[DIAG] design_prompt: {len(design_prompt) if design_prompt else 0} chars")
        print(f"[DIAG] descripcion: {len(context.get('descripcion', ''))} chars")
        print(f"[DIAG] qr_img_tag: {len(qr_img_tag)} chars")
        print(f"[DIAG] logo_url_str: {len(logo_url_str)} chars")
        print(f"[DIAG] fotos_galeria_str: {len(fotos_galeria_str)} chars")
        print(f"[DIAG] portada_url tipo: {str(context.get('portada_url', ''))[:50]}")
        print(f"[DIAG] portada_url largo: {len(str(context.get('portada_url', '')))} chars")

        prompt_step2 = f"""Sos un desarrollador frontend experto. Generá un HTML puro y autónomo para una ficha inmobiliaria premium.

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

DESCRIPCIÓN (generada por IA, insertala tal cual):
{context.get('descripcion', '')}

AMENIDADES: {', '.join(context.get('amenidades', []))}

DATOS DEL AGENTE:
- Nombre: {context.get('agente_nombre', '')}
- Agencia: {context.get('agencia_nombre', '')}
- Teléfono: {context.get('agente_telefono', '')}
- Email: {context.get('agente_email', '')}

IMÁGENES Y MULTIMEDIA:
- Foto de portada: Está adjunta a este mensaje como un archivo binario nativo (la única imagen adjunta). Usala en el tag <img> del Hero Section usando la sintaxis de inline blob que provee Gemini.
- Logo de la agencia (URL): {logo_url_str}
- Fotos de la galería (URLs):
{fotos_galeria_str}

Para el logo y la galería, DEBES usar ESTRICTAMENTE las URLs proporcionadas arriba en el atributo `src` de las etiquetas <img> correspondientes. NO intentes inventar URLs ni usar la imagen adjunta para la galería.

ESTRUCTURA HTML REQUERIDA:
1. Top bar con logo de agencia + badge de operación (VENTA/ALQUILER)
2. Hero section: foto portada full-width (height 420px) con overlay degradado y título de propiedad + ciudad encima
3. Barra de precio destacada con el precio en tipografía grande
4. Barra de stats: recámaras, baños, superficie cubierta, superficie total, estacionamientos con íconos SVG inline
5. Sección descripción con fondo diferenciado
6. Sección amenidades: chips con íconos SVG inline mapeados lógicamente
7. Galería: primera foto full-width, el resto en grid 2 columnas
8. Footer: avatar circular del agente (primera imagen = logo agencia en circle), datos del agente, QR:
{qr_img_tag}
9. Marca de agua LeadBook (insertar esto exactamente en el body antes del cierre </body>):
{watermark_html}

REGLAS ESTRICTAS:
- DEVOLVER SOLO CÓDIGO HTML VÁLIDO, sin markdown, sin backticks, sin explicaciones.
- Todo CSS en <style> en el <head>.
- Incluir Google Fonts según el diseño especificado.
- El HTML debe ser 100% autónomo (sin archivos externos salvo Google Fonts).
- La ÚNICA imagen adjunta binaria es la foto de portada. Para el logo y la galería usá EXCLUSIVAMENTE las URLs proporcionadas en sus atributos src."""

        contents_step2.append(prompt_step2)

        print(f"[HTML] ▶ Paso 2 - Largo del prompt texto: {len(prompt_step2)} chars")
        print(f"[HTML] ▶ Paso 2 - Enviando request a gemini-2.5-flash-lite...")
        t3 = time.time()
        
        def _call_step2():
            return client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=contents_step2,
            ).text.strip()

        html_output = execute_with_gemini_retry(agente, _call_step2)
        
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
