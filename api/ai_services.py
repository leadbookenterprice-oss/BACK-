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
from api.tracking import track_api_call

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
}

TEMPLATE_IDS = tuple(
    filename.replace('template_', '').replace('.html', '')
    for filename in TEMPLATE_COLORES.keys()
)


def _resolve_theme_from_context(context, template_file):
    tokens = context.get('template_tokens') if isinstance(context, dict) else None
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
    return f'template_{normalized}.html'


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

    template_id = template_elegido.replace('template_', '').replace('.html', '')
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
    pool_key = APIKey.objects.filter(servicio__nombre__iexact='nvidia', status__in=['available', 'assigned']).first()
    if pool_key:
        return pool_key.api_key
    return settings.NVIDIA_API_KEY

def _get_groq_key():
    from api.models import APIKey
    pool_key = APIKey.objects.filter(servicio__nombre__iexact='groq', status__in=['available', 'assigned']).first()
    if pool_key:
        return pool_key.api_key
    return settings.GROQ_API_KEY


# Excepción especial para cuota mensual de Gemini agotada.
# Los views la capturan y devuelven HTTP 429 con mensaje canonico.
class GeminiQuotaExhaustedError(Exception):
    """Cuota mensual/diaria de Gemini agotada. No tiene solución con reintentos."""
    pass


class APIKeyUnavailableError(Exception):
    """El usuario no tiene una API key asignada o el pool no tiene stock disponible."""
    pass

@track_api_call(service='gemini')
def call_gemini_api(prompt: str, agente=None, **kwargs) -> str:
    system_prompt = kwargs.get('system_prompt', '')
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    def _call(client):
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
    key = _get_groq_key() or os.environ.get('GROQ_API_KEY', '')
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
    import time
    for attempt in range(retries):
        try:
            result = call_gemini_api(prompt, agente=agente, **kwargs)
            if result:
                return result
        except APIKeyUnavailableError:
            raise
        except GeminiQuotaExhaustedError:
            raise
        except Exception as e:
            print(f"Gemini attempt {attempt+1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(1)
    return None

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
                raise Exception(LIMIT_REACHED_MESSAGE)
    elif fallback_env_key:
        key = fallback_env_key

    if not key and _allow_global_api_fallback() and fallback_env_key:
        key = fallback_env_key

    if not key:
        print("[ERROR] No hay ElevenLabs API Key disponible.")
        return None

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
                try:
                    from api.models import APIKey
                    k = APIKey.objects.filter(api_key=key, servicio__nombre__iexact='elevenlabs').first()
                    if k:
                        k.status = 'exhausted'
                        k.requests_this_month = k.google_monthly_limit or max(k.requests_this_month, k.google_daily_limit)
                        k.save(update_fields=['status', 'requests_this_month', 'updated_at'])
                except Exception as e:
                    logger.error(f"Error marcando ElevenLabs como agotada: {e}")
                raise Exception(LIMIT_REACHED_MESSAGE)

        return None
    except Exception as e:
        print(f"[ERROR] Exception in ElevenLabs call: {str(e)}")
        if str(e) == LIMIT_REACHED_MESSAGE:
            raise
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


def _mark_gemini_exhausted(agente, key_str, is_monthly=False):
    """Marca una key específica de Gemini como agotada en la DB."""
    try:
        from api.models import APIKey
        if key_str:
            k = APIKey.objects.filter(api_key=key_str).first()
            if k:
                k.status = 'exhausted'
                k.requests_this_month = k.google_monthly_limit or k.google_daily_limit or 1500
                k.save(update_fields=['status', 'requests_this_month', 'updated_at'])
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
    
    for attempt in range(max_retries + 5): # Damos margen para rotar llaves
        # 1. Obtener llave actual
        if agente:
            current_key = get_next_available_api(agente, 'gemini')
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
                is_monthly = any(term in original_error_msg for term in [
                    'GenerateRequestsPerDayPerProjectPerModel',
                    'generate_content_free_tier_requests',
                    'limit: 0'
                ])
                is_minute = any(term in original_error_msg for term in [
                    'GenerateContentInputTokensPerModelPerMinute',
                    'GenerateRequestsPerMinutePerProjectPerModel'
                ])
                
                if is_monthly or (not is_minute and '429' not in error_msg):
                    # Agotamiento REAL de cuota
                    if agente:
                        _mark_gemini_exhausted(agente, current_key, is_monthly=True)
                        # Intentar rotar: buscar si get_api_key ahora nos da otra llave
                        new_key = get_next_available_api(agente, 'gemini')
                        if new_key and new_key != current_key:
                            print(f"[Pool] 🔄 Rotando llave de Gemini: {current_key[:8]} -> {new_key[:8]}")
                            continue # Reintentar con la nueva llave
                    
                    # Si no hay agente o no hay más llaves, lanzar error definitivo
                    raise GeminiQuotaExhaustedError(
                        LIMIT_REACHED_MESSAGE
                    )
                
                if is_minute or '429' in error_msg:
                    # Rate limit por minuto (esperar y reintentar con la misma llave)
                    if attempt < max_retries:
                        logger.warning(f"Rate limit de Gemini (minuto) alcanzado. Esperando 60s... (Intento {attempt+1})")
                        time.sleep(60)
                        continue
            
            # Otros errores no relacionados a cuota
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
        # La llave y el cliente se gestionan dinámicamente en execute_with_gemini_retry
        pass

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
                if provider == "groq":
                    design_prompt = call_groq_html(prompt_step1)
                elif provider == "nim":
                    design_prompt = call_nim_model(prompt_step1, model_id)
                elif provider == "gemini":
                    def _call_step1(c):
                        return c.models.generate_content(
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
                if provider == "nim":
                    html_output = call_nim_model(prompt_step2_nim, model_id, imagen_url=portada_url)
                elif provider == "groq":
                    p2_modified = f"Foto de portada (URL): {portada_url}\n\n{prompt_step2_nim}"
                    html_output = call_groq_html(p2_modified)
                elif provider == "gemini":
                    def _call_step2(c):
                        return c.models.generate_content(
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

        html_output = _replace_fontawesome_icons(html_output)
        logger.info(f"[HTML Gen] Paso 2 completado. HTML generado ({len(html_output)} chars).")
        return html_output.strip()

    except Exception as e:
        print(f"[HTML] ❌ Error en generar_html_gemini: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # execute_with_gemini_retry ya manejó el 429 correctamente
        logger.error(f"Error en generar_html_gemini: {e}")
        return None
