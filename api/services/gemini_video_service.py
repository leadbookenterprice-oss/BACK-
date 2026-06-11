import base64
import io
import ipaddress
import logging
import mimetypes
import re
import socket
import time
import uuid
from urllib.parse import urlparse

import cloudinary.uploader
import requests
from cloudinary.utils import cloudinary_url
from decouple import config
from django.conf import settings
from django.utils import timezone
from google import genai
from google.genai import types
from PIL import Image, ImageOps

from api.ai_services import call_elevenlabs_api, normalize_elevenlabs_voice_choice
from api.pool_manager import get_next_available_api
from api.services.almacenamiento import AlmacenamientoCloudinary
from api.services.video_service import (
    _call_elevenlabs_direct,
    _format_count,
    _format_price_for_voice,
    _normalize_video_type,
    _prepare_tts_text,
    _sanitize_video_script,
)
from api.tracking import track_api_call

logger = logging.getLogger(__name__)


class GeminiVideoError(Exception):
    pass


class GeminiVideoVoiceRequiredError(GeminiVideoError):
    pass


def _value(datos, *keys, default=''):
    for key in keys:
        value = datos.get(key)
        if value not in (None, ''):
            return value
    return default


def _normalize_media_url(item):
    if isinstance(item, dict):
        resolved = AlmacenamientoCloudinary.obtener_url_foto(item)
        if resolved:
            return resolved
        for key in ('url', 'fotoUrl', 'foto_url', 'secure_url'):
            if item.get(key):
                return str(item[key]).strip()
    if isinstance(item, str):
        return item.strip()
    return ''


def _allow_global_api_fallback():
    return config('ALLOW_GLOBAL_API_FALLBACK', default=getattr(settings, 'DEBUG', False), cast=bool)


def _truthy(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off', 'none'}


def _max_video_photos():
    return max(1, min(8, config('VIDEO_MAX_REFERENCE_PHOTOS', default=8, cast=int)))


def _is_safe_video_asset_url(url):
    try:
        parsed = urlparse(str(url or '').strip())
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return False
        hostname = parsed.hostname.lower().rstrip('.')
        allowed = {
            str(host).lower().rstrip('.')
            for host in getattr(settings, 'REMOTE_ASSET_ALLOWED_HOSTS', ['res.cloudinary.com'])
            if str(host).strip()
        }
        if allowed and not any(hostname == host or hostname.endswith(f'.{host}') for host in allowed):
            return False
        for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


def _download_video_asset(url, timeout=(10, 35), max_bytes=10 * 1024 * 1024):
    if not _is_safe_video_asset_url(url):
        raise GeminiVideoError('URL de imagen no permitida para video')
    response = requests.get(url, timeout=timeout, stream=True, allow_redirects=False)
    response.raise_for_status()
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise GeminiVideoError('Imagen remota demasiado grande')
        chunks.append(chunk)
    return b''.join(chunks), (response.headers.get('content-type') or '')


def _ordered_media_items(items):
    if not isinstance(items, list):
        return []
    decorated = []
    for pos, item in enumerate(items):
        order = pos
        if isinstance(item, dict):
            for key in ('index', 'indice', 'orden', 'order', 'position', 'pos', 'id'):
                try:
                    if item.get(key) not in (None, ''):
                        order = int(item.get(key))
                        break
                except Exception:
                    continue
        decorated.append((order, pos, item))
    return [item for _, _, item in sorted(decorated, key=lambda row: (row[0], row[1]))]


def _absolute_media_url(url):
    raw = str(url or '').strip()
    if not raw:
        return ''
    if raw.startswith(('http://', 'https://', 'data:')):
        return raw
    if raw.startswith('//'):
        return f'https:{raw}'
    backend_url = config('BACKEND_URL', default=getattr(settings, 'BACKEND_URL', 'http://localhost:8000')).rstrip('/')
    if raw.startswith('/'):
        return f'{backend_url}{raw}'
    return raw


def _collect_photo_urls(listado):
    datos = listado.datos or {}
    urls = []

    def add(item):
        url = _normalize_media_url(item)
        if url:
            urls.append(url)

    explicit_video_photos = (
        datos.get('fotosVideo')
        or datos.get('videoPhotos')
        or datos.get('imagenesVideo')
        or datos.get('video_photo_urls')
    )
    storyboard = datos.get('video_storyboard') or datos.get('storyboard') or []
    if isinstance(storyboard, list) and storyboard:
        for item in _ordered_media_items(storyboard):
            if isinstance(item, dict):
                add(item.get('photo_url') or item.get('fotoUrl') or item.get('foto_url') or item.get('url'))
    elif isinstance(explicit_video_photos, list) and explicit_video_photos:
        for item in _ordered_media_items(explicit_video_photos):
            add(item)
    else:
        portada = _normalize_media_url(datos.get('portadaUrl') or datos.get('portada_url'))
        if portada:
            urls.append(portada)

        escenas = datos.get('escenas') or []
        if isinstance(escenas, list):
            for escena in _ordered_media_items(escenas):
                if isinstance(escena, dict):
                    add(escena.get('fotoUrl') or escena.get('foto_url') or escena.get('url'))

        for item in _ordered_media_items(datos.get('fotosRecorrido') or []):
            add(item)

    deduped = []
    seen = set()
    for url in urls:
        abs_url = _absolute_media_url(url)
        if abs_url and abs_url not in seen:
            deduped.append(abs_url)
            seen.add(abs_url)
        if len(deduped) >= _max_video_photos():
            break
    return deduped


def _fetch_image_bytes(url):
    if not url:
        return None, None
    if url.startswith('data:'):
        header, payload = url.split(',', 1)
        mime = header.split(';')[0].replace('data:', '') or 'image/jpeg'
        if len(payload) > 10 * 1024 * 1024:
            raise GeminiVideoError('Imagen base64 demasiado grande')
        return base64.b64decode(payload), mime

    content, content_type = _download_video_asset(url)
    mime = (content_type or '').split(';')[0].strip()
    if not mime or not mime.startswith('image/'):
        mime = mimetypes.guess_type(url)[0] or 'image/jpeg'
    return content, mime


def _prepare_reference_image(photo_urls):
    photos = list(photo_urls or [])[:_max_video_photos()]
    if not photos:
        return None, None

    loaded = []
    for url in photos:
        try:
            image_bytes, mime = _fetch_image_bytes(url)
            if not image_bytes:
                continue
            image = Image.open(io.BytesIO(image_bytes))
            image = ImageOps.exif_transpose(image).convert('RGB')
            loaded.append((image, mime or 'image/jpeg'))
        except Exception as exc:
            logger.warning('[VEO3] No se pudo cargar foto de referencia %s: %s', url, exc)

    if not loaded:
        return None, None

    if len(loaded) == 1:
        output = io.BytesIO()
        loaded[0][0].save(output, format='JPEG', quality=90, optimize=True)
        return output.getvalue(), 'image/jpeg'

    width = config('VIDEO_REFERENCE_WIDTH', default=1080, cast=int)
    height = config('VIDEO_REFERENCE_HEIGHT', default=1920, cast=int)
    columns = 2
    rows = min(4, (len(loaded) + columns - 1) // columns)
    tile_w = width // columns
    tile_h = height // rows
    resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS')
    sheet = Image.new('RGB', (width, height), (10, 10, 12))

    for idx, (image, _) in enumerate(loaded[:columns * rows]):
        row = idx // columns
        col = idx % columns
        tile = ImageOps.fit(image, (tile_w, tile_h), method=resample, centering=(0.5, 0.5))
        sheet.paste(tile, (col * tile_w, row * tile_h))

    output = io.BytesIO()
    sheet.save(output, format='JPEG', quality=88, optimize=True)
    return output.getvalue(), 'image/jpeg'


def _build_genai_image(image_bytes, mime_type):
    if not image_bytes:
        return None
    builders = [
        lambda: types.Image.from_bytes(data=image_bytes, mime_type=mime_type),
        lambda: types.Image(image_bytes=image_bytes, mime_type=mime_type),
        lambda: types.Image(data=image_bytes, mime_type=mime_type),
    ]
    for builder in builders:
        try:
            return builder()
        except Exception:
            continue
    return None


def _scene_texts(datos):
    escenas = datos.get('escenas') or []
    if not isinstance(escenas, list):
        return []
    texts = []
    for escena in _ordered_media_items(escenas):
        if not isinstance(escena, dict):
            continue
        text = str(escena.get('texto') or escena.get('text') or '').strip()
        text = re.sub(r'\s+', ' ', text).replace('**', '').strip()
        if text:
            texts.append(text)
    return texts


def _build_video_prompt(listado, photo_count=0):
    datos = listado.datos or {}
    tipo_video = _normalize_video_type(_value(datos, 'tipoVideo', 'tipo_video', default='reel'))
    tipo = _value(datos, 'tipoPropiedad', 'tipo_propiedad', default=listado.tipo_propiedad or 'propiedad')
    operacion = _value(datos, 'operacion', default=listado.operacion or 'venta')
    ciudad = listado.ciudad or _value(datos, 'ciudad')
    barrio = listado.barrio or _value(datos, 'barrio')
    recamaras = _format_count(_value(datos, 'recamaras', 'habitaciones'), 'habitacion', 'habitaciones')
    banos = _format_count(_value(datos, 'banos', 'bathrooms'), 'bano', 'banos')
    superficie = _value(datos, 'superficieCubierta', 'superficieConstruida', 'metros', 'superficie')
    tono = _value(datos, 'tono', default='profesional')
    contexto = _value(datos, 'contextoAdicional', 'contexto_adicional')

    detalles = ', '.join(x for x in [recamaras, banos, f'{superficie} m2' if superficie else ''] if x)
    location = ', '.join(x for x in [barrio, ciudad] if x)
    style = 'recorrido inmobiliario cinematografico' if tipo_video == 'tour' else 'reel inmobiliario dinamico para redes sociales'

    scene_hint = ' '.join(_scene_texts(datos)[:_max_video_photos()])
    if photo_count > 1:
        reference_instruction = (
            f'The reference image is a contact sheet with {photo_count} listing photos ordered left-to-right, top-to-bottom. '
            'Use those photos as the visual reference for a coherent property tour in that same order. '
            'Do not show the contact sheet, grid, split-screen, borders, or photo collage; turn it into smooth cinematic shots. '
        )
    else:
        reference_instruction = 'Use the provided real estate photo as visual reference. '

    scene_instruction = f'Narrative scene order: {scene_hint}. ' if scene_hint else ''

    return (
        f'Create a vertical 9:16 {style}. {reference_instruction}'
        f'Property: {tipo} en {operacion}. Location: {location}. Details: {detalles}. '
        f'Tone: {tono}. {contexto}. {scene_instruction}'
        'Use smooth camera movement, realistic lighting, premium real estate marketing style, '
        'natural depth, clean composition, no readable text, no subtitles, no logos, no watermark, no people talking to camera. '
        'The clip must look like a polished social media property video.'
    )


def _build_voice_script(listado):
    datos = listado.datos or {}
    tipo_video = _normalize_video_type(_value(datos, 'tipoVideo', 'tipo_video', default='reel'))
    tipo = _value(datos, 'tipoPropiedad', 'tipo_propiedad', default=listado.tipo_propiedad or 'propiedad')
    ciudad = listado.ciudad or _value(datos, 'ciudad')
    operacion = _value(datos, 'operacion', default=listado.operacion or 'venta')
    moneda = _value(datos, 'moneda', default=listado.moneda or '')
    price_voice = _format_price_for_voice(listado.precio, moneda)
    recamaras = _format_count(_value(datos, 'recamaras', 'habitaciones'), 'habitacion', 'habitaciones')
    banos = _format_count(_value(datos, 'banos', 'bathrooms'), 'bano', 'banos')
    detalles = ', '.join(x for x in [recamaras, banos] if x)

    script = ' '.join(_scene_texts(datos))
    if not script:
        script = (
            f'Conoce esta {tipo} en {operacion} en {ciudad}. '
            f'{detalles + ". " if detalles else ""}'
            f'Una oportunidad atractiva por ubicacion, comodidad y valor. '
            f'Precio {price_voice}. Escribinos para coordinar una visita.'
        )
    duration_seconds = max(4, config('VEO3_DURATION_SECONDS', default=8, cast=int))
    words_per_second = config('VEO3_VOICE_WORDS_PER_SECOND', default=2.25, cast=float)
    computed_max_words = max(10, int(duration_seconds * words_per_second))
    max_words_raw = config('VEO3_VOICE_MAX_WORDS', default='')
    try:
        max_words = int(max_words_raw) if str(max_words_raw).strip() else computed_max_words
    except Exception:
        max_words = computed_max_words
    words = script.split()
    if len(words) > max_words:
        script = ' '.join(words[:max_words]).rstrip(',.') + '.'
    script = _sanitize_video_script(script, price_voice)
    return _prepare_tts_text(script, is_tour=tipo_video == 'tour')


def _get_video_api_key(agente):
    if agente:
        try:
            pooled_key = get_next_available_api(agente, 'gemini')
        except Exception as exc:
            logger.warning('[VEO3] No se pudo obtener Gemini del pool user_id=%s: %s', getattr(agente, 'id', None), exc)
            pooled_key = None
        if pooled_key:
            return pooled_key
        if not _allow_global_api_fallback():
            return ''

    dedicated_key = (
        config('GEMINI_VIDEO_API_KEY', default='').strip()
        or config('VEO3_API_KEY', default='').strip()
    )
    if dedicated_key:
        return dedicated_key
    if getattr(settings, 'GEMINI_API_KEY', ''):
        return settings.GEMINI_API_KEY
    return ''


def _build_video_config():
    cfg_cls = getattr(types, 'GenerateVideosConfig', None)
    payload = {
        'number_of_videos': 1,
        'duration_seconds': config('VEO3_DURATION_SECONDS', default=8, cast=int),
        'aspect_ratio': config('VEO3_ASPECT_RATIO', default='9:16'),
        'person_generation': config('VEO3_PERSON_GENERATION', default='allow_adult'),
        'generate_audio': False,
        'negative_prompt': 'text overlays, captions, subtitles, logos, watermarks, distorted architecture, unrealistic rooms',
    }
    if not cfg_cls:
        return payload
    try:
        return cfg_cls(**payload)
    except TypeError:
        for key in ('person_generation', 'generate_audio', 'negative_prompt'):
            payload.pop(key, None)
        return cfg_cls(**payload)


def _operation_done(operation):
    if isinstance(operation, dict):
        return bool(operation.get('done'))
    return bool(getattr(operation, 'done', False))


def _refresh_operation(client, operation):
    try:
        return client.operations.get(operation)
    except TypeError:
        name = getattr(operation, 'name', None) or (operation.get('name') if isinstance(operation, dict) else None)
        if not name:
            raise
        return client.operations.get(name=name)


def _extract_response(operation):
    if isinstance(operation, dict):
        return operation.get('response') or operation.get('result')
    return getattr(operation, 'response', None) or getattr(operation, 'result', None)


def _get_attr(obj, *names):
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _extract_generated_video(response):
    generated = _get_attr(response, 'generated_videos', 'generatedVideos', 'videos') or []
    if not generated:
        raise GeminiVideoError('Veo no devolvio videos generados')
    first = generated[0]
    return _get_attr(first, 'video', 'file') or first


def _download_video_bytes(client, video_obj, api_key=''):
    with tempfile_path('.mp4') as path:
        if hasattr(video_obj, 'save'):
            try:
                video_obj.save(path)
                with open(path, 'rb') as handle:
                    return handle.read()
            except Exception:
                pass

        try:
            downloaded = client.files.download(file=video_obj)
            if isinstance(downloaded, bytes):
                return downloaded
            if hasattr(downloaded, 'read'):
                return downloaded.read()
            if hasattr(video_obj, 'save'):
                video_obj.save(path)
                with open(path, 'rb') as handle:
                    return handle.read()
        except Exception:
            pass

    raw = _get_attr(video_obj, 'video_bytes', 'data', 'bytes')
    if raw:
        return raw if isinstance(raw, bytes) else bytes(raw)

    uri = _get_attr(video_obj, 'uri', 'url', 'download_uri', 'downloadUrl')
    if uri:
        headers = {}
        if api_key:
            headers['x-goog-api-key'] = api_key
        response = requests.get(uri, headers=headers, timeout=(15, 180))
        response.raise_for_status()
        return response.content

    raise GeminiVideoError('No se pudo descargar el video generado por Veo')


class tempfile_path:
    def __init__(self, suffix):
        self.suffix = suffix
        self.path = None

    def __enter__(self):
        import tempfile
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=self.suffix)
        self.path = handle.name
        handle.close()
        return self.path

    def __exit__(self, exc_type, exc, tb):
        if self.path:
            try:
                import os
                os.remove(self.path)
            except Exception:
                pass


@track_api_call(service='gemini', action='veo3_video')
def _generate_veo_video_bytes(listado, agente=None):
    api_key = _get_video_api_key(agente or listado.agente)
    if not api_key:
        raise GeminiVideoError('Falta una key Gemini asignada al usuario en el pool')

    client = genai.Client(api_key=api_key)
    photo_urls = _collect_photo_urls(listado)
    prompt = _build_video_prompt(listado, photo_count=len(photo_urls))
    image_obj = None
    if photo_urls:
        try:
            image_bytes, mime = _prepare_reference_image(photo_urls)
            image_obj = _build_genai_image(image_bytes, mime)
        except Exception as exc:
            logger.warning('[VEO3] No se pudo preparar imagenes de referencia listado_id=%s: %s', listado.id, exc)

    kwargs = {
        'model': config('GEMINI_VIDEO_MODEL', default='veo-3.0-generate-preview').strip(),
        'prompt': prompt,
        'config': _build_video_config(),
    }
    if image_obj is not None:
        kwargs['image'] = image_obj

    operation = client.models.generate_videos(**kwargs)
    poll_seconds = config('VEO3_POLL_SECONDS', default=10, cast=int)
    timeout_seconds = config('VEO3_TIMEOUT_SECONDS', default=900, cast=int)
    started = time.time()

    while not _operation_done(operation):
        if time.time() - started > timeout_seconds:
            raise GeminiVideoError(f'Veo timeout despues de {timeout_seconds}s')
        listado.video_status = 'processing'
        listado.save(update_fields=['video_status', 'updated_at'])
        time.sleep(max(3, poll_seconds))
        operation = _refresh_operation(client, operation)

    response = _extract_response(operation)
    video_obj = _extract_generated_video(response)
    return _download_video_bytes(client, video_obj, api_key=api_key)


def _generate_voice_bytes(listado):
    script = _build_voice_script(listado)
    datos = listado.datos or {}
    voz = normalize_elevenlabs_voice_choice(_value(datos, 'voz', default='femenina'))
    custom_voice_id = _value(
        datos,
        'voiceIdPersonalizada',
        'voice_id_personalizada',
        'voiceId',
        'voice_id',
        'elevenlabsVoiceId',
    )
    voice_settings = datos.get('voiceSettings') or datos.get('voice_settings')
    audio_bytes = None
    try:
        audio_bytes = call_elevenlabs_api(
            script,
            agente=listado.agente,
            voz=voz,
            voice_id=custom_voice_id,
            voice_settings=voice_settings if isinstance(voice_settings, dict) else None,
        )
    except Exception as exc:
        logger.warning('[VEO3] ElevenLabs pool fallo listado_id=%s: %s', listado.id, exc)
    if not audio_bytes and _allow_global_api_fallback():
        audio_bytes = _call_elevenlabs_direct(
            script,
            voz=voz,
            voice_id=custom_voice_id,
            voice_settings=voice_settings if isinstance(voice_settings, dict) else None,
        )
    if not audio_bytes:
        raise GeminiVideoVoiceRequiredError('No se pudo generar la voz con ElevenLabs')
    return audio_bytes, script


def _cloudinary_creds():
    creds, key_id = AlmacenamientoCloudinary.get_mejor_cuenta()
    if not creds:
        creds = {
            'cloud_name': config('CLOUDINARY_CLOUD_NAME', default='').strip(),
            'api_key': config('CLOUDINARY_API_KEY', default='').strip(),
            'api_secret': config('CLOUDINARY_API_SECRET', default='').strip(),
        }
    if not all(creds.values()):
        raise GeminiVideoError('Cloudinary no esta configurado para guardar video/audio')
    return creds, key_id


def _upload_video_and_audio(video_bytes, audio_bytes, listado):
    creds, key_id = _cloudinary_creds()
    unique = uuid.uuid4().hex[:8]
    video_public_id = f'leadbook/videos/user_{listado.agente_id}/listado_{listado.id}_{unique}'
    audio_public_id = f'leadbook/audios/user_{listado.agente_id}/listado_{listado.id}_{unique}_voice'

    video_res = cloudinary.uploader.upload(
        io.BytesIO(video_bytes),
        resource_type='video',
        public_id=video_public_id,
        type='upload',
        overwrite=True,
        invalidate=True,
        **creds,
    )
    if key_id:
        AlmacenamientoCloudinary._invalidate_stats_cache(key_id)

    if not audio_bytes:
        return {
            'video_url': video_res.get('secure_url'),
            'raw_video_url': video_res.get('secure_url'),
            'audio_url': None,
            'video_public_id': video_res.get('public_id') or video_public_id,
            'audio_public_id': None,
        }

    audio_res = cloudinary.uploader.upload(
        io.BytesIO(audio_bytes),
        resource_type='video',
        public_id=audio_public_id,
        type='upload',
        overwrite=True,
        invalidate=True,
        **creds,
    )
    if key_id:
        AlmacenamientoCloudinary._invalidate_stats_cache(key_id)

    overlay_public_id = audio_public_id.replace('/', ':')
    final_url, _ = cloudinary_url(
        video_res.get('public_id') or video_public_id,
        resource_type='video',
        type='upload',
        secure=True,
        sign_url=True,
        transformation=[
            {'overlay': f'video:{overlay_public_id}', 'flags': 'layer_apply'},
            {'quality': 'auto', 'fetch_format': 'mp4'},
        ],
        **creds,
    )

    return {
        'video_url': final_url or video_res.get('secure_url'),
        'raw_video_url': video_res.get('secure_url'),
        'audio_url': audio_res.get('secure_url'),
        'video_public_id': video_res.get('public_id') or video_public_id,
        'audio_public_id': audio_res.get('public_id') or audio_public_id,
    }


def generar_video_listado_veo3(listado_id):
    listado = None
    try:
        from api.models import Listado

        listado = Listado.objects.select_related('agente').get(id=listado_id)
        listado.video_status = 'processing'
        listado.video_url = None
        listado.save(update_fields=['video_status', 'video_url', 'updated_at'])

        photo_urls = _collect_photo_urls(listado)
        video_bytes = _generate_veo_video_bytes(listado, agente=listado.agente)
        voice_enabled = _truthy((listado.datos or {}).get('voiceover'), default=True)
        audio_bytes = None
        script = ''
        if voice_enabled:
            audio_bytes, script = _generate_voice_bytes(listado)
        uploaded = _upload_video_and_audio(video_bytes, audio_bytes, listado)

        datos = listado.datos or {}
        datos['video_provider'] = 'veo3'
        datos['video_reference_photos'] = photo_urls
        datos['video_reference_photo_count'] = len(photo_urls)
        datos['video_voice_enabled'] = bool(audio_bytes)
        datos['video_voice_choice'] = normalize_elevenlabs_voice_choice(_value(datos, 'voz', default='femenina'))
        datos['video_audio_url'] = uploaded.get('audio_url')
        datos['video_raw_url'] = uploaded.get('raw_video_url')
        datos['video_voice_script'] = script
        datos['video_generated_at'] = timezone.now().isoformat()

        listado.datos = datos
        listado.video_url = uploaded['video_url']
        listado.video_status = 'done'
        listado.videos_creados = (listado.videos_creados or 0) + 1
        listado.save(update_fields=['datos_extra', 'video_url', 'video_status', 'videos_creados', 'updated_at'])
        return True
    except Exception as exc:
        logger.exception('[VEO3] Error generando video listado_id=%s', listado_id)
        if listado is not None:
            datos = listado.datos or {}
            datos['video_provider'] = 'veo3'
            if isinstance(exc, GeminiVideoVoiceRequiredError):
                datos['video_voice_status'] = 'failed'
                datos['video_voice_error'] = str(exc)[:500]
                datos['video_voice_requires_decision'] = True
                datos['video_error'] = ''
                listado.video_status = 'voice_failed'
            else:
                datos['video_error'] = str(exc)[:500]
                listado.video_status = 'error'
            listado.datos = datos
            listado.save(update_fields=['datos_extra', 'video_status', 'updated_at'])
        return False
