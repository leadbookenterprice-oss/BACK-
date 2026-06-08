from google import genai
from django.conf import settings
from groq import Groq
import logging
import time
import requests
import os
import random
import re
import unicodedata
import json
from api.tracking import track_api_call
from api.services.cerebras_slots import (
    CerebrasSlotUnavailable,
    estimate_cerebras_tokens,
    mark_cerebras_slot_exhausted,
    record_cerebras_slot_result,
    reserve_cerebras_slot,
    resolve_cerebras_max_completion_tokens,
)
from api.services.content_generation import (
    extract_rate_limit_headers,
    infer_step_from_task,
    record_cerebras_usage,
    retry_after_from_headers,
)
from api.services.template_contracts import (
    build_pdf_contract_text,
    get_template_contract,
    normalize_template_id as normalize_contract_template_id,
)
from api.services.ai_router import call_configured_ai

logger = logging.getLogger(__name__)
LIMIT_REACHED_MESSAGE = "Límite de generación alcanzado. Podés comprar más créditos o actualizar tu plan."
API_KEY_UNAVAILABLE_MESSAGE = "No hay una API asignada para este servicio. Pedile al admin que cargue o repare el pool de APIs."


def _settings_or_env(name, default=''):
    return (getattr(settings, name, '') or os.environ.get(name, default) or '').strip()


def _bool_env(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _allow_global_api_fallback():
    return _bool_env('ALLOW_GLOBAL_API_FALLBACK', getattr(settings, 'DEBUG', False))


CEREBRAS_CHAT_COMPLETIONS_URL = 'https://api.cerebras.ai/v1/chat/completions'
CEREBRAS_MODELS_CASCADE = [
    'gpt-oss-120b',
    'zai-glm-4.7',
]


def _get_cerebras_key(agente=None):
    from api.models import APIKey

    if agente is not None:
        return None

    if _allow_global_api_fallback():
        pool_key = APIKey.objects.filter(servicio__nombre__iexact='cerebras', status='available').first()
        if pool_key:
            return pool_key.api_key
        return _settings_or_env('CEREBRAS_API_KEY')
    return None


def _mark_cerebras_exhausted(key_value):
    try:
        from api.models import APIKey

        key_obj = APIKey.objects.filter(api_key=key_value, servicio__nombre__iexact='cerebras').first()
        if not key_obj:
            return
        key_obj.status = 'exhausted'
        key_obj.requests_today = key_obj.google_daily_limit or max(key_obj.requests_today, 1)
        key_obj.save(update_fields=['status', 'requests_today', 'updated_at'])
    except Exception:
        pass


def _is_hard_cerebras_429(response_text):
    normalized = str(response_text or '').lower()
    if not normalized:
        return False

    soft_terms = (
        'rate limit',
        'too many requests',
        'requests per minute',
        'tokens per minute',
        'rpm',
        'tpm',
        'try again',
        'retry after',
        'temporar',
    )
    if any(term in normalized for term in soft_terms):
        return False

    hard_terms = (
        'insufficient credits',
        'credit exhausted',
        'credits exhausted',
        'balance',
        'billing',
        'payment',
        'monthly quota',
        'daily quota',
        'quota exhausted',
        'quota limit',
        'project quota',
        'organization quota',
        'usage limit reached',
        'subscription',
    )
    return any(term in normalized for term in hard_terms)


def _record_cerebras_request_log(slot_id, user, *, success, status_code, elapsed_ms, tokens_used, error_message=''):
    try:
        from api.models import APIKey, APIRequestLog, Servicio

        key_obj = APIKey.objects.filter(pk=slot_id, servicio__nombre__iexact='cerebras').select_related('servicio').first() if slot_id else None
        servicio = key_obj.servicio if key_obj else Servicio.objects.filter(nombre__iexact='cerebras').first()
        if not servicio or not key_obj or not getattr(user, 'is_authenticated', False):
            return
        APIRequestLog.objects.create(
            api_key=key_obj,
            user=user,
            servicio=servicio,
            endpoint='call_cerebras_api',
            method='POST',
            success=bool(success),
            status_code=status_code,
            response_time_ms=max(int(elapsed_ms or 0), 0),
            tokens_used=max(int(tokens_used or 0), 0),
            error_message=str(error_message or '')[:500],
        )
    except Exception:
        pass


def _record_cerebras_usage_log(slot_id, user, *, listado_id=None, run_id=None, step_name=None, model='', task='',
                               success=False, status_code=None, elapsed_ms=0, estimated_tokens=0,
                               actual_tokens=None, rate_limit_headers=None, retry_after_seconds=None,
                               error_message='', metadata=None):
    try:
        record_cerebras_usage(
            slot_id=slot_id,
            user=user,
            listado_id=listado_id,
            run_id=run_id,
            step_name=step_name,
            model=model,
            task=task,
            status_code=status_code,
            success=success,
            estimated_tokens=estimated_tokens,
            actual_tokens=actual_tokens,
            response_time_ms=elapsed_ms,
            rate_limit_headers=rate_limit_headers or {},
            retry_after_seconds=retry_after_seconds,
            error_message=error_message,
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("[CEREBRAS] No se pudo registrar CerebrasUsageLog")


def normalize_elevenlabs_voice_choice(voz='femenina'):
    raw = str(voz or 'femenina').strip().lower()
    raw = ''.join(
        c for c in unicodedata.normalize('NFKD', raw)
        if not unicodedata.combining(c)
    )
    raw = re.sub(r'[^a-z0-9_\- ]+', '', raw).replace('-', '_').replace(' ', '_')
    aliases = {
        'female': 'femenina',
        'mujer': 'femenina',
        'voz_femenina': 'femenina',
        'femenino': 'femenina',
        'male': 'masculina',
        'hombre': 'masculina',
        'voz_masculina': 'masculina',
        'masculino': 'masculina',
        'energetico': 'energetica',
        'energia': 'energetica',
        'vibrante': 'energetica',
        'dinamica': 'energetica',
        'dinamico': 'energetica',
        'lujo': 'lujosa',
        'luxury': 'lujosa',
        'premium': 'lujosa',
        'sofisticada': 'lujosa',
        'sofisticado': 'lujosa',
        'custom': 'personalizada',
        'customizada': 'personalizada',
        'personalizado': 'personalizada',
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in {'femenina', 'masculina', 'energetica', 'lujosa', 'personalizada'} else 'femenina'


def resolve_elevenlabs_voice_profile(voz='femenina', voice_id=None, voice_settings=None):
    choice = normalize_elevenlabs_voice_choice(voz)
    env_female = _settings_or_env('ELEVENLABS_VOICE_ID_FEMALE')
    env_male = _settings_or_env('ELEVENLABS_VOICE_ID_MALE')
    env_energetic = _settings_or_env('ELEVENLABS_VOICE_ID_ENERGETIC') or _settings_or_env('ELEVENLABS_VOICE_ID_ENERGETICA')
    env_luxury = _settings_or_env('ELEVENLABS_VOICE_ID_LUXURY') or _settings_or_env('ELEVENLABS_VOICE_ID_LUJOSA')
    env_custom = _settings_or_env('ELEVENLABS_VOICE_ID_CUSTOM') or _settings_or_env('ELEVENLABS_VOICE_ID_PERSONALIZADA')

    default_female = "EXAVITQu4vr4xnSDxMaL"
    default_male = "21m00Tcm4TlvDq8ikWAM"
    legacy_male = "pNInz6obpgnuMvHLW6m8"

    candidate_map = {
        'femenina': [env_female, default_female, env_male, default_male, legacy_male],
        'masculina': [env_male, default_male, env_female, default_female, legacy_male],
        'energetica': [env_energetic, env_female, default_female, env_male, default_male, legacy_male],
        'lujosa': [env_luxury, env_female, default_female, env_male, default_male, legacy_male],
        'personalizada': [voice_id, env_custom, env_female, default_female, env_male, default_male, legacy_male],
    }

    settings_map = {
        'femenina': {'stability': 0.50, 'similarity_boost': 0.65, 'style': 0.25, 'use_speaker_boost': True},
        'masculina': {'stability': 0.55, 'similarity_boost': 0.65, 'style': 0.20, 'use_speaker_boost': True},
        'energetica': {'stability': 0.35, 'similarity_boost': 0.75, 'style': 0.75, 'use_speaker_boost': True},
        'lujosa': {'stability': 0.72, 'similarity_boost': 0.85, 'style': 0.35, 'use_speaker_boost': True},
        'personalizada': {'stability': 0.55, 'similarity_boost': 0.75, 'style': 0.45, 'use_speaker_boost': True},
    }

    filtered_candidates = []
    for candidate in candidate_map[choice]:
        candidate = str(candidate or '').strip()
        if candidate and candidate not in filtered_candidates:
            filtered_candidates.append(candidate)

    resolved_settings = dict(settings_map[choice])
    if isinstance(voice_settings, dict):
        for key in ('stability', 'similarity_boost', 'style'):
            if key in voice_settings:
                try:
                    resolved_settings[key] = float(voice_settings[key])
                except Exception:
                    pass
        if 'use_speaker_boost' in voice_settings:
            resolved_settings['use_speaker_boost'] = bool(voice_settings['use_speaker_boost'])

    return choice, filtered_candidates, resolved_settings

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
    # Nuevas variaciones mediterráneas
    'costa_serena': {
        'primario': '#2f5d73',
        'secundario': '#4d7f96',
        'acento': '#d3a45f',
    },
    'oliva_natural': {
        'primario': '#3f4a3c',
        'secundario': '#5c6b58',
        'acento': '#bfa37a',
    },
    'terracota_suave': {
        'primario': '#7d4434',
        'secundario': '#9c5c49',
        'acento': '#e0ad8d',
    },
    'brisa_calida': {
        'primario': '#8e5539',
        'secundario': '#b07153',
        'acento': '#e2a76f',
    },
    'arena_clara': {
        'primario': '#6b6355',
        'secundario': '#877e70',
        'acento': '#ccae85',
    },
}

TEMPLATE_IDS = (
    'costa_serena',
    'oliva_natural',
    'terracota_suave',
    'brisa_calida',
    'arena_clara',
    'dubai_night',
    'beverly_hills',
    'manhattan',
    'mediterraneo',
    'tech_modern',
)


def _resolve_theme_from_context(context, template_file):
    tokens = context.get('template_tokens') if isinstance(context, dict) else None
    
    # 1. Determinar el template_id para buscar los colores correctos
    template_id = None
    if isinstance(context, dict) and context.get('template_id'):
        template_id = _normalize_template_id(context.get('template_id'))
        
    if not template_id and template_file:
        template_id = template_file.replace('template_', '').replace('.html', '')

    # 2. Buscar en TEMPLATE_COLORES usando el id o el nombre del archivo
    base = {}
    if template_id:
        contract = get_template_contract(template_id)
        if contract:
            colors = contract.get('colors') or {}
            base = {
                'primario': colors.get('primary'),
                'secundario': colors.get('secondary'),
                'acento': colors.get('accent'),
            }
        else:
            base = TEMPLATE_COLORES.get(template_id, {})
    if not base and template_file:
        base = TEMPLATE_COLORES.get(template_file, {})
        
    if not isinstance(tokens, dict):
        return {
            'primario': base.get('primario', '#0d47a1'),
            'secundario': base.get('secundario', '#1565c0'),
            'acento': base.get('acento', '#00e5ff'),
            'display_font': 'DM Sans',
            'body_font': 'DM Sans',
            'mono_font': 'Space Mono',
            'font_import_url': '',
        }

    palette = tokens.get('palette') if isinstance(tokens.get('palette'), dict) else {}
    typography = tokens.get('typography') if isinstance(tokens.get('typography'), dict) else {}
    return {
        'primario': palette.get('primary', base.get('primario', '#0d47a1')),
        'secundario': palette.get('secondary', base.get('secundario', '#1565c0')),
        'acento': palette.get('accent', base.get('acento', '#00e5ff')),
        'display_font': typography.get('display', 'DM Sans'),
        'body_font': typography.get('body', 'DM Sans'),
        'mono_font': typography.get('mono', 'Space Mono'),
        'font_import_url': typography.get('font_import_url', ''),
    }


def _normalize_template_id(value):
    if not value:
        return None
    template_id = str(value).strip().lower()
    template_id = template_id.replace('template_', '').replace('post_', '').replace('.html', '')
    if template_id in TEMPLATE_IDS:
        return template_id
    return None


def _template_file_from_id(template_id):
    normalized = _normalize_template_id(template_id)
    if not normalized:
        return None
        
    # Mapeo de plantilla a archivo HTML base físico
    base_files = {
        'costa_serena': 'template_mediterraneo.html',
        'oliva_natural': 'template_beverly_hills.html',
        'terracota_suave': 'template_dubai_night.html',
        'brisa_calida': 'template_manhattan.html',
        'arena_clara': 'template_tech_modern.html',
        'dubai_night': 'template_dubai_night.html',
        'beverly_hills': 'template_beverly_hills.html',
        'manhattan': 'template_manhattan.html',
        'mediterraneo': 'template_mediterraneo.html',
        'tech_modern': 'template_tech_modern.html',
    }
    return base_files.get(normalized, f'template_{normalized}.html')


def _render_conditional_block(html_text, key, enabled, replacements=None):
    if not isinstance(html_text, str):
        return html_text

    replacements = replacements or {}
    key_escaped = re.escape(str(key))

    # Bloque con else
    pattern_with_else = re.compile(
        rf'\{{\{{#if {key_escaped}\}}\}}(.*?)\{{\{{else\}}\}}(.*?)\{{\{{/if\}}\}}',
        flags=re.DOTALL,
    )

    def _replace_with_else(match):
        chunk = match.group(1) if enabled else match.group(2)
        for token, value in replacements.items():
            chunk = chunk.replace(token, value)
        return chunk

    rendered = pattern_with_else.sub(_replace_with_else, html_text)

    # Bloque sin else
    pattern_plain = re.compile(rf'\{{\{{#if {key_escaped}\}}\}}(.*?)\{{\{{/if\}}\}}', flags=re.DOTALL)

    if enabled:
        def _replace_plain(match):
            chunk = match.group(1)
            for token, value in replacements.items():
                chunk = chunk.replace(token, value)
            return chunk

        rendered = pattern_plain.sub(_replace_plain, rendered)
    else:
        rendered = pattern_plain.sub('', rendered)

    return rendered


def _pdf_inline_icon(name='check'):
    paths = {
        'bed': '<path d="M4 11V6"/><path d="M20 18v-5a4 4 0 0 0-4-4H9a5 5 0 0 0-5 5v4"/><path d="M4 14h16"/><path d="M4 18h16"/>',
        'bath': '<path d="M4 12h16v2a6 6 0 0 1-6 6H10a6 6 0 0 1-6-6v-2Z"/><path d="M7 12V6a3 3 0 0 1 6 0"/>',
        'ruler': '<path d="M4 18 18 4l2 2L6 20l-2-2Z"/><path d="m8 14 2 2"/><path d="m11 11 2 2"/><path d="m14 8 2 2"/>',
        'car': '<path d="M5 12 7 7h10l2 5"/><path d="M4 12h16v5H4z"/><circle cx="7" cy="17" r="1.5"/><circle cx="17" cy="17" r="1.5"/>',
        'location': '<path d="M12 21s7-5.2 7-11a7 7 0 0 0-14 0c0 5.8 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
        'check': '<path d="m5 13 4 4L19 7"/>',
    }
    return (
        '<svg class="pdf-inline-icon" viewBox="0 0 24 24" aria-hidden="true" '
        'style="display:inline-block;width:1em;height:1em;fill:none;stroke:currentColor;stroke-width:2;'
        'stroke-linecap:round;stroke-linejoin:round;vertical-align:-0.12em;flex-shrink:0">'
        f'{paths.get(name, paths["check"])}</svg>'
    )


def _replace_fontawesome_icons(html_text):
    if not isinstance(html_text, str):
        return html_text

    cleaned = re.sub(
        r'<link[^>]+(?:font-awesome|cdnjs\.cloudflare\.com/ajax/libs/font-awesome)[^>]*>\s*',
        '',
        html_text,
        flags=re.IGNORECASE,
    )

    def icon_for_class(match):
        class_attr = match.group(1).lower()
        if 'fa-bed' in class_attr:
            return _pdf_inline_icon('bed')
        if 'fa-bath' in class_attr:
            return _pdf_inline_icon('bath')
        if 'fa-ruler' in class_attr:
            return _pdf_inline_icon('ruler')
        if 'fa-car' in class_attr:
            return _pdf_inline_icon('car')
        if 'fa-location' in class_attr:
            return _pdf_inline_icon('location')
        return _pdf_inline_icon('check')

    return re.sub(
        r'<i\s+class=["\']([^"\']*\bfa-[^"\']*)["\']\s*>\s*</i>',
        icon_for_class,
        cleaned,
        flags=re.IGNORECASE,
    )


def _format_phone_display(value):
    raw = str(value or '').strip()
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ''

    if raw.startswith('+'):
        normalized = f'+{digits}'
    else:
        normalized = f'+{digits}'

    country = ''
    area = ''
    local = ''

    if digits.startswith('54') and len(digits) >= 10:
        country = '54'
        rest = digits[2:]
        if rest.startswith('9') and len(rest) > 5:
            rest = rest[1:]
        if len(rest) >= 10:
            area = rest[:4]
            local = rest[4:]
        elif len(rest) >= 8:
            area = rest[:3]
            local = rest[3:]
        else:
            local = rest
    else:
        local = digits

    if country and area and local:
        return f'+{country} {area} {local}'
    return normalized

def generar_html_desde_template(context, agente):
    """
    Genera HTML usando un template prediseñado.
    Gemini solo elige los colores según el estilo de la propiedad.
    """
    print(f"[Template DEBUG] context keys: {list(context.keys())}")
    print(f"[Template DEBUG] portada_url raw: {repr(context.get('portada_url', 'NO EXISTE'))}")
    print(f"[Template DEBUG] portadaUrl raw: {repr(context.get('portadaUrl', 'NO EXISTE'))}")
    
    # 1. Resolver template con prioridad: payload/contexto -> DB -> aleatorio
    template_id = _normalize_template_id(context.get('template_id'))
    template_elegido = _template_file_from_id(template_id)

    listado_id = context.get('listado_id')
    listado = None

    if listado_id:
        try:
            from .models import Listado
            listado = Listado.objects.filter(id=listado_id).first()
            if listado and not template_elegido:
                datos = listado.datos_extra or {}
                template_id_db = _normalize_template_id(datos.get('template_id') or datos.get('template'))
                template_elegido = _template_file_from_id(template_id_db)
        except Exception as e:
            print(f"[Template] Error leyendo template en DB: {e}")

    if not template_elegido:
        template_elegido = random.choice(list(TEMPLATE_COLORES.keys()))

    template_id = _normalize_template_id(context.get('template_id')) or template_elegido.replace('template_', '').replace('.html', '')
    context['template_id'] = template_id

    if listado:
        try:
            datos = listado.datos_extra or {}
            datos['template_id'] = template_id
            datos['template'] = template_id
            listado.datos_extra = datos
            listado.save(update_fields=['datos_extra'])
            print(f"[Template] Guardado template en DB: {template_id}")
        except Exception as e:
            print(f"[Template] Error guardando template: {e}")
    
    # 2. Leer el template
    template_path = os.path.join(TEMPLATES_DIR, template_elegido)
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 3. Aplicar colores del template
    theme = _resolve_theme_from_context(context, template_elegido)
    html = html.replace('{{COLOR_PRIMARIO}}', theme['primario'])
    html = html.replace('{{COLOR_SECUNDARIO}}', theme['secundario'])
    html = html.replace('{{COLOR_ACENTO}}', theme['acento'])
    html = html.replace('{{ICON_TOTAL}}', _pdf_inline_icon('ruler'))
    html = html.replace('{{ICON_RECAMARAS}}', _pdf_inline_icon('bed'))
    html = html.replace('{{ICON_BANOS}}', _pdf_inline_icon('bath'))
    html = html.replace('{{ICON_CUBIERTA}}', _pdf_inline_icon('ruler'))
    html = html.replace('{{ICON_ESTACIONAMIENTOS}}', _pdf_inline_icon('car'))
    
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
    agent_phone_raw = str(context.get('agente_telefono', '') or '').strip()
    phone_href = ''.join(ch for ch in agent_phone_raw if ch.isdigit())
    if phone_href:
        phone_href = f'+{phone_href}'
    phone_display = _format_phone_display(agent_phone_raw)

    html = html.replace('{{AGENTE_NOMBRE}}', str(context.get('agente_nombre', '')))
    html = html.replace('{{AGENTE_TELEFONO}}', phone_display)
    html = html.replace('{{AGENTE_TELEFONO_DISPLAY}}', phone_display)
    html = html.replace('{{AGENTE_TELEFONO_HREF}}', phone_href)
    html = html.replace('{{AGENTE_EMAIL}}', str(context.get('agente_email', '')))
    html = html.replace('{{AGENCIA_NOMBRE}}', str(context.get('agencia_nombre', '')))
    html = html.replace('{{AGENTE_CONTACTO_HTML}}', str(context.get('agente_contacto_html', '')))
    html = html.replace('{{WHATSAPP_URL}}', str(context.get('whatsapp_url', '')))
    
    # 5. Logo de agencia
    logo_url = context.get('logo_url_raw', '')
    html = _render_conditional_block(
        html,
        'LOGO_AGENCIA',
        bool(logo_url),
        replacements={'{{LOGO_AGENCIA}}': str(logo_url or '')},
    )
    
    # 6. Foto del agente (perfil)
    agent_photo_raw = (
        context.get('agente_foto_url', '')
        or context.get('agente_foto', '')
    )
    if isinstance(agent_photo_raw, dict) and 'public_id' in agent_photo_raw:
        cloud = agent_photo_raw.get('cloudinary_account', 'df1vldrhb')
        pid = agent_photo_raw.get('public_id', '')
        agent_photo = f"https://res.cloudinary.com/{cloud}/image/upload/{pid}"
    elif isinstance(agent_photo_raw, str) and agent_photo_raw.startswith('http'):
        agent_photo = re.sub(r's--[^/]+--/', '', agent_photo_raw)
    else:
        agent_photo = ''
    html = _render_conditional_block(
        html,
        'AGENTE_FOTO',
        bool(agent_photo),
        replacements={'{{AGENTE_FOTO}}': agent_photo},
    )

    # 7. QR en base64 — CRÍTICO: reemplazar antes de cualquier otra cosa
    qr_code = context.get('qr_code', '')
    print(f"[Template] QR code presente: {bool(qr_code)}, largo: {len(str(qr_code))}")
    html = _render_conditional_block(
        html,
        'QR_CODE',
        bool(qr_code),
        replacements={'{{QR_CODE}}': str(qr_code or '')},
    )

    whatsapp_url = str(context.get('whatsapp_url', '') or '')
    html = _render_conditional_block(
        html,
        'WHATSAPP_URL',
        bool(whatsapp_url),
        replacements={'{{WHATSAPP_URL}}': whatsapp_url},
    )
    
    # 8. Foto de portada: usar la fuente principal del listado antes que la galeria.
    def _build_cloudinary_url(val):
        if isinstance(val, dict):
            direct_url = val.get('secure_url') or val.get('url')
            if isinstance(direct_url, str) and direct_url.startswith('http'):
                import re as re_module
                return re_module.sub(r's--[^/]+--/', '', direct_url)
            if val.get('public_id'):
                cloud = val.get('cloudinary_account') or val.get('cloud_name') or 'df1vldrhb'
                pid = val.get('public_id', '')
                return f"https://res.cloudinary.com/{cloud}/image/upload/{pid}"
        elif isinstance(val, str) and val.startswith('http'):
            import re as re_module
            return re_module.sub(r's--[^/]+--/', '', val)
        return ''

    portada_url = _build_cloudinary_url(
        context.get('portada_url', '') or context.get('portada_url_raw', '')
    )
    fotos_raw = context.get('fotos_recorrido_raw', [])
    if not isinstance(fotos_raw, list):
        fotos_raw = []

    if not portada_url and fotos_raw:
        portada_url = _build_cloudinary_url(fotos_raw[0])
    print(f"[Template] Portada URL FINAL: {portada_url}")
    html = html.replace('{{FOTO_PORTADA}}', portada_url)

    
    # 9. Fotos de galería
    galeria_html = ''
    for i, foto in enumerate(fotos_raw):
        foto_url = _build_cloudinary_url(foto)
        if foto_url:
            galeria_html += f'<img class="galeria-foto" src="{foto_url}" alt="Foto {i+1}">\n'

    html = html.replace('{{GALERIA_FOTOS}}', galeria_html)
    
    # 10. Amenidades — generar chips HTML (ANTES DE LIMPIAR)
    amenidades = context.get('amenidades', [])
    print(f"[Template] Amenidades: {amenidades}")
    amenity_icon = _pdf_inline_icon('check')
    chips_html = ''.join([f'<span class="amenidad-chip">{amenity_icon}{a}</span>' for a in amenidades])
    html = html.replace('{{AMENIDADES}}', chips_html)

    # Limpiar cualquier placeholder restante
    html = re.sub(r'\{\{#if [^}]+\}\}', '', html)
    html = re.sub(r'\{\{else\}\}', '', html)
    html = re.sub(r'\{\{/if\}\}', '', html)
    html = re.sub(r'\{\{[^}]+\}\}', '', html)

    if '</head>' in html:
        font_link = f'<link rel="stylesheet" href="{theme["font_import_url"]}">' if theme.get('font_import_url') else ''
        override = (
            '<style id="brand-template-overrides">'
            f"body{{font-family:'{theme['body_font']}',sans-serif !important;}}"
            f"h1,h2,h3,.hero-titulo,.section-title{{font-family:'{theme['display_font']}',sans-serif !important;}}"
            f".stat-label,.badge-operacion,.qr-label{{font-family:'{theme['mono_font']}',sans-serif !important;}}"
            '</style>'
        )
        html = html.replace('</head>', f'{font_link}{override}</head>', 1)
    
    
    html = _replace_fontawesome_icons(html)
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

# Cascada Cerebras Paso 1 — solo texto, rápidos
PASO1_CASCADE = [
    ('cerebras', 'gpt-oss-120b'),
    ('cerebras', 'zai-glm-4.7'),
]

# Cascada Cerebras Paso 2 — solo texto
PASO2_CASCADE = [
    ('cerebras', 'gpt-oss-120b'),
    ('cerebras', 'zai-glm-4.7'),
]

def _get_nvidia_key():
    from api.models import APIKey
    pool_key = APIKey.objects.filter(servicio__nombre__iexact='nvidia', status='available').first()
    if pool_key:
        return pool_key.api_key
    return settings.NVIDIA_API_KEY

def _get_gemini_key():
    from api.models import APIKey
    pool_key = APIKey.objects.filter(servicio__nombre__iexact='gemini', status='available').first()
    if pool_key:
        return pool_key.api_key
    return settings.GEMINI_API_KEY

def _get_groq_key():
    from api.models import APIKey
    pool_key = APIKey.objects.filter(servicio__nombre__iexact='groq', status='available').first()
    if pool_key:
        return pool_key.api_key
    return settings.GROQ_API_KEY


# Excepción especial para cuota mensual de Gemini agotada.
# Los views la capturan y devuelven HTTP 429 con mensaje canonico.
class GeminiQuotaExhaustedError(Exception):
    """Cuota mensual/diaria de Gemini agotada. No tiene solución con reintentos."""
    def __init__(
        self,
        message=LIMIT_REACHED_MESSAGE,
        *,
        provider='gemini',
        scope='provider',
        quota_state='hard_exhausted',
        retry_after_seconds=None,
    ):
        super().__init__(message)
        self.provider = provider
        self.scope = scope
        self.quota_state = quota_state
        self.retry_after_seconds = retry_after_seconds


class GeminiRateLimitedError(Exception):
    """Rate limit/saturación transitoria de Gemini."""
    def __init__(
        self,
        message="Servicio de IA temporalmente saturado. Reintentá en 10 minutos.",
        *,
        provider='gemini',
        scope='provider',
        quota_state='soft_rate_limited',
        retry_after_seconds=600,
    ):
        super().__init__(message)
        self.provider = provider
        self.scope = scope
        self.quota_state = quota_state
        self.retry_after_seconds = retry_after_seconds


class ElevenLabsQuotaExhaustedError(Exception):
    """Cuota real agotada de ElevenLabs."""
    def __init__(
        self,
        message=LIMIT_REACHED_MESSAGE,
        *,
        provider='elevenlabs',
        scope='provider',
        quota_state='hard_exhausted',
        retry_after_seconds=None,
    ):
        super().__init__(message)
        self.provider = provider
        self.scope = scope
        self.quota_state = quota_state
        self.retry_after_seconds = retry_after_seconds


class ElevenLabsRateLimitedError(Exception):
    """Rate limit/saturación transitoria de ElevenLabs."""
    def __init__(
        self,
        message="Servicio de voz temporalmente saturado. Reintentá en 10 minutos.",
        *,
        provider='elevenlabs',
        scope='provider',
        quota_state='soft_rate_limited',
        retry_after_seconds=600,
    ):
        super().__init__(message)
        self.provider = provider
        self.scope = scope
        self.quota_state = quota_state
        self.retry_after_seconds = retry_after_seconds


class APIKeyUnavailableError(Exception):
    """El usuario no tiene una API key asignada o el pool no tiene stock disponible."""
    def __init__(
        self,
        message=API_KEY_UNAVAILABLE_MESSAGE,
        *,
        provider='generic',
        scope='pool',
        quota_state='hard_exhausted',
        retry_after_seconds=None,
    ):
        super().__init__(message)
        self.provider = provider
        self.scope = scope
        self.quota_state = quota_state
        self.retry_after_seconds = retry_after_seconds

def call_gemini_api(prompt: str, agente=None, **kwargs) -> str:
    """Llama a Gemini usando una key activa del pool/admin o la env var."""
    key = _get_gemini_key()
    if not key:
        raise APIKeyUnavailableError(
            "No hay Gemini API Key disponible.",
            provider='gemini',
            scope='pool',
            quota_state='hard_exhausted',
        )

    system_prompt = str(kwargs.get('system_prompt') or '').strip()
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    model = kwargs.get('model') or 'gemini-2.5-flash-lite'

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
        )
        return str(getattr(response, 'text', '') or '').strip()
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if any(term in lowered for term in ('resource_exhausted', 'quota', 'billing', 'exceeded')):
            raise GeminiQuotaExhaustedError(message) from exc
        if any(term in lowered for term in ('rate limit', 'too many requests', '429')):
            raise GeminiRateLimitedError(message) from exc
        raise

def call_groq_api(prompt: str, **kwargs) -> str:
    """
    Llama a Groq. Usa modelos soportados (llama3-8b-8192 fue decomisionado).
    Permite override de modelo por kwargs['model'].
    """
    key = _get_groq_key() or os.environ.get('GROQ_API_KEY', '')
    if not key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    client = Groq(api_key=key)
    system_prompt = kwargs.get('system_prompt', '')
    model = kwargs.get('model') or 'llama-3.1-8b-instant'
    allow_model_fallback = kwargs.get('allow_model_fallback', True)

    # Lista de fallback para robustez ante deprecaciones
    modelos_fallback = [model] if not allow_model_fallback else [
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


def call_cerebras_api(prompt: str, agente=None, **kwargs) -> str:
    """Llama a Cerebras usando un slot backend temporal, no una key asignada al usuario."""
    system_prompt = kwargs.get('system_prompt', '')
    task = kwargs.get('task') or 'general'
    listado_id = kwargs.get('listado_id') or kwargs.get('listadoId')
    generation_run_id = kwargs.get('generation_run_id') or kwargs.get('generationRunId')
    generation_step = (
        kwargs.get('generation_step')
        or kwargs.get('generationStep')
        or infer_step_from_task(task)
    )
    max_completion_tokens = resolve_cerebras_max_completion_tokens(
        task,
        kwargs.get('max_completion_tokens'),
    )
    extra_metadata = kwargs.get('metadata') if isinstance(kwargs.get('metadata'), dict) else {}
    estimated_tokens = estimate_cerebras_tokens(
        prompt,
        system_prompt=system_prompt,
        max_completion_tokens=max_completion_tokens,
    )

    slot = None
    key = None
    if agente is not None:
        try:
            slot = reserve_cerebras_slot(
                agente,
                listado_id=listado_id,
                estimated_tokens=estimated_tokens,
            )
            key = slot.api_key
        except CerebrasSlotUnavailable as exc:
            raise APIKeyUnavailableError(
                str(exc),
                provider='cerebras',
                scope=getattr(exc, 'scope', 'slot'),
                quota_state=getattr(exc, 'quota_state', 'soft_rate_limited'),
                retry_after_seconds=getattr(exc, 'retry_after_seconds', None),
            )
    else:
        key = _get_cerebras_key(agente=None)

    if not key:
        raise APIKeyUnavailableError(
            'No hay slot Cerebras disponible para esta generación.',
            provider='cerebras',
            scope='pool',
        )

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    requested_model = kwargs.get('model') or CEREBRAS_MODELS_CASCADE[0]
    allow_model_fallback = kwargs.get('allow_model_fallback', True)
    models_fallback = [requested_model] if not allow_model_fallback else [requested_model] + [m for m in CEREBRAS_MODELS_CASCADE if m != requested_model]
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }
    payload_base = {
        'messages': [{'role': 'user', 'content': full_prompt}],
        'stream': False,
        'temperature': kwargs.get('temperature', 0.7),
        'top_p': kwargs.get('top_p', 1),
        'max_completion_tokens': max_completion_tokens,
    }

    if system_prompt:
        payload_base['messages'] = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ]

    last_err = None
    last_status_code = None
    for model_id in models_fallback:
        payload = dict(payload_base)
        payload['model'] = model_id
        attempt_started_at = time.time()
        attempt_recorded = False
        try:
            response = requests.post(CEREBRAS_CHAT_COMPLETIONS_URL, json=payload, headers=headers, timeout=60)
            last_status_code = response.status_code
            elapsed_ms = int((time.time() - attempt_started_at) * 1000)
            rate_limit_headers = extract_rate_limit_headers(response.headers)
            if response.status_code == 200:
                data = response.json() if response.content else {}
                content = ((data.get('choices') or [{}])[0].get('message') or {}).get('content')
                usage = data.get('usage') or {}
                actual_tokens_value, usage_metadata = _extract_cerebras_usage_tokens(usage)
                usage_extra_metadata = {**extra_metadata, **usage_metadata}
                if content:
                    if slot:
                        record_cerebras_slot_result(
                            slot.key_id,
                            estimated_tokens=estimated_tokens,
                            actual_tokens=actual_tokens_value,
                            success=True,
                        )
                        _record_cerebras_request_log(
                            slot.key_id,
                            agente,
                            success=True,
                            status_code=response.status_code,
                            elapsed_ms=elapsed_ms,
                            tokens_used=actual_tokens_value if actual_tokens_value is not None else estimated_tokens,
                        )
                    _record_cerebras_usage_log(
                        slot.key_id if slot else None,
                        agente,
                        listado_id=listado_id,
                        run_id=generation_run_id,
                        step_name=generation_step,
                        model=model_id,
                        task=task,
                        success=True,
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        estimated_tokens=estimated_tokens,
                        actual_tokens=actual_tokens_value,
                        rate_limit_headers=rate_limit_headers,
                        metadata={'max_completion_tokens': max_completion_tokens, **usage_extra_metadata},
                    )
                    attempt_recorded = True
                    return content

                last_err = RuntimeError('Cerebras devolvio una respuesta vacia')
                if slot:
                    record_cerebras_slot_result(
                        slot.key_id,
                        estimated_tokens=estimated_tokens,
                        success=False,
                        error_message=last_err,
                    )
                    _record_cerebras_request_log(
                        slot.key_id,
                        agente,
                        success=False,
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        tokens_used=0,
                        error_message=last_err,
                    )
                _record_cerebras_usage_log(
                    slot.key_id if slot else None,
                    agente,
                    listado_id=listado_id,
                    run_id=generation_run_id,
                    step_name=generation_step,
                    model=model_id,
                    task=task,
                    success=False,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    estimated_tokens=estimated_tokens,
                    actual_tokens=actual_tokens_value,
                    rate_limit_headers=rate_limit_headers,
                    error_message=last_err,
                    metadata={'max_completion_tokens': max_completion_tokens, 'empty_response': True, **usage_extra_metadata},
                )
                attempt_recorded = True
                continue

            response_text = str(getattr(response, 'text', '') or '')
            normalized = response_text.lower()
            if response.status_code in (401, 403):
                if slot:
                    record_cerebras_slot_result(
                        slot.key_id,
                        estimated_tokens=estimated_tokens,
                        success=False,
                        error_message=response_text or 'Cerebras auth failed',
                    )
                    _record_cerebras_request_log(
                        slot.key_id,
                        agente,
                        success=False,
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        tokens_used=0,
                        error_message=response_text or 'Cerebras auth failed',
                    )
                _record_cerebras_usage_log(
                    slot.key_id if slot else None,
                    agente,
                    listado_id=listado_id,
                    run_id=generation_run_id,
                    step_name=generation_step,
                    model=model_id,
                    task=task,
                    success=False,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    estimated_tokens=estimated_tokens,
                    rate_limit_headers=rate_limit_headers,
                    error_message=response_text or 'Cerebras auth failed',
                    metadata={'max_completion_tokens': max_completion_tokens, **extra_metadata},
                )
                attempt_recorded = True
                if slot:
                    mark_cerebras_slot_exhausted(slot.key_id, response_text or 'Cerebras auth failed')
                raise APIKeyUnavailableError(
                    API_KEY_UNAVAILABLE_MESSAGE,
                    provider='cerebras',
                    scope='pool',
                )

            if response.status_code == 429:
                retry_after_seconds = retry_after_from_headers(rate_limit_headers, 600)
                if slot:
                    record_cerebras_slot_result(
                        slot.key_id,
                        estimated_tokens=estimated_tokens,
                        success=False,
                        error_message=response_text or 'Cerebras rate limited',
                    )
                    _record_cerebras_request_log(
                        slot.key_id,
                        agente,
                        success=False,
                        status_code=response.status_code,
                        elapsed_ms=elapsed_ms,
                        tokens_used=0,
                        error_message=response_text or 'Cerebras rate limited',
                    )
                _record_cerebras_usage_log(
                    slot.key_id if slot else None,
                    agente,
                    listado_id=listado_id,
                    run_id=generation_run_id,
                    step_name=generation_step,
                    model=model_id,
                    task=task,
                    success=False,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    estimated_tokens=estimated_tokens,
                    rate_limit_headers=rate_limit_headers,
                    retry_after_seconds=retry_after_seconds,
                    error_message=response_text or 'Cerebras rate limited',
                    metadata={'max_completion_tokens': max_completion_tokens, **extra_metadata},
                )
                attempt_recorded = True
                if _is_hard_cerebras_429(normalized):
                    if slot:
                        mark_cerebras_slot_exhausted(slot.key_id, response_text or 'Cerebras quota exhausted')
                    else:
                        _mark_cerebras_exhausted(key)
                    raise GeminiQuotaExhaustedError(
                        LIMIT_REACHED_MESSAGE,
                        provider='cerebras',
                        scope='provider',
                        quota_state='hard_exhausted',
                    )
                raise GeminiRateLimitedError(
                    "Cerebras esta temporalmente saturado. Reintenta en 10 minutos.",
                    provider='cerebras',
                    scope='provider',
                    quota_state='soft_rate_limited',
                    retry_after_seconds=retry_after_seconds,
                )

            model_terms = ('model', 'not found', 'invalid model', 'unsupported model', 'deprecated')
            error_obj = RuntimeError(response_text or f'Error Cerebras ({response.status_code})')
            if slot:
                record_cerebras_slot_result(
                    slot.key_id,
                    estimated_tokens=estimated_tokens,
                    success=False,
                    error_message=error_obj,
                )
                _record_cerebras_request_log(
                    slot.key_id,
                    agente,
                    success=False,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    tokens_used=0,
                    error_message=error_obj,
                )
            _record_cerebras_usage_log(
                slot.key_id if slot else None,
                agente,
                listado_id=listado_id,
                run_id=generation_run_id,
                step_name=generation_step,
                model=model_id,
                task=task,
                success=False,
                status_code=response.status_code,
                elapsed_ms=elapsed_ms,
                estimated_tokens=estimated_tokens,
                rate_limit_headers=rate_limit_headers,
                error_message=error_obj,
                metadata={'max_completion_tokens': max_completion_tokens, **extra_metadata},
            )
            attempt_recorded = True
            if any(term in normalized for term in model_terms):
                last_err = RuntimeError(response_text or f'Modelo Cerebras no soportado: {model_id}')
                continue

            last_err = error_obj
        except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError) as exc:
            if slot and not attempt_recorded:
                record_cerebras_slot_result(
                    slot.key_id,
                    estimated_tokens=estimated_tokens,
                    success=False,
                    error_message=exc,
                )
                _record_cerebras_request_log(
                    slot.key_id,
                    agente,
                    success=False,
                    status_code=last_status_code or 500,
                    elapsed_ms=int((time.time() - attempt_started_at) * 1000),
                    tokens_used=0,
                    error_message=exc,
                )
                _record_cerebras_usage_log(
                    slot.key_id,
                    agente,
                    listado_id=listado_id,
                    run_id=generation_run_id,
                    step_name=generation_step,
                    model=model_id,
                    task=task,
                    success=False,
                    status_code=last_status_code or 500,
                    elapsed_ms=int((time.time() - attempt_started_at) * 1000),
                    estimated_tokens=estimated_tokens,
                    error_message=exc,
                    metadata={'max_completion_tokens': max_completion_tokens, **extra_metadata},
                )
            raise
        except Exception as exc:
            last_err = exc
            if slot and not attempt_recorded:
                record_cerebras_slot_result(
                    slot.key_id,
                    estimated_tokens=estimated_tokens,
                    success=False,
                    error_message=last_err,
                )
                _record_cerebras_request_log(
                    slot.key_id,
                    agente,
                    success=False,
                    status_code=last_status_code or 500,
                    elapsed_ms=int((time.time() - attempt_started_at) * 1000),
                    tokens_used=0,
                    error_message=last_err,
                )
                _record_cerebras_usage_log(
                    slot.key_id,
                    agente,
                    listado_id=listado_id,
                    run_id=generation_run_id,
                    step_name=generation_step,
                    model=model_id,
                    task=task,
                    success=False,
                    status_code=last_status_code or 500,
                    elapsed_ms=int((time.time() - attempt_started_at) * 1000),
                    estimated_tokens=estimated_tokens,
                    error_message=last_err,
                    metadata={'max_completion_tokens': max_completion_tokens, **extra_metadata},
                )

    if last_err:
        raise last_err
    return None

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
    except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError):
        raise
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
    import time
    for attempt in range(retries):
        try:
            result = call_configured_ai(prompt, agente=agente, **kwargs)
            if result:
                return result
        except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError):
            raise
        except Exception as e:
            print(f"AI root attempt {attempt+1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(1)
    return None


def _clip_text(value, max_chars=900):
    text = str(value or '').strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + '...'


def _as_clean_list(value, limit=8):
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        text = str(item or '').strip()
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _build_controlled_pdf_html_prompt(context):
    template_id = normalize_contract_template_id(context.get('template_id')) or 'tech_modern'
    contract = get_template_contract(template_id)
    if not contract:
        return None, None

    gallery = _as_clean_list(context.get('fotos_recorrido_raw') or context.get('fotos_recorrido'), limit=6)
    amenities = _as_clean_list(context.get('amenidades'), limit=12)
    payload = {
        'template_contract': build_pdf_contract_text(template_id),
        'property': {
            'title': f"{context.get('tipo_propiedad') or 'Propiedad'} en {context.get('ciudad') or ''}".strip(),
            'type': context.get('tipo_propiedad') or 'Propiedad',
            'operation': context.get('operacion') or 'Venta',
            'city': context.get('ciudad') or '',
            'price': f"{context.get('moneda') or 'USD'} {context.get('precio') or ''}".strip(),
            'bedrooms': context.get('recamaras') or 'N/A',
            'bathrooms': context.get('banos') or 'N/A',
            'covered_area': context.get('superficie_cubierta') or 'N/A',
            'total_area': context.get('superficie_total') or 'N/A',
            'parking': context.get('estacionamientos') or 'N/A',
            'description': _clip_text(context.get('descripcion'), 1100),
            'amenities': amenities,
        },
        'media': {
            'cover_url': context.get('portada_url') or '',
            'gallery_urls': gallery,
            'agency_logo_url': context.get('logo_url') or context.get('agencia_logo_url') or '',
            'agent_photo_url': context.get('agente_foto_url') or '',
            'qr_url': context.get('qr_code') or '',
        },
        'agent': {
            'name': context.get('agente_nombre') or '',
            'role': context.get('agente_rol') or 'Asesor Comercial',
            'phone': context.get('agente_telefono') or '',
            'email': context.get('agente_email') or '',
            'agency': context.get('agencia_nombre') or '',
            'contact_html': context.get('agente_contacto_html') or '',
        },
    }

    colors = contract['colors']
    fonts = contract['fonts']
    prompt = f"""
Genera UN HTML completo para PDF A4 inmobiliario de LeadBook.
No generes una web navegable. No uses nav, menu, Inicio, Propiedades, Contacto superior ni links de landing.
Devolve solo HTML puro completo, sin markdown ni explicaciones.

Contrato visual obligatorio:
- El tag raiz debe ser: <html lang="es" data-leadbook-pdf="true" data-template-id="{template_id}">
- Usar CSS dentro de <style> en <head>.
- Definir :root con estos colores exactos:
  --brand-primary:{colors['primary']}; --brand-secondary:{colors['secondary']}; --brand-accent:{colors['accent']}; --brand-bg:{colors['background']}; --brand-text:{colors['text']};
- Tipografias: display "{fonts['display']}", body "{fonts['body']}", mono "{fonts['mono']}".
- Incluir en el HTML visible o CSS los colores primary y accent exactos.
- Secciones obligatorias con data-section exacto: hero, price, stats, description, amenities, gallery, contact.
- Las secciones description, amenities y cada item de galeria deben tener break-inside: avoid; page-break-inside: avoid.
- Hero usa cover_url. Galeria usa gallery_urls reales. Si falta una imagen, no inventes URL.
- Amenidades deben tener chips con iconos SVG inline simples.
- Contacto debe incluir agente, agencia, telefono/email si existen, logo si existe y QR si existe.
- Si un dato falta, mostrar "No informado" dentro de la seccion correspondiente; no omitir secciones.

Datos compactos:
{json.dumps(payload, ensure_ascii=False)}
"""
    return prompt.strip(), contract


def _clean_ai_html_output(html_output):
    html_output = str(html_output or '').strip()
    if html_output.startswith('```html'):
        html_output = html_output[7:].strip()
    if html_output.startswith('```'):
        html_output = html_output[3:].strip()
    if html_output.endswith('```'):
        html_output = html_output[:-3].strip()
    return html_output.strip()


def _extract_cerebras_usage_tokens(usage):
    if not isinstance(usage, dict):
        return None, {}

    def _safe_int_token(value):
        try:
            if value is None:
                return None
            parsed = int(value)
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError):
            return None

    prompt_tokens = _safe_int_token(usage.get('prompt_tokens') or usage.get('input_tokens'))
    completion_tokens = _safe_int_token(usage.get('completion_tokens') or usage.get('output_tokens'))
    total_tokens = _safe_int_token(usage.get('total_tokens') or usage.get('total_tokens_used'))
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    metadata = {
        'usage': usage,
        'usage_prompt_tokens': prompt_tokens,
        'usage_completion_tokens': completion_tokens,
        'usage_total_tokens': total_tokens,
        'token_count_source': 'cerebras_usage' if total_tokens is not None else 'estimated_fallback',
    }
    return total_tokens, metadata


@track_api_call(service='elevenlabs')
def call_elevenlabs_api(text: str, agente=None, voz='femenina', voice_id=None, voice_settings=None) -> bytes:
    """Genera audio MP3 usando ElevenLabs y el Pool de APIs."""
    key = None
    fallback_env_key = _settings_or_env('ELEVENLABS_API_KEY')

    if agente is not None:
        try:
            from api.pool_manager import get_next_available_api
            key = get_next_available_api(agente, 'elevenlabs')
        except Exception as e:
            print(f"[WARN] Fallo pool_manager ElevenLabs ({type(e).__name__}).")
            key = None
        if not key:
            if _allow_global_api_fallback() and fallback_env_key:
                key = fallback_env_key
            else:
                print("[ERROR] No hay ElevenLabs API Key asignada para el usuario en el Pool.")
                raise APIKeyUnavailableError(
                    API_KEY_UNAVAILABLE_MESSAGE,
                    provider='elevenlabs',
                    scope='pool',
                )
    elif fallback_env_key:
        key = fallback_env_key

    if not key and _allow_global_api_fallback() and fallback_env_key:
        key = fallback_env_key

    if not key:
        print("[ERROR] No hay ElevenLabs API Key disponible.")
        raise APIKeyUnavailableError(
            API_KEY_UNAVAILABLE_MESSAGE,
            provider='elevenlabs',
            scope='pool',
        )

    voice_choice, filtered_candidates, resolved_voice_settings = resolve_elevenlabs_voice_profile(
        voz=voz,
        voice_id=voice_id,
        voice_settings=voice_settings,
    )
    if not filtered_candidates:
        if voice_choice == 'personalizada':
            print("[ERROR] No hay voice_id personalizada disponible para ElevenLabs.")
            return None
        print("[ERROR] No hay voces ElevenLabs disponibles.")
        return None

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": resolved_voice_settings,
    }

    try:
        for voice_id in filtered_candidates:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            response = requests.post(url, json=data, headers=headers, timeout=60)
            if response.status_code == 200:
                return response.content

            # si la voz no existe en la cuenta, probamos siguiente voice_id
            if response.status_code == 404 and 'voice_not_found' in (response.text or ''):
                print(f"[WARN] ElevenLabs voice_id no disponible: {voice_id}. Probando fallback...")
                continue

            print(f"[ERROR] ElevenLabs API failed ({response.status_code}): {response.text}")
            if agente and response.status_code in [401, 429]:
                response_text = str(response.text or '').lower()
                hard_quota_terms = (
                    'quota',
                    'credits',
                    'insufficient',
                    'exceeded',
                    'monthly',
                    'payment',
                    'balance',
                )
                is_hard_quota = any(term in response_text for term in hard_quota_terms) or response.status_code == 401
                try:
                    from api.models import APIKey
                    k = APIKey.objects.filter(api_key=key, servicio__nombre__iexact='elevenlabs').first()
                    if k and is_hard_quota:
                        k.status = 'exhausted'
                        k.requests_this_month = k.google_monthly_limit or max(k.requests_this_month, k.google_daily_limit, 10000)
                        k.save(update_fields=['status', 'requests_this_month', 'updated_at'])
                except Exception as e:
                    logger.error(f"Error marcando ElevenLabs como agotada: {e}")
                if is_hard_quota:
                    raise ElevenLabsQuotaExhaustedError(
                        LIMIT_REACHED_MESSAGE,
                        provider='elevenlabs',
                        scope='provider',
                        quota_state='hard_exhausted',
                    )
                raise ElevenLabsRateLimitedError(
                    "Servicio de voz temporalmente saturado. Reintentá en 10 minutos.",
                    provider='elevenlabs',
                    scope='provider',
                    quota_state='soft_rate_limited',
                    retry_after_seconds=600,
                )

        return None
    except Exception as e:
        print(f"[ERROR] Exception in ElevenLabs call: {str(e)}")
        if isinstance(e, (ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError)):
            raise
        return None


def _get_leadbook_watermark_url():
    configured = _settings_or_env('LEADBOOK_WATERMARK_URL')
    if configured.startswith('http'):
        return configured
    return 'https://res.cloudinary.com/df1vldrhb/image/upload/leadbook/sistema/watermark'


def _mark_gemini_exhausted(agente, key_str, is_monthly=False):
    """Marca una key específica de Gemini como agotada en la DB."""
    try:
        from api.models import APIKey
        if key_str:
            k = APIKey.objects.filter(api_key=key_str).first()
            if k:
                k.status = 'exhausted'
                if is_monthly:
                    k.requests_this_month = k.google_monthly_limit or k.google_daily_limit or 1500
                    update_fields = ['status', 'requests_this_month', 'updated_at']
                else:
                    k.requests_today = k.google_daily_limit or 1500
                    update_fields = ['status', 'requests_today', 'updated_at']
                k.save(update_fields=update_fields)
                print(f"[Pool] Key marcada como AGOTADA: {key_str[:10]}...")
    except Exception as ex:
        logger.error(f"Error marcando Gemini como agotada: {ex}")


def execute_with_gemini_retry(agente, operation_func, max_retries=3):
    """
    Ejecuta una operación de Gemini con manejo inteligente de errores y ROTACIÓN DE LLAVES.
    operation_func debe recibir un objeto 'client' como argumento.
    """
    from google import genai
    from api.pool_manager import get_next_available_api

    last_key = None
    soft_limited_keys = set()
    
    for attempt in range(max_retries + 5): # Damos margen para rotar llaves
        # 1. Obtener llave actual
        if agente:
            current_key = get_next_available_api(agente, 'gemini', exclude_keys=soft_limited_keys)
        else:
            current_key = settings.GEMINI_API_KEY

        if not current_key:
            raise APIKeyUnavailableError(API_KEY_UNAVAILABLE_MESSAGE)

        # 2. Crear cliente y ejecutar
        try:
            client = genai.Client(api_key=current_key)
            return operation_func(client)
        except Exception as e:
            error_msg = str(e).lower()
            original_error_msg = str(e)
            
            # Detectar errores de cuota (429, exhausted, limit)
            is_quota = '429' in error_msg or 'quota' in error_msg or 'exhausted' in error_msg
            
            if is_quota:
                hard_quota_terms = [
                    'generaterequestsperdayperprojectpermodel',
                    'requests per day',
                    'per day per project',
                    'generate_content_free_tier_requests',
                    'daily limit',
                    'monthly limit',
                    'limit: 0',
                ]
                soft_rate_terms = [
                    'generaterequestsperminuteperprojectpermodel',
                    'generatecontentinputtokenspermodelperminute',
                    'requests per minute',
                    'per minute per project',
                    'tokens per minute',
                    'too many requests',
                    'rate limit',
                    'resource exhausted',
                ]
                is_hard_quota = any(term in error_msg for term in hard_quota_terms)
                is_monthly_quota = 'monthly' in error_msg or 'per month' in error_msg
                is_minute = (
                    '429' in error_msg
                    or any(term in error_msg for term in soft_rate_terms)
                ) and not is_hard_quota
                
                if is_hard_quota:
                    # Agotamiento REAL de cuota
                    if agente:
                        _mark_gemini_exhausted(agente, current_key, is_monthly=is_monthly_quota)
                        # Intentar rotar: buscar si get_api_key ahora nos da otra llave
                        new_key = get_next_available_api(agente, 'gemini')
                        if new_key and new_key != current_key:
                            print(f"[Pool] 🔄 Rotando llave de Gemini: {current_key[:8]} -> {new_key[:8]}")
                            continue # Reintentar con la nueva llave
                    
                    # Si no hay agente o no hay más llaves, lanzar error definitivo
                    raise GeminiQuotaExhaustedError(
                        LIMIT_REACHED_MESSAGE,
                        provider='gemini',
                        scope='provider',
                        quota_state='hard_exhausted',
                    )
                
                if is_minute:
                    if agente:
                        soft_limited_keys.add(current_key)
                        alternate_key = get_next_available_api(agente, 'gemini', exclude_keys=soft_limited_keys)
                        if alternate_key:
                            logger.warning(
                                "Rate limit transitorio de Gemini en key actual. Rotando a otra key del pool (Intento %s)",
                                attempt + 1,
                            )
                            continue
                    # Rate limit por minuto (esperar y reintentar con la misma llave)
                    if attempt < max_retries:
                        logger.warning(f"Rate limit de Gemini (minuto) alcanzado. Esperando 60s... (Intento {attempt+1})")
                        retry_delay = max(int(getattr(settings, 'GEMINI_RATE_LIMIT_RETRY_DELAY_SECONDS', 8) or 8), 1)
                        time.sleep(min(retry_delay, 30))
                        continue
                    raise GeminiRateLimitedError(
                        "Servicio de IA temporalmente saturado. Reintentá en 10 minutos.",
                        provider='gemini',
                        scope='provider',
                        quota_state='soft_rate_limited',
                        retry_after_seconds=600,
                    )
                raise GeminiRateLimitedError(
                    "Servicio de IA temporalmente saturado. Reintenta en unos minutos.",
                    provider='gemini',
                    scope='provider',
                    quota_state='soft_rate_limited',
                    retry_after_seconds=600,
                )

            # Otros errores no relacionados a cuota
            raise e


def generar_html_gemini(context, agente):
    """
    Genera una ficha HTML inmobiliaria en DOS pasos:
      Paso 1 - gemini-2.5-flash-lite: genera un prompt creativo de diseño (sin imágenes)
      Paso 2 - Cascada de modelos (2.5 Pro -> 2.5 Flash -> 3 Flash -> ...): genera el HTML final
    """
    from google.genai import types
    from django.conf import settings
    from google import genai
    import random

    import time
    print(f"[HTML] ▶ Función iniciada. Usuario: {agente}")
    print(f"[HTML] ▶ Obteniendo API key...")

    try:
        # La llave y el cliente se gestionan dinámicamente en call_cerebras_api
        pass

        # ─── PASO 1: Generar prompt creativo de diseño ───────────────────────────
        # Variantes de estilo para que cada ficha sea visualmente distinta
        if getattr(settings, 'CEREBRAS_PDF_LEGACY_TWO_STEP', False):
            logger.warning("[HTML Gen] CEREBRAS_PDF_LEGACY_TWO_STEP ignorado: PDF_MODE=controlled_single_call")
        if True:
            prompt_step2, contract = _build_controlled_pdf_html_prompt(context)
            if not prompt_step2 or not contract:
                logger.error("[HTML] Template invalido para PDF controlado: %s", context.get('template_id'))
                return None
            logger.info("[HTML Gen] PDF_MODE=controlled_single_call template=%s", contract.get('id'))
            html_output = call_configured_ai(
                prompt_step2,
                agente=agente,
                task='html_full',
                listado_id=context.get('listado_id'),
                generation_run_id=context.get('generation_run_id'),
                generation_step=context.get('generation_step') or 'pdf',
                ai_provider=context.get('ai_provider'),
                system_prompt=(
                    "Sos un maquetador senior de PDFs inmobiliarios. "
                    "Cumplis contratos HTML estrictos y devolves solo HTML."
                ),
                temperature=0.35,
                top_p=0.9,
                max_completion_tokens=3400,
                metadata={
                    'pdf_controlled_prompt': True,
                    'template_id': contract.get('id'),
                    'base_layout': contract.get('base_layout'),
                },
            )
            html_output = _clean_ai_html_output(html_output)
            if not html_output:
                return None
            html_output = _replace_fontawesome_icons(html_output)
            logger.info(
                "[HTML Gen] PDF controlado template=%s chars=%s",
                contract.get('id'),
                len(html_output),
            )
            return html_output

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
        template_instructions = str(context.get('template_instructions') or '').strip()
        template_block = f"\nTEMPLATE PERSONALIZADO DEL USUARIO:\n{template_instructions}\n" if template_instructions else ''

        prompt_step1 = f"""Sos un director de arte de una agencia de branding de lujo y real estate premium.
        
Tu tarea es generar un PROMPT DE DISEÑO DETALLADO, creativo y técnico para que un desarrollador frontend senior genere el HTML de una landing page inmobiliaria de alto nivel.
El estilo base de esta ficha debe ser: {style_hint} (PERO EXPANDE ESTO CON MUCHO MÁS DETALLE VISUAL Y LUJO).

DATOS DE LA PROPIEDAD:
- Tipo: {tipo} en {operacion}
- Precio: {moneda} {precio}
- Ubicación: {ciudad}
- Amenidades: {amenidades}
- Agencia: {agencia_nombre} | Agente: {agente_nombre}
{template_block}

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
                if provider == 'cerebras':
                    design_prompt = call_configured_ai(
                        prompt_step1,
                        agente=agente,
                        task='html_design',
                        listado_id=context.get('listado_id'),
                        generation_run_id=context.get('generation_run_id'),
                        generation_step=context.get('generation_step') or 'pdf',
                        ai_provider=context.get('ai_provider'),
                    )
                
                if design_prompt:
                    print(f"[HTML] ✅ Paso 1 exitoso con {provider} ({model_id})")
                    break
            except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError):
                raise
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
        
        # Solo usamos URL remota para referencias visuales (sin data/base64).
        try:
            if portada_url and str(portada_url).startswith('https://'):
                print(f"[HTML] ▶ Paso 2 - Imagen de portada (URL) disponible para Cerebras.")
        except Exception as e:
            print(f"[HTML] ⚠️ Error procesando imagen de portada para el prompt: {e}")

        # QR embed
        qr_code = context.get('qr_code', '')
        qr_img_tag = f'<img src="{qr_code}" style="width:80px;height:80px;" alt="QR WhatsApp">' if qr_code else ''
        
        # URLs crudas (evitar enviar base64 enorme en el prompt de texto)
        logo_url_str = context.get('agencia_logo_url', '') or context.get('logo_url', '')
        watermark_html = context.get('watermark_html', '')

        fotos_recorrido = context.get('fotos_recorrido_raw', [])
        fotos_limpias = [f for f in fotos_recorrido if str(f or '').startswith('http')]
        fotos_galeria_str = "\n".join(fotos_limpias[:5])

        prompt_step2 = f"""CRÍTICO: GENERÁ EL HTML COMPLETO DE ARRIBA HACIA ABAJO SIN OMITIR NINGUNA SECCIÓN. 
EL ORDEN ES OBLIGATORIO: 1)head+CSS 2)top-bar 3)hero 4)precio 5)stats 6)descripción 7)amenidades 8)galería 9)footer.
NUNCA CORTES EL HTML A MITAD. SI NO PODÉS COMPLETAR UNA SECCIÓN, DEJÁ UN PLACEHOLDER PERO NO LA OMITAS.

Sos un desarrollador frontend senior especializado en landing pages inmobiliarias de lujo. Tu objetivo es convertir el siguiente prompt de diseño en un sitio web perfecto.

DISEÑO A IMPLEMENTAR (seguilo ESTRICTAMENTE):
{design_prompt}
{template_block}

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
{template_block}

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
                if provider == 'cerebras':
                    html_output = call_configured_ai(
                        prompt_step2_nim,
                        agente=agente,
                        task='html_full',
                        listado_id=context.get('listado_id'),
                        generation_run_id=context.get('generation_run_id'),
                        generation_step=context.get('generation_step') or 'pdf',
                        ai_provider=context.get('ai_provider'),
                    )
                if html_output:
                    print(f"[HTML] ✅ Paso 2 exitoso con {provider} ({model_id})")
                    break
            except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError):
                raise
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

        html_output = _replace_fontawesome_icons(html_output)
        logger.info(f"[HTML Gen] Paso 2 completado. HTML generado ({len(html_output)} chars).")
        return html_output.strip()

    except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError):
        raise
    except Exception as e:
        print(f"[HTML] ❌ Error en generar_html_gemini: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # execute_with_gemini_retry ya manejó el 429 correctamente
        logger.error(f"Error en generar_html_gemini: {e}")
        return None
