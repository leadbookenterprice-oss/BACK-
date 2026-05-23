import io
import ipaddress
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import glob
import random
from urllib.parse import urlparse

import requests
from decouple import config
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageOps

from api.ai_services import (
    APIKeyUnavailableError,
    ElevenLabsQuotaExhaustedError,
    ElevenLabsRateLimitedError,
    call_elevenlabs_api,
    normalize_elevenlabs_voice_choice,
)
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
        detail = (process.stderr or process.stdout or '').strip()
        if not detail:
            detail = f'ffmpeg fallo (returncode={process.returncode})'
            if process.returncode < 0:
                detail += f' signal={-process.returncode}'
        snippet = ' '.join(str(piece) for piece in cmd[:18])
        if len(cmd) > 18:
            snippet += ' ...'
        raise LightweightVideoError(f'{detail[-2400:]} | cmd: {snippet}')
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


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _safe_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _get_load_snapshot():
    try:
        from api.models import Listado
        return {
            'processing': int(Listado.objects.filter(video_status='processing').count()),
            'queued': int(Listado.objects.filter(video_status='queued').count()),
        }
    except Exception:
        return {'processing': 0, 'queued': 0}


def _resolve_render_profile(tipo_video):
    profile_name = (config('LIGHT_VIDEO_PROFILE', default='IG_PRO_MAX').strip() or 'IG_PRO_MAX').upper()
    is_reel = tipo_video == 'reel'

    if profile_name == 'IG_PRO_MAX':
        defaults = {
            'width': 1080,
            'height': 1920,
            'fps': 60,
            'crf': 20,
            'preset': 'fast',
            'max_photos': 6,
            'max_seconds': 32 if is_reel else 42,
            'min_seconds': 18 if is_reel else 26,
        }
    else:
        defaults = {
            'width': 720,
            'height': 1280,
            'fps': 24,
            'crf': 26,
            'preset': 'veryfast',
            'max_photos': 8,
            'max_seconds': 28 if is_reel else 38,
            'min_seconds': 16 if is_reel else 24,
        }

    width = int(_clamp(config('LIGHT_VIDEO_WIDTH', default=defaults['width'], cast=int), 540, 2160))
    height = int(_clamp(config('LIGHT_VIDEO_HEIGHT', default=defaults['height'], cast=int), 960, 3840))
    fps = int(_clamp(config('LIGHT_VIDEO_FPS', default=defaults['fps'], cast=int), 24, 60))
    crf = int(_clamp(config('LIGHT_VIDEO_CRF', default=defaults['crf'], cast=int), 16, 30))
    preset = config('LIGHT_VIDEO_PRESET', default=defaults['preset']).strip() or defaults['preset']
    max_photos = int(_clamp(config('LIGHT_VIDEO_MAX_PHOTOS', default=defaults['max_photos'], cast=int), 1, 12))
    max_seconds = int(_clamp(config('LIGHT_VIDEO_MAX_SECONDS', default=defaults['max_seconds'], cast=int), 12, 70))
    min_seconds = int(_clamp(config('LIGHT_VIDEO_MIN_SECONDS', default=defaults['min_seconds'], cast=int), 8, max_seconds))

    load = _get_load_snapshot()
    fallback_applied = False
    fallback_reason = ''
    fallback_enabled = config('LIGHT_VIDEO_LOAD_FALLBACK_ENABLED', default=True, cast=bool)
    fallback_fps = int(_clamp(config('LIGHT_VIDEO_LOAD_FALLBACK_FPS', default=30, cast=int), 24, 30))
    fallback_crf = int(_clamp(config('LIGHT_VIDEO_LOAD_FALLBACK_CRF', default=max(crf, 21), cast=int), crf, 30))
    fallback_preset = config('LIGHT_VIDEO_LOAD_FALLBACK_PRESET', default='veryfast').strip() or 'veryfast'
    fallback_queue = max(1, config('LIGHT_VIDEO_LOAD_FALLBACK_QUEUE', default=3, cast=int))
    fallback_processing = max(1, config('LIGHT_VIDEO_LOAD_FALLBACK_ACTIVE', default=2, cast=int))

    if fallback_enabled and fps > fallback_fps:
        if load['queued'] >= fallback_queue or load['processing'] >= fallback_processing:
            fallback_applied = True
            fallback_reason = (
                f"load queued={load['queued']} processing={load['processing']} "
                f"(thresholds queued>={fallback_queue} active>={fallback_processing})"
            )
            fps = fallback_fps
            crf = fallback_crf
            preset = fallback_preset

    # Guardrail por capacidad de worker (Railway / contenedores chicos):
    # evita SIGKILL (-9) en ffmpeg cuando la configuración es demasiado agresiva.
    runtime_guard = config('LIGHT_VIDEO_RUNTIME_GUARD', default=True, cast=bool)
    if runtime_guard:
        guard_max_fps = int(_clamp(config('LIGHT_VIDEO_RUNTIME_MAX_FPS', default=30, cast=int), 24, 30))
        guard_max_pixels = int(_clamp(config('LIGHT_VIDEO_RUNTIME_MAX_PIXELS', default=1474560, cast=int), 518400, 2073600))
        guard_preset = config('LIGHT_VIDEO_RUNTIME_PRESET', default='veryfast').strip() or 'veryfast'
        guard_crf = int(_clamp(config('LIGHT_VIDEO_RUNTIME_CRF', default=max(crf, 22), cast=int), crf, 32))
        guard_max_photos = int(_clamp(config('LIGHT_VIDEO_RUNTIME_MAX_PHOTOS', default=min(max_photos, 5), cast=int), 1, max_photos))
        guard_max_seconds = int(_clamp(config('LIGHT_VIDEO_RUNTIME_MAX_SECONDS', default=min(max_seconds, 30), cast=int), 10, max_seconds))

        original = (width, height, fps)
        if fps > guard_max_fps:
            fps = guard_max_fps

        pixels = width * height
        if pixels > guard_max_pixels:
            ratio = (guard_max_pixels / float(pixels)) ** 0.5
            width = int(max(540, round((width * ratio) / 2.0) * 2))
            height = int(max(960, round((height * ratio) / 2.0) * 2))
            width = min(width, 2160)
            height = min(height, 3840)

        if (width, height, fps) != original:
            fallback_applied = True
            if fallback_reason:
                fallback_reason += ' | '
            fallback_reason += (
                f"runtime_guard from {original[0]}x{original[1]}@{original[2]} "
                f"to {width}x{height}@{fps}"
            )
            preset = guard_preset
            crf = guard_crf
            max_photos = min(max_photos, guard_max_photos)
            max_seconds = min(max_seconds, guard_max_seconds)
            min_seconds = min(min_seconds, max_seconds)

    return {
        'profile': profile_name,
        'width': width,
        'height': height,
        'fps': fps,
        'crf': crf,
        'preset': preset,
        'max_photos': max_photos,
        'max_seconds': max_seconds,
        'min_seconds': min_seconds,
        'fallback_applied': fallback_applied,
        'fallback_reason': fallback_reason,
        'load': load,
    }


def _x264_low_memory_args():
    threads = int(_clamp(config('LIGHT_VIDEO_X264_THREADS', default=1, cast=int), 1, 4))
    params = str(
        config('LIGHT_VIDEO_X264_PARAMS', default='rc-lookahead=6:bframes=0:ref=1:me=dia:subme=2')
        or ''
    ).strip()
    args = ['-threads', str(threads)]
    if params:
        args.extend(['-x264-params', params])
    return args


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
    try:
        audio_bytes = call_elevenlabs_api(
            script,
            agente=listado.agente,
            voz=voz,
            voice_id=custom_voice_id,
            voice_settings=voice_settings if isinstance(voice_settings, dict) else None,
        )
    except (ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError, APIKeyUnavailableError) as exc:
        fail_open = config('LIGHT_VIDEO_TTS_FAIL_OPEN', default=True, cast=bool)
        if fail_open:
            logger.warning(
                '[LIGHT_VIDEO] TTS fallback sin voz listado_id=%s reason=%s quota_state=%s',
                listado.id,
                str(exc)[:220],
                getattr(exc, 'quota_state', None),
            )
            return '', 0.0
        raise

    if not audio_bytes:
        fail_open_empty = config('LIGHT_VIDEO_TTS_FAIL_OPEN', default=True, cast=bool)
        if fail_open_empty:
            logger.warning('[LIGHT_VIDEO] ElevenLabs sin audio, seguimos sin voz listado_id=%s', listado.id)
            return '', 0.0
        raise LightweightVideoError('ElevenLabs no devolvio audio')

    audio_path = os.path.join(temp_dir, 'voice.mp3')
    with open(audio_path, 'wb') as handle:
        handle.write(audio_bytes)
    duration = _probe_duration(audio_path) or max(2.0, len(script.split()) / 2.25)
    return audio_path, duration


def _download_image(url, timeout=(10, 40)):
    if str(url or '').startswith('data:'):
        raise LightweightVideoError('No se aceptan imagenes base64 para video')
    parsed = urlparse(str(url or '').strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise LightweightVideoError('URL de imagen no permitida para video')
    hostname = parsed.hostname.lower().rstrip('.')
    allowed = {
        str(host).lower().rstrip('.')
        for host in getattr(settings, 'REMOTE_ASSET_ALLOWED_HOSTS', ['res.cloudinary.com'])
        if str(host).strip()
    }
    if allowed and not any(hostname == host or hostname.endswith(f'.{host}') for host in allowed):
        raise LightweightVideoError('Host de imagen no permitido para video')
    for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise LightweightVideoError('IP de imagen no permitida para video')

    response = requests.get(url, timeout=timeout, stream=True, allow_redirects=False)
    response.raise_for_status()
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        total += len(chunk)
        if total > 10 * 1024 * 1024:
            raise LightweightVideoError('Imagen remota demasiado grande')
        chunks.append(chunk)
    return b''.join(chunks)


def _prepare_image(url, output_path, width, height):
    content = _download_image(url)
    image = Image.open(io.BytesIO(content))
    image = ImageOps.exif_transpose(image).convert('RGB')
    resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS')
    image = ImageOps.fit(image, (width, height), method=resample, centering=(0.5, 0.5))
    image.save(output_path, format='JPEG', quality=88, optimize=True)
    return output_path


def _prepare_images(listado, temp_dir, width, height, max_photos):
    max_photos = max(1, min(12, int(max_photos or 1)))
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


def _resolve_motion_patterns():
    raw = config('LIGHT_VIDEO_MOTION_PATTERNS', default='in,out,drift')
    allowed = {'in', 'out', 'drift'}
    patterns = [piece.strip().lower() for piece in str(raw or '').split(',') if piece.strip()]
    patterns = [pattern for pattern in patterns if pattern in allowed]
    return patterns or ['in', 'out', 'drift']


def _build_zoompan_filter(pattern, frames, width, height, fps):
    base_delta = _clamp(config('LIGHT_VIDEO_ZOOM_DELTA', default=0.080, cast=float), 0.010, 0.220)
    in_delta = _clamp(config('LIGHT_VIDEO_ZOOM_DELTA_IN', default=base_delta, cast=float), 0.010, 0.250)
    out_delta = _clamp(config('LIGHT_VIDEO_ZOOM_DELTA_OUT', default=max(0.010, base_delta * 0.90), cast=float), 0.010, 0.250)
    drift_delta = _clamp(config('LIGHT_VIDEO_ZOOM_DELTA_DRIFT', default=max(0.010, base_delta * 0.65), cast=float), 0.010, 0.160)
    drift_strength = _clamp(config('LIGHT_VIDEO_DRIFT_STRENGTH', default=20, cast=int), 6, 50)
    total = max(1, frames - 1)

    if pattern == 'out':
        z_expr = f"max({1.0 + out_delta:.5f}-({out_delta:.5f}*on/{total}),1.0)"
        x_expr = 'iw/2-(iw/zoom/2)'
        y_expr = 'ih/2-(ih/zoom/2)'
    elif pattern == 'drift':
        z_expr = f"min(1.0+({drift_delta:.5f}*on/{total}),{1.0 + drift_delta:.5f})"
        x_expr = f"iw/2-(iw/zoom/2)+sin(on*2*PI/{max(2, total)})*{drift_strength}"
        y_expr = f"ih/2-(ih/zoom/2)+cos(on*2*PI/{max(2, total)})*{max(4, int(drift_strength * 0.6))}"
    else:
        z_expr = f"min(1.0+({in_delta:.5f}*on/{total}),{1.0 + in_delta:.5f})"
        x_expr = 'iw/2-(iw/zoom/2)'
        y_expr = 'ih/2-(ih/zoom/2)'

    return (
        f"scale=iw*1.10:ih*1.10:flags=lanczos,"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps},"
        + _build_film_look_filter()
    )


def _build_film_look_filter():
    if not config('LIGHT_VIDEO_LOOK_ENABLED', default=True, cast=bool):
        return 'format=yuv420p'

    contrast = _clamp(config('LIGHT_VIDEO_LOOK_CONTRAST', default=1.06, cast=float), 0.85, 1.30)
    saturation = _clamp(config('LIGHT_VIDEO_LOOK_SATURATION', default=1.10, cast=float), 0.70, 1.45)
    brightness = _clamp(config('LIGHT_VIDEO_LOOK_BRIGHTNESS', default=0.015, cast=float), -0.08, 0.08)
    gamma = _clamp(config('LIGHT_VIDEO_LOOK_GAMMA', default=1.00, cast=float), 0.80, 1.20)
    sharpen = _clamp(config('LIGHT_VIDEO_LOOK_SHARPEN', default=0.70, cast=float), 0.0, 2.0)
    denoise = _clamp(config('LIGHT_VIDEO_LOOK_DENOISE', default=0.0, cast=float), 0.0, 4.0)

    filters = [
        f'eq=contrast={contrast:.3f}:saturation={saturation:.3f}:brightness={brightness:.3f}:gamma={gamma:.3f}'
    ]
    if denoise > 0:
        filters.append(f'hqdn3d={denoise:.2f}:{denoise:.2f}:{max(1.0, denoise * 1.5):.2f}:{max(1.0, denoise * 1.5):.2f}')
    if sharpen > 0:
        filters.append(f'unsharp=5:5:{sharpen:.2f}:5:5:0.00')
    filters.append('format=yuv420p')
    return ','.join(filters)


def _resolve_transition_effects():
    if not config('LIGHT_VIDEO_TRANSITIONS_ENABLED', default=True, cast=bool):
        return []
    allowed = {
        'fade',
        'fadeblack',
        'fadegrays',
        'dissolve',
        'smoothleft',
        'smoothright',
        'slideleft',
        'slideright',
        'coverleft',
        'coverright',
        'revealleft',
        'revealright',
    }
    raw = str(config('LIGHT_VIDEO_TRANSITION_EFFECTS', default='fade,dissolve,smoothleft,smoothright') or '')
    effects = [piece.strip().lower() for piece in raw.split(',') if piece.strip()]
    effects = [effect for effect in effects if effect in allowed]
    return effects or ['fade']


def _render_image_segment(image_path, output_path, duration, width, height, fps, crf, preset, scene_index):
    frames = max(1, int(duration * fps))
    patterns = _resolve_motion_patterns()
    pattern = patterns[scene_index % len(patterns)]
    vf = _build_zoompan_filter(pattern, frames=frames, width=width, height=height, fps=fps)
    timeout = max(90, int(duration * 20))
    cmd_primary = [
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
        preset,
        '-crf',
        str(crf),
    ]
    cmd_primary.extend(_x264_low_memory_args())
    cmd_primary.extend(
        [
        '-pix_fmt',
        'yuv420p',
        output_path,
        ]
    )
    try:
        _run(cmd_primary, timeout=timeout)
        return
    except Exception as primary_exc:
        logger.warning(
            '[LIGHT_VIDEO] Segment render fallback scene=%s pattern=%s err=%s',
            scene_index,
            pattern,
            str(primary_exc)[:320],
        )

    # Fallback estable para Railway: mantiene fps y resolución, sin zoompan complejo.
    fallback_vf = f'scale={width}:{height}:flags=lanczos,fps={fps},format=yuv420p'
    cmd_fallback = [
        _ffmpeg_bin(),
        '-y',
        '-hide_banner',
        '-loglevel',
        'error',
        '-loop',
        '1',
        '-t',
        f'{duration:.3f}',
        '-i',
        image_path,
        '-vf',
        fallback_vf,
        '-frames:v',
        str(frames),
        '-an',
        '-c:v',
        'libx264',
        '-preset',
        config('LIGHT_VIDEO_SEGMENT_FALLBACK_PRESET', default='ultrafast'),
        '-crf',
        str(max(crf, int(_clamp(config('LIGHT_VIDEO_SEGMENT_FALLBACK_CRF', default=24, cast=int), 20, 32)))),
    ]
    cmd_fallback.extend(_x264_low_memory_args())
    cmd_fallback.extend(
        [
        '-pix_fmt',
        'yuv420p',
        output_path,
        ]
    )
    _run(cmd_fallback, timeout=timeout)


def _concat_segments(segment_paths, output_path, fps, crf, preset):
    if len(segment_paths) <= 1:
        cmd = [
            _ffmpeg_bin(),
            '-y',
            '-hide_banner',
            '-loglevel',
            'error',
            '-i',
            segment_paths[0],
            '-c:v',
            'libx264',
            '-preset',
            preset,
            '-crf',
            str(crf),
        ]
        cmd.extend(_x264_low_memory_args())
        cmd.extend(
            [
                '-pix_fmt',
                'yuv420p',
                output_path,
            ]
        )
        _run(cmd, timeout=120)
        return

    transitions = _resolve_transition_effects()
    transition_seconds = _clamp(config('LIGHT_VIDEO_TRANSITION_SECONDS', default=0.30, cast=float), 0.10, 0.90)
    if not transitions:
        transition_seconds = 0.0

    can_xfade = len(segment_paths) > 1 and transition_seconds > 0
    if can_xfade:
        durations = [_probe_duration(path) for path in segment_paths]
        if any(duration <= 0 for duration in durations):
            can_xfade = False
        elif any(duration <= transition_seconds + 0.12 for duration in durations):
            can_xfade = False

    if can_xfade:
        cmd = [_ffmpeg_bin(), '-y', '-hide_banner', '-loglevel', 'error']
        for path in segment_paths:
            cmd.extend(['-i', path])

        filters = []
        for index in range(len(segment_paths)):
            filters.append(f'[{index}:v]settb=AVTB,format=yuv420p[v{index}]')

        prev_label = 'v0'
        elapsed = durations[0]
        for index in range(1, len(segment_paths)):
            effect = transitions[(index - 1) % len(transitions)]
            offset = max(0.0, elapsed - transition_seconds)
            out_label = f'vx{index}'
            filters.append(
                f'[{prev_label}][v{index}]xfade=transition={effect}:duration={transition_seconds:.3f}:offset={offset:.3f}[{out_label}]'
            )
            prev_label = out_label
            elapsed += max(0.0, durations[index] - transition_seconds)

        cmd.extend(
            [
                '-filter_complex',
                ';'.join(filters),
                '-map',
                f'[{prev_label}]',
                '-r',
                str(fps),
                '-c:v',
                'libx264',
                '-preset',
                preset,
                '-crf',
                str(crf),
            ]
        )
        cmd.extend(_x264_low_memory_args())
        cmd.extend(
            [
                '-pix_fmt',
                'yuv420p',
                output_path,
            ]
        )

        try:
            _run(cmd, timeout=max(180, int(sum(durations) * 8)))
            return
        except Exception as xfade_exc:
            logger.warning('[LIGHT_VIDEO] Xfade fallback a concat tradicional: %s', str(xfade_exc)[:320])

    list_path = os.path.join(os.path.dirname(output_path), 'segments.txt')
    with open(list_path, 'w', encoding='utf-8') as handle:
        for path in segment_paths:
            safe = path.replace('\\', '/')
            handle.write(f"file '{safe}'\n")
    cmd = [
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
        '-c:v',
        'libx264',
        '-preset',
        preset,
        '-crf',
        str(crf),
        '-r',
        str(fps),
    ]
    cmd.extend(_x264_low_memory_args())
    cmd.extend(
        [
            '-pix_fmt',
            'yuv420p',
            output_path,
        ]
    )
    _run(cmd, timeout=120)


def _normalize_path(value):
    if not value:
        return ''
    path = str(value).strip().strip('"').strip("'")
    if not path:
        return ''
    return os.path.abspath(path) if os.path.exists(path) else ''


def _pick_music_track(datos):
    if not config('LIGHT_VIDEO_MUSIC_ENABLED', default=True, cast=bool):
        return ''
    custom = _normalize_path(config('LIGHT_VIDEO_MUSIC_FILE', default=''))
    if custom:
        return custom

    music_dir = os.path.join(os.path.dirname(__file__), 'musica_videos')
    tracks = sorted(glob.glob(os.path.join(music_dir, '*.mp3')))
    if not tracks:
        return ''

    tone = str(_value(datos, 'tono', default='profesional') or 'profesional').strip().lower()
    if tone == 'energetico':
        preferred = [
            track for track in tracks
            if any(key in os.path.basename(track).lower() for key in ('snapshots', 'city', 'bonita', 'indigo'))
        ]
    elif tone == 'lujo':
        preferred = [
            track for track in tracks
            if any(key in os.path.basename(track).lower() for key in ('elevated', 'selfless', 'phases'))
        ]
    else:
        preferred = [
            track for track in tracks
            if any(key in os.path.basename(track).lower() for key in ('butterflies', 'galanthus', 'phases'))
        ]
    pool = preferred or tracks
    return random.choice(pool)


def _resolve_sfx_inputs(cut_times):
    if not cut_times or not config('LIGHT_VIDEO_SFX_ENABLED', default=True, cast=bool):
        return []
    limit = max(0, min(12, config('LIGHT_VIDEO_SFX_MAX_EVENTS', default=8, cast=int)))
    if not limit:
        return []
    whoosh_custom = _normalize_path(config('LIGHT_VIDEO_SFX_WHOOSH_FILE', default=''))
    impact_custom = _normalize_path(config('LIGHT_VIDEO_SFX_IMPACT_FILE', default=''))
    whoosh_duration = _clamp(config('LIGHT_VIDEO_SFX_WHOOSH_SECONDS', default=0.34, cast=float), 0.18, 1.50)
    impact_duration = _clamp(config('LIGHT_VIDEO_SFX_IMPACT_SECONDS', default=0.20, cast=float), 0.10, 1.00)
    sfx_inputs = []

    for idx, cut_time in enumerate(cut_times[:limit]):
        if idx % 2 == 0:
            if whoosh_custom:
                sfx_inputs.append({'mode': 'file', 'path': whoosh_custom, 'delay': float(cut_time), 'type': 'whoosh'})
            else:
                sfx_inputs.append({
                    'mode': 'lavfi',
                    'src': f"anoisesrc=color=white:r=48000:d={whoosh_duration:.3f},highpass=f=300,lowpass=f=5400,afade=t=out:st={max(0.05, whoosh_duration - 0.10):.3f}:d=0.10",
                    'delay': float(cut_time),
                    'type': 'whoosh',
                })
        else:
            if impact_custom:
                sfx_inputs.append({'mode': 'file', 'path': impact_custom, 'delay': float(cut_time), 'type': 'impact'})
            else:
                sfx_inputs.append({
                    'mode': 'lavfi',
                    'src': f"sine=frequency=120:sample_rate=48000:duration={impact_duration:.3f},afade=t=out:st={max(0.05, impact_duration - 0.08):.3f}:d=0.08",
                    'delay': float(cut_time),
                    'type': 'impact',
                })
    return sfx_inputs


def _build_audio_mix(voice_path, music_path, cut_times, duration, output_path):
    target_duration = max(2.0, float(duration or 0))
    music_volume = _clamp(config('LIGHT_VIDEO_MUSIC_VOLUME', default=0.30, cast=float), 0.0, 1.2)
    voice_volume = _clamp(config('LIGHT_VIDEO_VOICE_VOLUME', default=1.00, cast=float), 0.1, 2.0)
    sfx_volume = _clamp(config('LIGHT_VIDEO_SFX_VOLUME', default=0.11, cast=float), 0.0, 1.5)
    threshold = _safe_float(config('LIGHT_VIDEO_DUCKING_THRESHOLD', default='0.040'), 0.040)
    ratio = _safe_float(config('LIGHT_VIDEO_DUCKING_RATIO', default='10'), 10)
    attack = _safe_float(config('LIGHT_VIDEO_DUCKING_ATTACK', default='25'), 25)
    release = _safe_float(config('LIGHT_VIDEO_DUCKING_RELEASE', default='320'), 320)

    cmd = [
        _ffmpeg_bin(),
        '-y',
        '-hide_banner',
        '-loglevel',
        'error',
        '-f',
        'lavfi',
        '-t',
        f'{target_duration:.3f}',
        '-i',
        'anullsrc=channel_layout=stereo:sample_rate=48000',
    ]
    input_labels = {'silence': 0}
    next_input = 1

    if voice_path:
        cmd.extend(['-i', voice_path])
        input_labels['voice'] = next_input
        next_input += 1

    if music_path:
        cmd.extend(['-stream_loop', '-1', '-t', f'{target_duration:.3f}', '-i', music_path])
        input_labels['music'] = next_input
        next_input += 1

    sfx_inputs = _resolve_sfx_inputs(cut_times)
    sfx_indexes = []
    for sfx in sfx_inputs:
        if sfx['mode'] == 'file':
            cmd.extend(['-i', sfx['path']])
        else:
            cmd.extend(['-f', 'lavfi', '-i', sfx['src']])
        sfx_indexes.append((next_input, sfx))
        next_input += 1

    filters = ['[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.0[silence]']

    has_voice = 'voice' in input_labels
    has_music = 'music' in input_labels
    if has_voice:
        filters.append(
            f"[{input_labels['voice']}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"acompressor=threshold=0.12:ratio=2.2:attack=6:release=120,volume={voice_volume:.3f}[voice]"
        )
    if has_music:
        filters.append(
            f"[{input_labels['music']}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume={music_volume:.3f}[music]"
        )

    if has_voice and has_music:
        filters.append(
            f"[music][voice]sidechaincompress=threshold={threshold:.5f}:ratio={ratio:.3f}:attack={attack:.1f}:release={release:.1f}[ducked]"
        )
        filters.append('[ducked][voice]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[bed]')
    elif has_voice:
        filters.append('[voice]anull[bed]')
    elif has_music:
        filters.append('[music]anull[bed]')
    else:
        filters.append('[silence]anull[bed]')

    sfx_labels = []
    for idx, (stream_index, sfx) in enumerate(sfx_indexes):
        delay_ms = max(0, int(float(sfx.get('delay') or 0) * 1000))
        label = f'sfx{idx}'
        filters.append(
            f"[{stream_index}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"volume={sfx_volume:.3f},adelay={delay_ms}|{delay_ms}[{label}]"
        )
        sfx_labels.append(label)

    if sfx_labels:
        mix_inputs = '[silence][bed]' + ''.join(f'[{label}]' for label in sfx_labels)
        filters.append(
            f"{mix_inputs}amix=inputs={2 + len(sfx_labels)}:duration=longest:dropout_transition=0:normalize=0,"
            'alimiter=limit=0.94[mix]'
        )
    else:
        filters.append('[silence][bed]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.94[mix]')

    filters.append('[mix]atrim=duration={:.3f},asetpts=PTS-STARTPTS[aout]'.format(target_duration))

    cmd.extend(
        [
            '-filter_complex',
            ';'.join(filters),
            '-map',
            '[aout]',
            '-c:a',
            'aac',
            '-b:a',
            config('LIGHT_VIDEO_AUDIO_BITRATE', default='192k'),
            '-ac',
            '2',
            '-ar',
            '48000',
            output_path,
        ]
    )
    _run(cmd, timeout=180)


def _mux_audio(video_path, mixed_audio_path, output_path):
    if not mixed_audio_path or not os.path.exists(mixed_audio_path):
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
            mixed_audio_path,
            '-c:v',
            'copy',
            '-c:a',
            'aac',
            '-b:a',
            config('LIGHT_VIDEO_AUDIO_BITRATE', default='192k'),
            '-ac',
            '2',
            '-ar',
            '48000',
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


def _normalize_caption_language(raw):
    value = str(raw or '').strip().lower()
    if not value:
        return ''
    aliases = {
        'es': 'es',
        'spanish': 'es',
        'espanol': 'es',
        'espanhol': 'es',
        'espanol_ar': 'es',
        'en': 'en',
        'english': 'en',
        'ingles': 'en',
        'pt': 'pt',
        'portuguese': 'pt',
        'portugues': 'pt',
        'it': 'it',
        'italian': 'it',
        'italiano': 'it',
        'fr': 'fr',
        'french': 'fr',
        'frances': 'fr',
        'de': 'de',
        'german': 'de',
        'aleman': 'de',
    }
    if value in aliases:
        return aliases[value]
    match = re.match(r'^([a-z]{2})', value)
    return match.group(1) if match else ''


def _resolve_groq_key_for_whisper(agente):
    try:
        if agente is not None:
            from api.pool_manager import get_next_available_api
            key = get_next_available_api(agente, 'groq')
            if key:
                return key
    except Exception:
        pass

    return (
        str(config('GROQ_API_KEY', default='') or '').strip()
        or str(getattr(settings, 'GROQ_API_KEY', '') or '').strip()
    )


def _word_chunks_from_whisper_payload(payload, chunk_size, duration):
    words_raw = payload.get('words') if isinstance(payload, dict) else None
    if not isinstance(words_raw, list):
        words_raw = []
        for segment in payload.get('segments', []) if isinstance(payload, dict) else []:
            for item in segment.get('words', []) if isinstance(segment, dict) else []:
                if isinstance(item, dict):
                    words_raw.append(item)

    words = []
    for item in words_raw:
        if not isinstance(item, dict):
            continue
        token = str(item.get('word') or '').strip()
        if not token:
            continue
        start = _safe_float(item.get('start'), -1)
        end = _safe_float(item.get('end'), -1)
        if start < 0 or end <= start:
            continue
        words.append({'word': token, 'start': start, 'end': end})

    chunks = []
    if words:
        for idx in range(0, len(words), chunk_size):
            group = words[idx:idx + chunk_size]
            if not group:
                continue
            start = max(0.0, _safe_float(group[0].get('start'), 0.0))
            end = _safe_float(group[-1].get('end'), start + 0.9)
            if end <= start:
                end = start + 0.9
            text = ' '.join(item['word'] for item in group).strip()
            if text:
                chunks.append({'start': start, 'end': min(duration, end), 'text': text.upper()})
        return chunks

    # Segment fallback if word-level timestamps are unavailable.
    for segment in payload.get('segments', []) if isinstance(payload, dict) else []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get('text') or '').strip()
        if not text:
            continue
        start = max(0.0, _safe_float(segment.get('start'), -1))
        end = _safe_float(segment.get('end'), -1)
        if start < 0:
            continue
        if end <= start:
            end = start + 1.0
        chunks.append({'start': start, 'end': min(duration, end), 'text': text.upper()})
    return chunks


def _transcribe_whisper_for_captions(audio_path, script, duration, agente=None, datos=None):
    enabled = config('LIGHT_VIDEO_WHISPER_CAPTIONS_ENABLED', default=True, cast=bool)
    if not enabled:
        return {'ok': False, 'engine': 'disabled'}
    if not audio_path or not os.path.exists(audio_path):
        return {'ok': False, 'engine': 'no_audio'}

    key = _resolve_groq_key_for_whisper(agente)
    if not key:
        return {'ok': False, 'engine': 'no_key'}

    model = str(config('LIGHT_VIDEO_WHISPER_MODEL', default='whisper-large-v3-turbo') or 'whisper-large-v3-turbo').strip()
    endpoint = str(
        config(
            'LIGHT_VIDEO_WHISPER_API_URL',
            default='https://api.groq.com/openai/v1/audio/transcriptions',
        )
        or 'https://api.groq.com/openai/v1/audio/transcriptions'
    ).strip()
    timeout = int(_clamp(config('LIGHT_VIDEO_WHISPER_TIMEOUT', default=90, cast=int), 20, 180))
    chunk_size = int(_clamp(config('LIGHT_VIDEO_CAPTION_WORDS', default=4, cast=int), 2, 14))
    lang = _normalize_caption_language((datos or {}).get('idioma') or (datos or {}).get('language') or '')
    prompt = str((script or '')[:220]).strip()

    form_data = [
        ('model', model),
        ('response_format', 'verbose_json'),
        ('temperature', '0'),
        ('timestamp_granularities[]', 'word'),
        ('timestamp_granularities[]', 'segment'),
    ]
    if lang:
        form_data.append(('language', lang))
    if prompt:
        form_data.append(('prompt', prompt))

    try:
        with open(audio_path, 'rb') as handle:
            files = {'file': (os.path.basename(audio_path), handle, 'audio/mpeg')}
            response = requests.post(
                endpoint,
                headers={'Authorization': f'Bearer {key}'},
                data=form_data,
                files=files,
                timeout=timeout,
            )
        if response.status_code >= 400:
            logger.warning(
                '[LIGHT_VIDEO] Whisper captions failed status=%s detail=%s',
                response.status_code,
                (response.text or '')[:260],
            )
            return {'ok': False, 'engine': 'http_error', 'status': response.status_code}
        payload = response.json()
        chunks = _word_chunks_from_whisper_payload(payload, chunk_size=chunk_size, duration=duration)
        if not chunks:
            return {'ok': False, 'engine': 'empty_transcript'}
        return {'ok': True, 'engine': 'groq_whisper', 'chunks': chunks, 'model': model, 'language': lang or ''}
    except Exception as exc:
        logger.warning('[LIGHT_VIDEO] Whisper captions exception: %s', str(exc)[:220])
        return {'ok': False, 'engine': 'exception', 'error': str(exc)[:220]}


def _write_srt(script, duration, output_path, audio_path='', agente=None, datos=None):
    words = [w.strip() for w in re.split(r'\s+', script or '') if w.strip()]
    if not words or duration <= 1:
        return {'ok': False, 'engine': 'empty_script'}

    chunk_size = int(_clamp(config('LIGHT_VIDEO_CAPTION_WORDS', default=4, cast=int), 2, 14))
    whisper_result = _transcribe_whisper_for_captions(
        audio_path=audio_path,
        script=script,
        duration=duration,
        agente=agente,
        datos=datos,
    )
    timed_chunks = []
    caption_engine = 'heuristic'
    whisper_model = ''
    whisper_lang = ''
    if whisper_result.get('ok'):
        timed_chunks = whisper_result.get('chunks') or []
        caption_engine = whisper_result.get('engine') or 'groq_whisper'
        whisper_model = whisper_result.get('model') or ''
        whisper_lang = whisper_result.get('language') or ''
    else:
        chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        usable = max(1.0, duration - 0.8)
        per_chunk = usable / max(1, len(chunks))
        start_offset = 0.35
        for idx, chunk in enumerate(chunks, start=1):
            start = start_offset + ((idx - 1) * per_chunk)
            end = min(duration - 0.15, start + max(0.85, per_chunk * 0.92))
            if end <= start:
                break
            timed_chunks.append({'start': start, 'end': end, 'text': chunk.upper()})

    with open(output_path, 'w', encoding='utf-8') as handle:
        for idx, chunk in enumerate(timed_chunks, start=1):
            start = max(0.0, _safe_float(chunk.get('start'), 0.0))
            end = min(duration, _safe_float(chunk.get('end'), start + 0.9))
            if end <= start:
                break
            handle.write(f'{idx}\n')
            handle.write(f'{_srt_time(start)} --> {_srt_time(end)}\n')
            handle.write(str(chunk.get('text') or '').strip().upper() + '\n\n')
    return {
        'ok': True,
        'engine': caption_engine,
        'model': whisper_model,
        'language': whisper_lang,
        'chunks': len(timed_chunks),
        'whisper_state': whisper_result.get('engine') if isinstance(whisper_result, dict) else '',
    }


def _subtitle_filter_path(path):
    normalized = path.replace('\\', '/')
    return normalized.replace(':', '\\:').replace("'", "\\'")


def _ass_color_from_hex(value, default='#FFFFFF', opacity=1.0):
    raw = str(value or default).strip()
    if raw.startswith('0x'):
        raw = raw[2:]
    if raw.startswith('#'):
        raw = raw[1:]
    if len(raw) == 3:
        raw = ''.join(ch * 2 for ch in raw)
    if len(raw) != 6 or not all(ch in '0123456789abcdefABCDEF' for ch in raw):
        raw = default.replace('#', '')
    r = int(raw[0:2], 16)
    g = int(raw[2:4], 16)
    b = int(raw[4:6], 16)
    opacity = _clamp(float(opacity), 0.0, 1.0)
    alpha = int(round((1.0 - opacity) * 255.0))
    return f'&H{alpha:02X}{b:02X}{g:02X}{r:02X}'


def _resolve_caption_alignment():
    raw = str(config('LIGHT_VIDEO_CAPTION_ALIGN', default='2') or '2').strip().lower()
    aliases = {
        'bottom_center': 2,
        'bottom': 2,
        'center_bottom': 2,
        'top_center': 8,
        'top': 8,
        'middle_center': 5,
        'middle': 5,
        'left_bottom': 1,
        'right_bottom': 3,
    }
    if raw.isdigit():
        value = int(raw)
        return value if 1 <= value <= 9 else 2
    return aliases.get(raw, 2)


def _subtitle_style_for_dimensions(height):
    font_name = config('LIGHT_VIDEO_CAPTION_FONT', default='Montserrat').strip() or 'Montserrat'
    base_size = config('LIGHT_VIDEO_CAPTION_SIZE', default=54, cast=int)
    size = int(_clamp(base_size * (height / 1920.0), 28, 92))
    margin_v = config('LIGHT_VIDEO_CAPTION_MARGIN_V', default=320, cast=int)
    margin_v = int(_clamp(margin_v * (height / 1920.0), 110, int(height * 0.40)))
    text_color = _ass_color_from_hex(config('LIGHT_VIDEO_CAPTION_TEXT_COLOR', default='#FFFFFF'), default='#FFFFFF', opacity=1.0)
    outline_color = _ass_color_from_hex(config('LIGHT_VIDEO_CAPTION_OUTLINE_COLOR', default='#000000'), default='#000000', opacity=0.74)
    bg_color = str(config('LIGHT_VIDEO_CAPTION_BG_COLOR', default='#000000') or '#000000')
    bg_opacity = _clamp(config('LIGHT_VIDEO_CAPTION_BG_ALPHA', default=0.58, cast=float), 0.0, 1.0)
    back_color = _ass_color_from_hex(bg_color, default='#000000', opacity=bg_opacity)
    alignment = _resolve_caption_alignment()
    bold = 1 if config('LIGHT_VIDEO_CAPTION_BOLD', default=True, cast=bool) else 0
    outline = _clamp(config('LIGHT_VIDEO_CAPTION_OUTLINE', default=2.0, cast=float), 0.5, 4.0)

    style = (
        f'FontName={font_name},FontSize={size},PrimaryColour={text_color},'
        f'OutlineColour={outline_color},BackColour={back_color},'
        f'BorderStyle=4,Outline={outline:.1f},Shadow=0,'
        f'MarginV={margin_v},Alignment={alignment},Bold={bold}'
    )
    return style


def _burn_subtitles(video_path, srt_path, output_path, crf, preset, height):
    style = _subtitle_style_for_dimensions(height=height)
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
            preset,
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
    started_at = time.time()
    try:
        from api.models import Listado

        listado = Listado.objects.select_related('agente').get(id=listado_id)
        listado.video_status = 'processing'
        listado.video_url = None
        listado.save(update_fields=['video_status', 'video_url', 'updated_at'])

        datos = listado.datos or {}
        tipo_video = _normalize_video_type(_value(datos, 'tipoVideo', 'tipo_video', default='reel'))
        render_profile = _resolve_render_profile(tipo_video=tipo_video)
        width = render_profile['width']
        height = render_profile['height']
        fps = render_profile['fps']
        crf = render_profile['crf']
        preset = render_profile['preset']
        max_seconds = render_profile['max_seconds']
        min_seconds = render_profile['min_seconds']
        max_photos = render_profile['max_photos']

        logger.info(
            '[LIGHT_VIDEO] Inicio listado_id=%s profile=%s %sx%s@%sfps crf=%s preset=%s queued=%s processing=%s fallback=%s',
            listado.id,
            render_profile['profile'],
            width,
            height,
            fps,
            crf,
            preset,
            render_profile['load']['queued'],
            render_profile['load']['processing'],
            render_profile['fallback_applied'],
        )
        if render_profile['fallback_applied']:
            logger.warning('[LIGHT_VIDEO] Fallback por carga listado_id=%s: %s', listado.id, render_profile['fallback_reason'])

        temp_dir = tempfile.mkdtemp(prefix=f'leadbook_video_{listado.id}_')
        image_paths, used_urls = _prepare_images(listado, temp_dir, width, height, max_photos=max_photos)
        script = _build_voice_script(listado, max_seconds=max_seconds)
        audio_path, audio_duration = _generate_voice_file(listado, temp_dir, script)

        target_duration = max(min_seconds, audio_duration + (0.7 if audio_duration else 0))
        target_duration = min(float(max_seconds), target_duration)
        scene_duration = max(2.0, target_duration / max(1, len(image_paths)))
        target_duration = scene_duration * len(image_paths)

        segment_paths = []
        cut_times = []
        for index, image_path in enumerate(image_paths):
            segment_path = os.path.join(temp_dir, f'segment_{index:02d}.mp4')
            if index > 0:
                cut_times.append(round(index * scene_duration, 3))
            _render_image_segment(
                image_path=image_path,
                output_path=segment_path,
                duration=scene_duration,
                width=width,
                height=height,
                fps=fps,
                crf=crf,
                preset=preset,
                scene_index=index,
            )
            segment_paths.append(segment_path)

        visual_path = os.path.join(temp_dir, 'visual.mp4')
        _concat_segments(
            segment_paths,
            visual_path,
            fps=fps,
            crf=crf,
            preset=preset,
        )

        music_path = _pick_music_track(datos)
        mixed_audio_path = os.path.join(temp_dir, 'mix.m4a')
        mix_strategy = 'pro_mix'
        logger.info(
            '[LIGHT_VIDEO] Audio plan listado_id=%s voice=%s music=%s cuts=%s sfx=%s',
            listado.id,
            bool(audio_path),
            os.path.basename(music_path) if music_path else 'none',
            len(cut_times),
            config('LIGHT_VIDEO_SFX_ENABLED', default=True, cast=bool),
        )
        try:
            _build_audio_mix(
                voice_path=audio_path,
                music_path=music_path,
                cut_times=cut_times,
                duration=target_duration,
                output_path=mixed_audio_path,
            )
        except Exception as mix_exc:
            logger.warning('[LIGHT_VIDEO] Mezcla pro fallo listado_id=%s: %s', listado.id, mix_exc)
            if audio_path:
                shutil.copy2(audio_path, mixed_audio_path)
                mix_strategy = 'voice_only_fallback'
            else:
                mixed_audio_path = ''
                mix_strategy = 'silent_fallback'

        voiced_path = os.path.join(temp_dir, 'voiced.mp4')
        _mux_audio(visual_path, mixed_audio_path, voiced_path)

        final_path = voiced_path
        caption_meta = {'ok': False, 'engine': 'disabled'}
        if config('LIGHT_VIDEO_BURN_CAPTIONS', default=True, cast=bool) and script:
            srt_path = os.path.join(temp_dir, 'captions.srt')
            caption_meta = _write_srt(
                script,
                target_duration,
                srt_path,
                audio_path=audio_path,
                agente=listado.agente,
                datos=datos,
            )
            logger.info(
                '[LIGHT_VIDEO] Captions listado_id=%s engine=%s chunks=%s state=%s',
                listado.id,
                caption_meta.get('engine'),
                caption_meta.get('chunks'),
                caption_meta.get('whisper_state'),
            )
            if caption_meta.get('ok'):
                subtitled_path = os.path.join(temp_dir, 'final.mp4')
                try:
                    _burn_subtitles(voiced_path, srt_path, subtitled_path, crf=crf, preset=preset, height=height)
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
        datos['video_music_enabled'] = bool(music_path)
        if music_path:
            datos['video_music_track'] = os.path.basename(music_path)
        datos['video_sfx_enabled'] = config('LIGHT_VIDEO_SFX_ENABLED', default=True, cast=bool)
        datos['video_audio_mix_strategy'] = mix_strategy
        datos['video_voice_choice'] = normalize_elevenlabs_voice_choice(_value(datos, 'voz', default='femenina'))
        datos['video_voice_script'] = script
        datos['video_captions_enabled'] = bool(config('LIGHT_VIDEO_BURN_CAPTIONS', default=True, cast=bool))
        datos['video_caption_engine'] = caption_meta.get('engine')
        if caption_meta.get('model'):
            datos['video_caption_model'] = caption_meta.get('model')
        if caption_meta.get('language'):
            datos['video_caption_language'] = caption_meta.get('language')
        if caption_meta.get('chunks') is not None:
            datos['video_caption_chunks'] = caption_meta.get('chunks')
        if caption_meta.get('whisper_state'):
            datos['video_caption_whisper_state'] = caption_meta.get('whisper_state')
        datos['video_duration_seconds'] = round(target_duration, 2)
        datos['video_resolution'] = f'{width}x{height}'
        datos['video_fps'] = fps
        datos['video_crf'] = crf
        datos['video_preset'] = preset
        datos['video_profile'] = render_profile['profile']
        datos['video_render_fallback_applied'] = render_profile['fallback_applied']
        if render_profile['fallback_reason']:
            datos['video_render_fallback_reason'] = render_profile['fallback_reason']
        datos['video_queue_snapshot'] = render_profile['load']
        datos['video_cut_points'] = cut_times
        datos['video_audio_mix'] = {
            'music_volume': _clamp(config('LIGHT_VIDEO_MUSIC_VOLUME', default=0.30, cast=float), 0.0, 1.2),
            'voice_volume': _clamp(config('LIGHT_VIDEO_VOICE_VOLUME', default=1.00, cast=float), 0.1, 2.0),
            'sfx_volume': _clamp(config('LIGHT_VIDEO_SFX_VOLUME', default=0.11, cast=float), 0.0, 1.5),
            'ducking': {
                'threshold': _safe_float(config('LIGHT_VIDEO_DUCKING_THRESHOLD', default='0.040'), 0.040),
                'ratio': _safe_float(config('LIGHT_VIDEO_DUCKING_RATIO', default='10'), 10),
                'attack': _safe_float(config('LIGHT_VIDEO_DUCKING_ATTACK', default='25'), 25),
                'release': _safe_float(config('LIGHT_VIDEO_DUCKING_RELEASE', default='320'), 320),
            },
        }
        datos['video_generation_seconds'] = round(time.time() - started_at, 2)
        datos['video_generated_at'] = timezone.now().isoformat()

        listado.datos = datos
        listado.video_url = video_url
        listado.video_status = 'done'
        listado.videos_creados = (listado.videos_creados or 0) + 1
        listado.save(update_fields=['datos_extra', 'video_url', 'video_status', 'videos_creados', 'updated_at'])
        logger.info(
            '[LIGHT_VIDEO] OK listado_id=%s dur=%.2fs render=%.2fs output=%s',
            listado.id,
            target_duration,
            (time.time() - started_at),
            video_url,
        )
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
