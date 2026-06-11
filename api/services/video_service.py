import subprocess
import os
import json
import logging
import shutil
import glob
import time
import requests
import re
import random
from django.conf import settings
from decouple import config
from api.models import Listado

import cloudinary
import cloudinary.uploader
import cloudinary.api
from api.ai_services import call_elevenlabs_api, resolve_elevenlabs_voice_profile, smart_call
from api.services.almacenamiento import AlmacenamientoCloudinary
from api.services.video_quality_profile import get_video_profile, get_visual_theme

cloudinary.config( 
  cloud_name = config('CLOUDINARY_CLOUD_NAME', default=''), 
  api_key = config('CLOUDINARY_API_KEY', default=''), 
  api_secret = config('CLOUDINARY_API_SECRET', default='') 
)

def _cloudinary_ready():
    return bool(config('CLOUDINARY_CLOUD_NAME', default='').strip() and config('CLOUDINARY_API_KEY', default='').strip() and config('CLOUDINARY_API_SECRET', default='').strip())

def _normalize_video_type(value):
    raw = str(value or 'reel').strip().lower().replace(' ', '_')
    aliases = {
        'tour_narrado': 'tour',
        'tour-narrado': 'tour',
        'tour': 'tour',
        'reel_rapido': 'reel',
        'reel_rápido': 'reel',
        'reel-rápido': 'reel',
        'reel': 'reel',
    }
    return aliases.get(raw, 'tour' if 'tour' in raw else 'reel')

def _detect_ffmpeg_bin_dir():
    ffmpeg_bin = config('FFMPEG_BIN', default='').strip()
    if ffmpeg_bin and os.path.isdir(ffmpeg_bin):
        return ffmpeg_bin

    winget_root = os.path.join(
        os.environ.get('LOCALAPPDATA', ''),
        'Microsoft',
        'WinGet',
        'Packages',
        'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe',
    )
    pattern = os.path.join(winget_root, 'ffmpeg-*', 'bin')
    matches = sorted(glob.glob(pattern), reverse=True)
    if matches:
        return matches[0]
    return ''

def _call_elevenlabs_direct(text: str, voz='femenina', voice_id=None, voice_settings=None):
    key = config('ELEVENLABS_API_KEY', default='').strip() or getattr(settings, 'ELEVENLABS_API_KEY', '')
    if not key:
        return None

    _, filtered_candidates, resolved_voice_settings = resolve_elevenlabs_voice_profile(
        voz=voz,
        voice_id=voice_id,
        voice_settings=voice_settings,
    )
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key,
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": resolved_voice_settings,
    }
    for attempt in range(3):
        try:
            for voice_id in filtered_candidates:
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                response = requests.post(url, json=payload, headers={**headers, "Connection": "close"}, timeout=(20, 120))
                if response.status_code == 200:
                    return response.content
                if response.status_code == 404 and 'voice_not_found' in (response.text or ''):
                    continue
                logging.error(f"ElevenLabs direct fallback failed ({response.status_code}) attempt {attempt+1}: {response.text[:250]}")
        except Exception as e:
            logging.error(f"ElevenLabs direct fallback exception attempt {attempt+1}: {e}")
        time.sleep(1.2 * (attempt + 1))
    return None

def _prepare_tts_text(raw_text: str, is_tour: bool) -> str:
    text = (raw_text or '').strip()
    if not text:
        return ''

    # Limpieza básica para TTS
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('**', '').replace('"', '').strip()
    text = re.sub(r'\bUSD\b', 'dólares', text, flags=re.IGNORECASE)
    text = re.sub(r'\bUS\$\b', 'dólares', text, flags=re.IGNORECASE)
    text = re.sub(r'\bARS\b', 'pesos argentinos', text, flags=re.IGNORECASE)
    text = re.sub(r'\bMXN\b', 'pesos mexicanos', text, flags=re.IGNORECASE)
    text = re.sub(r'\bCLP\b', 'pesos chilenos', text, flags=re.IGNORECASE)
    text = re.sub(r'\bCOP\b', 'pesos colombianos', text, flags=re.IGNORECASE)
    text = re.sub(r'\bEUR\b', 'euros', text, flags=re.IGNORECASE)
    text = re.sub(r'\$', ' dólares ', text)
    text = re.sub(r'\bu\.?s\.?d\b', 'dólares', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdólares\s+dólares\b', 'dólares', text, flags=re.IGNORECASE)
    text = re.sub(r'\b1\s+baños\b', 'un baño', text, flags=re.IGNORECASE)
    text = re.sub(r'\b1\s+baño\b', 'un baño', text, flags=re.IGNORECASE)
    text = re.sub(r'\buna\s+baño\b', 'un baño', text, flags=re.IGNORECASE)
    text = re.sub(r'\b1\s+recámaras\b', 'una recámara', text, flags=re.IGNORECASE)
    text = re.sub(r'\b1\s+recámara\b', 'una recámara', text, flags=re.IGNORECASE)
    text = re.sub(r'\b1\s+habitaciones\b', 'una habitación', text, flags=re.IGNORECASE)
    text = re.sub(r'\b1\s+habitación\b', 'una habitación', text, flags=re.IGNORECASE)


    max_chars = 1500 if is_tour else 900
    if len(text) <= max_chars:
        return text

    # Recorte por oración para evitar cortes abruptos de API
    parts = re.split(r'(?<=[\.!?])\s+', text)
    acc = []
    total = 0
    for p in parts:
        if total + len(p) + 1 > max_chars:
            break
        acc.append(p)
        total += len(p) + 1

    if not acc:
        return text[:max_chars]
    return ' '.join(acc).strip()


def _to_int_price(price_raw):
    s = str(price_raw or '').strip()
    if not s:
        return None
    digits = ''.join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _num_to_es(n: int) -> str:
    units = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
    teens = ["diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve"]
    tens = ["", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
    hundreds = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos", "ochocientos", "novecientos"]

    def _lt100(x):
        if x < 10:
            return units[x]
        if 10 <= x < 20:
            return teens[x - 10]
        if 20 <= x < 30:
            return "veinte" if x == 20 else f"veinti{units[x - 20]}"
        d, u = divmod(x, 10)
        return tens[d] if u == 0 else f"{tens[d]} y {units[u]}"

    def _lt1000(x):
        if x < 100:
            return _lt100(x)
        if x == 100:
            return "cien"
        c, r = divmod(x, 100)
        return hundreds[c] if r == 0 else f"{hundreds[c]} {_lt100(r)}"

    if n < 1000:
        return _lt1000(n)
    if n < 1000000:
        m, r = divmod(n, 1000)
        mtxt = "mil" if m == 1 else f"{_lt1000(m)} mil"
        return mtxt if r == 0 else f"{mtxt} {_lt1000(r)}"
    return str(n)


def _format_price_for_voice(price_raw, moneda_raw):
    moneda = str(moneda_raw or '').strip().lower()
    n = _to_int_price(price_raw)
    if n is None:
        return str(price_raw or '').strip()

    if moneda in ['usd', 'us$', 'dolar', 'dólar', 'dolares', 'dólares']:
        currency_word = 'dólares'
    elif moneda in ['ars', 'peso', 'pesos']:
        currency_word = 'pesos argentinos'
    elif moneda in ['mxn']:
        currency_word = 'pesos mexicanos'
    elif moneda in ['clp']:
        currency_word = 'pesos chilenos'
    elif moneda in ['cop']:
        currency_word = 'pesos colombianos'
    elif moneda in ['eur', 'euro', 'euros']:
        currency_word = 'euros'
    else:
        currency_word = 'pesos'

    return f"{_num_to_es(n)} {currency_word}"


def _format_count(value, singular, plural):
    raw = str(value or '').strip()
    if not raw:
        return ''
    try:
        n = int(float(raw))
    except Exception:
        return ''
    if n == 1 and singular == 'baño':
        return 'un baño'
    if n == 1 and singular in ['recámara', 'habitación']:
        return f'una {singular}'
    return f"{n} {singular if n == 1 else plural}"


def _build_property_script(datos, listado, price_voice):
    tipo = str(datos.get('tipoPropiedad') or datos.get('tipo_propiedad') or listado.tipo_propiedad or 'propiedad')
    tipo_lower = tipo.lower()
    masculine_types = ['departamento', 'depto', 'apartamento', 'terreno', 'lote', 'local', 'duplex', 'dúplex', 'ph']
    feminine_types = ['casa', 'propiedad', 'oficina', 'unidad', 'quinta']
    article = 'este' if any(x in tipo_lower for x in masculine_types) else 'esta'
    if any(x in tipo_lower for x in feminine_types):
        article = 'esta'
    ciudad = str(datos.get('ciudad') or listado.ciudad or '').strip()
    operacion = str(datos.get('operacion') or 'venta').strip()
    rec = _format_count(datos.get('recamaras') or datos.get('habitaciones'), 'recámara', 'recámaras')
    banos = _format_count(datos.get('banos') or datos.get('bathrooms'), 'baño', 'baños')
    sup = str(datos.get('superficieCubierta') or datos.get('superficieConstruida') or datos.get('metros') or '').strip()

    features = [x for x in [rec, banos, f"{sup} metros cuadrados cubiertos" if sup else ''] if x]
    features_txt = ', '.join(features)
    variant = int(time.time()) % 3

    if variant == 0:
        return (
            f"Conocé {article} {tipo} en {operacion} en {ciudad}. "
            f"{features_txt + '. ' if features_txt else ''}"
            f"Una propuesta pensada para vivir cómodo, con buena distribución y potencial de valorización. "
            f"Precio {price_voice}. Coordiná una visita y descubrí si es la oportunidad que estabas buscando."
        )

    if variant == 1:
        return (
            f"{article.capitalize()} {tipo} en {ciudad} combina ubicación, funcionalidad y una excelente oportunidad comercial. "
            f"{features_txt + '. ' if features_txt else ''}"
            f"Ideal para quienes buscan un espacio listo para disfrutar o invertir con criterio. "
            f"Precio {price_voice}. Escribinos para recibir más información."
        )

    return (
        f"Si estás buscando una propiedad con buena proyección, {article} {tipo} en {ciudad} merece tu atención. "
        f"{features_txt + '. ' if features_txt else ''}"
        f"Una alternativa atractiva por ubicación, prestaciones y valor de mercado. "
        f"Precio {price_voice}. Contactanos y coordinamos una visita."
    )


def _sanitize_video_script(text, price_voice):
    cleaned = str(text or '')
    # Reemplaza frases de precio con abreviaturas o símbolos por una versión hablable única.
    cleaned = re.sub(
        r'precio\s*[:\-]?\s*(?:usd|ars|mxn|clp|cop|eur|us\$|\$)?\s*[\d\.,]+\s*(?:usd|ars|mxn|clp|cop|eur|dólares|dolares|pesos|euros)?',
        f'Precio {price_voice}',
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r'\b1\s+baños\b', 'un baño', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b1\s+baño\b', 'un baño', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\buna\s+baño\b', 'un baño', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b1\s+recámaras\b', 'una recámara', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b1\s+recámara\b', 'una recámara', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b1\s+habitaciones\b', 'una habitación', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b1\s+habitación\b', 'una habitación', cleaned, flags=re.IGNORECASE)
    return cleaned

def generar_video_listado(listado_id):
    try:
        listado = Listado.objects.get(id=listado_id)
        listado.video_status = 'processing'
        listado.save()
        
        # Paths
        engine_dir = os.path.join(settings.BASE_DIR, 'hyperframes_engine')
        output_filename = f"video_{listado.id}_{int(time.time())}.mp4"
        output_path = os.path.join(settings.MEDIA_ROOT, 'assets', output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Temp render directory
        render_dir = os.path.join(settings.MEDIA_ROOT, 'temp_render', str(listado.id))
        os.makedirs(render_dir, exist_ok=True)

        backend_url = config('BACKEND_URL', default='http://localhost:8000')

        def _absolute_media_url(url):
            if not url:
                return ''
            u = str(url).strip()
            if not u:
                return ''
            if u.startswith('http://') or u.startswith('https://'):
                return u
            if u.startswith('//'):
                return f"https:{u}"
            if u.startswith('/'):
                return f"{backend_url}{u}"
            return u

        def _existing_local_media_url(relative_path):
            rel = relative_path.replace('/', os.sep)
            full_path = os.path.join(settings.MEDIA_ROOT, rel)
            if os.path.exists(full_path):
                return f"{backend_url}/media/{relative_path}"
            return ''

        def _pick_local_music():
            music_dir = os.path.join(os.path.dirname(__file__), 'musica_videos')
            tracks = sorted(glob.glob(os.path.join(music_dir, '*.mp3')))
            if not tracks:
                return ''

            tone = str(datos.get('tono') or '').lower()
            if tone == 'energetico':
                preferred = [p for p in tracks if any(k in os.path.basename(p).lower() for k in ['snapshots', 'city', 'bonita', 'indigo'])]
            elif tone == 'lujo':
                preferred = [p for p in tracks if any(k in os.path.basename(p).lower() for k in ['elevated', 'selfless', 'phases'])]
            else:
                preferred = [p for p in tracks if any(k in os.path.basename(p).lower() for k in ['butterflies', 'galanthus', 'phases'])]

            return random.choice(preferred or tracks)
        
        datos = listado.datos
        
        # Assets logic from DB
        from api.models import VideoMusic, VideoSFX
        
        # MUSIC
        music_id = datos.get('music_id')
        music_obj = None
        if music_id:
            music_obj = VideoMusic.objects.filter(id=music_id, activo=True).first()
        if not music_obj:
            music_obj = VideoMusic.objects.filter(activo=True).order_by('?').first()
        
        music_url = _absolute_media_url(music_obj.archivo.url) if music_obj else _existing_local_media_url('assets/music/fondo.mp3')
        local_music_path = '' if music_url else _pick_local_music()
        
        # SFX: Swoosh
        sfx_swoosh = VideoSFX.objects.filter(tipo='swoosh', activo=True).order_by('?').first()
        sfx_swoosh_url = _absolute_media_url(sfx_swoosh.archivo.url) if sfx_swoosh else _existing_local_media_url('assets/sfx/EMP - Techno House Samples - Fx Swoosh 1.wav')
        
        # SFX: Impact
        sfx_impact = VideoSFX.objects.filter(tipo='impact', activo=True).order_by('?').first()
        sfx_impact_url = _absolute_media_url(sfx_impact.archivo.url) if sfx_impact else _existing_local_media_url('assets/sfx/CBE_Impact_150_02.wav')
        
        # SFX: Camera
        sfx_camera = VideoSFX.objects.filter(tipo='camera', activo=True).order_by('?').first()
        sfx_camera_url = _absolute_media_url(sfx_camera.archivo.url) if sfx_camera else _existing_local_media_url('assets/sfx/CameraShot.wav')

        escenas = datos.get('escenas', [])

        def _normalize_url(item):
            if isinstance(item, dict):
                resolved = AlmacenamientoCloudinary.obtener_url_foto(item)
                if resolved:
                    return resolved
                for key in ('url', 'secure_url', 'fotoUrl', 'foto_url'):
                    if item.get(key):
                        return str(item.get(key)).strip()
            if isinstance(item, str):
                return item.strip()
            return ''

        fotos_escenas = []
        if isinstance(escenas, list):
            for escena in escenas:
                if not isinstance(escena, dict):
                    continue
                foto_url = _normalize_url(escena.get('fotoUrl'))
                if foto_url:
                    fotos_escenas.append(foto_url)

        fotos_base = []
        portada = _normalize_url(datos.get('portadaUrl'))
        if portada:
            fotos_base.append(portada)
        for f in datos.get('fotosRecorrido', []) or []:
            u = _normalize_url(f)
            if u and u not in fotos_base:
                fotos_base.append(u)

        fotos = fotos_escenas or fotos_base
        fotos = [_absolute_media_url(f) for f in fotos if f]
        if not fotos:
            fotos = ["https://via.placeholder.com/1080x1920/111"]

        # --- VOICE OVER GENERATION ---
        audio_filename = f'audio_{listado.id}.mp3'
        audio_path = os.path.join(settings.MEDIA_ROOT, 'assets', audio_filename)
        
        tipo_video = _normalize_video_type(datos.get('tipoVideo') or datos.get('tipo_video') or 'reel')
        tipo_propiedad_raw = str(datos.get('tipoPropiedad') or datos.get('tipo_propiedad') or listado.tipo_propiedad or '').lower()
        is_land = any(x in tipo_propiedad_raw for x in ['terreno', 'lote', 'lot', 'land'])
        quality_profile = get_video_profile(tipo_video=tipo_video, is_land=is_land)
        voz_seleccionada = datos.get('voz', 'femenina').lower()
        tono_seleccionado = datos.get('tono', 'profesional')
        visual_theme = get_visual_theme(is_land=is_land, tone=tono_seleccionado)
        contexto_adicional = datos.get('contextoAdicional', '')
        is_tour = tipo_video == 'tour'
        
        # Parámetros según el estilo
        vo_duration = 0.0
        duracion_texto = "entre 45 y 60 segundos. Describí los ambientes con detalle y de forma inmersiva" if is_tour else "unos 15-20 segundos. Sé muy dinámico y enfocado en el hook"
        script_vo = ""
        voice_enabled = str(datos.get('voiceover', True)).strip().lower() not in {'false', '0', 'no', 'off'}
        silent_accepted = bool(
            datos.get('video_silent_accepted')
            or datos.get('voice_fallback_accepted')
            or datos.get('allow_silent_video')
        )
        
        try:
            superficie_terreno = (
                str(datos.get('superficieTerreno') or datos.get('superficieTotal') or datos.get('superficie') or '').strip()
            )
            moneda = str(datos.get('moneda') or listado.moneda or '').strip()
            price_voice = _format_price_for_voice(listado.precio, moneda)

            # SI EL USUARIO EDITÓ EL GUION EN EL PASO 5, USAR ESO Y NO REGENERAR
            if is_land:
                dim_text = f"Cuenta con una superficie aproximada de {superficie_terreno} metros cuadrados. " if superficie_terreno else ""
                if is_tour:
                    script_vo = (
                        f"Presentamos este terreno en {listado.ciudad}, una oportunidad para recorrer con calma y evaluar su potencial. "
                        f"{dim_text}"
                        f"Su ubicación, entorno y posibilidades de desarrollo lo convierten en una alternativa interesante para inversión o proyecto propio. "
                        f"El valor es {price_voice}. Contactanos para recibir más información y coordinar una visita al lugar."
                    )
                else:
                    script_vo = (
                        f"Presentamos este terreno en {listado.ciudad}, una excelente oportunidad de inversión. "
                        f"{dim_text}"
                        f"Ideal para desarrollo residencial o comercial, con gran potencial de valorización. "
                        f"Precio: {price_voice}. Contactanos para más información y coordinar una visita."
                    )
            elif escenas and isinstance(escenas, list) and len(escenas) > 0:
                script_vo = _build_property_script(datos, listado, price_voice)
            else:
                prompt_vo = f"""Escribí un guion persuasivo para un video sobre esta propiedad.
Tipo: {listado.tipo_propiedad} en {listado.ciudad}
Precio: {listado.precio}
Detalles: {listado.titulo}

El guion debe durar {duracion_texto}.
Tono de voz deseado: {tono_seleccionado}.
Enfoque especial solicitado por el usuario: {contexto_adicional}.

No incluyas preámbulos, solo el texto en español neutro."""
                
                script_vo = smart_call(prompt_vo, agente=listado.agente)
                if not script_vo:
                    script_vo = _build_property_script(datos, listado, price_voice)

            if script_vo and voice_enabled:
                script_vo = _sanitize_video_script(script_vo, price_voice)
                script_vo = _prepare_tts_text(script_vo, is_tour=is_tour)
                audio_bytes = call_elevenlabs_api(script_vo, agente=listado.agente, voz=voz_seleccionada)
                if not audio_bytes and config('ALLOW_GLOBAL_API_FALLBACK', default=False, cast=bool):
                    audio_bytes = _call_elevenlabs_direct(script_vo, voz=voz_seleccionada)
                if audio_bytes:
                    with open(audio_path, 'wb') as f_audio:
                        f_audio.write(audio_bytes)

                    # Fallback duration if Whisper/ffprobe is unavailable; prevents a 0s VO clip.
                    vo_duration = max(2.0, len(script_vo.split()) / 2.6)
                    
                    # Transcribe for word-level timing using Local Whisper
                    try:
                        import whisper
                        # Load the base model (downloads automatically if not cached)
                        model = whisper.load_model("base")
                        result = model.transcribe(audio_path, word_timestamps=True)
                        
                        words = []
                        for segment in result.get('segments', []):
                            for word_data in segment.get('words', []):
                                words.append({
                                    "word": word_data['word'].strip(),
                                    "start": word_data['start'],
                                    "end": word_data['end']
                                })
                                
                        transcript_path = audio_path.replace('.mp3', '.json')
                        with open(transcript_path, 'w', encoding='utf-8') as f:
                            json.dump(words, f)
                            
                        if words:
                            vo_duration = words[-1]['end'] + 0.5
                    except Exception as e:
                        logging.error(f"Local Whisper transcription failed: {e}")
                        # Fallback to dummy transcript if whisper fails
                        transcript_path = audio_path.replace('.mp3', '.json')
                        words_list = script_vo.split()
                        dummy_transcript = []
                        step = vo_duration / len(words_list) if words_list else 1
                        for i, w in enumerate(words_list):
                            dummy_transcript.append({
                                "word": w,
                                "start": i * step,
                                "end": (i + 1) * step
                            })
                        with open(transcript_path, 'w', encoding='utf-8') as f_dummy:
                            json.dump(dummy_transcript, f_dummy)
                else:
                    raise RuntimeError('ElevenLabs no devolvio audio')
        except Exception as e:
            logging.error(f"Voiceover/Transcription failed: {e}")
            if not silent_accepted:
                datos['video_provider'] = 'hyperframes'
                datos['video_voice_status'] = 'failed'
                datos['video_voice_error'] = str(e)[:500]
                datos['video_voice_requires_decision'] = True
                listado.datos = datos
                listado.video_status = 'voice_failed'
                listado.save(update_fields=['datos_extra', 'video_status', 'updated_at'])
                return False

        ffmpeg_bin_dir = _detect_ffmpeg_bin_dir()

        # --- VIDEO COMPOSITION LOGIC ---
        target_min_duration = quality_profile['min_duration']

        if is_tour:
            scene_duration = max(quality_profile['scene_min'], (target_min_duration - 2.0) / max(1, len(fotos)))
            first_overlap = quality_profile['first_overlap']
        else:
            scene_duration = max(quality_profile['scene_min'], (target_min_duration - 2.0) / max(1, len(fotos)))
            first_overlap = quality_profile['first_overlap']

        if len(fotos) <= 1:
            visual_duration = scene_duration + 2
        else:
            visual_duration = (scene_duration + first_overlap) + ((len(fotos) - 1) * scene_duration)

        total_duration = max(vo_duration + 2.0, visual_duration + 1.0, target_min_duration)
        total_duration = max(10.0, total_duration)
        cta_start = max(1.5, total_duration - 3.5)
        
        images_html = ""
        ken_burns_js = ""
        sfx_camera_html = ""
        cut_times = []
        
        for i, url in enumerate(fotos):
            if i == 0:
                start = 0.0
                duration = scene_duration + (first_overlap if len(fotos) > 1 else 0.5)
                track_index = 6
            elif i == 1:
                start = scene_duration - first_overlap
                duration = scene_duration
                track_index = 7
            else:
                start = (scene_duration - first_overlap) + ((i - 1) * scene_duration)
                duration = scene_duration
                track_index = 6

            if i == len(fotos) - 1:
                duration = max(duration, total_duration - start)

            start_str = f"{start:.3f}".rstrip('0').rstrip('.')
            duration_str = f"{duration:.3f}".rstrip('0').rstrip('.')
            images_html += f'<img id="img{i}" class="scene-img clip" data-start="{start_str}" data-duration="{duration_str}" data-track-index="{track_index}" src="{url}" />\n'
            zoom_scale = float(quality_profile['zoom_scale'])
            ken_burns_js += f'tl.fromTo("#img{i}", {{ scale: 1.000 }}, {{ scale: {zoom_scale:.3f}, duration: {duration_str}, ease: "none" }}, {start_str});\n'

            camera_volume = float(quality_profile['camera_sfx_volume'])
            if i > 0 and sfx_camera_url and camera_volume > 0:
                sfx_camera_html += f'<audio class="clip" data-start="{start_str}" data-duration="1" data-track-index="2" data-volume="{camera_volume}" src="{sfx_camera_url}"></audio>\n'
                cut_times.append(start_str)
            elif i > 0:
                cut_times.append(start_str)

        # Build Captions
        captions_html = ""
        words_js = ""
        if script_vo:
            token_list = [w for w in re.split(r'\s+', script_vo.replace('\n', ' ').strip()) if w]
            chunk_size = int(quality_profile['caption_chunk_size'])
            chunk_idx = 0
            start_base = 0.9
            usable = max(8.0, total_duration - 2.2)
            total_chunks = max(1, (len(token_list) + chunk_size - 1) // chunk_size)
            per_chunk = max(0.85, usable / total_chunks)

            for i in range(0, len(token_list), chunk_size):
                chunk = token_list[i:i + chunk_size]
                caption_text = ' '.join(chunk).upper().strip()
                if not caption_text:
                    continue

                extra_class = ""
                if any(x in caption_text for x in ["PESOS", "$", "USD", "DÓLARES"]):
                    extra_class = "price"
                elif len(caption_text) > 22:
                    extra_class = "gold"

                start_t = start_base + (chunk_idx * per_chunk)
                end_t = min(total_duration - 0.8, start_t + per_chunk * 0.92)
                if end_t <= start_t:
                    break

                captions_html += f'<div id="cg-{chunk_idx}" class="cap-word"><div class="cap-inner"><span class="cap-text {extra_class}">{caption_text}</span></div></div>\n'
                words_js += f'[{chunk_idx}, {start_t:.3f}, {end_t:.3f}],\n'
                chunk_idx += 1

        transcript_path = audio_path.replace('.mp3', '.json')
        if not words_js and os.path.exists(transcript_path):
            with open(transcript_path, 'r', encoding='utf-8') as f_trans:
                words = json.load(f_trans)
            chunk_size = 4
            chunk_idx = 0
            i = 0
            while i < len(words):
                chunk = words[i:i + chunk_size]
                tokens = []
                starts = []
                ends = []
                for w in chunk:
                    t = str(w.get('word', '')).strip()
                    if not t:
                        continue
                    tokens.append(t)
                    starts.append(float(w.get('start', 0.0)))
                    ends.append(float(w.get('end', 0.0)))

                if not tokens:
                    i += chunk_size
                    continue

                caption_text = ' '.join(tokens).upper()
                extra_class = ""
                if any(x in caption_text for x in ["PESOS", "$", "USD"]):
                    extra_class = "price"
                elif len(caption_text) > 22:
                    extra_class = "gold"

                start_t = max(0.0, min(starts) + 0.45)
                end_t = max(start_t + float(quality_profile['caption_min_duration']), max(ends) + 0.7)

                captions_html += f'<div id="cg-{chunk_idx}" class="cap-word"><div class="cap-inner"><span class="cap-text {extra_class}">{caption_text}</span></div></div>\n'
                words_js += f'[{chunk_idx}, {start_t:.3f}, {end_t:.3f}],\n'
                chunk_idx += 1
                i += chunk_size

        if not words_js and isinstance(escenas, list) and escenas:
            phrase_idx = 0
            t = 0.8
            usable_duration = max(6.0, total_duration - 2.0)
            scene_slot = usable_duration / max(1, len(escenas))
            for escena in escenas:
                if not isinstance(escena, dict):
                    continue
                raw_text = str(escena.get('texto', '')).strip()
                if not raw_text:
                    continue
                words = [w for w in raw_text.replace('\n', ' ').split(' ') if w.strip()]
                if not words:
                    continue
                per_word = max(0.32, min(0.75, scene_slot / max(2, len(words))))
                scene_end = min(total_duration - 0.8, t + scene_slot)
                for token in words[:14]:
                    clean = token.strip()
                    if not clean:
                        continue
                    if t + per_word > scene_end:
                        break
                    upper = clean.upper()
                    extra_class = ""
                    if any(x in upper for x in ["PESOS", "$", "USD"]):
                        extra_class = "price"
                    elif len(upper) > 8:
                        extra_class = "gold"
                    captions_html += f'<div id="cg-{phrase_idx}" class="cap-word"><div class="cap-inner"><span class="cap-text {extra_class}">{upper}</span></div></div>\n'
                    words_js += f'[{phrase_idx}, {t:.3f}, {(t + per_word):.3f}],\n'
                    t += per_word
                    phrase_idx += 1
                t = max(t + 0.18, scene_end)

        has_voiceover_file = os.path.exists(audio_path)
        local_audio_name = os.path.basename(audio_path)
        render_audio_path = os.path.join(render_dir, local_audio_name)
        if has_voiceover_file:
            shutil.copy2(audio_path, render_audio_path)

        # Music fallback local: ensures audible track in local/dev
        effective_music_url = music_url
        if not effective_music_url and local_music_path:
            local_music_name = f"music_{listado.id}_{int(time.time())}.mp3"
            local_music_render_path = os.path.join(render_dir, local_music_name)
            try:
                shutil.copy2(local_music_path, local_music_render_path)
                effective_music_url = f"./{local_music_name}"
            except Exception as e:
                logging.error(f"No se pudo copiar musica local: {e}")

        if not effective_music_url:
            ffmpeg_exe = os.path.join(ffmpeg_bin_dir, 'ffmpeg.exe') if ffmpeg_bin_dir else 'ffmpeg'
            fallback_music = os.path.join(render_dir, 'fallback_music.mp3')
            try:
                subprocess.run(
                    [
                        ffmpeg_exe,
                        '-y',
                        '-f', 'lavfi',
                        '-i', f'sine=frequency=196:sample_rate=44100:duration={max(10.0, total_duration):.2f}',
                        '-filter:a', 'volume=0.08',
                        '-c:a', 'libmp3lame',
                        fallback_music,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=90,
                )
                if os.path.exists(fallback_music):
                    effective_music_url = './fallback_music.mp3'
            except Exception:
                effective_music_url = ''

        music_html = ''
        if effective_music_url:
            music_html = (
                f'<audio id="audio-music" class="clip" data-start="0" '
                f'data-duration="{f"{total_duration:.3f}".rstrip("0").rstrip(".")}" '
                f'data-track-index="0" data-volume="{quality_profile["music_volume"]}" src="{effective_music_url}"></audio>'
            )

        vo_html = ''
        if has_voiceover_file:
            vo_html = (
                f'<audio id="audio-vo" class="clip" data-start="0.5" '
                f'data-duration="{f"{vo_duration:.3f}".rstrip("0").rstrip(".")}" '
                f'data-track-index="1" data-volume="1.0" src="./{local_audio_name}"></audio>'
            )

        sfx_swoosh_html = ''
        if sfx_swoosh_url:
            sfx_swoosh_html = (
                f'<audio id="sfx-swoosh1" class="clip" data-start="0" data-duration="3" data-track-index="4" data-volume="{quality_profile["sfx_volume"]}" src="{sfx_swoosh_url}"></audio>'
                f'<audio id="sfx-swoosh2" class="clip" data-start="{f"{cta_start:.3f}".rstrip("0").rstrip(".")}" data-duration="3" data-track-index="4" data-volume="{quality_profile["sfx_volume"]}" src="{sfx_swoosh_url}"></audio>'
            )

        sfx_impact_html = ''
        if sfx_impact_url:
            sfx_impact_html = (
                f'<audio id="sfx-impact" class="clip" data-start="{f"{cta_start:.3f}".rstrip("0").rstrip(".")}" data-duration="2" data-track-index="5" data-volume="{quality_profile["sfx_volume"]}" src="{sfx_impact_url}"></audio>'
            )

        # --- FILL TEMPLATE ---
        template_path = os.path.join(engine_dir, 'template_index.html')
        with open(template_path, 'r', encoding='utf-8') as f_temp:
            html_content = f_temp.read()
        
        replacements = {
            '{{ duration }}': f"{total_duration:.3f}".rstrip('0').rstrip('.'),
            '{{ images_html }}': images_html,
            '{{ music_html }}': music_html,
            '{{ vo_html }}': vo_html,
            '{{ sfx_swoosh_html }}': sfx_swoosh_html,
            '{{ sfx_impact_html }}': sfx_impact_html,
            '{{ sfx_swoosh_url }}': sfx_swoosh_url,
            '{{ sfx_impact_url }}': sfx_impact_url,
            '{{ cta_start }}': f"{cta_start:.3f}".rstrip('0').rstrip('.'),
            '{{ sfx_camera_html }}': sfx_camera_html,
            '{{ captions_html }}': captions_html,
            '{{ price }}': listado.precio,
            '{{ location }}': f"{listado.ciudad}",
            '{{ contact_cta }}': 'Escribinos para coordinar visita',
            '{{ ken_burns_js }}': ken_burns_js,
            '{{ cut_times }}': ",".join(cut_times),
            '{{ words_js }}': words_js,
            '{{ cut_flash_opacity }}': str(quality_profile['cut_flash_opacity']),
            '{{ cut_flash_duration }}': str(quality_profile['cut_flash_duration']),
            '{{ cut_fade_duration }}': str(quality_profile['cut_fade_duration']),
            '{{ caption_anim }}': quality_profile['caption_anim'],
        }

        agent_name = str(datos.get('agenteNombre') or datos.get('agente_nombre') or '').strip()
        agent_phone = str(datos.get('agenteTelefono') or datos.get('agente_telefono') or '').strip()
        if agent_phone:
            replacements['{{ contact_cta }}'] = f"Contacto: {agent_phone}"
        elif agent_name:
            replacements['{{ contact_cta }}'] = f"Asesor: {agent_name}"

        replacements.update({
            '{{ caption_bg }}': visual_theme['caption_bg'],
            '{{ caption_primary }}': visual_theme['caption_primary'],
            '{{ caption_accent }}': visual_theme['caption_accent'],
            '{{ caption_stroke }}': visual_theme['caption_stroke'],
            '{{ cta_border }}': visual_theme['cta_border'],
            '{{ cta_accent }}': visual_theme['cta_accent'],
            '{{ caption_top }}': visual_theme['caption_top'],
            '{{ caption_size }}': visual_theme['caption_size'],
            '{{ cta_top }}': visual_theme['cta_top'],
        })
        
        for k, v in replacements.items():
            html_content = html_content.replace(k, v)

        # Write final index.html in the temp render directory
        index_path = os.path.join(render_dir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f_out:
            f_out.write(html_content)

        # --- RENDER ---
        render_cmd = [
            "npx.cmd" if os.name == 'nt' else "npx",
            "-y",
            "hyperframes",
            "render",
            ".", # Render the current (temp) directory
            "--output", output_path,
            "--quality", config('HYPERFRAMES_QUALITY', default='standard'),
            "--workers", str(config('HYPERFRAMES_WORKERS', default=1, cast=int)),
        ]

        # En entornos tipo Railway conviene evitar GPU hardware para Chromium.
        browser_gpu_mode = config(
            'HYPERFRAMES_BROWSER_GPU_MODE',
            default='auto' if settings.DEBUG else 'software'
        ).strip().lower()
        if browser_gpu_mode:
            render_cmd.extend(["--browser-gpu-mode", browser_gpu_mode])

        render_timeout_seconds = int(config('HYPERFRAMES_RENDER_TIMEOUT', default=420))

        render_env = os.environ.copy()
        if ffmpeg_bin_dir and os.path.isdir(ffmpeg_bin_dir):
            render_env['PATH'] = ffmpeg_bin_dir + os.pathsep + render_env.get('PATH', '')
        # Más robusto en contenedores para Chromium/Playwright.
        render_env.setdefault('PLAYWRIGHT_BROWSERS_PATH', '0')
        render_env.setdefault('CHROME_DISABLE_GPU', '1')

        try:
            process = subprocess.run(
                render_cmd,
                cwd=render_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True if os.name == 'nt' else False,
                timeout=render_timeout_seconds,
                env=render_env,
            )
        except subprocess.TimeoutExpired as e:
            listado.video_status = 'error'
            listado.save(update_fields=['video_status'])
            logging.error(
                f"Render timeout after {render_timeout_seconds}s for listado {listado.id}. "
                f"stdout={str(e.stdout)[:2000]} stderr={str(e.stderr)[:2000]}"
            )
            return False

        # Cleanup
        try:
            shutil.rmtree(render_dir)
            transcript_path = audio_path.replace('.mp3', '.json')
            if os.path.exists(transcript_path): os.remove(transcript_path)
        except:
            pass

        if process.returncode == 0:
            try:
                if _cloudinary_ready():
                    video_url = AlmacenamientoCloudinary.guardar_video(
                        output_path,
                        user_id=listado.agente.id,
                        listado_id=listado.id,
                    )
                    if video_url:
                        listado.video_url = video_url
                    else:
                        listado.video_url = f"/media/assets/{output_filename}"
                else:
                    listado.video_url = f"/media/assets/{output_filename}"
                    
                listado.video_status = 'done'
                listado.save()
            except Exception as e:
                listado.video_url = f"/media/assets/{output_filename}"
                listado.video_status = 'done'
                listado.save()
                logging.error(f"Cloudinary upload failed: {e}")
            
            return True
        else:
            listado.video_status = 'error'
            listado.save()
            logging.error(f"Render failed: {process.stderr}")
            return False

    except Exception as e:
        if 'listado' in locals() and listado:
            listado.video_status = 'error'
            listado.save()
        logging.error(f"Generate video failed: {e}")
        return False
