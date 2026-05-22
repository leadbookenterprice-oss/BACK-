import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

import requests
from decouple import config
from django.utils import timezone
from PIL import Image, ImageOps

from api.ai_services import call_elevenlabs_api, normalize_elevenlabs_voice_choice
from api.services.almacenamiento import AlmacenamientoCloudinary
from api.services.gemini_video_service import _collect_photo_urls, _value
from api.services.video_service import (
    _format_count,
    _format_price_for_voice,
    _normalize_video_type,
    _prepare_tts_text,
    _sanitize_video_script,
)

logger = logging.getLogger(__name__)


class LightweightVideoError(Exception):
    pass


def _run(cmd, timeout=180):
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if process.returncode != 0:
        raise LightweightVideoError((process.stderr or process.stdout or 'ffmpeg fallo')[-3000:])
    return process


def _ffmpeg_bin(name='ffmpeg'):
    return config('FFMPEG_BIN', default=name).strip() or name


def _ffprobe_bin():
    configured = config('FFPROBE_BIN', default='').strip()
    if configured:
        return configured
    ffmpeg = _ffmpeg_bin('ffmpeg')
    if ffmpeg.endswith('ffmpeg.exe'):
        return ffmpeg[:-10] + 'ffprobe.exe'
    if ffmpeg.endswith('ffmpeg'):
        return ffmpeg[:-6] + 'ffprobe'
    return 'ffprobe'


def _probe_duration(path):
    try:
        process = subprocess.run(
            [
                _ffprobe_bin(),
                '-v',
                'error',
                '-show_entries',
                'format=duration',
                '-of',
                'default=noprint_wrappers=1:nokey=1',
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if process.returncode == 0:
            return max(0.0, float((process.stdout or '0').strip() or 0))
    except Exception:
        pass
    return 0.0


def _ordered_scene_texts(datos):
    escenas = datos.get('escenas') or []
    if not isinstance(escenas, list):
        return []

    decorated = []
    for pos, escena in enumerate(escenas):
        if not isinstance(escena, dict):
            continue
        order = pos
        for key in ('index', 'indice', 'orden', 'order', 'position', 'pos', 'id'):
            try:
                if escena.get(key) not in (None, ''):
                    order = int(escena.get(key))
                    break
            except Exception:
                continue
        text = str(escena.get('texto') or escena.get('text') or '').strip()
        text = re.sub(r'\s+', ' ', text).replace('**', '').strip()
        if text:
            decorated.append((order, pos, text))
    return [text for _, _, text in sorted(decorated, key=lambda row: (row[0], row[1]))]


def _build_voice_script(listado, max_seconds):
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

    script = ' '.join(_ordered_scene_texts(datos))
    if not script:
        script = (
            f'Conoce esta {tipo} en {operacion} en {ciudad}. '
            f'{detalles + ". " if detalles else ""}'
            f'Una oportunidad atractiva por ubicacion, comodidad y valor. '
            f'Precio {price_voice}. Escribinos para coordinar una visita.'
        )

    words_per_second = config('LIGHT_VIDEO_WORDS_PER_SECOND', default=2.25, cast=float)
    max_words = max(10, int(max_seconds * words_per_second))
    words = script.split()
    if len(words) > max_words:
        script = ' '.join(words[:max_words]).rstrip(',.') + '.'

    script = _sanitize_video_script(script, price_voice)
    return _prepare_tts_text(script, is_tour=tipo_video == 'tour')


def _generate_voice_file(listado, temp_dir, script):
    if not script:
        return '', 0.0

    datos = listado.datos or {}
    voice_enabled = str(datos.get('voiceover', True)).strip().lower() not in {'0', 'false', 'no', 'off'}
    if not voice_enabled:
        return '', 0.0

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
    audio_bytes = call_elevenlabs_api(
        script,
        agente=listado.agente,
        voz=voz,
        voice_id=custom_voice_id,
        voice_settings=voice_settings if isinstance(voice_settings, dict) else None,
    )
    if not audio_bytes:
        raise LightweightVideoError('ElevenLabs no devolvio audio')

    audio_path = os.path.join(temp_dir, 'voice.mp3')
    with open(audio_path, 'wb') as handle:
        handle.write(audio_bytes)
    duration = _probe_duration(audio_path) or max(2.0, len(script.split()) / 2.25)
    return audio_path, duration


def _download_image(url, timeout=(10, 40)):
    if str(url or '').startswith('data:'):
        raise LightweightVideoError('No se aceptan imagenes base64 para video')
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _prepare_image(url, output_path, width, height):
    content = _download_image(url)
    image = Image.open(io.BytesIO(content))
    image = ImageOps.exif_transpose(image).convert('RGB')
    resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS')
    image = ImageOps.fit(image, (width, height), method=resample, centering=(0.5, 0.5))
    image.save(output_path, format='JPEG', quality=88, optimize=True)
    return output_path


def _prepare_images(listado, temp_dir, width, height):
    max_photos = max(1, min(8, config('LIGHT_VIDEO_MAX_PHOTOS', default=8, cast=int)))
    urls = _collect_photo_urls(listado)[:max_photos]
    if not urls:
        raise LightweightVideoError('El listado no tiene fotos publicas para generar video')

    paths = []
    used_urls = []
    for index, url in enumerate(urls):
        try:
            output_path = os.path.join(temp_dir, f'image_{index:02d}.jpg')
            _prepare_image(url, output_path, width, height)
            paths.append(output_path)
            used_urls.append(url)
        except Exception as exc:
            logger.warning('[LIGHT_VIDEO] No se pudo usar foto %s: %s', url, exc)

    if not paths:
        raise LightweightVideoError('No se pudo descargar ninguna foto valida para video')
    return paths, used_urls


def _render_image_segment(image_path, output_path, duration, width, height, fps, crf):
    frames = max(1, int(duration * fps))
    zoom_delta = config('LIGHT_VIDEO_ZOOM_DELTA', default=0.055, cast=float)
    zoom_step = zoom_delta / max(1, frames)
    vf = (
        f"zoompan=z='min(1+on*{zoom_step:.8f},{1 + zoom_delta:.4f})':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},"
        'format=yuv420p'
    )
    _run(
        [
            _ffmpeg_bin(),
            '-y',
            '-hide_banner',
            '-loglevel',
            'error',
            '-framerate',
            str(fps),
            '-loop',
            '1',
            '-t',
            f'{duration:.3f}',
            '-i',
            image_path,
            '-vf',
            vf,
            '-frames:v',
            str(frames),
            '-an',
            '-c:v',
            'libx264',
            '-preset',
            config('LIGHT_VIDEO_PRESET', default='veryfast'),
            '-crf',
            str(crf),
            '-pix_fmt',
            'yuv420p',
            output_path,
        ],
        timeout=max(90, int(duration * 20)),
    )


def _concat_segments(segment_paths, output_path):
    list_path = os.path.join(os.path.dirname(output_path), 'segments.txt')
    with open(list_path, 'w', encoding='utf-8') as handle:
        for path in segment_paths:
            safe = path.replace('\\', '/')
            handle.write(f"file '{safe}'\n")
    _run(
        [
            _ffmpeg_bin(),
            '-y',
            '-hide_banner',
            '-loglevel',
            'error',
            '-f',
            'concat',
            '-safe',
            '0',
            '-i',
            list_path,
            '-c',
            'copy',
            output_path,
        ],
        timeout=120,
    )


def _mux_audio(video_path, audio_path, output_path):
    if not audio_path:
        shutil.copy2(video_path, output_path)
        return
    _run(
        [
            _ffmpeg_bin(),
            '-y',
            '-hide_banner',
            '-loglevel',
            'error',
            '-i',
            video_path,
            '-i',
            audio_path,
            '-c:v',
            'copy',
            '-c:a',
            'aac',
            '-b:a',
            config('LIGHT_VIDEO_AUDIO_BITRATE', default='128k'),
            '-shortest',
            output_path,
        ],
        timeout=120,
    )


def _srt_time(seconds):
    seconds = max(0.0, float(seconds or 0))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f'{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}'


def _write_srt(script, duration, output_path):
    words = [w.strip() for w in re.split(r'\s+', script or '') if w.strip()]
    if not words or duration <= 1:
        return False

    chunk_size = config('LIGHT_VIDEO_CAPTION_WORDS', default=5, cast=int)
    chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    usable = max(1.0, duration - 0.8)
    per_chunk = usable / max(1, len(chunks))
    start_offset = 0.35

    with open(output_path, 'w', encoding='utf-8') as handle:
        for idx, chunk in enumerate(chunks, start=1):
            start = start_offset + ((idx - 1) * per_chunk)
            end = min(duration - 0.15, start + max(0.85, per_chunk * 0.92))
            if end <= start:
                break
            handle.write(f'{idx}\n')
            handle.write(f'{_srt_time(start)} --> {_srt_time(end)}\n')
            handle.write(chunk.upper() + '\n\n')
    return True


def _subtitle_filter_path(path):
    normalized = path.replace('\\', '/')
    return normalized.replace(':', '\\:').replace("'", "\\'")


def _burn_subtitles(video_path, srt_path, output_path, crf):
    style = (
        'FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,'
        'OutlineColour=&HAA000000,BackColour=&H66000000,'
        'BorderStyle=4,Outline=1,Shadow=0,MarginV=120,Alignment=2,Bold=1'
    )
    vf = f"subtitles='{_subtitle_filter_path(srt_path)}':force_style='{style}'"
    _run(
        [
            _ffmpeg_bin(),
            '-y',
            '-hide_banner',
            '-loglevel',
            'error',
            '-i',
            video_path,
            '-vf',
            vf,
            '-c:v',
            'libx264',
            '-preset',
            config('LIGHT_VIDEO_PRESET', default='veryfast'),
            '-crf',
            str(crf),
            '-c:a',
            'copy',
            output_path,
        ],
        timeout=180,
    )


def generar_video_listado_liviano(listado_id):
    listado = None
    temp_dir = ''
    try:
        from api.models import Listado

        listado = Listado.objects.select_related('agente').get(id=listado_id)
        listado.video_status = 'processing'
        listado.video_url = None
        listado.save(update_fields=['video_status', 'video_url', 'updated_at'])

        datos = listado.datos or {}
        tipo_video = _normalize_video_type(_value(datos, 'tipoVideo', 'tipo_video', default='reel'))
        width = config('LIGHT_VIDEO_WIDTH', default=720, cast=int)
        height = config('LIGHT_VIDEO_HEIGHT', default=1280, cast=int)
        fps = config('LIGHT_VIDEO_FPS', default=24, cast=int)
        crf = config('LIGHT_VIDEO_CRF', default=26, cast=int)
        max_seconds = config('LIGHT_VIDEO_MAX_SECONDS', default=28 if tipo_video == 'reel' else 38, cast=int)
        min_seconds = config('LIGHT_VIDEO_MIN_SECONDS', default=16 if tipo_video == 'reel' else 24, cast=int)

        temp_dir = tempfile.mkdtemp(prefix=f'leadbook_video_{listado.id}_')
        image_paths, used_urls = _prepare_images(listado, temp_dir, width, height)
        script = _build_voice_script(listado, max_seconds=max_seconds)
        audio_path, audio_duration = _generate_voice_file(listado, temp_dir, script)

        target_duration = max(min_seconds, audio_duration + (0.7 if audio_duration else 0))
        target_duration = min(float(max_seconds), target_duration)
        scene_duration = max(2.0, target_duration / max(1, len(image_paths)))
        target_duration = scene_duration * len(image_paths)

        segment_paths = []
        for index, image_path in enumerate(image_paths):
            segment_path = os.path.join(temp_dir, f'segment_{index:02d}.mp4')
            _render_image_segment(image_path, segment_path, scene_duration, width, height, fps, crf)
            segment_paths.append(segment_path)

        visual_path = os.path.join(temp_dir, 'visual.mp4')
        _concat_segments(segment_paths, visual_path)

        voiced_path = os.path.join(temp_dir, 'voiced.mp4')
        _mux_audio(visual_path, audio_path, voiced_path)

        final_path = voiced_path
        if config('LIGHT_VIDEO_BURN_CAPTIONS', default=True, cast=bool) and script:
            srt_path = os.path.join(temp_dir, 'captions.srt')
            if _write_srt(script, target_duration, srt_path):
                subtitled_path = os.path.join(temp_dir, 'final.mp4')
                try:
                    _burn_subtitles(voiced_path, srt_path, subtitled_path, crf)
                    final_path = subtitled_path
                except Exception as exc:
                    logger.warning('[LIGHT_VIDEO] No se pudieron quemar subtitulos listado_id=%s: %s', listado.id, exc)

        video_url = AlmacenamientoCloudinary.guardar_video(
            final_path,
            user_id=listado.agente_id,
            listado_id=listado.id,
        )
        if not video_url:
            raise LightweightVideoError('Cloudinary no devolvio URL del video')

        datos = listado.datos or {}
        datos['video_provider'] = 'leadbook_sync'
        datos['video_reference_photos'] = used_urls
        datos['video_reference_photo_count'] = len(used_urls)
        datos['video_voice_enabled'] = bool(audio_path)
        datos['video_voice_choice'] = normalize_elevenlabs_voice_choice(_value(datos, 'voz', default='femenina'))
        datos['video_voice_script'] = script
        datos['video_duration_seconds'] = round(target_duration, 2)
        datos['video_generated_at'] = timezone.now().isoformat()

        listado.datos = datos
        listado.video_url = video_url
        listado.video_status = 'done'
        listado.videos_creados = (listado.videos_creados or 0) + 1
        listado.save(update_fields=['datos_extra', 'video_url', 'video_status', 'videos_creados', 'updated_at'])
        return True
    except Exception as exc:
        logger.exception('[LIGHT_VIDEO] Error generando video listado_id=%s', listado_id)
        if listado is not None:
            datos = listado.datos or {}
            datos['video_provider'] = 'leadbook_sync'
            datos['video_error'] = str(exc)[:500]
            listado.datos = datos
            listado.video_status = 'error'
            listado.save(update_fields=['datos_extra', 'video_status', 'updated_at'])
        return False
    finally:
        if temp_dir:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
