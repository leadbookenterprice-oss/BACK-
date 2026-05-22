import base64
import io
import logging
import mimetypes
import time
import uuid

import cloudinary.uploader
import requests
from cloudinary.utils import cloudinary_url
from decouple import config
from django.conf import settings
from django.utils import timezone
from google import genai
from google.genai import types

from api.ai_services import call_elevenlabs_api
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

logger = logging.getLogger(__name__)


class GeminiVideoError(Exception):
    pass


def _value(datos, *keys, default=''):
    for key in keys:
        value = datos.get(key)
        if value not in (None, ''):
            return value
    return default


def _normalize_media_url(item):
    if isinstance(item, dict):
        for key in ('url', 'fotoUrl', 'foto_url', 'secure_url'):
            if item.get(key):
                return str(item[key]).strip()
    if isinstance(item, str):
        return item.strip()
    return ''


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

    escenas = datos.get('escenas') or []
    if isinstance(escenas, list):
        for escena in escenas:
            if isinstance(escena, dict):
                url = _normalize_media_url(escena.get('fotoUrl') or escena.get('foto_url') or escena.get('url'))
                if url:
                    urls.append(url)

    for item in datos.get('fotosRecorrido') or []:
        url = _normalize_media_url(item)
        if url:
            urls.append(url)

    portada = _normalize_media_url(datos.get('portadaUrl') or datos.get('portada_url'))
    if portada:
        urls.insert(0, portada)

    deduped = []
    seen = set()
    for url in urls:
        abs_url = _absolute_media_url(url)
        if abs_url and abs_url not in seen:
            deduped.append(abs_url)
            seen.add(abs_url)
    return deduped


def _fetch_image_bytes(url):
    if not url:
        return None, None
    if url.startswith('data:'):
        header, payload = url.split(',', 1)
        mime = header.split(';')[0].replace('data:', '') or 'image/jpeg'
        return base64.b64decode(payload), mime

    response = requests.get(url, timeout=(10, 35))
    response.raise_for_status()
    mime = (response.headers.get('content-type') or '').split(';')[0].strip()
    if not mime or not mime.startswith('image/'):
        mime = mimetypes.guess_type(url)[0] or 'image/jpeg'
    return response.content, mime


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


def _build_video_prompt(listado):
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

    return (
        f'Create a vertical 9:16 {style} using the provided real estate photo as visual reference. '
        f'Property: {tipo} en {operacion}. Location: {location}. Details: {detalles}. '
        f'Tone: {tono}. {contexto}. '
        'Use smooth camera movement, realistic lighting, premium real estate marketing style, '
        'natural depth, clean composition, no readable text, no subtitles, no logos, no watermark, no people talking to camera. '
        'The clip must look like a polished social media property video.'
    )


def _build_voice_script(listado):
    datos = listado.datos or {}
    tipo = _value(datos, 'tipoPropiedad', 'tipo_propiedad', default=listado.tipo_propiedad or 'propiedad')
    ciudad = listado.ciudad or _value(datos, 'ciudad')
    operacion = _value(datos, 'operacion', default=listado.operacion or 'venta')
    moneda = _value(datos, 'moneda', default=listado.moneda or '')
    price_voice = _format_price_for_voice(listado.precio, moneda)
    recamaras = _format_count(_value(datos, 'recamaras', 'habitaciones'), 'habitacion', 'habitaciones')
    banos = _format_count(_value(datos, 'banos', 'bathrooms'), 'bano', 'banos')
    detalles = ', '.join(x for x in [recamaras, banos] if x)

    script = (
        f'Conoce esta {tipo} en {operacion} en {ciudad}. '
        f'{detalles + ". " if detalles else ""}'
        f'Una oportunidad atractiva por ubicacion, comodidad y valor. '
        f'Precio {price_voice}. Escribinos para coordinar una visita.'
    )
    max_words = config('VEO3_VOICE_MAX_WORDS', default=34, cast=int)
    words = script.split()
    if len(words) > max_words:
        script = ' '.join(words[:max_words]).rstrip(',.') + '.'
    script = _sanitize_video_script(script, price_voice)
    return _prepare_tts_text(script, is_tour=False)


def _get_video_api_key(agente):
    dedicated_key = (
        config('GEMINI_VIDEO_API_KEY', default='').strip()
        or config('VEO3_API_KEY', default='').strip()
    )
    if dedicated_key:
        return dedicated_key
    if getattr(settings, 'GEMINI_API_KEY', ''):
        return settings.GEMINI_API_KEY
    if agente:
        return get_next_available_api(agente, 'gemini')
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


def _download_video_bytes(client, video_obj):
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
        api_key = config('GEMINI_VIDEO_API_KEY', default='').strip() or config('VEO3_API_KEY', default='').strip()
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


def _generate_veo_video_bytes(listado):
    api_key = _get_video_api_key(listado.agente)
    if not api_key:
        raise GeminiVideoError('Falta GEMINI_VIDEO_API_KEY, VEO3_API_KEY, GEMINI_API_KEY o una key Gemini asignada')

    client = genai.Client(api_key=api_key)
    prompt = _build_video_prompt(listado)
    image_obj = None
    photo_urls = _collect_photo_urls(listado)
    if photo_urls:
        try:
            image_bytes, mime = _fetch_image_bytes(photo_urls[0])
            image_obj = _build_genai_image(image_bytes, mime)
        except Exception as exc:
            logger.warning('[VEO3] No se pudo preparar imagen de referencia listado_id=%s: %s', listado.id, exc)

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
    return _download_video_bytes(client, video_obj)


def _generate_voice_bytes(listado):
    script = _build_voice_script(listado)
    voz = str(_value(listado.datos or {}, 'voz', default='femenina') or 'femenina').strip().lower()
    audio_bytes = None
    try:
        audio_bytes = call_elevenlabs_api(script, agente=listado.agente, voz=voz)
    except Exception as exc:
        logger.warning('[VEO3] ElevenLabs pool fallo listado_id=%s: %s', listado.id, exc)
    if not audio_bytes:
        audio_bytes = _call_elevenlabs_direct(script, voz=voz)
    if not audio_bytes:
        raise GeminiVideoError('No se pudo generar la voz con ElevenLabs')
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

        video_bytes = _generate_veo_video_bytes(listado)
        audio_bytes, script = _generate_voice_bytes(listado)
        uploaded = _upload_video_and_audio(video_bytes, audio_bytes, listado)

        datos = listado.datos or {}
        datos['video_provider'] = 'veo3'
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
            datos['video_error'] = str(exc)[:500]
            listado.datos = datos
            listado.video_status = 'error'
            listado.save(update_fields=['datos_extra', 'video_status', 'updated_at'])
        return False
