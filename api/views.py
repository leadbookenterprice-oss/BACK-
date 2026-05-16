from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
import requests
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from decouple import config
import cloudinary
import cloudinary.uploader
import random
import re
import json
import io
import zipfile
import html as html_lib
import unicodedata
from api.services.almacenamiento import AlmacenamientoCloudinary
import logging

logger = logging.getLogger(__name__)

from .models import (
    GeneratedAsset, Listado, OTPCode, ComercialAgentProfile,
    AgentMediaAsset, UserContentPreference,
    BrandTemplate, BrandTemplateRevision, default_template_tokens,
    AgentAssociation, CRMClient,
    TerminosCondiciones, PoliticaPrivacidad, UsageLog
)
from .serializers import (
    RegisterSerializer, GeneratedAssetSerializer,
    TerminosCondicionesSerializer, PoliticaPrivacidadSerializer,
    ComercialAgentProfileSerializer, BrandTemplateSerializer,
    BrandTemplateRevisionSerializer, AgentMediaAssetSerializer,
    UserContentPreferenceSerializer, CRMClientSerializer,
)
from .tasks import run_asset_generation
from .ai_services import call_groq_api, call_gemini_api, smart_call, GeminiQuotaExhaustedError
from .utils import crear_notificacion
from django.template.loader import render_to_string
from .services.render_engine import render_html_to_image
from .plan_utils import puede_generar, incrementar_uso, registrar_uso

def actualizar_resultados_listado(listado, tipo, resultado):
    """
    Guarda el resultado (URL, caption, etc) dentro del JSON de datos del listado.
    Esto permite persistencia entre sesiones.
    """
    if not listado: return
    if not isinstance(listado.datos_extra, dict):
        listado.datos_extra = {}
    
    if 'resultados' not in listado.datos_extra:
        listado.datos_extra['resultados'] = {}
    
    listado.datos_extra['resultados'][tipo] = resultado
    listado.save(update_fields=['datos_extra'])


TEMPLATE_IDS = (
    'dubai_night',
    'beverly_hills',
    'manhattan',
    'mediterraneo',
    'tech_modern',
)

TEMPLATE_CATALOG = {
    'dubai_night': {
        'name': 'Dubai Night',
        'description': 'Lujo nocturno con contraste alto y acento dorado.',
        'colors': {
            'primary': '#1a0a2e',
            'secondary': '#2d1b4e',
            'accent': '#c9a84c',
            'background': '#080808',
            'text': '#f5f3ee',
        },
        'fonts': {
            'display': 'Playfair Display / Bebas Neue',
            'body': 'Inter / DM Sans',
            'mono': 'Space Mono',
        },
    },
    'beverly_hills': {
        'name': 'Beverly Hills',
        'description': 'Editorial elegante, limpio y sofisticado.',
        'colors': {
            'primary': '#2c3e50',
            'secondary': '#34495e',
            'accent': '#e8c547',
            'background': '#fafaf8',
            'text': '#20242a',
        },
        'fonts': {
            'display': 'Cormorant Garamond',
            'body': 'DM Sans',
            'mono': 'DM Sans',
        },
    },
    'manhattan': {
        'name': 'Manhattan',
        'description': 'Urbano industrial, fuerte y de alto impacto.',
        'colors': {
            'primary': '#111111',
            'secondary': '#1a1a1a',
            'accent': '#e63946',
            'background': '#101010',
            'text': '#f3f3f3',
        },
        'fonts': {
            'display': 'Oswald',
            'body': 'Source Sans 3 / Source Serif 4',
            'mono': 'Oswald',
        },
    },
    'mediterraneo': {
        'name': 'Mediterraneo',
        'description': 'Calido, residencial y organico con tonos tierra.',
        'colors': {
            'primary': '#6b4423',
            'secondary': '#8b5e3c',
            'accent': '#c17f3a',
            'background': '#f8f4ef',
            'text': '#2c2416',
        },
        'fonts': {
            'display': 'Libre Baskerville',
            'body': 'Lato',
            'mono': 'Lato',
        },
    },
    'tech_modern': {
        'name': 'Tech Modern',
        'description': 'Estetica digital premium con acento neon.',
        'colors': {
            'primary': '#0d47a1',
            'secondary': '#1565c0',
            'accent': '#00e5ff',
            'background': '#081421',
            'text': '#e8f3ff',
        },
        'fonts': {
            'display': 'Space Grotesk',
            'body': 'Space Grotesk',
            'mono': 'Space Mono',
        },
    },
}

TEMPLATE_POST_MAP = {
    template_id: f'renders/post_{template_id}.html'
    for template_id in TEMPLATE_IDS
}

TEMPLATE_STORY_MAP = {
    template_id: f'renders/story_{template_id}.html'
    for template_id in TEMPLATE_IDS
}

TEMPLATE_CAROUSEL_MAP = {
    template_id: f'renders/carousel_{template_id}.html'
    for template_id in TEMPLATE_IDS
}

TEMPLATE_EMAIL_MAP = {
    template_id: f'emails/marketing_{template_id}.html'
    for template_id in TEMPLATE_IDS
}

MAX_CAROUSEL_GALLERY_IMAGES = 8


SYSTEM_FONT_IMPORT_MAP = {
    'Playfair Display': 'Playfair Display',
    'Bebas Neue': 'Bebas Neue',
    'Inter': 'Inter',
    'DM Sans': 'DM Sans',
    'Space Mono': 'Space Mono',
    'Cormorant Garamond': 'Cormorant Garamond',
    'Oswald': 'Oswald',
    'Source Sans 3': 'Source Sans 3',
    'Source Serif 4': 'Source Serif 4',
    'Libre Baskerville': 'Libre Baskerville',
    'Lato': 'Lato',
    'Space Grotesk': 'Space Grotesk',
}


TEMPLATE_TOKEN_OPTIONS = {
    'fonts': list(SYSTEM_FONT_IMPORT_MAP.keys()),
    'palette_fields': [
        {'key': 'primary', 'label': 'Primario'},
        {'key': 'secondary', 'label': 'Secundario'},
        {'key': 'accent', 'label': 'Acento'},
        {'key': 'background', 'label': 'Fondo'},
        {'key': 'text', 'label': 'Texto'},
    ],
    'layout_styles': [
        {'id': 'editorial', 'label': 'Editorial elegante'},
        {'id': 'dark_luxury', 'label': 'Lujo oscuro'},
        {'id': 'minimal_light', 'label': 'Minimalista claro'},
        {'id': 'urban_strong', 'label': 'Urbano fuerte'},
        {'id': 'mediterranean_warm', 'label': 'Mediterraneo calido'},
        {'id': 'tech_modern', 'label': 'Tech moderno'},
        {'id': 'commercial_direct', 'label': 'Comercial directo'},
    ],
    'density': [
        {'id': 'compact', 'label': 'Compacto'},
        {'id': 'comfortable', 'label': 'Comodo'},
        {'id': 'spacious', 'label': 'Espaciado'},
    ],
    'border_radius': [
        {'id': 'none', 'label': 'Sin bordes'},
        {'id': 'soft', 'label': 'Suave'},
        {'id': 'medium', 'label': 'Medio'},
        {'id': 'strong', 'label': 'Fuerte'},
    ],
    'image_treatment': [
        {'id': 'normal', 'label': 'Normal'},
        {'id': 'dark', 'label': 'Oscuro'},
        {'id': 'warm', 'label': 'Calido'},
        {'id': 'black_white', 'label': 'Blanco y negro'},
        {'id': 'high_contrast', 'label': 'Alto contraste'},
    ],
    'copy_tones': [
        {'id': 'premium', 'label': 'Premium'},
        {'id': 'profesional', 'label': 'Profesional'},
        {'id': 'lujo', 'label': 'Lujo'},
        {'id': 'minimal', 'label': 'Minimal'},
    ],
}


def _build_template_gemini_instructions(template_name, base_template_id, tokens):
    tokens = _resolve_brand_template_tokens(tokens)
    palette = tokens.get('palette') or {}
    typography = tokens.get('typography') or {}
    copy = tokens.get('copy') or {}
    layout = tokens.get('layout') or {}
    hashtags = ' '.join(copy.get('hashtags') or [])
    return (
        f"Template personalizado: {template_name or 'Template de marca'}\n"
        f"Base visual: {base_template_id or 'tech_modern'}\n"
        "Respetar estos tokens de marca al generar copy, HTML o narrativa visual.\n"
        f"Colores: primario {palette.get('primary')}, secundario {palette.get('secondary')}, "
        f"acento {palette.get('accent')}, fondo {palette.get('background')}, texto {palette.get('text')}.\n"
        f"Tipografias: titulares {typography.get('display')}, cuerpo {typography.get('body')}, mono/acento {typography.get('mono')}.\n"
        f"Layout: estilo {layout.get('style', 'tech_modern')}, densidad {layout.get('density', 'comfortable')}, "
        f"bordes {layout.get('border_radius', 'medium')}, tratamiento de imagen {layout.get('image_treatment', 'normal')}, "
        f"logo {layout.get('logo_position')}, agente {layout.get('agent_block_position')}, QR {layout.get('qr_position')}.\n"
        f"Copy: tono {copy.get('tone')}, emojis {copy.get('emoji_density')}, CTA {copy.get('cta_style')}, hashtags {hashtags}.\n"
        "No inventar una identidad distinta. Mantener el HTML estructural y adaptar textos al estilo anterior."
    )


def _template_options_payload():
    return {
        'base_templates': [
            {
                'id': template_id,
                'label': meta.get('name', template_id.replace('_', ' ').title()),
                'description': meta.get('description', ''),
                'colors': meta.get('colors', {}),
                'fonts': meta.get('fonts', {}),
                'default_tokens': _default_tokens_for_base_template(template_id),
            }
            for template_id, meta in TEMPLATE_CATALOG.items()
        ],
        'token_options': TEMPLATE_TOKEN_OPTIONS,
        'default_tokens': default_template_tokens(),
        'default_tokens_by_base': {
            template_id: _default_tokens_for_base_template(template_id)
            for template_id in TEMPLATE_IDS
        },
    }


def _template_catalog_payload(user=None):
    system_items = []
    for template_id in TEMPLATE_IDS:
        meta = TEMPLATE_CATALOG.get(template_id, {})
        system_items.append({
            'id': template_id,
            'type': 'system',
            'name': meta.get('name', template_id.replace('_', ' ').title()),
            'description': meta.get('description', ''),
            'colors': meta.get('colors', {}),
            'fonts': meta.get('fonts', {}),
            'base_template_id': template_id,
            'brand_template_id': None,
        })

    custom_items = []
    if user and getattr(user, 'id', None):
        templates = BrandTemplate.objects.filter(owner=user, is_active=True).order_by('-is_default', '-updated_at')
        for tpl in templates:
            published = tpl.revisions.filter(status='published').order_by('-revision').first()
            tokens = published.tokens_json if published and isinstance(published.tokens_json, dict) else default_template_tokens()
            custom_items.append({
                'id': f'custom:{tpl.id}',
                'type': 'custom',
                'name': tpl.name,
                'description': tpl.description or f"Basado en {tpl.base_template_id.replace('_', ' ').title()}",
                'colors': (tokens.get('palette') or {}),
                'fonts': (tokens.get('typography') or {}),
                'base_template_id': tpl.base_template_id,
                'brand_template_id': tpl.id,
                'is_default': tpl.is_default,
                'published_revision': published.revision if published else None,
            })

    return {
        'templates': custom_items + system_items,
        'custom_templates': custom_items,
        'system_templates': system_items,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def templates_catalog(request):
    return Response(_template_catalog_payload(request.user), status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brand_templates_options(request):
    return Response(_template_options_payload(), status=status.HTTP_200_OK)


def _normalize_template_id(value):
    if not value:
        return None
    template_id = str(value).strip().lower()
    template_id = (
        template_id
        .replace('template_', '')
        .replace('post_', '')
        .replace('story_', '')
        .replace('carousel_', '')
        .replace('carrusel_', '')
        .replace('email_', '')
        .replace('.html', '')
    )
    if template_id in TEMPLATE_IDS:
        return template_id
    return None


def _parse_brand_template_id(value):
    if value in (None, ''):
        return None

    raw = str(value).strip()
    if raw.startswith('custom:'):
        raw = raw.split(':', 1)[1]
    elif raw.startswith('custom-'):
        raw = raw.split('-', 1)[1]

    try:
        parsed = int(raw)
        return parsed if parsed > 0 else None
    except Exception:
        return None


def _extract_brand_template_id_from_payload(data):
    if not isinstance(data, dict):
        return None

    direct = _parse_brand_template_id(
        data.get('brand_template_id')
        or data.get('brandTemplateId')
    )
    if direct:
        return direct

    return _parse_brand_template_id(data.get('template_id') or data.get('templateId') or data.get('template'))


def _extract_template_id_from_payload(data):
    if not isinstance(data, dict):
        return None
    return _normalize_template_id(
        data.get('template_id')
        or data.get('templateId')
        or data.get('template')
    )


def _template_id_from_listado(listado):
    if not listado or not isinstance(listado.datos_extra, dict):
        return None
    return _normalize_template_id(
        listado.datos_extra.get('template_id')
        or listado.datos_extra.get('template')
    )


def _build_font_import_url(typography):
    if not isinstance(typography, dict):
        return ''
    fonts = typography.get('google_fonts') if isinstance(typography.get('google_fonts'), list) else []
    clean = []
    for font in fonts:
        mapped = SYSTEM_FONT_IMPORT_MAP.get(font)
        if mapped and mapped not in clean:
            clean.append(mapped)
    if not clean:
        return ''
    parts = [f"family={font.replace(' ', '+')}:wght@400;500;700" for font in clean]
    return f"https://fonts.googleapis.com/css2?{'&'.join(parts)}&display=swap"


def _deep_merge_dict(base, override):
    result = dict(base or {})
    if not isinstance(override, dict):
        return result

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result.get(key), value)
        else:
            result[key] = value
    return result


def _pick_template_font(value, fallback):
    candidates = []
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split('/')]
    elif isinstance(value, (list, tuple)):
        candidates = [str(part).strip() for part in value]
    for candidate in candidates:
        if candidate in SYSTEM_FONT_IMPORT_MAP:
            return candidate
    return fallback if fallback in SYSTEM_FONT_IMPORT_MAP else 'DM Sans'


def _default_tokens_for_base_template(base_template_id):
    template_id = _normalize_template_id(base_template_id) or 'tech_modern'
    tokens = default_template_tokens()
    meta = TEMPLATE_CATALOG.get(template_id, TEMPLATE_CATALOG['tech_modern'])
    colors = meta.get('colors') if isinstance(meta.get('colors'), dict) else {}
    fonts = meta.get('fonts') if isinstance(meta.get('fonts'), dict) else {}

    palette = tokens.get('palette', {}).copy()
    for key in ('primary', 'secondary', 'accent', 'background', 'text'):
        if colors.get(key):
            palette[key] = colors[key]
    palette['surface'] = colors.get('secondary') or palette.get('surface') or palette.get('background')
    palette['muted_text'] = '#b8b0a0' if template_id == 'dubai_night' else palette.get('muted_text', '#8fb1d1')
    palette['border'] = colors.get('accent') or colors.get('secondary') or palette.get('border', '#1d3e5d')
    palette['overlay'] = 'rgba(0,0,0,0.72)' if template_id in {'dubai_night', 'manhattan'} else palette.get('overlay', 'rgba(0,0,0,0.65)')

    display_font = _pick_template_font(fonts.get('display'), tokens['typography']['display'])
    body_font = _pick_template_font(fonts.get('body'), tokens['typography']['body'])
    mono_font = _pick_template_font(fonts.get('mono'), tokens['typography']['mono'])

    style_map = {
        'dubai_night': 'dark_luxury',
        'beverly_hills': 'editorial',
        'manhattan': 'urban_strong',
        'mediterraneo': 'mediterranean_warm',
        'tech_modern': 'tech_modern',
    }
    image_map = {
        'dubai_night': 'dark',
        'beverly_hills': 'normal',
        'manhattan': 'high_contrast',
        'mediterraneo': 'warm',
        'tech_modern': 'normal',
    }

    tokens['palette'] = palette
    tokens['typography'] = {
        **tokens.get('typography', {}),
        'display': display_font,
        'body': body_font,
        'mono': mono_font,
        'google_fonts': list(dict.fromkeys([display_font, body_font, mono_font])),
    }
    tokens['layout'] = {
        **tokens.get('layout', {}),
        'style': style_map.get(template_id, 'tech_modern'),
        'image_treatment': image_map.get(template_id, 'normal'),
    }
    return _resolve_brand_template_tokens(tokens)


def _resolve_brand_template_tokens(tokens):
    source = tokens if isinstance(tokens, dict) else default_template_tokens()
    fallback = default_template_tokens()

    palette = source.get('palette') if isinstance(source.get('palette'), dict) else {}
    typography = source.get('typography') if isinstance(source.get('typography'), dict) else {}
    emoji = source.get('emoji') if isinstance(source.get('emoji'), dict) else {}
    copy = source.get('copy') if isinstance(source.get('copy'), dict) else {}
    layout = source.get('layout') if isinstance(source.get('layout'), dict) else {}
    components = source.get('components') if isinstance(source.get('components'), dict) else {}
    formats = source.get('formats') if isinstance(source.get('formats'), dict) else {}

    merged = {
        'schema_version': 2,
        'palette': {
            'primary': palette.get('primary') or fallback['palette']['primary'],
            'secondary': palette.get('secondary') or fallback['palette']['secondary'],
            'accent': palette.get('accent') or fallback['palette']['accent'],
            'background': palette.get('background') or fallback['palette']['background'],
            'surface': palette.get('surface') or fallback['palette'].get('surface', fallback['palette']['secondary']),
            'text': palette.get('text') or fallback['palette']['text'],
            'muted_text': palette.get('muted_text') or fallback['palette'].get('muted_text', '#8fb1d1'),
            'border': palette.get('border') or fallback['palette'].get('border', fallback['palette']['secondary']),
            'overlay': palette.get('overlay') or fallback['palette'].get('overlay', 'rgba(0,0,0,0.65)'),
        },
        'typography': {
            'display': typography.get('display') or fallback['typography']['display'],
            'body': typography.get('body') or fallback['typography']['body'],
            'mono': typography.get('mono') or fallback['typography']['mono'],
            'google_fonts': typography.get('google_fonts') or fallback['typography']['google_fonts'],
            'title_transform': typography.get('title_transform') or fallback['typography'].get('title_transform', 'uppercase'),
            'letter_spacing': typography.get('letter_spacing') or fallback['typography'].get('letter_spacing', 'normal'),
        },
        'emoji': {
            'headline': emoji.get('headline') or fallback['emoji']['headline'],
            'price': emoji.get('price') or fallback['emoji']['price'],
            'location': emoji.get('location') or fallback['emoji']['location'],
            'cta': emoji.get('cta') or fallback['emoji']['cta'],
        },
        'copy': {
            'tone': copy.get('tone') or fallback['copy']['tone'],
            'emoji_density': copy.get('emoji_density') or fallback['copy']['emoji_density'],
            'cta_style': copy.get('cta_style') or fallback['copy']['cta_style'],
            'hashtags': copy.get('hashtags') or fallback['copy'].get('hashtags', []),
        },
        'layout': {
            'logo_position': layout.get('logo_position') or fallback['layout']['logo_position'],
            'agent_block_position': layout.get('agent_block_position') or fallback['layout']['agent_block_position'],
            'qr_position': layout.get('qr_position') or fallback['layout']['qr_position'],
            'style': layout.get('style') or fallback['layout'].get('style', 'tech_modern'),
            'density': layout.get('density') or fallback['layout'].get('density', 'comfortable'),
            'border_radius': layout.get('border_radius') or fallback['layout'].get('border_radius', 'medium'),
            'image_treatment': layout.get('image_treatment') or fallback['layout'].get('image_treatment', 'normal'),
        },
        'components': _deep_merge_dict(fallback.get('components', {}), components),
        'formats': _deep_merge_dict(fallback.get('formats', {}), formats),
    }
    merged['typography']['font_import_url'] = _build_font_import_url(merged['typography'])
    return merged


def _persist_template_id(listado, template_id, source=''):
    if not listado or not template_id:
        return

    if not isinstance(listado.datos_extra, dict):
        listado.datos_extra = {}

    datos = listado.datos_extra
    datos['template_id'] = template_id
    datos['template'] = template_id

    resultados = datos.get('resultados')
    if not isinstance(resultados, dict):
        resultados = {}

    meta = resultados.get('template_meta')
    if not isinstance(meta, dict):
        meta = {}

    meta['template_id'] = template_id
    meta['updated_at'] = timezone.now().isoformat()
    if source:
        meta['last_source'] = source

    resultados['template_meta'] = meta
    datos['resultados'] = resultados
    listado.datos_extra = datos
    listado.save(update_fields=['datos_extra'])


def _deterministic_template_id(seed_value):
    if seed_value is None:
        return random.choice(TEMPLATE_IDS)
    try:
        seed_int = int(seed_value)
    except Exception:
        seed_int = sum(ord(ch) for ch in str(seed_value))
    return TEMPLATE_IDS[seed_int % len(TEMPLATE_IDS)]


def _get_default_brand_template(user):
    if not user or not getattr(user, 'id', None):
        return None
    return BrandTemplate.objects.filter(owner=user, is_active=True, is_default=True).first()


def _resolve_template_selection(data, user, listado_obj=None, listado_id_hint=None):
    payload_brand_template_id = _extract_brand_template_id_from_payload(data)
    payload_template_id = _extract_template_id_from_payload(data)

    brand_template = None
    if payload_brand_template_id:
        brand_template = BrandTemplate.objects.filter(
            id=payload_brand_template_id,
            owner=user,
            is_active=True,
        ).first()

    if not brand_template and listado_obj and listado_obj.brand_template_id:
        candidate = listado_obj.brand_template
        if candidate and candidate.owner_id == user.id and candidate.is_active:
            brand_template = candidate

    if not brand_template:
        brand_template = _get_default_brand_template(user)

    published_revision = None
    tokens = None
    template_instructions = ''
    if brand_template:
        published_revision = brand_template.revisions.filter(status='published').order_by('-revision').first()
        if published_revision:
            tokens = _resolve_brand_template_tokens(published_revision.tokens_json)
            template_instructions = (
                published_revision.gemini_instructions
                or _build_template_gemini_instructions(brand_template.name, brand_template.base_template_id, tokens)
            )

    if brand_template:
        template_id = brand_template.base_template_id
    elif payload_template_id:
        template_id = payload_template_id
    else:
        listado_template = _template_id_from_listado(listado_obj)
        if listado_template:
            template_id = listado_template
        elif listado_id_hint:
            template_id = _deterministic_template_id(listado_id_hint)
        elif listado_obj and getattr(listado_obj, 'id', None):
            template_id = _deterministic_template_id(listado_obj.id)
        else:
            template_id = random.choice(TEMPLATE_IDS)

    return {
        'template_id': template_id,
        'brand_template': brand_template,
        'brand_template_revision': published_revision,
        'template_tokens': tokens,
        'template_instructions': template_instructions,
    }


def _persist_template_selection(listado, selection, source=''):
    if not listado or not isinstance(selection, dict):
        return

    template_id = selection.get('template_id')
    brand_template = selection.get('brand_template')
    brand_template_revision = selection.get('brand_template_revision')

    _persist_template_id(listado, template_id, source=source)

    updates = []
    listado.brand_template = brand_template
    updates.append('brand_template')
    listado.brand_template_revision = brand_template_revision
    updates.append('brand_template_revision')

    if not isinstance(listado.datos_extra, dict):
        listado.datos_extra = {}
    datos = listado.datos_extra
    resultados = datos.get('resultados') if isinstance(datos.get('resultados'), dict) else {}
    meta = resultados.get('template_meta') if isinstance(resultados.get('template_meta'), dict) else {}
    meta['template_source'] = 'custom' if brand_template else 'system'
    meta['brand_template_id'] = brand_template.id if brand_template else None
    meta['brand_template_revision'] = brand_template_revision.revision if brand_template_revision else None
    meta['updated_at'] = timezone.now().isoformat()
    if source:
        meta['last_source'] = source
    resultados['template_meta'] = meta
    datos['resultados'] = resultados
    listado.datos_extra = datos
    updates.append('datos_extra')
    listado.save(update_fields=updates)


def _apply_template_tokens_to_html(html, template_id, template_tokens):
    if not html or not isinstance(template_tokens, dict):
        return html

    themed = str(html)
    palette = template_tokens.get('palette') or {}
    typography = template_tokens.get('typography') or {}
    layout = template_tokens.get('layout') or {}
    components = template_tokens.get('components') or {}

    base_meta = TEMPLATE_CATALOG.get(template_id, {})
    base_colors = base_meta.get('colors') if isinstance(base_meta.get('colors'), dict) else {}
    for key in ('primary', 'secondary', 'accent', 'background', 'text'):
        old_val = base_colors.get(key)
        new_val = palette.get(key)
        if old_val and new_val and old_val != new_val:
            themed = themed.replace(str(old_val), str(new_val))

    font_import_url = typography.get('font_import_url') or ''
    display_font = typography.get('display') or 'DM Sans'
    body_font = typography.get('body') or display_font
    mono_font = typography.get('mono') or body_font
    title_transform = typography.get('title_transform') or 'uppercase'
    letter_spacing_value = {
        'tight': '-0.04em',
        'normal': '0',
        'wide': '0.08em',
    }.get(typography.get('letter_spacing'), '0')
    logo_order = (-1, 1) if layout.get('logo_position') == 'top_left' else (2, 1)
    layout_css = (
        ".top{display:flex!important;}"
        f".top .logo{{order:{logo_order[0]}!important;}}"
        f".top .badge{{order:{logo_order[1]}!important;}}"
    )
    layout_css += (
        ".agent-row,.footer,.contact-strip{flex-direction:row-reverse!important;}"
        if layout.get('agent_block_position') == 'bottom_right' or layout.get('qr_position') == 'bottom_left'
        else ".agent-row,.footer,.contact-strip{flex-direction:row!important;}"
    )
    radius_map = {'none': '0', 'soft': '8px', 'medium': '16px', 'strong': '28px'}
    density_map = {'compact': '0.85', 'comfortable': '1', 'spacious': '1.15'}
    image_filter_map = {
        'normal': 'none',
        'dark': 'brightness(.72) saturate(.95)',
        'warm': 'sepia(.18) saturate(1.15) brightness(.98)',
        'black_white': 'grayscale(1) contrast(1.08)',
        'high_contrast': 'contrast(1.18) saturate(1.18)',
    }
    layout_css += (
        f".hero img,.bg,.bg-image,.galeria-foto,.gallery-item{{filter:{image_filter_map.get(layout.get('image_treatment'), 'none')} !important;}}"
        f".stat,.stat-item,.price-box,.precio-box,.qr-block img,.amenidad-chip{{border-radius:{radius_map.get(layout.get('border_radius'), '16px')} !important;}}"
        f".content,.bottom,.bottom-section,.descripcion,.amenidades,.galeria{{gap:calc(20px * {density_map.get(layout.get('density'), '1')}) !important;}}"
    )
    hero_tokens = components.get('hero') if isinstance(components.get('hero'), dict) else {}
    price_tokens = components.get('price') if isinstance(components.get('price'), dict) else {}
    stats_tokens = components.get('stats') if isinstance(components.get('stats'), dict) else {}
    contact_tokens = components.get('contact') if isinstance(components.get('contact'), dict) else {}
    overlay_strength = {
        'none': 'rgba(0,0,0,0)',
        'soft': 'rgba(0,0,0,.32)',
        'medium': 'rgba(0,0,0,.58)',
        'strong': 'rgba(0,0,0,.78)',
    }.get(hero_tokens.get('overlay_strength'), None)
    if overlay_strength:
        layout_css += f".overlay,.hero-overlay{{background:linear-gradient(0deg,{overlay_strength} 0%,rgba(0,0,0,.24) 60%,rgba(0,0,0,.08) 100%)!important;}}"
    if hero_tokens.get('show_badge') is False:
        layout_css += ".badge,.badge-operacion{display:none!important;}"
    price_size = {'small': '.84', 'medium': '1', 'large': '1.22', 'xlarge': '1.42'}.get(price_tokens.get('size'), '1')
    layout_css += f".price-box,.precio-valor,.price-value{{transform:scale({price_size});transform-origin:left center;}}"
    if stats_tokens.get('show_icons') is False:
        layout_css += ".stat-icon,.pdf-inline-icon{display:none!important;}"
    if contact_tokens.get('show_qr') is False:
        layout_css += ".qr-box,.qr-container,.qr-block{display:none!important;}"
    if contact_tokens.get('show_agent_photo') is False:
        layout_css += ".agent-avatar,.agent-photo,.lb-agent-photo{display:none!important;}"

    style_block = (
        '<style id="brand-template-overrides">'
        f":root{{--brand-primary:{palette.get('primary', '#0d47a1')};"
        f"--brand-secondary:{palette.get('secondary', '#1565c0')};"
        f"--brand-accent:{palette.get('accent', '#00e5ff')};"
        f"--brand-bg:{palette.get('background', '#081421')};"
        f"--brand-text:{palette.get('text', '#e8f3ff')};"
        f"--brand-surface:{palette.get('surface', '#0d1b2a')};"
        f"--brand-muted-text:{palette.get('muted_text', '#8fb1d1')};"
        f"--brand-border:{palette.get('border', '#1d3e5d')};"
        f"--primario:{palette.get('primary', '#0d47a1')};"
        f"--secundario:{palette.get('secondary', '#1565c0')};"
        f"--acento:{palette.get('accent', '#00e5ff')};"
        f"--accent:{palette.get('accent', '#00e5ff')};}}"
        f"body{{font-family:'{body_font}',sans-serif !important;}}"
        f"h1,h2,h3,.title,.headline,.hero-titulo{{font-family:'{display_font}',sans-serif !important;text-transform:{title_transform}!important;letter-spacing:{letter_spacing_value}!important;}}"
        f".badge,.stat-label,.agent-role,.qr-label,.mono{{font-family:'{mono_font}',sans-serif !important;}}"
        f"{layout_css}"
        '</style>'
    )

    link_block = f'<link rel="stylesheet" href="{font_import_url}">' if font_import_url else ''
    injection = f'{link_block}{style_block}'

    if '</head>' in themed:
        themed = themed.replace('</head>', f'{injection}</head>', 1)
    else:
        themed = f'{injection}{themed}'

    return themed


def _inject_agent_photo_html(html, photo_url):
    if not html or not photo_url:
        return html
    photo = str(photo_url).strip()
    if not photo.startswith('http'):
        return html
    css = (
        '<style id="agent-photo-overrides">'
        '.lb-agent-photo{width:72px;height:72px;border-radius:50%;object-fit:cover;display:block;'
        'border:3px solid var(--accent,var(--acento,#00d4ff));margin-bottom:10px;background:#111;}'
        '.agent-info,.agent-box{align-items:flex-start;}'
        '.agent-box .lb-agent-photo{width:58px;height:58px;margin-bottom:6px;}'
        '</style>'
    )
    img = f'<img src="{photo}" alt="Foto agente" class="lb-agent-photo">'
    out = html.replace('</head>', f'{css}</head>', 1) if '</head>' in html else f'{css}{html}'
    for marker in ('<div class="agent-info">', '<div class="agent-box">'):
        if marker in out:
            return out.replace(marker, f'{marker}{img}', 1)
    return out


def _select_template_id(data, listado_obj=None, listado_id_hint=None, user=None):
    effective_user = user or getattr(listado_obj, 'agente', None)
    return _resolve_template_selection(data, effective_user, listado_obj, listado_id_hint).get('template_id')


def _resolve_cloudinary_asset_url(value):
    if isinstance(value, dict):
        if value.get('secure_url') and isinstance(value.get('secure_url'), str):
            return value.get('secure_url').strip()
        if value.get('url') and isinstance(value.get('url'), str):
            return value.get('url').strip()
        if value.get('public_id'):
            cloud_name = value.get('cloudinary_account', 'df1vldrhb')
            public_id = value.get('public_id', '')
            return f"https://res.cloudinary.com/{cloud_name}/image/upload/{public_id}"

    if isinstance(value, str):
        val = value.strip()
        if val.startswith('http'):
            return re.sub(r's--[^/]+--/', '', val)

    return ''


def _resolve_listing_cover_frame(data):
    if not isinstance(data, dict):
        return ''

    resultados = data.get('resultados') if isinstance(data.get('resultados'), dict) else {}
    pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}

    pdf_candidates = [
        pdf_result.get('cover_frame_url'),
        pdf_result.get('cover_url'),
        pdf_result.get('thumbnail_url'),
        pdf_result.get('image_url'),
        data.get('dashboard_image_url'),
    ]
    for candidate in pdf_candidates:
        resolved = _resolve_cloudinary_asset_url(candidate)
        if resolved:
            return resolved

    candidates = [
        data.get('portadaUrl'),
        data.get('portada_url'),
        data.get('fotoPortada'),
        data.get('fotoportada'),
    ]

    gallery = data.get('fotosRecorrido') or data.get('fotos_recorrido') or []
    if isinstance(gallery, list) and gallery:
        candidates.append(gallery[0])

    candidates.extend([
        data.get('cover_frame_url'),
        data.get('coverFrameUrl'),
    ])

    for candidate in candidates:
        resolved = _resolve_cloudinary_asset_url(candidate)
        if resolved:
            return resolved
    return ''


def _render_and_store_pdf_cover(listado, html):
    if not listado or not html:
        return ''
    try:
        from api.services.almacenamiento import AlmacenamientoCloudinary

        cover_stream = render_html_to_image(html, 1200, 800)
        cover_url = AlmacenamientoCloudinary.guardar_pdf_cover(
            cover_stream,
            user_id=listado.agente_id,
            listado_id=listado.id,
        )
        return cover_url or ''
    except Exception as exc:
        logger.warning('[PDF] No se pudo generar portada para dashboard listado=%s: %s', getattr(listado, 'id', None), exc)
        return ''


def _ensure_listing_pdf_cover_frame(listado):
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    resultados = datos.get('resultados') if isinstance(datos.get('resultados'), dict) else {}
    pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}

    existing = ''
    for key in ('cover_frame_url', 'cover_url', 'thumbnail_url', 'image_url'):
        existing = _resolve_cloudinary_asset_url(pdf_result.get(key))
        if existing:
            break
    if existing:
        if datos.get('dashboard_image_url') != existing or datos.get('cover_frame_url') != existing:
            datos['dashboard_image_url'] = existing
            datos['cover_frame_url'] = existing
            listado.datos_extra = datos
            listado.save(update_fields=['datos_extra'])
        return existing

    html = pdf_result.get('html')
    cover_url = _render_and_store_pdf_cover(listado, html)
    if cover_url:
        pdf_result['cover_frame_url'] = cover_url
        pdf_result['cover_url'] = cover_url
        resultados['pdf'] = pdf_result
        datos['resultados'] = resultados
        datos['dashboard_image_url'] = cover_url
        datos['cover_frame_url'] = cover_url
        listado.datos_extra = datos
        listado.save(update_fields=['datos_extra'])
    return cover_url


def _ensure_listing_cover_frame(listado):
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    cover_url = _resolve_listing_cover_frame(datos)
    if cover_url and datos.get('cover_frame_url') != cover_url:
        datos['cover_frame_url'] = cover_url
        listado.datos_extra = datos
        listado.save(update_fields=['datos_extra'])
    return cover_url


def _resolve_pdf_cover_from_data(data):
    if not isinstance(data, dict):
        return ''
    resultados = data.get('resultados') if isinstance(data.get('resultados'), dict) else {}
    pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}
    for key in ('cover_frame_url', 'cover_url', 'thumbnail_url', 'image_url'):
        resolved = _resolve_cloudinary_asset_url(pdf_result.get(key))
        if resolved:
            return resolved
    return ''


def _merge_listing_extra_preserving_covers(existing, incoming):
    existing = existing if isinstance(existing, dict) else {}
    merged = incoming.copy() if isinstance(incoming, dict) else {}

    existing_pdf_cover = _resolve_pdf_cover_from_data(existing)
    incoming_pdf_cover = _resolve_pdf_cover_from_data(merged)
    if existing_pdf_cover and not incoming_pdf_cover:
        resultados = merged.get('resultados') if isinstance(merged.get('resultados'), dict) else {}
        pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}
        pdf_result['cover_frame_url'] = existing_pdf_cover
        pdf_result['cover_url'] = pdf_result.get('cover_url') or existing_pdf_cover
        resultados['pdf'] = pdf_result
        merged['resultados'] = resultados

    cover_url = _resolve_listing_cover_frame(merged) or _resolve_listing_cover_frame(existing)
    if cover_url:
        merged['dashboard_image_url'] = cover_url
        merged['cover_frame_url'] = cover_url
    return merged


def _serialize_listing_summary(listado):
    cover_url = _ensure_listing_pdf_cover_frame(listado) or _ensure_listing_cover_frame(listado)
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    return {
        'id': listado.id,
        'titulo': listado.titulo,
        'tipo_propiedad': listado.tipo_propiedad,
        'operacion': listado.operacion,
        'ciudad': listado.ciudad,
        'precio': listado.precio,
        'moneda': listado.moneda,
        'creado_en': listado.creado_en,
        'videos_creados': listado.videos_creados,
        'video_url': listado.video_url,
        'video_status': listado.video_status,
        'dashboard_image_url': cover_url,
        'cover_frame_url': cover_url,
        'fotoportada': cover_url,
        'datos': datos,
    }


def _resolve_primary_property_image(data):
    if not isinstance(data, dict):
        return ''

    for key in ('portadaUrl', 'portada_url', 'fotoPortada', 'fotoportada'):
        resolved = _resolve_cloudinary_asset_url(data.get(key))
        if resolved:
            return resolved
    return ''


def _looks_like_property_image(value):
    """Evita que portada/galeria del listado se usen como logo o avatar."""
    if isinstance(value, dict):
        raw = ' '.join(
            str(value.get(key) or '')
            for key in ('public_id', 'url', 'secure_url')
        )
    else:
        raw = str(value or '')

    normalized = raw.replace('\\', '/').lower()
    if not normalized:
        return False

    property_markers = (
        '/listado_',
        'listado_',
        '/galeria',
        'galeria_',
        '/portada',
        'tipo_foto=galeria',
        'tipo_foto=portada',
    )
    return any(marker in normalized for marker in property_markers)


def _resolve_brand_asset_url(value, allow_data_url=False):
    if not value or _looks_like_property_image(value):
        return ''

    if isinstance(value, str):
        cleaned = value.strip()
        if allow_data_url and cleaned.startswith('data:image'):
            return cleaned
        if cleaned.startswith('http'):
            return re.sub(r's--[^/]+--/', '', cleaned)
        return ''

    resolved = _resolve_cloudinary_asset_url(value)
    if resolved and not _looks_like_property_image(resolved):
        return resolved
    return ''


def _inject_agency_logo_fallback(html, logo_url, agency_name):
    if logo_url or not agency_name or '<div></div>' not in html:
        return html

    safe_agency = html_lib.escape(str(agency_name).strip())
    if not safe_agency:
        return html

    css = (
        '<style id="agency-logo-fallback">'
        '.agency-logo-text{max-width:260px;color:var(--accent,var(--acento,#c9a84c));'
        'font-family:Inter,DM Sans,Arial,sans-serif;font-size:24px;font-weight:900;'
        'line-height:1.05;letter-spacing:3px;text-transform:uppercase;text-align:right;}'
        '</style>'
    )
    out = html.replace('</head>', f'{css}</head>', 1) if '</head>' in html else f'{css}{html}'
    return out.replace('<div></div>', f'<div class="agency-logo-text">{safe_agency}</div>', 1)


def _inject_agency_brand_lockup(html, logo_url, agency_name):
    if not html:
        return html

    safe_agency = html_lib.escape(str(agency_name or '').strip())
    if not safe_agency:
        return html

    has_lockup = 'class="lb-brand-lockup"' in html or "class='lb-brand-lockup'" in html

    css = (
        '<style id="agency-brand-lockup">'
        '.lb-brand-lockup{display:flex!important;align-items:center!important;gap:14px!important;'
        'max-width:420px!important;min-height:62px!important;padding:8px 14px!important;'
        'border-radius:999px!important;background:rgba(0,0,0,.28)!important;'
        'border:1px solid rgba(255,255,255,.14)!important;backdrop-filter:blur(10px)!important;}'
        '.lb-brand-lockup .logo,.lb-brand-logo{width:58px!important;height:58px!important;'
        'max-width:58px!important;max-height:58px!important;border-radius:999px!important;'
        'object-fit:contain!important;padding:6px!important;background:rgba(255,255,255,.92)!important;'
        'filter:none!important;flex:0 0 auto!important;}'
        '.lb-brand-name{display:block!important;max-width:300px!important;color:var(--accent,var(--acento,#c9a84c))!important;'
        'font-family:Inter,DM Sans,Arial,sans-serif!important;font-size:22px!important;font-weight:900!important;'
        'line-height:1.05!important;letter-spacing:.6px!important;text-transform:uppercase!important;'
        'text-align:left!important;text-shadow:0 2px 14px rgba(0,0,0,.35)!important;}'
        '</style>'
    )
    out = html
    if 'id="agency-brand-lockup"' not in out:
        out = out.replace('</head>', f'{css}</head>', 1) if '</head>' in out else f'{css}{out}'

    if has_lockup:
        return out

    logo_pattern = re.compile(r'(<img\b(?=[^>]*class=["\'][^"\']*\blogo\b[^"\']*["\'])(?=[^>]*src=["\'][^"\']+["\'])[^>]*>)', re.IGNORECASE)
    match = logo_pattern.search(out)
    if match:
        logo_img = match.group(1)
        lockup = f'<div class="lb-brand-lockup">{logo_img}<span class="lb-brand-name">{safe_agency}</span></div>'
        return out[:match.start()] + lockup + out[match.end():]

    if '<div></div>' in out:
        return out.replace('<div></div>', f'<div class="lb-brand-lockup"><span class="lb-brand-name">{safe_agency}</span></div>', 1)

    return out


def _collect_property_images(data):
    portada = _resolve_primary_property_image(data)
    fotos = data.get('fotosRecorrido', []) if isinstance(data, dict) else []
    if not isinstance(fotos, list):
        fotos = []

    excluded = set()
    for key in ('logoAgenciaUrl', 'logo_url', 'logoUrl', 'agencyLogo', 'agenteFotoUrl', 'agente_foto_url'):
        resolved_brand = _resolve_brand_asset_url(data.get(key), allow_data_url=True) if isinstance(data, dict) else ''
        if resolved_brand:
            excluded.add(resolved_brand)

    candidates = []
    if portada:
        candidates.append(portada)
    candidates.extend(fotos)

    urls = []
    seen = set()
    for item in candidates:
        item_val = item
        if isinstance(item, dict) and item.get('url') and not item.get('public_id'):
            item_val = item.get('url')
        resolved = _resolve_cloudinary_asset_url(item_val)
        if resolved and resolved not in seen and resolved not in excluded:
            seen.add(resolved)
            urls.append(resolved)
    return urls


def _normalize_phone_e164(value, default_country_code='54'):
    if value in (None, ''):
        return ''

    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return ''

    if str(value).strip().startswith('+'):
        normalized = f'+{digits}'
    else:
        normalized = f'+{default_country_code}{digits}' if not digits.startswith(default_country_code) else f'+{digits}'

    if re.match(r'^\+[1-9]\d{6,14}$', normalized):
        return normalized
    return ''


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

    if country and area and local:
        return f'+{country} {area} {local}'
    return normalized


def _build_agent_contact_html(phone, email):
    phone_value = str(phone or '').strip()
    email_value = str(email or '').strip()
    parts = []

    if phone_value:
        phone_display = _format_phone_display(phone_value) or phone_value
        parts.append(
            f'<a href="tel:{html_lib.escape(phone_value)}">{html_lib.escape(phone_display)}</a>'
        )

    if email_value:
        parts.append(
            f'<a href="mailto:{html_lib.escape(email_value)}">{html_lib.escape(email_value)}</a>'
        )

    return ' &nbsp;·&nbsp; '.join(parts)


def _get_default_commercial_agent(user):
    if not user or not getattr(user, 'id', None):
        return None

    default_profile = ComercialAgentProfile.objects.filter(
        owner=user,
        activo=True,
        is_default=True,
    ).first()
    if default_profile:
        return default_profile

    return ComercialAgentProfile.objects.filter(owner=user, activo=True).order_by('-updated_at').first()


def _serialize_commercial_agent(profile):
    if not profile:
        return None
    return ComercialAgentProfileSerializer(profile).data


def _resolve_branding_payload(data, user):
    payload = data if isinstance(data, dict) else {}
    default_profile = _get_default_commercial_agent(user)

    payload_logo = (
        payload.get('logoAgenciaUrl')
        or payload.get('logo_url')
        or payload.get('logoUrl')
        or payload.get('agencyLogo')
        or payload.get('agenciaLogoUrl')
    )
    active_asset = None
    if default_profile:
        active_asset = default_profile.media_assets.filter(kind='agent_photo', is_active=True).order_by('-uploaded_at').first()

    profile_photo = (
        (active_asset.secure_url if active_asset else '')
        or payload.get('agenteFotoUrl')
        or payload.get('agente_foto_url')
        or (default_profile.foto_url if default_profile else '')
        or ''
    )

    agent_name = (
        payload.get('agenteNombre')
        or payload.get('agente_nombre')
        or (default_profile.nombre if default_profile else '')
        or getattr(user, 'nombre', '')
        or ''
    )

    agent_role = (
        payload.get('agenteRol')
        or payload.get('agente_rol')
        or (default_profile.rol if default_profile else '')
        or 'Asesor Comercial'
    )

    agent_email = (
        payload.get('agenteEmail')
        or payload.get('agente_email')
        or (default_profile.email if default_profile else '')
        or getattr(user, 'email', '')
        or ''
    )

    default_phone = (default_profile.telefono_e164 if default_profile else '') or getattr(user, 'telefono', '')
    raw_phone = payload.get('agenteTelefono') or payload.get('agente_telefono') or default_phone or ''
    agent_phone = _normalize_phone_e164(raw_phone)
    agent_contact_html = _build_agent_contact_html(agent_phone, agent_email)

    agency_name = (
        payload.get('agenciaNombre')
        or payload.get('agencia_nombre')
        or getattr(user, 'nombre_inmobiliaria', '')
        or getattr(user, 'agencia', '')
        or 'Agencia'
    )

    logo_url = (
        _resolve_brand_asset_url(payload_logo, allow_data_url=True)
        or _resolve_brand_asset_url(getattr(user, 'logo_url', ''), allow_data_url=True)
    )
    agent_photo_url = _resolve_brand_asset_url(profile_photo, allow_data_url=True)

    return {
        'agente_nombre': str(agent_name).strip(),
        'agente_rol': str(agent_role).strip(),
        'agente_email': str(agent_email).strip(),
        'agente_telefono': str(agent_phone).strip(),
        'agencia_nombre': str(agency_name).strip(),
        'logo_url': str(logo_url or '').strip(),
        'agente_foto_url': str(agent_photo_url or '').strip(),
        'agente_contacto_html': agent_contact_html,
        'agente_foto_asset': active_asset.as_cloudinary_ref() if active_asset else None,
        'default_agent_profile': default_profile,
    }


def _normalize_hashtags(value):
    if not value:
        return []
    raw_items = re.split(r'[\s,]+', value) if isinstance(value, str) else value
    if not isinstance(raw_items, list):
        return []
    tags = []
    for item in raw_items:
        tag = str(item or '').strip()
        if not tag:
            continue
        tag = tag if tag.startswith('#') else f'#{tag}'
        tag = re.sub(r'[^#\wÁÉÍÓÚÜÑáéíóúüñ]', '', tag)
        if len(tag) > 1 and tag not in tags:
            tags.append(tag[:50])
    return tags[:35]


def _hashtag_from_text(value):
    text = str(value or '').strip()
    if not text:
        return ''
    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r'[^A-Za-z0-9]+', ' ', ascii_text).strip().title().replace(' ', '')
    return f'#{cleaned[:48]}' if cleaned else ''


def _build_dynamic_hashtags(data, formato='post'):
    data = data if isinstance(data, dict) else {}
    tipo = data.get('tipoPropiedad') or data.get('tipo_propiedad') or ''
    ciudad = data.get('ciudad') or ''
    pais = data.get('pais') or ''
    operacion = str(data.get('operacion') or '').strip().lower()

    tags = [
        '#RealEstate', '#Inmobiliaria', '#Propiedades', '#BienesRaices',
        '#InversionInmobiliaria', '#OportunidadInmobiliaria', '#PropiedadPremium',
        '#LuxuryRealEstate', '#RealEstateMarketing', '#BrokerInmobiliario',
        '#AgenteInmobiliario', '#ListadoInmobiliario', '#TourInmobiliario',
        '#VentaInmobiliaria', '#CompraInteligente', '#InversionSegura',
        '#MercadoInmobiliario', '#RealEstateLatam', '#LeadBook',
    ]

    for candidate in (tipo, ciudad, pais):
        tag = _hashtag_from_text(candidate)
        if tag:
            tags.append(tag)

    tipo_tag = _hashtag_from_text(tipo)
    if tipo_tag:
        suffix = 'EnAlquiler' if any(word in operacion for word in ('alquiler', 'renta', 'rent')) else 'EnVenta'
        tags.append(f'{tipo_tag}{suffix}'[:50])

    ciudad_tag = _hashtag_from_text(ciudad)
    if ciudad_tag:
        tags.extend([f'{ciudad_tag}RealEstate'[:50], f'#VivirEn{ciudad_tag[1:]}'[:50]])

    if formato == 'carrusel':
        tags.extend(['#CarruselInmobiliario', '#DeslizaParaVer', '#FichaInmobiliaria'])
    elif formato == 'story':
        tags.extend(['#InstagramStories', '#ConsultaPorWhatsApp', '#DisponibleAhora'])
    else:
        tags.extend(['#InstagramRealEstate', '#PostInmobiliario', '#AgendaTuVisita'])

    normalized = _normalize_hashtags(tags)
    return normalized[:32]


def _resolve_content_preferences(user, template_tokens=None, payload=None):
    payload = payload if isinstance(payload, dict) else {}
    tokens_copy = (template_tokens or {}).get('copy') if isinstance(template_tokens, dict) else {}
    try:
        prefs = getattr(user, 'content_preferences', None)
    except Exception:
        prefs = None

    hashtags = (
        payload.get('hashtags')
        or (tokens_copy or {}).get('hashtags')
        or (prefs.hashtags if prefs else None)
        or [
            '#RealEstate', '#Inmobiliaria', '#Propiedades', '#BienesRaices',
            '#InversionInmobiliaria', '#PropiedadPremium', '#LuxuryRealEstate',
            '#OportunidadInmobiliaria', '#AgenteInmobiliario', '#AgendaTuVisita',
        ]
    )
    emoji_density = (
        payload.get('emoji_density')
        or (tokens_copy or {}).get('emoji_density')
        or (prefs.emoji_density if prefs else 'medium')
    )
    use_emojis = payload.get('use_emojis')
    if use_emojis is None:
        use_emojis = (prefs.use_emojis if prefs else True)

    tone = payload.get('tone') or (tokens_copy or {}).get('tone') or (prefs.tone if prefs else 'premium')
    return {
        'hashtags': _normalize_hashtags(hashtags),
        'emoji_density': emoji_density if emoji_density in {'none', 'low', 'medium', 'high'} else 'medium',
        'use_emojis': bool(use_emojis),
        'tone': tone,
    }


def _caption_preference_prompt(prefs):
    emoji_text = 'sin emojis' if not prefs.get('use_emojis') or prefs.get('emoji_density') == 'none' else f"emojis densidad {prefs.get('emoji_density')}"
    hashtags = ' '.join(prefs.get('hashtags') or [])
    template_instructions = str(prefs.get('template_instructions') or '').strip()
    extra = f" Instrucciones del template personalizado: {template_instructions}" if template_instructions else ''
    return f"Tono {prefs.get('tone', 'premium')}; {emoji_text}; usar estos hashtags base si aplican y sumar hashtags especificos de ciudad, propiedad, inversion y lifestyle: {hashtags}.{extra}"


def _attach_template_instructions_to_prefs(prefs, selection):
    prefs = dict(prefs or {})
    if isinstance(selection, dict) and selection.get('template_instructions'):
        prefs['template_instructions'] = selection.get('template_instructions')
    return prefs


def _apply_caption_preferences(caption, prefs, max_chars=2200, data=None, formato='post'):
    text = str(caption or '').strip()
    tag_pool = []
    tag_pool.extend(prefs.get('hashtags') or [])
    tag_pool.extend(_build_dynamic_hashtags(data or {}, formato=formato))
    tags = [tag for tag in _normalize_hashtags(tag_pool) if tag not in text]
    if tags:
        selected = []
        for tag in tags[:32]:
            candidate = ' '.join(selected + [tag])
            if len(text) + len(candidate) + 2 > max_chars:
                break
            selected.append(tag)
        if selected:
            text = f"{text}\n\n{' '.join(selected)}".strip()
    if not prefs.get('use_emojis') or prefs.get('emoji_density') == 'none':
        text = re.sub(r'[\U0001F300-\U0001FAFF\U00002700-\U000027BF]+', '', text).strip()
    return text[:max_chars].rstrip()


def _extract_urls_for_export(value):
    urls = []

    def _walk(item):
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned.startswith('http'):
                urls.append(cleaned)
            return

        if isinstance(item, dict):
            if isinstance(item.get('url'), str) and item.get('url', '').startswith('http'):
                urls.append(item.get('url').strip())
            if isinstance(item.get('slides'), list):
                for slide in item['slides']:
                    _walk(slide)
            return

        if isinstance(item, list):
            for child in item:
                _walk(child)

    _walk(value)

    unique = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _download_remote_asset(url, timeout=25):
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            return None, None

        content_type = response.headers.get('content-type', '').lower()
        return response.content, content_type
    except Exception:
        return None, None


def _sanitize_caption_text(raw_text, max_chars=2200):
    if not raw_text:
        return ''

    text = str(raw_text).strip()
    text = re.sub(r"```(?:json|markdown|text)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    text = text.replace("**", "")
    text = re.sub(r'^\s*---+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*#{1,6}\s*', '', text, flags=re.MULTILINE)

    intro_patterns = [
        r'^\s*[!¡]*\s*absolutamente[!¡\s\-,:.]*',
        r'^\s*(opci[oó]n|option)\s*\d+\s*(?:\([^\)]*\))?\s*[:\-–.]*\s*',
        r'^\s*(aqui|aquí)\s+tienes\s+un\s+caption[^:\n]{0,180}:\s*',
        r'^\s*(aqui|aquí)\s+tienes[^:\n]{0,180}:\s*',
        r'^\s*te\s+comparto\s+un\s+caption[^:\n]{0,180}:\s*',
    ]
    for pattern in intro_patterns:
        text = re.sub(pattern, '', text, count=1, flags=re.IGNORECASE)

    meta_prefix = re.compile(
        r'^\s*(caption|copy|salida|output|explicacion|explicación|nota|instrucciones|observaciones?)\s*:\s*',
        flags=re.IGNORECASE,
    )

    def _is_meta_paragraph(paragraph):
        p = str(paragraph or '').strip().lower()
        if not p:
            return False
        meta_signals = (
            'aqui tienes',
            'aquí tienes',
            'caption optimizado',
            'caption para instagram',
            'disenado para captar',
            'diseñado para captar',
            'te comparto el caption',
            'este caption',
            'copia optimizada',
            'i can process',
            'i cannot process',
            "i can't process",
            'as an ai',
            'como modelo de ia',
            'no puedo procesar',
        )
        return any(signal in p for signal in meta_signals)

    cleaned_lines = []
    for line in text.splitlines():
        current = line.strip()
        if not current:
            cleaned_lines.append('')
            continue

        current = re.sub(r'^\s*[-*•]+\s*', '', current)
        current = meta_prefix.sub('', current).strip()

        if re.match(r'^(json|formato|estructura)\b', current, flags=re.IGNORECASE):
            continue

        cleaned_lines.append(current)

    text = '\n'.join(cleaned_lines)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    while paragraphs and _is_meta_paragraph(paragraphs[0]):
        paragraphs.pop(0)
    text = '\n\n'.join(paragraphs)

    text = re.sub(r'\n{3,}', '\n\n', text).strip().strip('"').strip("'")
    text = re.sub(r'[ \t]{2,}', ' ', text)

    if len(text) > max_chars:
        text = text[:max_chars].rstrip()

    return text


def _caption_needs_fallback(text):
    lowered = str(text or '').strip().lower()
    if not lowered:
        return True
    bad_signals = (
        'i can process',
        'i cannot process',
        "i can't process",
        'i am unable',
        "i'm unable",
        'as an ai',
        'cannot access',
        'no puedo procesar',
        'no puedo acceder',
        'como modelo de ia',
        'opcion 1',
        'opción 1',
        'option 1',
    )
    return any(signal in lowered for signal in bad_signals)


def _finalize_caption_text(raw_text, data, formato='post', prefs=None, max_chars=2200):
    caption = _sanitize_caption_text(raw_text, max_chars=max_chars)
    if _caption_needs_fallback(caption):
        caption = ''
    caption = _ensure_caption_length(caption, data, formato=formato)
    if prefs:
        caption = _apply_caption_preferences(caption, prefs, max_chars=max_chars, data=data, formato=formato)
    return caption


def _fallback_caption_text(data, formato='post'):
    tipo = str(data.get('tipoPropiedad') or 'Propiedad').strip()
    ciudad = str(data.get('ciudad') or '').strip()
    operacion = str(data.get('operacion') or 'venta').strip().lower()
    moneda = str(data.get('moneda') or 'USD').strip()
    precio = str(data.get('precio') or '').strip()
    recamaras = str(data.get('recamaras') or '').strip()
    banos = str(data.get('banos') or '').strip()
    superficie = str(data.get('superficieCubierta') or data.get('superficieTotal') or '').strip()

    detalles = []
    if recamaras:
        detalles.append(f"{recamaras} recamaras")
    if banos:
        detalles.append(f"{banos} banos")
    if superficie:
        detalles.append(f"{superficie} m2")
    specs = ', '.join(detalles) if detalles else 'excelente distribucion'

    if formato == 'story':
        return (
            f"{tipo} en {ciudad}. {operacion.title()} por {moneda} {precio}. "
            f"Con {specs}, esta opcion destaca por ubicacion, estilo y potencial de valorizacion. "
            "Si queres fotos, ficha completa y coordinar visita, escribinos ahora y te asesoramos en minutos. "
            "#DisponibleAhora #ConsultaPorWhatsApp #Propiedades #RealEstate"
        )
    if formato == 'carrusel':
        return (
            f"{tipo} en {ciudad}: una oportunidad real para {operacion} con propuesta premium y excelente ubicacion. "
            f"Precio publicado: {moneda} {precio}. La propiedad ofrece {specs}, ambientes luminosos y funcionales para vivir o invertir. "
            "Desliza el carrusel para ver recorrido, diferenciales y datos clave antes de decidir. "
            "Escribinos para enviarte toda la informacion, disponibilidad actualizada y coordinar visita. "
            "#RealEstate #Inmobiliaria #Inversion #BienesRaices #PropiedadPremium #CarruselInmobiliario"
        )
    return (
        f"{tipo} en {ciudad} en {operacion}, pensada para quienes buscan ubicacion, calidad y rentabilidad. "
        f"Precio de referencia: {moneda} {precio}. Con {specs}, esta propiedad combina diseno, comodidad y una excelente proyeccion de valor. "
        "Ideal para compradores e inversores que valoran informacion clara, buen asesoramiento y una decision segura. "
        "Contactanos para recibir la ficha completa, resolver dudas, revisar condiciones comerciales y coordinar visita personalizada. "
        "#RealEstate #Inmobiliaria #Propiedades #Inversion #BienesRaices #PropiedadPremium #AgendaTuVisita"
    )


def _fallback_descripcion_pdf(data):
    tipo = str(data.get('tipoPropiedad') or data.get('tipo_propiedad') or 'Propiedad').strip()
    ciudad = str(data.get('ciudad') or '').strip()
    operacion = str(data.get('operacion') or 'Venta').strip()
    moneda = str(data.get('moneda') or 'USD').strip()
    precio = str(data.get('precio') or '').strip()
    recamaras = str(data.get('recamaras') or '').strip()
    banos = str(data.get('banos') or '').strip()
    superficie = str(data.get('superficieCubierta') or data.get('superficieConstruida') or data.get('superficieTotal') or '').strip()

    linea_specs = []
    if recamaras:
        linea_specs.append(f"{recamaras} recamaras")
    if banos:
        linea_specs.append(f"{banos} banos")
    if superficie:
        linea_specs.append(f"{superficie} m2")
    specs = ', '.join(linea_specs) if linea_specs else 'excelente distribucion'

    return (
        f"{tipo} en {operacion} ubicado en {ciudad}, con propuesta ideal para vivienda o inversion. "
        f"Precio de publicacion: {moneda} {precio}. "
        f"La propiedad ofrece {specs}, ambientes funcionales y buena iluminacion natural.\n\n"
        f"Una opcion destacada para quienes buscan una decision segura en {ciudad}. "
        "Coordina una visita para conocer cada detalle de forma presencial."
    )


def _get_leadbook_logo_data_url():
    logo_path = os.path.join(os.path.dirname(__file__), 'leadbook_logo.png')
    try:
        with open(logo_path, 'rb') as f:
            logo_b64 = base64.b64encode(f.read()).decode('utf-8')
        return f"data:image/png;base64,{logo_b64}"
    except Exception:
        return ''


def _ensure_caption_length(text, data, formato='post'):
    caption = str(text or '').strip()
    min_chars_map = {'post': 1100, 'story': 380, 'carrusel': 1150}
    max_chars_map = {'post': 2200, 'story': 650, 'carrusel': 2200}

    min_chars = min_chars_map.get(formato, 120)
    max_chars = max_chars_map.get(formato, 2200)

    if not caption:
        caption = _fallback_caption_text(data, formato=formato)

    if len(caption) < min_chars:
        tipo = str(data.get('tipoPropiedad') or 'propiedad').strip()
        ciudad = str(data.get('ciudad') or '').strip()
        operacion = str(data.get('operacion') or 'venta').strip().title()
        moneda = str(data.get('moneda') or 'USD').strip()
        precio = str(data.get('precio') or '').strip()

        if formato == 'story':
            extension_blocks = [
                f"{operacion} · {tipo} en {ciudad}",
                f"Precio de referencia: {moneda} {precio}.",
                "Ideal para quienes priorizan ubicación, distribución funcional y potencial de valorización.",
                "Escribinos por WhatsApp y te enviamos ficha completa, recorrido y disponibilidad actualizada.",
                "#Propiedades #Inmobiliaria #Oportunidad",
            ]
        elif formato == 'carrusel':
            extension_blocks = [
                "\nDESTACADOS",
                f"• {operacion} de {tipo} en {ciudad}.",
                f"• Precio publicado: {moneda} {precio}.",
                "• Propuesta ideal para vivir bien o invertir con estrategia.",
                "\nPOR QUE VALE LA PENA",
                "• Ubicación competitiva frente a opciones similares de la zona.",
                "• Distribución pensada para comodidad, funcionalidad y estilo.",
                "• Potencial de renta y valorización a mediano plazo.",
                "• Contenido visual pensado para evaluar la propiedad con más claridad antes de visitar.",
                "\nCTA",
                "Escribinos para recibir la ficha completa, comparativa de mercado, disponibilidad y coordinar visita privada.",
                "#RealEstate #InversionInmobiliaria #Propiedades #BienesRaices #PropiedadPremium #CarruselInmobiliario #AgendaTuVisita #LuxuryRealEstate",
            ]
        else:
            extension_blocks = [
                "\nDETALLES CLAVE",
                f"• {operacion} de {tipo} en {ciudad}.",
                f"• Valor de referencia: {moneda} {precio}.",
                "• Balance entre calidad constructiva, ubicación y proyección de valor.",
                "\nENFOQUE COMERCIAL",
                "Esta propiedad se posiciona como una alternativa sólida para quien busca decidir con información clara y respaldo profesional.",
                "Además, permite comunicar valor desde el primer contacto: ubicación, estilo de vida, potencial de inversión y una propuesta concreta para avanzar sin vueltas.",
                "\nSIGUIENTE PASO",
                "Escribinos para enviarte la ficha técnica completa, videos, disponibilidad y agendar visita personalizada.",
                "#RealEstate #Propiedades #Inmobiliaria #Inversion #BienesRaices #PropiedadPremium #OportunidadInmobiliaria #AgendaTuVisita #LuxuryRealEstate #BrokerInmobiliario",
            ]

        for block in extension_blocks:
            if len(caption) >= min_chars:
                break
            separator = "\n\n" if caption else ""
            caption = f"{caption}{separator}{block}".strip()

    if len(caption) > max_chars:
        caption = caption[:max_chars].rstrip()

    return caption

LIMITES_PLAN = {
    'free':     {'listados_mes': 10},
    'starter':  {'listados_mes': 40},
    'pro':      {'listados_mes': 150},
    'scale':    {'listados_mes': 999999},
    'business': {'listados_mes': 999999},
}

def verificar_limite_plan(agent):
    from datetime import datetime
    plan = getattr(agent, 'plan_nombre', 'free')
    limite = LIMITES_PLAN.get(plan, LIMITES_PLAN['free'])
    
    ahora = datetime.now()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=ahora.year,
        creado_en__month=ahora.month
    ).count()
    
    if listados_mes >= limite['listados_mes']:
        return False, listados_mes, limite['listados_mes']
    return True, listados_mes, limite['listados_mes']

from io import BytesIO
from django.template.loader import get_template

from django.http import HttpResponse

import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import tempfile
import uuid
import os
import time

def generar_whatsapp_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import urllib.parse
    # Limpiar teléfono: solo dígitos
    raw_phone = str(telefono or '').strip()
    tel_limpio = ''.join(filter(str.isdigit, raw_phone))
    # Si no viene en E.164, asumir Argentina (+54) por compatibilidad histórica.
    if tel_limpio and not raw_phone.startswith('+') and not tel_limpio.startswith('54'):
        tel_limpio = '54' + tel_limpio
    if not tel_limpio:
        return ''
    # Armar mensaje profesional
    detalle = f"{tipo_propiedad} en {ciudad}".strip(' en') if tipo_propiedad or ciudad else "propiedad"
    precio_str = f" por {moneda} {precio}" if precio else ""
    op_str = f" en {operacion.lower()}" if operacion else ""
    mensaje = f"Hola! Me interesa {detalle}{op_str}{precio_str}. ¿Podés darme más información?"
    # Armar URL de WhatsApp
    return f"https://wa.me/{tel_limpio}?text={urllib.parse.quote(mensaje)}"


def generar_qr_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import urllib.parse, urllib.request, base64
    wa_url = generar_whatsapp_url(telefono, tipo_propiedad, ciudad, operacion, precio, moneda)
    if not wa_url:
        return ''
    # Generar QR de la URL de WhatsApp
    qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_url)}"
    try:
        with urllib.request.urlopen(qr_api, timeout=5) as resp:
            png_bytes = resp.read()
        b64 = base64.b64encode(png_bytes).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[QR] Error: {e}")
        return ''


def _sanitize_generated_email_html(raw_html):
    html_text = str(raw_html or '').strip()
    if not html_text:
        return ''

    html_text = re.sub(r'(?is)<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', html_text)
    html_text = re.sub(r'(?is)<a\b[^>]*>(.*?)</a>', r'\1', html_text)
    html_text = re.sub(r'(?is)</?(html|head|body)[^>]*>', '', html_text)
    html_text = re.sub(r'(?i)\b(?:mailto:|tel:|https?://|www\.)\S+', '', html_text)
    html_text = re.sub(r'(?i)href\s*=\s*["\']?(?:mailto:|tel:|https?://|www\.)[^"\'>\s]+["\']?', '', html_text)
    html_text = re.sub(r'(?i)\b[\w.+-]+@[\w-]+\.[\w.-]+\b', '', html_text)
    html_text = re.sub(r'>\s+<', '><', html_text)
    html_text = re.sub(r'\s{2,}', ' ', html_text)
    return html_text.strip()


def _sanitize_generated_email_text(raw_text):
    text = re.sub(r'(?is)<[^>]+>', ' ', str(raw_text or ''))
    text = re.sub(r'(?i)\b(?:mailto:|tel:|https?://|www\.)\S+', '', text)
    text = re.sub(r'(?i)\b[\w.+-]+@[\w-]+\.[\w.-]+\b', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

from rest_framework_simplejwt.views import TokenObtainPairView
from api.models import BannedIP, Agent

class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'detail': 'Tu IP ha sido bloqueada. Contacta al soporte.'}, status=status.HTTP_403_FORBIDDEN)
        
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Login successful
            email = request.data.get('email')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            try:
                agent = Agent.objects.get(email=email)
                from django.utils import timezone
                agent.last_login_ip = ip
                agent.last_login_user_agent = user_agent
                agent.last_login = timezone.now()
                agent.save(update_fields=['last_login_ip', 'last_login_user_agent', 'last_login'])
                response.data['user'] = {
                    'id': agent.id,
                    'email': agent.email,
                    'nombre': agent.nombre,
                    'is_staff': agent.is_staff,
                }
            except Agent.DoesNotExist:
                pass
        return response

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        from datetime import timedelta
        from django.utils import timezone
        email = request.data.get('email', '').strip().lower()
        
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'error': 'Tu IP ha sido bloqueada. No podés crear cuentas.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Verificar blacklist de emails baneados permanentemente
        from .models import Agent, BannedEmail
        if BannedEmail.objects.filter(email=email).exists():
            return Response({"error": "Esta cuenta ha sido inhabilitada permanentemente. No podés registrarte con este email."}, status=403)
        
        # Validar email duplicado
        if Agent.objects.filter(email=email).exists():
            return Response({"error": "Este email ya está registrado. ¿Olvidaste tu contraseña?"}, status=400)

        otp_verificado = OTPCode.objects.filter(
            email=email,
            verified=True,
            creado_en__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        if not otp_verificado:
            return Response({"error": "Debés verificar tu email primero"}, status=400)
            
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Asignar plan free por defecto
            user.plan_nombre = 'free'
            user.plan_activo = True
            user.plan_seleccionado = True
            user.save()
            
            # TAREA 3: Consumir el OTP para que no pueda reutilizarse
            otp_usado = OTPCode.objects.filter(
                email=email,
                verified=True,
                creado_en__gte=timezone.now() - timedelta(hours=1)
            ).order_by('-creado_en').first()
            if otp_usado:
                otp_usado.verified = False
                otp_usado.code_hash = 'USED'
                otp_usado.save()

            user.last_login_ip = ip
            user.last_login_user_agent = request.META.get('HTTP_USER_AGENT', '')
            user.save(update_fields=['last_login_ip', 'last_login_user_agent'])
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class PropertyViewSet(viewsets.ModelViewSet):
    """Stub — Property fue eliminado en v2.0. Se mantiene para compatibilidad con el router."""
    permission_classes = [IsAuthenticated]
    queryset = Listado.objects.none()
    serializer_class = RegisterSerializer  # placeholder

    def get_queryset(self):
        return Listado.objects.none()


class GeneratedAssetViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = GeneratedAsset.objects.none()
    serializer_class = GeneratedAssetSerializer

    def get_queryset(self):
        return GeneratedAsset.objects.filter(agent=self.request.user)
import os
import concurrent.futures

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_guion(request):
    import json as _json
    data = request.data
    tipo_video_raw = str(data.get('tipoVideo', 'reel')).strip().lower()
    tipo_video = {
        'tour_narrado': 'tour',
        'tour-narrado': 'tour',
        'reel_rapido': 'reel',
        'reel-rapido': 'reel',
    }.get(tipo_video_raw, tipo_video_raw if tipo_video_raw in ('tour', 'reel') else 'reel')

    script_rules = {
        'tour': {
            'required_scenes': 7,
            'min_total_words': 190,
            'max_total_words': 330,
            'scene_min_words': 24,
            'scene_max_words': 55,
            'scene_style': '2 a 3 frases por escena, con descripcion sensorial y argumento comercial concreto',
            'scene_names': [
                'Gancho',
                'Fachada y entorno',
                'Zona social',
                'Cocina y detalles',
                'Habitaciones',
                'Beneficio de inversion',
                'Cierre con CTA',
            ],
        },
        'reel': {
            'required_scenes': 4,
            'min_total_words': 30,
            'max_total_words': 65,
            'scene_min_words': 6,
            'scene_max_words': 18,
            'scene_style': '1 frase breve por escena, directa y de alto impacto',
            'scene_names': [
                'Gancho',
                'Diferencial',
                'Prueba social',
                'Cierre con CTA',
            ],
        },
    }
    rules = script_rules[tipo_video]

    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    pais = data.get('pais', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    recamaras = str(data.get('recamaras', '') or data.get('habitaciones', ''))
    banos = str(data.get('banos', '') or data.get('bathrooms', ''))
    voz = data.get('voz', 'femenina')
    tono = data.get('tono', 'profesional')
    contexto_adicional = data.get('contextoAdicional', '')

    tono_map = {
        'profesional': 'profesional y formal, transmite confianza sin sonar rigido',
        'lujo': 'sofisticado, aspiracional y sensorial',
        'energetico': 'dinamico, directo y de alto impacto',
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])

    narrador_instrucciones = (
        'voz masculina: firme y segura'
        if voz == 'masculina'
        else 'voz femenina: calida y cercana'
    )

    contexto_extra = f"\nENFOQUE ADICIONAL: {contexto_adicional}" if contexto_adicional else ''
    scene_names_hint = ', '.join(rules['scene_names'])

    prompt = f"""Sos copywriter inmobiliario experto en videos cortos para redes.
Genera un guion para formato {tipo_video.upper()}.

DATOS:
- Tipo: {tipo}
- Operacion: {operacion}
- Ciudad: {ciudad}
- Pais: {pais}
- Precio: {moneda} {precio}
- Recamaras: {recamaras}
- Banos: {banos}
- Tono: {tono_instrucciones}
- Narrador: {narrador_instrucciones}{contexto_extra}

REGLAS ESTRICTAS (OBLIGATORIAS):
- EXACTAMENTE {rules['required_scenes']} escenas
- TOTAL de palabras entre {rules['min_total_words']} y {rules['max_total_words']}
- Cada escena entre {rules['scene_min_words']} y {rules['scene_max_words']} palabras
- Estilo por escena: {rules['scene_style']}
- Escenas sugeridas (orden recomendado): {scene_names_hint}
- No repitas frases entre escenas
- Salida SOLO en JSON valido (sin markdown, sin texto extra)

FORMATO:
{{"escenas": [
  {{"nombre":"...","texto":"...","icono":"🎬"}}
]}}
"""

    def _count_words(text):
        return len(re.findall(r"\b[\w\u00C0-\u017F']+\b", str(text), flags=re.UNICODE))

    def _clean_scene_text(text):
        cleaned = str(text or '').strip()
        cleaned = cleaned.replace('**', '')
        cleaned = re.sub(r'^\s*[-*•]+\s*', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip('"').strip("'").strip()
        return cleaned

    def _extract_json_candidates(text):
        source = str(text or '').strip()
        candidates = [source]
        if not source:
            return candidates

        fence_trimmed = re.sub(r'^\s*```(?:json)?\s*', '', source, flags=re.IGNORECASE)
        fence_trimmed = re.sub(r'\s*```\s*$', '', fence_trimmed, flags=re.IGNORECASE).strip()
        if fence_trimmed and fence_trimmed != source:
            candidates.append(fence_trimmed)

        for open_char, close_char in (('{', '}'), ('[', ']')):
            start = source.find(open_char)
            while start != -1:
                depth = 0
                for idx in range(start, len(source)):
                    char = source[idx]
                    if char == open_char:
                        depth += 1
                    elif char == close_char:
                        depth -= 1
                        if depth == 0:
                            snippet = source[start:idx + 1].strip()
                            if snippet:
                                candidates.append(snippet)
                            break
                start = source.find(open_char, start + 1)

        return candidates

    def _parse_json_flexible(text):
        used = set()
        for candidate in _extract_json_candidates(text):
            if not candidate or candidate in used:
                continue
            used.add(candidate)
            try:
                return _json.loads(candidate)
            except Exception:
                continue
        return None

    def _extract_escenas(parsed):
        if isinstance(parsed, list):
            return parsed

        if isinstance(parsed, dict):
            if isinstance(parsed.get('escenas'), list):
                return parsed.get('escenas')
            for key in ('scenes', 'guion', 'slides'):
                if isinstance(parsed.get(key), list):
                    return parsed.get(key)
            if parsed and all(isinstance(v, (dict, str)) for v in parsed.values()):
                return list(parsed.values())

        return []

    def _normalize_escenas(parsed):
        source = _extract_escenas(parsed)
        normalized = []

        for idx, escena in enumerate(source, start=1):
            if isinstance(escena, dict):
                texto = _clean_scene_text(escena.get('texto', ''))
                nombre = _clean_scene_text(escena.get('nombre') or f'Escena {idx}')
                icono = _clean_scene_text(escena.get('icono') or '🎬')
            elif isinstance(escena, str):
                texto = _clean_scene_text(escena)
                nombre = f'Escena {idx}'
                icono = '🎬'
            else:
                continue

            if texto:
                normalized.append({
                    'nombre': nombre or f'Escena {idx}',
                    'texto': texto,
                    'icono': icono[:2] if icono else '🎬',
                })

        return normalized

    def _validate_escenas(escenas):
        if len(escenas) < rules['required_scenes']:
            return False, f"Escenas insuficientes: {len(escenas)}/{rules['required_scenes']}", None

        limited = escenas[:rules['required_scenes']]
        total_words = sum(_count_words(e.get('texto', '')) for e in limited)
        too_short = [
            idx + 1
            for idx, escena in enumerate(limited)
            if _count_words(escena.get('texto', '')) < max(4, rules['scene_min_words'] - 2)
        ]

        if too_short:
            return False, f"Escenas demasiado cortas: {too_short}", None

        if total_words < rules['min_total_words']:
            return False, f"Palabras insuficientes: {total_words}/{rules['min_total_words']}", None

        return True, '', {
            'escenas': limited,
            'total_words': total_words,
        }

    def _repair_with_gemini(raw_text, reason):
        repair_prompt = f"""Reformatea y mejora este guion inmobiliario.
Motivo de correccion: {reason}

Objetivo final obligatorio:
- EXACTAMENTE {rules['required_scenes']} escenas
- Minimo {rules['min_total_words']} palabras totales
- Cada escena entre {rules['scene_min_words']} y {rules['scene_max_words']} palabras
- Mantener tono {tono_instrucciones}
- Devolver SOLO JSON valido con la clave \"escenas\"

Contenido original:
{str(raw_text)[:7000]}
"""
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(call_gemini_api, repair_prompt, agente=request.user)
            return future.result(timeout=25)

    try:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(call_gemini_api, prompt, agente=request.user)
            raw_response = future.result(timeout=25)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        logger.exception("Error llamando Gemini en generar_guion")
        return Response({"error": "gemini_no_disponible", "detalle": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if not raw_response:
        return Response({"error": "gemini_sin_respuesta"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    attempts = [str(raw_response).strip()]
    final_validation = None
    final_reason = 'sin detalle'

    for attempt_idx in range(2):
        candidate_text = attempts[-1]
        parsed = _parse_json_flexible(candidate_text)

        if parsed is None:
            final_reason = 'Gemini no devolvio JSON parseable'
            if attempt_idx == 0:
                try:
                    repaired = _repair_with_gemini(candidate_text, final_reason)
                    if repaired:
                        attempts.append(str(repaired).strip())
                        continue
                except GeminiQuotaExhaustedError as e:
                    return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
                except Exception:
                    pass
            break

        escenas = _normalize_escenas(parsed)
        is_valid, reason, payload = _validate_escenas(escenas)
        final_reason = reason or final_reason
        if is_valid:
            final_validation = payload
            break

        if attempt_idx == 0:
            try:
                repaired = _repair_with_gemini(_json.dumps({'escenas': escenas}, ensure_ascii=False), reason)
                if repaired:
                    attempts.append(str(repaired).strip())
                    continue
            except GeminiQuotaExhaustedError as e:
                return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            except Exception:
                pass

    if not final_validation:
        return Response(
            {
                "error": "respuesta_ia_invalida",
                "detalle": final_reason,
                "raw": attempts[-1][:900],
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    escenas_finales = final_validation['escenas']
    total_words = final_validation['total_words']

    from .plan_utils import registrar_uso
    registrar_uso(request.user, 'ai')
    return Response(
        {
            'escenas': escenas_finales,
            'tipo_video': tipo_video,
            'source': 'gemini',
            'meta': {
                'required_scenes': rules['required_scenes'],
                'actual_scenes': len(escenas_finales),
                'min_total_words': rules['min_total_words'],
                'actual_total_words': total_words,
            },
        }
    )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_listado(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'ai'):
    #     return Response({
    #         "error": "limite_alcanzado", 
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)
            
    prompt_text = request.data.get("prompt", "")
    if not prompt_text:
        return Response({"error": "No prompt provided. Please pass a 'prompt' field in the JSON body."}, status=status.HTTP_400_BAD_REQUEST)
        
    system_prompt = "Sos un as copywriter de real estate. Escribí descripciones profesionales, persuasivas y completas (listados) para propiedades en venta o alquiler en español."

    try:
        result = call_groq_api(prompt_text, system_prompt=system_prompt)
    except Exception as e_groq:
        # Fallback: intentar con Gemini si Groq falla
        try:
            result = call_gemini_api(prompt_text, system_prompt=system_prompt, agente=request.user)
        except GeminiQuotaExhaustedError as e_gem:
            return Response({"error": "cuota_ia_agotada", "mensaje": str(e_gem)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except Exception as e_gem:
            return Response({
                "error": "IA no disponible",
                "detalle": f"Groq: {e_groq} | Gemini: {e_gem}"
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if request.user.is_authenticated:
        incrementar_uso(request.user, 'ai')
    return Response({"generated_text": result}, status=status.HTTP_200_OK)

class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        listados = Listado.objects.filter(agente=user)
        property_usage = UsageLog.objects.filter(agent=user, tipo='property')
        listados_este_mes = property_usage.filter(fecha__gte=start_of_month).count()
        total_generados = property_usage.count()
        
        videos_creados = listados.aggregate(total_videos=Sum('videos_creados'))['total_videos'] or 0

        listados_recientes = [
            _serialize_listing_summary(listado)
            for listado in listados.order_by('-creado_en')[:8]
        ]

        susc = get_suscripcion(user)
        plan = susc.plan

        return Response({
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "listados_este_mes": listados_este_mes,
            "total_generados": total_generados,
            "videos_creados": videos_creados,
            "conexiones_activas": 0,
            "listados_recientes": list(listados_recientes),
            "plan": plan.nombre,
            "plan_limites": {
                "properties_per_month": plan.properties_per_month,
                "ai_generations": plan.ai_generations,
                "image_generations": plan.image_generations,
                "video_generations": plan.video_generations,
                "branding": plan.branding
            },
            "uso_actual": {
                "properties_used": susc.properties_used,
                "ai_used": susc.ai_used,
                "images_used": susc.images_used,
                "videos_used": susc.videos_used
            }
        })

class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        default_agent = _get_default_commercial_agent(user)
        asociados = AgentAssociation.objects.filter(agente=user).select_related('asociado')
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": [
                {
                    "id": rel.asociado.id,
                    "nombre": rel.asociado.nombre,
                    "email": rel.asociado.email,
                }
                for rel in asociados
            ],
            "default_agent": _serialize_commercial_agent(default_agent),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter'),
            "is_staff": user.is_staff,
            "plan_seleccionado": user.plan_seleccionado,
            "plan_activo": user.plan_activo,
        })

    def put(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        if 'meta_access_token' in data:
            user.meta_access_token = data['meta_access_token']
        if 'meta_instagram_account_id' in data:
            user.meta_instagram_account_id = data['meta_instagram_account_id']
        if 'telefono' in data:
            user.telefono = _normalize_phone_e164(data['telefono']) or data['telefono']
        if 'agencia' in data:
            user.agencia = data['agencia']
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
        if 'nacionalidad' in data:
            user.nacionalidad = data['nacionalidad']
        if 'sitio_web' in data:
            user.sitio_web = data['sitio_web']
        if 'bio' in data:
            user.bio = data['bio']
            
        user.save()

        default_agent = _get_default_commercial_agent(user)
        asociados = AgentAssociation.objects.filter(agente=user).select_related('asociado')
        return Response({
            "message": "Perfil actualizado exitosamente",
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": [
                {
                    "id": rel.asociado.id,
                    "nombre": rel.asociado.nombre,
                    "email": rel.asociado.email,
                }
                for rel in asociados
            ],
            "default_agent": _serialize_commercial_agent(default_agent),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def commercial_agents_collection(request):
    if request.method == 'GET':
        profiles = ComercialAgentProfile.objects.filter(owner=request.user, activo=True).order_by('-is_default', '-updated_at')
        serializer = ComercialAgentProfileSerializer(profiles, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = ComercialAgentProfileSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    created = serializer.save(owner=request.user)

    if created.is_default:
        ComercialAgentProfile.objects.filter(owner=request.user, activo=True).exclude(id=created.id).update(is_default=False)
    elif not ComercialAgentProfile.objects.filter(owner=request.user, activo=True, is_default=True).exclude(id=created.id).exists():
        created.is_default = True
        created.save(update_fields=['is_default'])

    return Response(ComercialAgentProfileSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def commercial_agent_detail(request, agent_id):
    profile = get_object_or_404(ComercialAgentProfile, id=agent_id, owner=request.user)

    if request.method == 'GET':
        return Response(ComercialAgentProfileSerializer(profile).data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        was_default = profile.is_default
        profile.activo = False
        profile.is_default = False
        profile.save(update_fields=['activo', 'is_default'])

        if was_default:
            fallback = ComercialAgentProfile.objects.filter(owner=request.user, activo=True).order_by('-updated_at').first()
            if fallback:
                fallback.is_default = True
                fallback.save(update_fields=['is_default'])

        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ComercialAgentProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()

    if updated.is_default:
        ComercialAgentProfile.objects.filter(owner=request.user, activo=True).exclude(id=updated.id).update(is_default=False)

    return Response(ComercialAgentProfileSerializer(updated).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def commercial_agent_set_default(request, agent_id):
    profile = get_object_or_404(ComercialAgentProfile, id=agent_id, owner=request.user, activo=True)
    ComercialAgentProfile.objects.filter(owner=request.user, activo=True, is_default=True).exclude(id=profile.id).update(is_default=False)
    profile.is_default = True
    profile.save(update_fields=['is_default'])
    return Response({'ok': True, 'default_agent': ComercialAgentProfileSerializer(profile).data}, status=status.HTTP_200_OK)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def commercial_agent_photo(request, agent_id):
    profile = get_object_or_404(ComercialAgentProfile, id=agent_id, owner=request.user, activo=True)

    if request.method == 'DELETE':
        assets = profile.media_assets.filter(kind='agent_photo', is_active=True)
        for asset in assets:
            try:
                destroy_kwargs = {'resource_type': asset.resource_type or 'image'}
                for key_obj in AlmacenamientoCloudinary._get_pool_keys():
                    creds = AlmacenamientoCloudinary._parse_cloudinary_url(key_obj.api_key)
                    if creds and creds.get('cloud_name') == asset.cloud_name:
                        destroy_kwargs.update(creds)
                        break
                cloudinary.uploader.destroy(asset.public_id, **destroy_kwargs)
            except Exception as e:
                logger.warning(f"[AgentPhoto] No se pudo eliminar Cloudinary {asset.public_id}: {e}")
        assets.update(is_active=False)
        profile.foto_url = ''
        profile.save(update_fields=['foto_url', 'updated_at'])
        return Response({'ok': True, 'agent': ComercialAgentProfileSerializer(profile).data}, status=status.HTTP_200_OK)

    file_obj = request.FILES.get('file') or request.FILES.get('foto') or request.FILES.get('avatar')
    if not file_obj:
        return Response({'error': 'Archivo requerido en campo file.'}, status=status.HTTP_400_BAD_REQUEST)
    content_type = str(getattr(file_obj, 'content_type', '') or '').lower()
    if content_type and not content_type.startswith('image/'):
        return Response({'error': 'El archivo debe ser una imagen.'}, status=status.HTTP_400_BAD_REQUEST)

    metadata = AlmacenamientoCloudinary.guardar_avatar_metadata(file_obj, user_id=request.user.id)
    if not metadata or not metadata.get('public_id'):
        return Response({'error': 'No se pudo subir la foto del agente.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    profile.media_assets.filter(kind='agent_photo', is_active=True).update(is_active=False)
    asset = AgentMediaAsset.objects.create(
        owner=request.user,
        profile=profile,
        kind='agent_photo',
        cloud_name=metadata.get('cloud_name') or metadata.get('cloudinary_account') or '',
        public_id=metadata.get('public_id') or '',
        resource_type=metadata.get('resource_type') or 'image',
        secure_url=metadata.get('secure_url') or metadata.get('url') or '',
        bytes=metadata.get('bytes') or 0,
        format=metadata.get('format') or '',
        folder=metadata.get('folder') or '',
        original_filename=getattr(file_obj, 'name', '') or metadata.get('original_filename') or '',
        version=metadata.get('version') or '',
    )
    profile.foto_url = asset.secure_url or metadata.get('url') or ''
    profile.save(update_fields=['foto_url', 'updated_at'])
    return Response({
        'ok': True,
        'asset': AgentMediaAssetSerializer(asset).data,
        'agent': ComercialAgentProfileSerializer(profile).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def content_preferences_detail(request):
    prefs, _ = UserContentPreference.objects.get_or_create(owner=request.user)
    if request.method == 'GET':
        return Response(UserContentPreferenceSerializer(prefs).data, status=status.HTTP_200_OK)
    serializer = UserContentPreferenceSerializer(prefs, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(owner=request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def crm_clients_collection(request):
    if request.method == 'GET':
        clients = CRMClient.objects.filter(owner=request.user).order_by('-updated_at')
        estado = request.query_params.get('estado')
        if estado:
            clients = clients.filter(estado=estado)
        serializer = CRMClientSerializer(clients, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = CRMClientSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    created = serializer.save(owner=request.user)
    return Response(CRMClientSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def crm_client_detail(request, client_id):
    client = get_object_or_404(CRMClient, id=client_id, owner=request.user)

    if request.method == 'GET':
        return Response(CRMClientSerializer(client).data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = CRMClientSerializer(client, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save(owner=request.user)
    return Response(CRMClientSerializer(updated).data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def brand_templates_collection(request):
    if request.method == 'GET':
        templates = BrandTemplate.objects.filter(owner=request.user, is_active=True).order_by('-is_default', '-updated_at')
        serializer = BrandTemplateSerializer(templates, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = BrandTemplateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        created = serializer.save(owner=request.user)

        initial_tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
        if bool(request.data.get('use_base_tokens', False)) or not isinstance(initial_tokens, dict):
            initial_tokens = _default_tokens_for_base_template(created.base_template_id)
        else:
            initial_tokens = _resolve_brand_template_tokens(initial_tokens)
        initial_instructions = str(request.data.get('gemini_instructions') or '').strip()
        if not initial_instructions:
            initial_instructions = _build_template_gemini_instructions(created.name, created.base_template_id, initial_tokens)

        revision_serializer = BrandTemplateRevisionSerializer(data={
            'template': created.id,
            'tokens_json': initial_tokens,
            'gemini_instructions': initial_instructions,
            'status': 'published',
            'notes': 'Revision inicial',
        })
        revision_serializer.is_valid(raise_exception=True)
        revision_serializer.save(template=created, created_by=request.user)

        if created.is_default:
            BrandTemplate.objects.filter(owner=request.user, is_active=True).exclude(id=created.id).update(is_default=False)
        elif not BrandTemplate.objects.filter(owner=request.user, is_active=True, is_default=True).exclude(id=created.id).exists():
            created.is_default = True
            created.save(update_fields=['is_default'])

    return Response(BrandTemplateSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_clone(request):
    source_id = request.data.get('source_template_id') or request.data.get('sourceTemplateId')
    base_template_id = _normalize_template_id(request.data.get('base_template_id') or request.data.get('baseTemplateId')) or 'tech_modern'
    name = str(request.data.get('name') or 'Template duplicado').strip()[:120]
    description = request.data.get('description') or ''

    tokens = None
    if source_id:
        source_template = BrandTemplate.objects.filter(id=_parse_brand_template_id(source_id), owner=request.user, is_active=True).first()
        if source_template:
            published = source_template.revisions.filter(status='published').order_by('-revision').first()
            tokens = published.tokens_json if published else None
            base_template_id = source_template.base_template_id
    if not isinstance(tokens, dict):
        tokens = _default_tokens_for_base_template(base_template_id)
    instructions = str(request.data.get('gemini_instructions') or '').strip()

    created = BrandTemplate.objects.create(
        owner=request.user,
        name=name,
        description=description,
        base_template_id=base_template_id,
        is_default=bool(request.data.get('is_default', False)),
    )
    BrandTemplateRevision.objects.create(
        template=created,
        tokens_json=tokens,
        gemini_instructions=instructions or _build_template_gemini_instructions(name, base_template_id, tokens),
        status='published',
        created_by=request.user,
        notes='Clonado desde panel',
    )
    if created.is_default:
        BrandTemplate.objects.filter(owner=request.user, is_active=True).exclude(id=created.id).update(is_default=False)
    return Response(BrandTemplateSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def brand_template_detail(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user)

    if request.method == 'GET':
        return Response(BrandTemplateSerializer(template).data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        was_default = template.is_default
        template.is_active = False
        template.is_default = False
        template.save(update_fields=['is_active', 'is_default'])
        if was_default:
            fallback = BrandTemplate.objects.filter(owner=request.user, is_active=True).order_by('-updated_at').first()
            if fallback:
                fallback.is_default = True
                fallback.save(update_fields=['is_default'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = BrandTemplateSerializer(template, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    if updated.is_default:
        BrandTemplate.objects.filter(owner=request.user, is_active=True).exclude(id=updated.id).update(is_default=False)
    return Response(BrandTemplateSerializer(updated).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_set_default(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    BrandTemplate.objects.filter(owner=request.user, is_active=True, is_default=True).exclude(id=template.id).update(is_default=False)
    template.is_default = True
    template.save(update_fields=['is_default'])
    return Response({'ok': True, 'default_template': BrandTemplateSerializer(template).data}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def brand_template_revisions_collection(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)

    if request.method == 'GET':
        revisions = template.revisions.order_by('-revision')
        serializer = BrandTemplateRevisionSerializer(revisions, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = BrandTemplateRevisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    status_value = serializer.validated_data.get('status', 'draft')
    instructions = serializer.validated_data.get('gemini_instructions') or ''
    if not instructions:
        instructions = _build_template_gemini_instructions(
            template.name,
            template.base_template_id,
            serializer.validated_data.get('tokens_json') or default_template_tokens(),
        )
    created = serializer.save(template=template, created_by=request.user, status='draft', gemini_instructions=instructions)

    if status_value == 'published':
        template.revisions.filter(status='published').exclude(id=created.id).update(status='archived')
        created.status = 'published'
        created.save(update_fields=['status'])

    return Response(BrandTemplateRevisionSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_publish_revision(request, template_id, revision_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    revision = get_object_or_404(BrandTemplateRevision, id=revision_id, template=template)
    template.revisions.filter(status='published').exclude(id=revision.id).update(status='archived')
    revision.status = 'published'
    revision.save(update_fields=['status'])
    return Response({'ok': True, 'revision': BrandTemplateRevisionSerializer(revision).data}, status=status.HTTP_200_OK)


def _demo_qr_image_url():
    import urllib.parse
    wa_url = generar_whatsapp_url(
        '+541123456789',
        tipo_propiedad='Casa',
        ciudad='Miami Beach',
        operacion='Venta',
        precio='850.000',
        moneda='USD',
    )
    if not wa_url:
        return ''
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(wa_url)}"


def _brand_template_demo_context():
    return {
        'portada_url': 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1400&q=80',
        'logo_url': '',
        'operacion': 'Venta',
        'ciudad': 'Miami Beach',
        'titulo': 'Residencia premium',
        'tipoPropiedad': 'Casa',
        'moneda': 'USD',
        'precio': '850.000',
        'caracteristicas': [
            {'label': 'Dorm.', 'valor': '4'},
            {'label': 'Banos', 'valor': '3'},
            {'label': 'm2', 'valor': '320'},
            {'label': 'Coch.', 'valor': '2'},
        ],
        'agente_nombre': 'Agente LeadBook',
        'agente_telefono': '+54 11 2345 6789',
        'agencia_nombre': 'LeadBook Realty',
        'qr_url': _demo_qr_image_url(),
        'leadbook_logo_url': '',
    }


def _preview_dimensions(preview_format):
    if preview_format == 'story':
        return {'width': 1080, 'height': 1920}
    if preview_format == 'email':
        return {'width': 600, 'height': 900}
    return {'width': 1080, 'height': 1350}


def _render_brand_template_preview_html(base_template_id, tokens, preview_format='post'):
    template_id = _normalize_template_id(base_template_id) or 'tech_modern'
    resolved_tokens = _resolve_brand_template_tokens(tokens or _default_tokens_for_base_template(template_id))
    preview_format = str(preview_format or 'post').strip().lower()
    demo_context = _brand_template_demo_context()

    if preview_format == 'story':
        template_file = TEMPLATE_STORY_MAP.get(template_id, TEMPLATE_STORY_MAP['tech_modern'])
        html = render_to_string(template_file, demo_context)
    elif preview_format in ('carousel', 'carrusel'):
        preview_format = 'carousel'
        template_file = TEMPLATE_CAROUSEL_MAP.get(template_id, TEMPLATE_CAROUSEL_MAP['tech_modern'])
        carousel_context = {
            **demo_context,
            'headline': 'Residencia premium',
            'subheadline': 'Venta por USD 850.000. 320 m2, 4 hab, 3 banos. Desliza para ver la galeria.',
            'slide_number': 1,
            'total_slides': 6,
        }
        html = render_to_string(template_file, carousel_context)
    elif preview_format == 'email':
        template_file = TEMPLATE_EMAIL_MAP.get(template_id, TEMPLATE_EMAIL_MAP['tech_modern'])
        email_context = {
            'asunto': 'Residencia premium disponible',
            'logo_url': demo_context.get('logo_url', ''),
            'agenciaNombre': demo_context.get('agencia_nombre', ''),
            'tipoPropiedad': demo_context.get('tipoPropiedad', ''),
            'ciudad': demo_context.get('ciudad', ''),
            'portada_url': demo_context.get('portada_url', ''),
            'html_content': '<strong>Oportunidad destacada.</strong><br>Una propiedad pensada para vivir o invertir con alto valor percibido.',
            'moneda': demo_context.get('moneda', ''),
            'precio': demo_context.get('precio', ''),
            'operacion': demo_context.get('operacion', ''),
            'agenteNombre': demo_context.get('agente_nombre', ''),
            'agenteRol': 'Asesor Comercial',
            'agenteTelefono': demo_context.get('agente_telefono', ''),
            'agenteTelefonoDisplay': demo_context.get('agente_telefono', ''),
            'agenteEmail': 'agente@leadbook.com',
            'whatsapp_url': '',
        }
        html = render_to_string(template_file, email_context)
    else:
        preview_format = 'post'
        template_file = TEMPLATE_POST_MAP.get(template_id, TEMPLATE_POST_MAP['tech_modern'])
        html = render_to_string(template_file, demo_context)

    html = _apply_template_tokens_to_html(html, template_id, resolved_tokens)
    html = _inject_agency_brand_lockup(html, demo_context.get('logo_url', ''), demo_context.get('agencia_nombre', ''))
    return html, preview_format, resolved_tokens, _preview_dimensions(preview_format)


def _parse_json_object(text):
    source = str(text or '').strip()
    candidates = [source]
    cleaned = re.sub(r'^\s*```(?:json)?\s*', '', source, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.IGNORECASE).strip()
    if cleaned and cleaned != source:
        candidates.append(cleaned)
    start = source.find('{')
    while start != -1:
        depth = 0
        for idx in range(start, len(source)):
            if source[idx] == '{':
                depth += 1
            elif source[idx] == '}':
                depth -= 1
                if depth == 0:
                    candidates.append(source[start:idx + 1])
                    break
        start = source.find('{', start + 1)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            continue
    return None


def _is_hex_color(value):
    return isinstance(value, str) and bool(re.match(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', value.strip()))


def _sanitize_template_patch(patch):
    if not isinstance(patch, dict):
        return {}
    clean = {}
    palette = patch.get('palette') if isinstance(patch.get('palette'), dict) else {}
    clean_palette = {
        key: value.strip()
        for key, value in palette.items()
        if key in {'primary', 'secondary', 'accent', 'background', 'surface', 'text', 'muted_text', 'border'} and _is_hex_color(value)
    }
    overlay = palette.get('overlay')
    if isinstance(overlay, str) and re.match(r'^(rgba?\([^)]+\)|transparent)$', overlay.strip(), flags=re.IGNORECASE):
        clean_palette['overlay'] = overlay.strip()
    if clean_palette:
        clean['palette'] = clean_palette

    typography = patch.get('typography') if isinstance(patch.get('typography'), dict) else {}
    clean_typography = {}
    for key in ('display', 'body', 'mono'):
        if typography.get(key) in SYSTEM_FONT_IMPORT_MAP:
            clean_typography[key] = typography.get(key)
    if typography.get('title_transform') in {'uppercase', 'none'}:
        clean_typography['title_transform'] = typography.get('title_transform')
    if typography.get('letter_spacing') in {'tight', 'normal', 'wide'}:
        clean_typography['letter_spacing'] = typography.get('letter_spacing')
    if clean_typography:
        fonts = [clean_typography.get(k) for k in ('display', 'body', 'mono') if clean_typography.get(k)]
        if fonts:
            clean_typography['google_fonts'] = list(dict.fromkeys(fonts))
        clean['typography'] = clean_typography

    layout = patch.get('layout') if isinstance(patch.get('layout'), dict) else {}
    layout_allowed = {
        'logo_position': {'top_left', 'top_right'},
        'agent_block_position': {'bottom_left', 'bottom_right'},
        'qr_position': {'bottom_left', 'bottom_right'},
        'style': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['layout_styles']},
        'density': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['density']},
        'border_radius': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['border_radius']},
        'image_treatment': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['image_treatment']},
    }
    clean_layout = {key: value for key, value in layout.items() if key in layout_allowed and value in layout_allowed[key]}
    if clean_layout:
        clean['layout'] = clean_layout

    copy = patch.get('copy') if isinstance(patch.get('copy'), dict) else {}
    clean_copy = {}
    if copy.get('tone') in {'premium', 'profesional', 'lujo', 'minimal'}:
        clean_copy['tone'] = copy.get('tone')
    if copy.get('emoji_density') in {'none', 'low', 'medium', 'high'}:
        clean_copy['emoji_density'] = copy.get('emoji_density')
    if copy.get('cta_style') in {'whatsapp_direct', 'soft', 'strong'}:
        clean_copy['cta_style'] = copy.get('cta_style')
    if isinstance(copy.get('hashtags'), list):
        clean_copy['hashtags'] = [str(tag)[:50] for tag in copy.get('hashtags')[:20] if str(tag or '').strip()]
    if clean_copy:
        clean['copy'] = clean_copy

    components = patch.get('components') if isinstance(patch.get('components'), dict) else {}
    clean_components = {}
    hero = components.get('hero') if isinstance(components.get('hero'), dict) else {}
    clean_hero = {}
    if hero.get('overlay_strength') in {'none', 'soft', 'medium', 'strong'}:
        clean_hero['overlay_strength'] = hero.get('overlay_strength')
    if isinstance(hero.get('show_badge'), bool):
        clean_hero['show_badge'] = hero.get('show_badge')
    if clean_hero:
        clean_components['hero'] = clean_hero
    price = components.get('price') if isinstance(components.get('price'), dict) else {}
    if price.get('size') in {'small', 'medium', 'large', 'xlarge'}:
        clean_components['price'] = {'size': price.get('size')}
    stats = components.get('stats') if isinstance(components.get('stats'), dict) else {}
    if isinstance(stats.get('show_icons'), bool):
        clean_components['stats'] = {'show_icons': stats.get('show_icons')}
    contact = components.get('contact') if isinstance(components.get('contact'), dict) else {}
    clean_contact = {}
    for key in ('show_agent_photo', 'show_qr'):
        if isinstance(contact.get(key), bool):
            clean_contact[key] = contact.get(key)
    if clean_contact:
        clean_components['contact'] = clean_contact
    if clean_components:
        clean['components'] = clean_components
    return clean


def _template_ai_patch_from_message(message, current_tokens, base_template_id, user=None):
    prompt = f"""
Actua como disenador senior de templates inmobiliarios. Convierte el pedido del usuario en un JSON seguro de tokens visuales.
No generes HTML. No inventes campos fuera del schema. Responde SOLO JSON valido.

Template base: {base_template_id}
Tokens actuales:
{json.dumps(current_tokens, ensure_ascii=False)}

Pedido del usuario:
{message}

Formato exacto:
{{
  "reply": "respuesta breve para el usuario",
  "token_patch": {{}}
}}

Campos permitidos en token_patch: palette, typography, layout, components, copy.
Fuentes permitidas: {', '.join(SYSTEM_FONT_IMPORT_MAP.keys())}.
Colores solo HEX. No uses HTML ni CSS libre.
"""
    try:
        raw = smart_call(prompt, retries=1, agente=user)
        parsed = _parse_json_object(raw)
        if not isinstance(parsed, dict):
            return None
        patch = _sanitize_template_patch(parsed.get('token_patch') or {})
        reply = str(parsed.get('reply') or '').strip()
        if patch:
            return {'reply': reply, 'token_patch': patch}
    except GeminiQuotaExhaustedError:
        raise
    except Exception as exc:
        logger.warning("Template Studio AI patch failed: %s", exc)
    return None


def _template_patch_from_message(message):
    text = unicodedata.normalize('NFKD', str(message or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    patch = {}

    def merge(fragment):
        nonlocal patch
        patch = _deep_merge_dict(patch, fragment)

    if any(word in text for word in ('todo negro', 'full black', 'black', 'oscuro', 'negro')):
        merge({
            'palette': {
                'primary': '#000000',
                'secondary': '#080808',
                'accent': '#d6d6d6',
                'background': '#000000',
                'surface': '#111111',
                'text': '#ffffff',
                'muted_text': '#a1a1aa',
                'border': '#2a2a2a',
                'overlay': 'rgba(0,0,0,0.72)',
            },
            'layout': {'image_treatment': 'dark', 'style': 'dark_luxury'},
            'components': {'hero': {'overlay_strength': 'strong'}},
        })
    if any(word in text for word in ('dorado', 'gold', 'oro', 'luxury')):
        merge({'palette': {'accent': '#c9a84c'}, 'copy': {'tone': 'lujo'}})
    if any(word in text for word in ('rojo', 'red', 'colorado')):
        merge({'palette': {'accent': '#ef4444'}})
    if any(word in text for word in ('blanco', 'white', 'minimal', 'limpio')):
        merge({
            'palette': {
                'primary': '#111111',
                'secondary': '#f2f2f2',
                'accent': '#111111',
                'background': '#ffffff',
                'surface': '#f7f7f7',
                'text': '#111111',
                'muted_text': '#666666',
                'border': '#dddddd',
            },
            'layout': {'style': 'minimal_light', 'image_treatment': 'normal'},
        })
    if any(word in text for word in ('azul', 'blue', 'tech', 'neon')):
        merge({'palette': {'primary': '#0d47a1', 'secondary': '#1565c0', 'accent': '#00e5ff', 'background': '#081421', 'text': '#e8f3ff'}, 'layout': {'style': 'tech_modern'}})
    if any(word in text for word in ('calido', 'tierra', 'mediterraneo', 'warm')):
        merge({'palette': {'primary': '#6b4423', 'secondary': '#8b5e3c', 'accent': '#c17f3a', 'background': '#f8f4ef', 'text': '#2c2416'}, 'layout': {'style': 'mediterranean_warm', 'image_treatment': 'warm'}})

    if 'precio' in text and any(word in text for word in ('grande', 'mas grande', 'gigante', 'large')):
        merge({'components': {'price': {'size': 'large'}}})
    if 'precio' in text and any(word in text for word in ('chico', 'pequeno', 'small')):
        merge({'components': {'price': {'size': 'small'}}})
    wants_no_qr = any(phrase in text for phrase in ('sin qr', 'ocultar qr', 'no qr', 'sin codigo qr', 'sin codigo', 'quitar qr'))
    if wants_no_qr:
        merge({'components': {'contact': {'show_qr': False}}})
    wants_qr = any(phrase in text for phrase in (
        'mostrar qr', 'con qr', 'codigo qr', 'qr visible', 'quiero qr', 'tenga qr', 'incluir qr', 'activar qr'
    ))
    if wants_qr and not wants_no_qr:
        merge({'components': {'contact': {'show_qr': True}}})
    if 'sin foto agente' in text or 'ocultar agente' in text:
        merge({'components': {'contact': {'show_agent_photo': False}}})
    if 'sin iconos' in text:
        merge({'components': {'stats': {'show_icons': False}}})
    if 'con iconos' in text:
        merge({'components': {'stats': {'show_icons': True}}})

    if 'logo' in text:
        if 'izquierda' in text or 'left' in text:
            merge({'layout': {'logo_position': 'top_left'}})
        if 'derecha' in text or 'right' in text:
            merge({'layout': {'logo_position': 'top_right'}})
    if 'agente' in text:
        if 'derecha' in text or 'right' in text:
            merge({'layout': {'agent_block_position': 'bottom_right'}})
        if 'izquierda' in text or 'left' in text:
            merge({'layout': {'agent_block_position': 'bottom_left'}})
    if 'qr' in text:
        if 'izquierda' in text or 'left' in text:
            merge({'layout': {'qr_position': 'bottom_left'}})
        if 'derecha' in text or 'right' in text:
            merge({'layout': {'qr_position': 'bottom_right'}})

    if any(word in text for word in ('redondo', 'rounded', 'bordes grandes')):
        merge({'layout': {'border_radius': 'strong'}})
    if any(word in text for word in ('sin bordes', 'bordes rectos', 'square')):
        merge({'layout': {'border_radius': 'none'}})
    if any(word in text for word in ('espaciado', 'aire', 'spacious')):
        merge({'layout': {'density': 'spacious'}})
    if any(word in text for word in ('compacto', 'compact')):
        merge({'layout': {'density': 'compact'}})

    if any(word in text for word in ('bebas', 'alto impacto')):
        merge({'typography': {'display': 'Bebas Neue', 'google_fonts': ['Bebas Neue', 'DM Sans', 'Space Mono']}})
    if any(word in text for word in ('editorial', 'elegante')):
        merge({'typography': {'display': 'Cormorant Garamond', 'body': 'DM Sans', 'google_fonts': ['Cormorant Garamond', 'DM Sans']}})
    if any(word in text for word in ('mayuscula', 'uppercase')):
        merge({'typography': {'title_transform': 'uppercase'}})
    if any(word in text for word in ('minuscula', 'normal case')):
        merge({'typography': {'title_transform': 'none'}})

    if not patch:
        merge({'layout': {'density': 'comfortable'}})
    return patch


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_preview(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(tokens, dict):
        published = template.revisions.filter(status='published').order_by('-revision').first()
        tokens = published.tokens_json if published and isinstance(published.tokens_json, dict) else default_template_tokens()

    preview_format = str(request.data.get('format') or request.data.get('preview_format') or 'post').strip().lower()
    html, preview_format, resolved_tokens, dimensions = _render_brand_template_preview_html(template.base_template_id, tokens, preview_format)
    instructions = str(request.data.get('gemini_instructions') or '').strip() or _build_template_gemini_instructions(
        template.name,
        template.base_template_id,
        resolved_tokens,
    )
    return Response({
        'html': html,
        'format': preview_format,
        'dimensions': dimensions,
        'tokens_json': resolved_tokens,
        'gemini_instructions': instructions,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_draft_preview(request):
    base_template_id = _normalize_template_id(request.data.get('base_template_id') or request.data.get('baseTemplateId')) or 'tech_modern'
    tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(tokens, dict):
        tokens = _default_tokens_for_base_template(base_template_id)
    preview_format = str(request.data.get('format') or request.data.get('preview_format') or 'post').strip().lower()
    html, preview_format, resolved_tokens, dimensions = _render_brand_template_preview_html(base_template_id, tokens, preview_format)
    return Response({
        'html': html,
        'format': preview_format,
        'dimensions': dimensions,
        'base_template_id': base_template_id,
        'tokens_json': resolved_tokens,
        'gemini_instructions': _build_template_gemini_instructions('Borrador de template', base_template_id, resolved_tokens),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_draft_chat(request):
    base_template_id = _normalize_template_id(request.data.get('base_template_id') or request.data.get('baseTemplateId')) or 'tech_modern'
    message = str(request.data.get('message') or '').strip()
    current_tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(current_tokens, dict):
        current_tokens = _default_tokens_for_base_template(base_template_id)
    preview_format = str(request.data.get('format') or request.data.get('preview_format') or 'post').strip().lower()

    try:
        ai_result = _template_ai_patch_from_message(message, current_tokens, base_template_id, request.user) if message else None
    except GeminiQuotaExhaustedError as exc:
        return Response({'error': 'cuota_ia_agotada', 'mensaje': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if ai_result:
        token_patch = ai_result.get('token_patch') or {}
        reply = ai_result.get('reply') or 'Apliqué los cambios al borrador. Revisá la preview y guardá cuando te guste.'
    else:
        token_patch = _template_patch_from_message(message)
        reply = 'Apliqué los cambios al borrador. Revisá la preview y guardá cuando te guste.' if message else 'Decime qué querés cambiar: colores, tipografías, logo, QR, precio, bordes o estilo visual.'

    merged_tokens = _resolve_brand_template_tokens(_deep_merge_dict(current_tokens, token_patch))
    html, preview_format, merged_tokens, dimensions = _render_brand_template_preview_html(base_template_id, merged_tokens, preview_format)
    estimated_tokens = max(120, int((len(message) + len(json.dumps(current_tokens, ensure_ascii=False))) / 4)) if message else 0

    return Response({
        'reply': reply,
        'token_patch': token_patch,
        'tokens_json': merged_tokens,
        'html': html,
        'format': preview_format,
        'dimensions': dimensions,
        'base_template_id': base_template_id,
        'gemini_instructions': _build_template_gemini_instructions('Borrador de template', base_template_id, merged_tokens),
        'usage': {
            'ai_tokens_consumed': bool(message),
            'estimated_tokens': estimated_tokens,
            'note': 'Cada mensaje del chat consume tokens/creditos de IA.',
        },
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_chat(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    message = str(request.data.get('message') or '').strip()
    current_tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(current_tokens, dict):
        published = template.revisions.filter(status='published').order_by('-revision').first()
        current_tokens = published.tokens_json if published and isinstance(published.tokens_json, dict) else default_template_tokens()

    try:
        ai_result = _template_ai_patch_from_message(message, current_tokens, template.base_template_id, request.user) if message else None
    except GeminiQuotaExhaustedError as exc:
        return Response({'error': 'cuota_ia_agotada', 'mensaje': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    token_patch = (ai_result or {}).get('token_patch') or _template_patch_from_message(message)
    merged_tokens = _resolve_brand_template_tokens(_deep_merge_dict(current_tokens, token_patch))
    reply = (ai_result or {}).get('reply') or 'Apliqué los cambios al borrador. Revisá la preview y guardá la revisión si te gusta.'
    if not message:
        reply = 'Decime qué querés cambiar: colores, tipografías, logo, QR, precio, bordes o estilo visual.'

    return Response({
        'reply': reply,
        'token_patch': token_patch,
        'tokens_json': merged_tokens,
        'gemini_instructions': _build_template_gemini_instructions(template.name, template.base_template_id, merged_tokens),
    }, status=status.HTTP_200_OK)

from .services.instagram_service import (
    publicar_post,
    publicar_story,
    publicar_carrusel,
    MAX_INSTAGRAM_CAROUSEL_ITEMS,
    publicar_media_upload_api,
    consultar_uploadpost_status,
    get_upload_post_accounts,
)
from django.conf import settings

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_instagram(request):
    try:
        data = request.data
        tipo = data.get('tipo', 'post')
        imagen_url = data.get('imagen_url', '')
        imagenes_urls = data.get('imagenes_urls', [])
        caption = data.get('caption', '')
        
        user = request.user
        access_token = user.meta_access_token or getattr(settings, 'META_ACCESS_TOKEN', '')
        account_id = user.meta_instagram_account_id or getattr(settings, 'META_INSTAGRAM_ACCOUNT_ID', '')
        
        if not access_token or not account_id:
            return Response({"success": False, "error": "Credenciales de Instagram no configuradas."}, status=status.HTTP_400_BAD_REQUEST)
            
        if tipo == 'post':
            result = publicar_post(imagen_url, caption, access_token, account_id)
        elif tipo == 'story':
            result = publicar_story(imagen_url, access_token, account_id)
        elif tipo == 'carrusel':
            result = publicar_carrusel(imagenes_urls, caption, access_token, account_id)
        else:
            return Response({"success": False, "error": "Tipo invalido (post/story/carrusel)"}, status=status.HTTP_400_BAD_REQUEST)
            
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_redes_sociales(request):
    """
    Endpoint unificado para publicar contenido en redes sociales vía Upload Post API.
    Tipos soportados: image, video, carousel, document (PDF).
    """
    try:
        data = request.data
        media_type = data.get('media_type', 'image') # image, video, carousel, document
        caption = data.get('caption', '')
        
        # URLs de contenido
        image_url = data.get('image_url')
        video_url = data.get('video_url')
        document_url = data.get('document_url')
        images = data.get('images', []) # array de URLs para carrusel
        
        # Opciones extra
        platforms = data.get('platforms') # ej: ['instagram', 'facebook', 'youtube']
        scheduled_at = data.get('scheduled_at') # string ISO 8601
        request_id = data.get('request_id')
        
        user = request.user
        
        # Llamar al servicio unificado de Upload Post
        result = publicar_media_upload_api(
            media_type=media_type,
            caption=caption,
            image_url=image_url,
            video_url=video_url,
            images=images,
            document_url=document_url,
            platforms=platforms,
            scheduled_at=scheduled_at,
            request_id=request_id,
            agente=user
        )
        
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _extract_publish_image_url(payload):
    if not isinstance(payload, dict):
        return None
    return payload.get('image_url') or payload.get('url') or payload.get('imageUrl')


def _extract_publish_images(payload):
    if not isinstance(payload, dict):
        return []
    images = payload.get('images') or payload.get('imagenes_urls') or payload.get('imagenesUrls') or []
    if not images and payload.get('slides'):
        images = payload.get('slides')
    if isinstance(images, str):
        images = [images]

    normalized = []
    for item in images or []:
        if isinstance(item, str):
            url = item
        elif isinstance(item, dict):
            url = item.get('url') or item.get('image_url') or item.get('imageUrl')
        else:
            url = None
        if url:
            normalized.append(url)
    return normalized


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_redes_todo(request):
    """
    Publica automáticamente en Instagram las tres piezas principales:
    post de feed, story y carrusel. Cada pieza genera un request_id separado.
    """
    try:
        import uuid

        user = request.user
        data = request.data or {}
        batch_id = str(data.get('batch_id') or uuid.uuid4().hex[:12]).replace(' ', '-')[:64]

        accounts = get_upload_post_accounts(user)
        if accounts.get('success') and not any(str(red.get('platform')).lower() == 'instagram' for red in accounts.get('redes', [])):
            return Response({
                "success": False,
                "error": "No hay una cuenta de Instagram conectada. Conectala desde Conexiones antes de publicar."
            }, status=status.HTTP_400_BAD_REQUEST)

        post_payload = data.get('post') or {}
        story_payload = data.get('story') or {}
        carousel_payload = data.get('carousel') or data.get('carrusel') or {}

        post_image = _extract_publish_image_url(post_payload)
        story_image = _extract_publish_image_url(story_payload)
        carousel_images = _extract_publish_images(carousel_payload)
        carousel_original_count = len(carousel_images)

        missing = []
        if not post_image:
            missing.append('post')
        if not story_image:
            missing.append('story')
        if not carousel_images:
            missing.append('carousel')
        if missing:
            return Response({
                "success": False,
                "error": f"Faltan piezas para publicar: {', '.join(missing)}. Regenerá el contenido antes de publicar todo."
            }, status=status.HTTP_400_BAD_REQUEST)

        results = {}
        warnings = []
        if story_payload.get('caption') or story_payload.get('texto'):
            warnings.append('Instagram Stories no acepta caption por API; se publica solo la imagen de la story.')
        if carousel_original_count > MAX_INSTAGRAM_CAROUSEL_ITEMS:
            carousel_images = carousel_images[:MAX_INSTAGRAM_CAROUSEL_ITEMS]
            warnings.append(
                f"Instagram permite hasta {MAX_INSTAGRAM_CAROUSEL_ITEMS} imágenes por carrusel; "
                f"se publicarán las primeras {MAX_INSTAGRAM_CAROUSEL_ITEMS} de {carousel_original_count}."
            )

        publish_jobs = [
            ('post', 'image', post_payload.get('caption') or post_payload.get('texto') or '', post_image, None),
            ('story', 'story', story_payload.get('caption') or story_payload.get('texto') or '', story_image, None),
            ('carousel', 'carousel', carousel_payload.get('caption') or carousel_payload.get('texto') or '', None, carousel_images),
        ]

        for key, media_type, caption, image_url, images in publish_jobs:
            request_id = f"leadbook-{user.id}-{batch_id}-{key}"
            results[key] = publicar_media_upload_api(
                media_type=media_type,
                caption=caption,
                image_url=image_url,
                images=images,
                platforms=['instagram'],
                request_id=request_id,
                agente=user,
            )

        any_success = any(result.get('success') for result in results.values())
        all_success = all(result.get('success') for result in results.values())

        response_data = {
            "success": all_success,
            "partial_success": any_success and not all_success,
            "batch_id": batch_id,
            "results": results,
            "warnings": warnings,
        }
        return Response(response_data, status=status.HTTP_200_OK if any_success else status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def publicar_redes_status(request):
    result = consultar_uploadpost_status(
        request_id=request.query_params.get('request_id'),
        job_id=request.query_params.get('job_id'),
        agente=request.user,
    )
    return Response(result, status=status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_carrusel(request):
    """Genera carrusel narrativo con secciones editadas y galeria limpia."""
    try:
        user = request.user
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(user, 'image'):
        #      return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        listado_id_val = data.get('listado_id') or data.get('listadoId')

        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_carousel = TEMPLATE_CAROUSEL_MAP.get(template_id, TEMPLATE_CAROUSEL_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='carrusel')

        images_pool = _collect_property_images(data)
        gallery_images = images_pool[:MAX_CAROUSEL_GALLERY_IMAGES]
        gallery_omitted = max(0, len(images_pool) - len(gallery_images))
        recamaras = data.get('recamaras') or 'N/D'
        banos = data.get('banos') or 'N/D'
        superficie = data.get('superficieCubierta') or data.get('superficieTotal') or 'N/D'
        amenidades = data.get('amenidades') if isinstance(data.get('amenidades'), list) else []
        amenities_text = ', '.join(amenidades[:5]) if amenidades else 'amenidades seleccionadas para vivir mejor'
        precio_text = f"{data.get('moneda', 'USD')} {data.get('precio', '')}".strip()
        descripcion = str(data.get('descripcion') or data.get('descripcionGenerada') or '').strip()
        descripcion_corta = descripcion[:180].rstrip() if descripcion else 'Una propuesta pensada para vivir, invertir y decidir con informacion clara.'
        ubicacion_text = str(data.get('ciudad') or '').strip()
        tipo_propiedad = data.get('tipoPropiedad', 'Propiedad')
        operacion_text = data.get('operacion', 'Venta')

        def pick_image(index=0):
            if not images_pool:
                return None
            return images_pool[index % len(images_pool)]

        def render_clean_gallery_slide(image_url):
            return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ width: 1080px; height: 1350px; background: #050505; overflow: hidden; }}
  .photo {{ width: 100%; height: 100%; object-fit: contain; display: block; background: #050505; }}
</style>
</head>
<body>
  <img class="photo" src="{image_url}" alt="Galeria propiedad">
</body>
</html>"""

        def render_contact_slide(context):
            safe_agency = html_lib.escape(str(context.get("agencia_nombre", "") or '').strip()) or 'Agencia'
            safe_agent = html_lib.escape(str(context.get("agente_nombre", "") or '').strip()) or 'Asesor'
            safe_role = html_lib.escape(str(context.get("agente_rol", "") or 'Asesor Comercial').strip())
            if context.get('logo_url'):
                logo_html = (
                    f'<div class="brand-lockup"><img class="logo" src="{context.get("logo_url", "")}" alt="{safe_agency}">'
                    f'<span class="agency">{safe_agency}</span></div>'
                )
            else:
                logo_html = f'<div class="brand-lockup"><span class="agency">{safe_agency}</span></div>'
            agent_photo = f'<img class="agent-photo" src="{context.get("agente_foto_url", "")}" alt="{safe_agent}">' if context.get('agente_foto_url') else ''
            contact_html = str(context.get('agente_contacto_html') or '').strip()
            contact_line = f'<div class="meta">{contact_html}</div>' if contact_html else ''
            qr_html = f'<img class="qr" src="{context.get("qr_url", "")}" alt="QR WhatsApp">' if context.get('qr_url') else ''
            return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;700;900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ width: 1080px; height: 1350px; background: radial-gradient(circle at top right, rgba(201,168,76,.28), transparent 34%), #070707; color: #f7f3e8; overflow: hidden; font-family: 'DM Sans', sans-serif; }}
  .wrap {{ width: 100%; height: 100%; padding: 88px 82px; display: flex; flex-direction: column; justify-content: space-between; }}
  .top {{ display: flex; justify-content: flex-end; align-items: center; min-height: 90px; }}
  .brand-lockup {{ display: flex; align-items: center; gap: 16px; max-width: 520px; padding: 10px 16px; border: 1px solid rgba(255,255,255,.14); border-radius: 999px; background: rgba(0,0,0,.28); }}
  .logo {{ width: 66px; height: 66px; border-radius: 999px; object-fit: contain; padding: 7px; background: rgba(255,255,255,.94); }}
  .agency {{ font-size: 22px; letter-spacing: 3px; text-transform: uppercase; color: #c9a84c; font-weight: 900; line-height: 1.05; }}
  .headline {{ font-family: 'Bebas Neue', sans-serif; font-size: 168px; line-height: .86; letter-spacing: 3px; color: #c9a84c; text-transform: uppercase; }}
  .sub {{ margin-top: 28px; max-width: 820px; font-size: 38px; line-height: 1.2; color: rgba(255,255,255,.82); }}
  .contact {{ border: 1px solid rgba(201,168,76,.42); border-radius: 28px; padding: 34px; background: rgba(255,255,255,.045); display: flex; justify-content: space-between; gap: 36px; align-items: center; }}
  .agent {{ display: flex; align-items: center; gap: 22px; min-width: 0; }}
  .agent-photo {{ width: 116px; height: 116px; border-radius: 999px; object-fit: cover; border: 3px solid #c9a84c; }}
  .name {{ font-size: 44px; line-height: 1; font-weight: 900; color: #fff; }}
  .role {{ margin-top: 10px; font-size: 17px; letter-spacing: 3px; color: rgba(255,255,255,.48); text-transform: uppercase; }}
  .meta {{ margin-top: 12px; font-size: 24px; color: #c9a84c; }}
  .qr {{ width: 190px; height: 190px; padding: 10px; background: #fff; border-radius: 18px; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="top">{logo_html}</div>
    <main>
      <div class="headline">Contacto<br>Directo</div>
      <div class="sub">Pedí la ficha completa, disponibilidad y condiciones comerciales actualizadas.</div>
    </main>
    <section class="contact">
      <div class="agent">
        {agent_photo}
        <div>
          <div class="name">{safe_agent}</div>
          <div class="role">{safe_role} · {safe_agency}</div>
          {contact_line}
        </div>
      </div>
      {qr_html}
    </section>
  </div>
</body>
</html>"""

        hook_title = str(data.get('titulo') or f"{tipo_propiedad} en {ubicacion_text}" or tipo_propiedad).strip()
        hook_subheadline = (
            f"{operacion_text} por {precio_text}. {superficie} m2, {recamaras} hab, {banos} banos. "
            "Deslizá para ver la galería y guardá esta oportunidad."
        )

        slides_urls = []
        slides_content = [
            {"kind": "template", "image": pick_image(0), "headline": hook_title, "subheadline": hook_subheadline},
        ]

        for image_url in gallery_images:
            slides_content.append({"kind": "gallery", "image": image_url})

        slides_content.append({"kind": "contact", "image": None, "headline": "Contacto", "subheadline": ""})

        for i in range(len(slides_content)):
            slide = slides_content[i]
            context = {
                "portada_url": slide.get("image"),
                "headline": slide.get("headline", ""),
                "subheadline": slide.get("subheadline", ""),
                "slide_number": i + 1,
                "total_slides": len(slides_content),
                "logo_url": branding.get('logo_url', ''),
                "operacion": data.get('operacion', 'Venta'),
                "agente_nombre": branding.get('agente_nombre', ''),
                "agente_telefono": branding.get('agente_telefono', ''),
                "agente_email": branding.get('agente_email', ''),
                "agente_rol": branding.get('agente_rol', 'Asesor Comercial'),
                "agencia_nombre": branding.get('agencia_nombre', ''),
                "agente_foto_url": branding.get('agente_foto_url', ''),
                "agente_contacto_html": branding.get('agente_contacto_html', ''),
                "qr_url": generar_qr_url(
                    telefono=branding.get('agente_telefono', ''),
                    tipo_propiedad=data.get('tipoPropiedad', ''),
                    ciudad=data.get('ciudad', ''),
                    operacion=data.get('operacion', ''),
                    precio=data.get('precio', ''),
                    moneda=data.get('moneda', ''),
                ),
                "template_id": template_id,
            }

            if slide.get('kind') == 'gallery':
                html_content = render_clean_gallery_slide(slide.get('image'))
            elif slide.get('kind') == 'contact':
                html_content = render_contact_slide(context)
            else:
                html_content = render_to_string(template_carousel, context)
                html_content = _apply_template_tokens_to_html(html_content, template_id, selection.get('template_tokens'))
                html_content = _inject_agent_photo_html(html_content, branding.get('agente_foto_url', ''))
                html_content = _inject_agency_brand_lockup(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
                html_content = _inject_agency_logo_fallback(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
            image_stream = render_html_to_image(html_content, 1080, 1350)

            try:
                image_stream.seek(0)
                url = AlmacenamientoCloudinary.guardar_slide_carrusel(
                    image_stream,
                    user_id=request.user.id,
                    listado_id=listado_id_val,
                    indice=i + 1
                )
                if not url:
                    raise Exception('Almacenamiento devolvió None')
                slides_urls.append(url)
            except Exception as cloud_err:
                print(f"[DEBUG] ERROR Almacenamiento Slide {i+1}: {str(cloud_err)}")
                return Response({"error": f"Error subiendo slide {i+1}"}, status=500)

        prompt_text = f"""Escribí UN SOLO caption final para Instagram Carrusel, listo para publicar.
Propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}, {data.get('pais', '')}.
Operación y precio: {data.get('operacion', 'Venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.
Detalles: {recamaras} habitaciones, {banos} baños, {superficie} m2. Amenities/diferenciales: {amenities_text}. Contexto: {descripcion_corta}.

Requisitos obligatorios:
- 1100 a 1900 caracteres.
- Gancho con personalidad en la primera línea.
- 2 a 4 párrafos cortos, con deseo, exclusividad, inversión y beneficio concreto.
- Mencionar que el carrusel muestra recorrido/fotos reales y que conviene guardar o compartir.
- CTA claro a WhatsApp/consulta privada.
- Cerrar con 25 a 30 hashtags variados y específicos, no genéricos repetidos.
- No des opciones, no uses títulos como "Opción 1", no expliques el caption, no menciones que sos IA.
{_caption_preference_prompt(content_prefs)}"""
        caption = smart_call(prompt_text, system_prompt="Sos un director de marketing inmobiliario digital. Devolvés solo copy final listo para publicar.", agente=user)
        caption = _finalize_caption_text(caption, data, formato='carrusel', prefs=content_prefs, max_chars=2200)

        if listado_obj:
            actualizar_resultados_listado(
                listado_obj,
                'carrusel',
                {
                    "slides": slides_urls,
                    "caption": caption,
                    "template_id": template_id,
                    "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                    "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                    "total_slides": len(slides_urls),
                    "gallery_used": len(gallery_images),
                    "gallery_omitted": gallery_omitted,
                },
            )

        if user.is_authenticated:
            incrementar_uso(user, 'image')

        return Response({
            "slides": slides_urls,
            "caption": caption,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
            "total_slides": len(slides_urls),
            "gallery_used": len(gallery_images),
            "gallery_omitted": gallery_omitted,
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'La API free respondió límite real. Vamos a reintentar automáticamente en el próximo reset de 12 horas.'
        )
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_upload_avatar(request):
    try:
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=400)
        url = AlmacenamientoCloudinary.guardar_avatar(file, user_id=request.user.id)
        if not url:
            return Response({'error': 'Error al subir imagen'}, status=500)
        return Response({'url': url})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return self.put(request)

    def put(self, request):
        user = request.user
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
            
        if 'telefono' in data:
            user.telefono = _normalize_phone_e164(data['telefono']) or data['telefono']
        if 'agencia' in data:
            user.agencia = data['agencia']
        if 'nacionalidad' in data:
            user.nacionalidad = data['nacionalidad']
        if 'sitio_web' in data:
            user.sitio_web = data['sitio_web']
        elif 'sitioWeb' in data:
            user.sitio_web = data['sitioWeb']
        if 'bio' in data:
            user.bio = data['bio']
            
        user.save()
        default_agent = _get_default_commercial_agent(user)
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "default_agent": _serialize_commercial_agent(default_agent),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def video_status(request, listado_id):
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id, agente=request.user)

        status_map = {
            'ready': 'done',
            'failed': 'error',
            'none': 'idle',
        }
        normalized_status = status_map.get(listado.video_status, listado.video_status)

        return Response({
            "status": normalized_status,
            "video_url": listado.video_url
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class ListadosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devuelve todos los listados del usuario logueado"""
        listados = Listado.objects.filter(agente=request.user)
        data = [_serialize_listing_summary(listado) for listado in listados]
        return Response(data)

    def post(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # puede, usados, maximo = verificar_limite_plan(user)
        # if not puede:
        #     return Response({
        #         "error": f"Alcanzaste el límite de tu plan ({usados}/{maximo} listados este mes). Actualizá tu plan para continuar.",
        #         "limite_alcanzado": True,
        #         "usados": usados,
        #         "maximo": maximo
        #     }, status=403)
            
        data = request.data
        
        # Permitir tanto JSON plano como objeto anidado 'formData' (React)
        payload = data.get('formData') if isinstance(data, dict) and 'formData' in data else data
        if not isinstance(payload, dict):
            payload = {}
            
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(user, 'property'):
        #     return Response({"error": "limite_alcanzado", "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción."}, status=status.HTTP_403_FORBIDDEN)
        
        titulo = payload.get('titulo') or f"Propiedad en {payload.get('ciudad', 'Desconocida')}"
        tipo_propiedad = payload.get('tipoPropiedad', payload.get('tipo_propiedad', ''))
        operacion = payload.get('operacion', 'venta')
        ciudad = payload.get('ciudad', '')
        precio = str(payload.get('precio', ''))
        moneda = payload.get('moneda', 'USD')
        
        cover_frame_url = _resolve_listing_cover_frame(payload)
        if cover_frame_url:
            payload = {**payload, 'cover_frame_url': cover_frame_url}

        # Guardamos en datos_extra el payload limpio
        listado = Listado.objects.create(
            agente=user,
            titulo=titulo,
            tipo_propiedad=tipo_propiedad,
            operacion=operacion,
            ciudad=ciudad,
            precio=precio,
            moneda=moneda,
            datos_extra=payload
        )
        
        registrar_uso(user, 'property')
        
        return Response({
            "mensaje": "Listado guardado", 
            "id": listado.id,
            "titulo": listado.titulo
        }, status=status.HTTP_201_CREATED)

class ListadoDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk, agente=request.user)
            cover_url = _ensure_listing_pdf_cover_frame(listado) or _ensure_listing_cover_frame(listado)
            return Response({
                "id": listado.id,
                "titulo": listado.titulo,
                "tipo_propiedad": listado.tipo_propiedad,
                "operacion": listado.operacion,
                "ciudad": listado.ciudad,
                "precio": listado.precio,
                "moneda": listado.moneda,
                "video_url": listado.video_url,
                "video_status": listado.video_status,
                "dashboard_image_url": cover_url,
                "cover_frame_url": cover_url,
                "fotoportada": cover_url,
                "datos": listado.datos_extra
            }, status=status.HTTP_200_OK)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para eliminar este listado"}, status=status.HTTP_403_FORBIDDEN)

        # ── Eliminar assets de Cloudinary antes de borrar el registro ─────────
        datos = listado.datos_extra or {}
        public_ids_a_eliminar = []  # [(public_id, resource_type, cloud_name, api_key, api_secret)]

        def _extraer_public_id(obj):
            """Extrae public_id y credenciales de un dict de asset de Cloudinary."""
            if isinstance(obj, dict) and obj.get('public_id'):
                return (
                    obj['public_id'],
                    obj.get('resource_type', 'image'),
                    obj.get('cloudinary_account') or obj.get('cloud_name'),
                    obj.get('api_key'),
                    obj.get('api_secret'),
                )
            return None

        # Portada
        portada = datos.get('portadaUrl') or datos.get('portada_url')
        ref = _extraer_public_id(portada)
        if ref:
            public_ids_a_eliminar.append(ref)

        # Fotos de galería
        for foto in (datos.get('fotosRecorrido') or datos.get('fotos_recorrido') or []):
            ref = _extraer_public_id(foto)
            if ref:
                public_ids_a_eliminar.append(ref)

        # Assets generados en resultados
        resultados = datos.get('resultados') or {}
        for key, val in resultados.items():
            if isinstance(val, dict):
                ref = _extraer_public_id(val)
                if ref:
                    public_ids_a_eliminar.append(ref)
                # Slides de carrusel
                for slide in (val.get('slides') or []):
                    ref = _extraer_public_id(slide)
                    if ref:
                        public_ids_a_eliminar.append(ref)
            elif isinstance(val, list):
                for item in val:
                    ref = _extraer_public_id(item)
                    if ref:
                        public_ids_a_eliminar.append(ref)

        # Eliminar en Cloudinary — fallo individual no interrumpe la operación
        import cloudinary
        import cloudinary.uploader
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from django.conf import settings

        for (pub_id, res_type, cloud_name, api_key_val, api_secret_val) in public_ids_a_eliminar:
            try:
                # Usar credenciales del asset si las tiene, sino la cuenta global
                if cloud_name and api_key_val and api_secret_val:
                    cld_cfg = cloudinary.Config(
                        cloud_name=cloud_name,
                        api_key=api_key_val,
                        api_secret=api_secret_val,
                    )
                    cloudinary.uploader.destroy(pub_id, resource_type=res_type, config=cld_cfg)
                else:
                    cloudinary.uploader.destroy(pub_id, resource_type=res_type)
                logger.info(f"[Eliminar] Asset Cloudinary eliminado: {pub_id}")
            except Exception as cld_err:
                logger.warning(f"[Eliminar] No se pudo eliminar asset {pub_id} de Cloudinary: {cld_err}")

        # ── Borrar el registro de PostgreSQL ──────────────────────────────────
        listado.delete()
        return Response({"mensaje": "Listado eliminado"}, status=status.HTTP_200_OK)


    def put(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para modificar este listado"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data
        if 'datos' in data:
            datos = _merge_listing_extra_preserving_covers(listado.datos_extra, data['datos'])
            listado.datos_extra = datos
        if 'video_url' in data:
            listado.video_url = data['video_url']
        if 'video_status' in data:
            listado.video_status = data['video_status']
        
        listado.save()
        return Response({"mensaje": "Listado actualizado"}, status=status.HTTP_200_OK)


# ---- Celery task + endpoint para generación de video ----
from celery import shared_task
from .services.video_service import generar_video_listado

@shared_task
def generar_video_task(listado_id):
    """Genera video con Remotion para el listado"""
    try:
        success = generar_video_listado(listado_id)
        if success:
            from .models import Listado
            from .plan_utils import registrar_uso
            listado = Listado.objects.get(id=listado_id)
            registrar_uso(listado.agente, 'video')
            return {"status": "completado", "id": listado_id}
        else:
            return {"status": "fallido", "id": listado_id}
    except Exception as e:
        return {"error": str(e)}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_video(request, pk):
    """Dispara la generación de video asincronamente"""
    try:
        listado = Listado.objects.get(id=pk, agente=request.user)
        listado.video_status = 'queued'
        listado.save(update_fields=['video_status'])
        # Dispara tarea Celery
        generar_video_task.delay(pk)
        return Response({
            "status": "queued",
            "mensaje": "El video se está generando en segundo plano",
            "id": pk
        })
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)

def construir_contexto_pdf(data, user, request=None):
    # ─── Extraer hint de listado para el almacenamiento ──────────────────────
    listado_id_hint  = data.get('listado_id') or data.get('listadoId')

    # ─── Helpers de imágenes para WeasyPrint ─────────────────────────────
    temp_files = []

    def resolver_imagen(val, tipo='portada', indice=0):
        if not val: return None
        
        if isinstance(val, dict) and 'public_id' in val:
            from api.services.almacenamiento import AlmacenamientoCloudinary
            return AlmacenamientoCloudinary.obtener_url_foto(val)
            
        if isinstance(val, str):
            if val.startswith('http'):
                return val
            if val.startswith('data:'):
                from api.services.almacenamiento import AlmacenamientoCloudinary
                try:
                    res = AlmacenamientoCloudinary.guardar_foto_propiedad(
                        base64_str=val,
                        user_id=user.id,
                        listado_id=listado_id_hint,
                        tipo_foto=tipo,
                        indice=indice
                    )
                    if res and 'public_id' in res:
                        return AlmacenamientoCloudinary.obtener_url_foto(res)
                except Exception as e:
                    logger.error(f"Error subiendo base64 en resolver_imagen: {e}")
                return None
                
        return None



    # ─── Extraer campos normalizados ──────────────────────────────────────
    tipo_propiedad   = data.get('tipoPropiedad', data.get('tipo_propiedad', 'Propiedad'))
    ciudad           = data.get('ciudad', '')
    precio           = str(data.get('precio', ''))
    moneda           = data.get('moneda', 'USD')
    operacion        = data.get('operacion', 'Venta')
    recamaras        = data.get('recamaras', '')
    banos            = data.get('banos', '')
    superficie_cubierta = data.get('superficieCubierta', data.get('superficieConstruida', ''))
    superficie_total = data.get('superficieTotal', data.get('superficieTerreno', ''))
    estacionamientos = data.get('estacionamientos', '')
    amenidades       = data.get('amenidades', [])
    if not isinstance(amenidades, list):
        amenidades = []

    branding = _resolve_branding_payload(data, user)
    agente_nombre = branding.get('agente_nombre', '')
    agente_email = branding.get('agente_email', '')
    agencia_nombre = branding.get('agencia_nombre', '')
    agente_telefono = branding.get('agente_telefono', '')
    agente_rol = branding.get('agente_rol', 'Asesor Comercial')
    agente_foto_url = branding.get('agente_foto_url', '')

    # ─── Procesar imágenes (base64 Y URLs) ───────────────────────────────
    logo_url = branding.get('logo_url', '')

    portada_val_raw = data.get('portadaUrl', '')
    fotos_raw = data.get('fotosRecorrido', [])

    fotos_limpias = []
    for f in fotos_raw:
        if isinstance(f, dict):
            if f.get('public_id') and _resolve_cloudinary_asset_url(f) != logo_url:
                fotos_limpias.append(f)
        elif isinstance(f, str) and f and f != logo_url:
            fotos_limpias.append(f)

    # Si la portada viene vacía o es igual al logo, usar la primera foto real de la propiedad
    if not portada_val_raw or portada_val_raw == logo_url:
        if fotos_limpias:
            portada_val_raw = fotos_limpias[0]

    portada_url = resolver_imagen(portada_val_raw)

    fotos_recorrido_urls = []
    for fv in fotos_limpias:
        url_firma = resolver_imagen(fv)
        if url_firma:
            fotos_recorrido_urls.append(url_firma)

    # ─── Procesar escenas si las hay ─────────────────────────────────────
    escenas = data.get('escenas', [])
    if isinstance(escenas, list):
        escenas_procesadas = []
        for escena in escenas:
            if isinstance(escena, dict) and escena.get('fotoUrl'):
                url_firma = resolver_imagen(escena['fotoUrl'])
                escena = {**escena, 'fotoUrl': url_firma or escena['fotoUrl']}
            escenas_procesadas.append(escena)
        data['escenas'] = escenas_procesadas

    # ─── Descripción IA (si no viene en el payload) ──────────────────────
    descripcion = data.get('descripcion', '')
    if not descripcion:
        amenidades_str = ', '.join(amenidades) if amenidades else 'no especificadas'
        prompt_desc = f"""Generá una descripción inmobiliaria profesional de 2 párrafos para:
{tipo_propiedad} en {operacion} en {ciudad}.
Precio: {moneda} {precio}.
Recámaras: {recamaras}. Baños: {banos}.
Superficie construida: {superficie_cubierta}m2.
Terreno: {superficie_total}m2.
Amenidades: {amenidades_str}.

Párrafo 1: Descripción general de la propiedad y ubicación (3-4 oraciones).
Párrafo 2: Destacar amenidades y estilo de vida que ofrece (3-4 oraciones).
Tono elegante y persuasivo. Solo los 2 párrafos, sin títulos ni bullets."""
        descripcion_ia = smart_call(prompt_desc, system_prompt="Sos un copywriter inmobiliario de lujo. Escribís en español, con tono sofisticado y persuasivo.", agente=user)
        if descripcion_ia:
            descripcion = descripcion_ia
            from .plan_utils import registrar_uso
            registrar_uso(user, 'ai')
        else:
            logger.warning("[PDF] Gemini sin key/respuesta para descripcion. Usando fallback estatico.")
            descripcion = _fallback_descripcion_pdf(data)


    # QR Code del agente
    qr_base64_ = generar_qr_url(
        telefono=agente_telefono,
        tipo_propiedad=tipo_propiedad,
        ciudad=ciudad,
        operacion=operacion,
        precio=precio,
        moneda=moneda
    )

    # ─── Construir contexto del template ─────────────────────────────────
    context = {
        'tipo_propiedad':     tipo_propiedad,
        'ciudad':             ciudad,
        'precio':             precio,
        'moneda':             moneda,
        'operacion':          operacion,
        'recamaras':          recamaras,
        'banos':              banos,
        'superficie_cubierta': superficie_cubierta,
        'superficie_total':   superficie_total,
        'estacionamientos':   estacionamientos,
        'descripcion':        descripcion,
        'amenidades':         amenidades,
        'portada_url':        portada_url or '',
        'fotos_recorrido':    fotos_recorrido_urls,
        'logo_url':           logo_url or '',
        'agencia_logo_url':   logo_url or '',
        'portada_url_raw':    portada_url or '',
        'fotos_recorrido_raw': fotos_recorrido_urls,
        'logo_url_raw':       logo_url or '',
        'agente_nombre':      agente_nombre,
        'agente_telefono':    agente_telefono,
        'agente_email':       agente_email,
        'agente_rol':         agente_rol,
        'agente_foto_url':    agente_foto_url,
        'agencia_nombre':     agencia_nombre,
        'agente_contacto_html': _build_agent_contact_html(agente_telefono, agente_email),
        'qr_code':            qr_base64_,
        'whatsapp_url':       generar_whatsapp_url(
            telefono=agente_telefono,
            tipo_propiedad=tipo_propiedad,
            ciudad=ciudad,
            operacion=operacion,
            precio=precio,
            moneda=moneda,
        ),
    }


    return context, temp_files, listado_id_hint, tipo_propiedad, ciudad

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_pdf(request):
    # TODO: re-habilitar cuando el sistema de planes esté estable
    # if not puede_generar(request.user, 'property'):
    #     return Response({
    #         "error": "limite_alcanzado",
    #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        print(f"[PAYLOAD] portadaUrl tipo: {type(data.get('portadaUrl')).__name__} | valor: {str(data.get('portadaUrl', ''))[:80]}")
        print(f"[PAYLOAD] fotosRecorrido tipo: {type(data.get('fotosRecorrido')).__name__} | largo: {len(data.get('fotosRecorrido', []))}")
        if data.get('fotosRecorrido'):
            primera = data['fotosRecorrido'][0]
            print(f"[PAYLOAD] primera foto tipo: {type(primera).__name__} | valor: {str(primera)[:80]}")

        context, temp_files, listado_id_hint, tipo_propiedad, ciudad = construir_contexto_pdf(data, request.user, request)

        print(f"\n[PDF] Generando para {tipo_propiedad} en {ciudad} | portada: {bool(context.get('portada_url'))} | fotos: {len(context.get('fotos_recorrido', []))} | QR: sí")

        from django.template.loader import render_to_string
        from django.http import HttpResponse
        from api.services.render_engine import render_html_to_pdf
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from api.ai_services import generar_html_gemini, generar_html_desde_template
        from .models import Listado

        listado_obj = None
        if listado_id_hint:
            listado_obj = Listado.objects.filter(id=listado_id_hint, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_hint)
        template_id = selection.get('template_id')

        context['listado_id'] = listado_id_hint
        context['template_id'] = template_id
        context['template_tokens'] = selection.get('template_tokens')
        context['template_instructions'] = selection.get('template_instructions')

        logger.info(
            "[PDF] generar_pdf listado_id=%s template_id=%s user_id=%s",
            listado_id_hint,
            template_id,
            request.user.id,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='pdf')

        try:
            html_string = generar_html_desde_template(context, request.user)
        except Exception as e:
            print(f"[PDF] Error en sistema de templates: {e}. Usando fallback Gemini.")
            html_string = generar_html_gemini(context, request.user)
            
        if not html_string:
            print("[PDF] Fallback: Gemini falló, usando render_to_string estático")
            html_string = render_to_string('pdf/property_brochure_html.html', context)

        html_string = _inject_agency_brand_lockup(html_string, context.get('logo_url', ''), context.get('agencia_nombre', ''))

        # ─── Conversión a PDF Real con Playwright ────────────────────────────
        pdf_url = None
        pdf_cover_url = None
        try:
            print(f"[PDF] Iniciando conversión Playwright para listado {listado_id_hint}...")
            pdf_bytes = render_html_to_pdf(html_string)
            if pdf_bytes:
                print(f"[PDF] Conversión exitosa ({len(pdf_bytes)} bytes). Subiendo a Cloudinary...")
                pdf_url = AlmacenamientoCloudinary.guardar_pdf(
                    pdf_bytes, 
                    user_id=request.user.id, 
                    listado_id=listado_id_hint
                )
                
                # Persistir la URL en el listado para el historial
                if listado_obj and pdf_url:
                    pdf_cover_url = _render_and_store_pdf_cover(listado_obj, html_string)
                    if not listado_obj.datos_extra:
                        listado_obj.datos_extra = {}
                    if 'resultados' not in listado_obj.datos_extra:
                        listado_obj.datos_extra['resultados'] = {}

                    listado_obj.datos_extra['resultados']['pdf'] = {
                        "html": html_string,
                        "url": pdf_url,
                        "cover_frame_url": pdf_cover_url,
                        "cover_url": pdf_cover_url,
                        "template_id": template_id,
                        "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                        "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                    }
                    if pdf_cover_url:
                        listado_obj.datos_extra['dashboard_image_url'] = pdf_cover_url
                        listado_obj.datos_extra['cover_frame_url'] = pdf_cover_url
                    listado_obj.save(update_fields=['datos_extra'])
                    print(f"[PDF] URL guardada en DB: {pdf_url}")
            else:
                print("[PDF] Error: Playwright devolvió bytes vacíos.")
        except Exception as pdf_err:
            print(f"[PDF ERROR] Falló la conversión/subida: {pdf_err}")
            # El fallback es seguir adelante con el HTML solo

        # ─── Limpiar archivos temporales de imágenes ─────────────────────────
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        # Devolvemos JSON para que el frontend maneje el preview y el link de descarga
        return Response({
            "html": html_string,
            "url": pdf_url,
            "cover_frame_url": pdf_cover_url,
            "cover_url": pdf_cover_url,
            "listado_id": listado_id_hint,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
        }, status=status.HTTP_200_OK)

    except GeminiQuotaExhaustedError as e:
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'La API free respondió límite real. Vamos a reintentar automáticamente en el próximo reset de 12 horas.'
        )
        return Response({
            "error": "cuota_ia_agotada",
            "mensaje": str(e),
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)

    except Exception as e:
        import traceback
        error_completo = traceback.format_exc()
        print(f"[PDF ERROR COMPLETO]\n{error_completo}")
        return Response({"error": str(e), "trace": error_completo}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_post(request):
    """Genera imagen POST y la sube a Cloudinary"""
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        
        print(f"[POST DEBUG] agenteNombre: {data.get('agenteNombre')}")
        print(f"[POST DEBUG] agenteTelefono: {data.get('agenteTelefono')}")
        print(f"[POST DEBUG] agenciaNombre: {data.get('agenciaNombre')}")
        print(f"[POST DEBUG] keys recibidas: {list(data.keys())}")

        branding = _resolve_branding_payload(data, request.user)

        # Preparar contexto para la plantilla premium
        context = {
            "portada_url": data.get('portadaUrl'),
            "operacion": data.get('operacion', 'Venta'),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "titulo": f"{data.get('tipoPropiedad', '')} en {data.get('ciudad', '')}",
            "agente_email": branding.get('agente_email', ''),
            "logo_url": branding.get('logo_url', ''),
            "caracteristicas": [
                {"label": "m²", "valor": data.get('superficieCubierta') or data.get('superficieTotal')},
                {"label": "Hab", "valor": data.get('recamaras')},
                {"label": "Baños", "valor": data.get('banos')},
            ],
            "agente_nombre": branding.get('agente_nombre', ''),
            "agente_telefono": branding.get('agente_telefono', ''),
            "agente_rol": branding.get('agente_rol', 'Asesor Comercial'),
            "agencia_nombre": branding.get('agencia_nombre', ''),
            "agente_foto_url": branding.get('agente_foto_url', ''),
            "agente_contacto_html": branding.get('agente_contacto_html', ''),
            "leadbook_logo_url": _get_leadbook_logo_data_url(),
            "qr_url": generar_qr_url(
                telefono=branding.get('agente_telefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', '')
            ),
        }
        
        fotos_raw = data.get('fotosRecorrido', [])
        portada_val = fotos_raw[0] if fotos_raw else data.get('portadaUrl', '')
        if isinstance(portada_val, dict) and 'public_id' in portada_val:
            cloud = portada_val.get('cloudinary_account', 'df1vldrhb')
            pid = portada_val.get('public_id', '')
            portada_post = f"https://res.cloudinary.com/{cloud}/image/upload/{pid}"
        else:
            portada_post = str(portada_val) if portada_val else ''
            
        context["portada_url"] = portada_post
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        listado_id_val = data.get('listado_id') or data.get('listadoId')
        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_post = TEMPLATE_POST_MAP.get(template_id, TEMPLATE_POST_MAP['dubai_night'])
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='post')

        html_content = render_to_string(template_post, context)
        html_content = _apply_template_tokens_to_html(html_content, template_id, selection.get('template_tokens'))
        html_content = _inject_agent_photo_html(html_content, branding.get('agente_foto_url', ''))
        html_content = _inject_agency_brand_lockup(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        html_content = _inject_agency_logo_fallback(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        print(f"[POST] Template elegido: {template_post}")
        image_stream = render_html_to_image(html_content, 1080, 1350)

        prompt_text = f"""Escribí UN SOLO caption final para Instagram Feed, listo para publicar.
Propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}, {data.get('pais', '')}.
Operación y precio: {data.get('operacion', 'venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.
Datos: habitaciones {data.get('recamaras', '')}, baños {data.get('banos', '')}, superficie {data.get('superficieCubierta') or data.get('superficieTotal') or ''}. Amenities: {', '.join(data.get('amenidades', [])) if isinstance(data.get('amenidades'), list) else ''}.
Contexto adicional: {data.get('contextoAdicional', '') or data.get('notasAdicionales', '')}.

Requisitos obligatorios:
- 1100 a 1900 caracteres.
- Primera línea con gancho fuerte y personalidad, no genérica.
- 2 a 4 párrafos cortos con deseo, valor comercial, inversión/estilo de vida y urgencia elegante.
- Incluir detalles concretos, no solo adjetivos.
- CTA directo a WhatsApp o mensaje privado para ficha completa, disponibilidad y visita.
- Cerrar con 25 a 30 hashtags variados, mezclando ciudad, país, tipo de propiedad, operación, inversión, lujo y real estate.
- No des opciones, no uses títulos como "Opción 1", no expliques el caption, no menciones que sos IA.
Máximo 2200 caracteres. {_caption_preference_prompt(content_prefs)}"""
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales. Devolvés solo copy final listo para publicar.", agente=request.user)
        caption = _finalize_caption_text(caption, data, formato='post', prefs=content_prefs, max_chars=2200)

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            img_url = AlmacenamientoCloudinary.guardar_post(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolvió una URL válida")
            public_id = img_url
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crítico subiendo imagen: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la imagen a la nube. Reintentá en unos segundos."
            }, status=500)

        if listado_obj:
            actualizar_resultados_listado(
                listado_obj,
                'post',
                {
                    "url": img_url,
                    "caption": caption,
                    "template_id": template_id,
                    "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                    "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                },
            )

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "public_id": public_id,
            "caption": caption,
            "texto": caption,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_story(request):
    """Genera imagen Story, la sube a Cloudinary y devuelve también Base64 como respaldo"""
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado",
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        listado_id_val = data.get('listado_id') or data.get('listadoId')

        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_story = TEMPLATE_STORY_MAP.get(template_id, TEMPLATE_STORY_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='story')

        story_cover = _resolve_primary_property_image(data)
        images_pool = _collect_property_images(data)
        if not story_cover:
            story_cover = images_pool[0] if images_pool else ''

        # Preparar contexto para la plantilla premium
        context = {
            "portada_url": story_cover,
            "operacion": data.get('operacion', 'Venta'),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "logo_url": branding.get('logo_url', ''),
            "titulo": f"{data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}",
            "agente_nombre": branding.get('agente_nombre', ''),
            "agente_telefono": branding.get('agente_telefono', ''),
            "agente_rol": branding.get('agente_rol', 'Asesor Comercial'),
            "agente_email": branding.get('agente_email', ''),
            "agencia_nombre": branding.get('agencia_nombre', ''),
            "agente_foto_url": branding.get('agente_foto_url', ''),
            "agente_contacto_html": branding.get('agente_contacto_html', ''),
            "qr_url": generar_qr_url(
                telefono=branding.get('agente_telefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', ''),
            ),
            "caracteristicas": [
                {"label": "m²", "valor": data.get('superficieCubierta') or data.get('superficieTotal')},
                {"label": "Hab", "valor": data.get('recamaras')},
                {"label": "Baños", "valor": data.get('banos')},
            ]
        }
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        # Renderizar HTML y luego convertir a imagen PNG con Playwright (Formato vertical 9:16)
        html_content = render_to_string(template_story, context)
        html_content = _apply_template_tokens_to_html(html_content, template_id, selection.get('template_tokens'))
        html_content = _inject_agent_photo_html(html_content, branding.get('agente_foto_url', ''))
        html_content = _inject_agency_brand_lockup(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        html_content = _inject_agency_logo_fallback(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        image_stream = render_html_to_image(html_content, 1080, 1920)

        caption = ''

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            img_url = AlmacenamientoCloudinary.guardar_story(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolvió una URL válida")
            public_id = img_url
            img_base64 = None
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crítico subiendo story: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la historia a la nube."
            }, status=500)

        if listado_obj:
            actualizar_resultados_listado(
                listado_obj,
                'story',
                {
                    "url": img_url,
                    "caption": caption,
                    "template_id": template_id,
                    "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                    "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                },
            )

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "img_base64": img_base64,
            "public_id": public_id,
            "caption": caption,
            "texto": caption,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_caption_story(request):
    """Genera caption para Story solo cuando el usuario lo solicita."""
    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        listado_id_val = data.get('listado_id') or data.get('listadoId')
        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        prompt_text = f"""Escribí UN SOLO caption opcional para Instagram Story, listo para publicar.
Propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}, {data.get('pais', '')}.
Operación y precio: {data.get('operacion', 'venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.
Máximo 650 caracteres.
Debe tener: gancho breve, sensación premium, razón concreta para consultar, CTA a responder la story o escribir por WhatsApp y 8 a 12 hashtags.
No des opciones, no uses títulos como "Opción 1", no expliques el caption, no menciones que sos IA.
{_caption_preference_prompt(content_prefs)}"""
        raw_caption = smart_call(
            prompt_text,
            system_prompt="Sos un experto en marketing inmobiliario para stories. Devolvés solo copy final listo para publicar.",
            agente=request.user,
        )
        caption = _finalize_caption_text(raw_caption, data, formato='story', prefs=content_prefs, max_chars=650)

        if listado_obj:
            datos = listado_obj.datos_extra if isinstance(listado_obj.datos_extra, dict) else {}
            story_result = (((datos.get('resultados') or {}).get('story')) or {})
            if not isinstance(story_result, dict):
                story_result = {}
            story_result['caption'] = caption
            story_result['texto'] = caption
            actualizar_resultados_listado(listado_obj, 'story', story_result)

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'ai')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'ai')

        return Response({"caption": caption, "texto": caption}, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_email(request):
    try:
        # TODO: re-habilitar cuando el sistema de planes esté estable
        # if not puede_generar(request.user, 'ai'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        listado_id_val = data.get('listado_id') or data.get('listadoId')

        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_email = TEMPLATE_EMAIL_MAP.get(template_id, TEMPLATE_EMAIL_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='email')

        email_cover = _resolve_primary_property_image(data)
        images_pool = _collect_property_images(data)
        if not email_cover:
            email_cover = images_pool[0] if images_pool else ''
        email_gallery = [image_url for image_url in images_pool if image_url != email_cover][:6]
        template_meta = TEMPLATE_CATALOG.get(template_id, {})
        
        prompt_text = f"""
Redacta el cuerpo de un email profesional para ofrecer esta propiedad a un cliente interesado.
Tipo: {data.get('tipoPropiedad', 'Propiedad')}
Ciudad: {data.get('ciudad', '')}
Precio: {data.get('precio', '')}
Operación: {data.get('operacion', 'venta')}
Recámaras: {data.get('recamaras', '')}
Baños: {data.get('banos', '')}
Superficie: {data.get('superficieCubierta') or data.get('superficieTotal') or ''}
Amenidades: {', '.join(data.get('amenidades', [])) if isinstance(data.get('amenidades'), list) else ''}
Agente: {branding.get('agente_nombre', '')}
Agencia: {branding.get('agencia_nombre', '')}
Preferencias de copy: {_caption_preference_prompt(content_prefs)}

Debe incluir: introducción, galería/recorrido, amenities, precio y una invitación general a responder el correo.
No incluyas teléfonos, emails, WhatsApp, links, botones ni etiquetas <a>; la plantilla se encarga de los contactos reales.

Devuelve **ÚNICAMENTE** y estrictamente un objeto JSON válido (sin Markdown, sin ````json) con la siguiente estructura y nada más:
{{
  "asunto": "el asunto sugerido del correo",
  "html": "el cuerpo del email en una línea, todo en codigo html inline, usando etiquetas como <br>, <strong> (sin los tags <html>, <head> o <body>, solo contenido directo)",
  "texto_plano": "el equivalente en texto plano básico pero atractivo"
}}
"""
        json_str = smart_call(prompt_text, system_prompt="Sos un asistente técnico que solo responde en JSON.", agente=request.user)
        
        if json_str is None:
            json_str = '{"asunto": "Propiedad destacada", "html": "<div>Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles.</div>", "texto_plano": "Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles."}'
            
        import json
        try:
            parsed = json.loads(json_str)
        except:
            if '```json' in json_str:
                json_str = json_str.split('```json')[1].split('```')[0].strip()
                parsed = json.loads(json_str)
            else:
                parsed = {
                    "asunto": "Propiedad destacada",
                    "html": "<div>Propiedad disponible</div>",
                    "texto_plano": "Propiedad disponible"
                }
                
        if request.user.is_authenticated:
            incrementar_uso(request.user, 'ai')

        parsed_html = _sanitize_generated_email_html(parsed.get('html', ''))
        parsed_text = _sanitize_generated_email_text(parsed.get('texto_plano', '') or parsed.get('html', ''))
        if not parsed_html:
            fallback_body = parsed_text or 'Propiedad disponible'
            parsed_html = f'<div>{html_lib.escape(fallback_body).replace("\n", "<br>")}</div>'

        parsed['asunto'] = str(parsed.get('asunto', 'Propiedad destacada')).strip() or 'Propiedad destacada'
        parsed['html'] = parsed_html
        parsed['texto_plano'] = parsed_text or 'Propiedad disponible'

        # Inyectar en plantilla premium para consistencia visual total
        context = {
            "asunto": parsed.get("asunto", "Propiedad destacada"),
            "tipoPropiedad": data.get('tipoPropiedad', 'Propiedad'),
            "ciudad": data.get('ciudad', ''),
            "precio": data.get('precio', ''),
            "moneda": data.get('moneda', 'USD'),
            "operacion": data.get('operacion', 'Venta'),
            "agenteNombre": branding.get('agente_nombre') or getattr(request.user, 'first_name', '') or getattr(request.user, 'nombre', '') or request.user.email,
            "agenteEmail": branding.get('agente_email', ''),
            "agenteTelefono": branding.get('agente_telefono', ''),
            "agenteRol": branding.get('agente_rol', 'Asesor Comercial'),
            "agenciaNombre": branding.get('agencia_nombre', ''),
            "agenteFotoUrl": branding.get('agente_foto_url', ''),
            "agente_contacto_html": branding.get('agente_contacto_html', ''),
            "portada_url": email_cover,
            "galeria_urls": email_gallery,
            "logo_url": branding.get('logo_url', ''),
            "whatsapp_url": generar_whatsapp_url(
                telefono=branding.get('agente_telefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', ''),
            ),
            "agenteTelefonoDisplay": _format_phone_display(branding.get('agente_telefono', '')),
            "qr_url": generar_qr_url(
                telefono=branding.get('agente_telefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', ''),
            ),
            "html_content": parsed.get("html", ""),
            "template_id": template_id,
            "template_name": template_meta.get('name', ''),
            "color_primary": (template_meta.get('colors') or {}).get('primary', '#111111'),
            "color_secondary": (template_meta.get('colors') or {}).get('secondary', '#222222'),
            "color_accent": (template_meta.get('colors') or {}).get('accent', '#c9a84c'),
        }
        premium_html = render_to_string(template_email, context)
        if email_gallery:
            gallery_cells = ''.join(
                f'<td width="50%" style="padding:6px;"><img src="{url}" alt="Galeria" width="260" style="display:block;width:100%;height:150px;object-fit:cover;border:1px solid #2a2a2a;"></td>'
                for url in email_gallery[:6]
            )
            rows = []
            for idx in range(0, len(email_gallery[:6]), 2):
                pair = email_gallery[idx:idx + 2]
                cells = ''.join(
                    f'<td width="50%" style="padding:6px;"><img src="{url}" alt="Galeria" width="260" style="display:block;width:100%;height:150px;object-fit:cover;border:1px solid #2a2a2a;"></td>'
                    for url in pair
                )
                if len(pair) == 1:
                    cells += '<td width="50%" style="padding:6px;"></td>'
                rows.append(f'<tr>{cells}</tr>')
            gallery_block = (
                '<tr><td style="padding:10px 34px 0 34px;">'
                '<div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8fb1d1;margin-bottom:8px;font-weight:700;">Galeria</div>'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
                + ''.join(rows) +
                '</table></td></tr>'
            )
            premium_html = premium_html.replace('<tr>\n            <td style="padding:30px 34px 22px 34px;">', f'{gallery_block}\n<tr>\n            <td style="padding:30px 34px 22px 34px;">', 1)
        premium_html = _apply_template_tokens_to_html(premium_html, template_id, selection.get('template_tokens'))
        if branding.get('agente_foto_url'):
            agent_img = (
                f'<img src="{branding.get("agente_foto_url")}" alt="Foto agente" '
                'width="58" height="58" style="display:block;width:58px;height:58px;border-radius:50%;object-fit:cover;margin-bottom:10px;border:2px solid #00e5ff;">'
            )
            premium_html = re.sub(
                r'(<div style="padding-top:20px;border-top:[^"]*;color:[^"]*;font-size:13px;line-height:1\.6;">)',
                r'\1' + agent_img,
                premium_html,
                count=1,
            )
        parsed["html"] = premium_html
        parsed["template_id"] = template_id
        parsed["brand_template_id"] = (selection.get('brand_template').id if selection.get('brand_template') else None)
        parsed["brand_template_revision"] = (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None)
        
        # PERSISTENCIA: Guardar en el listado
        if listado_obj:
            actualizar_resultados_listado(listado_obj, 'email', parsed)
            
        return Response(parsed, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def serve_pdf_file(request, uuid_str):
    """Sirve el PDF generado. Soporta ambos prefijos (lb_pdf_ y pdf_) para compatibilidad."""
    from django.http import FileResponse
    # Buscar con nuevo prefijo primero, luego el legacy
    for prefix in ['lb_pdf_', 'pdf_']:
        pdf_path = os.path.join(tempfile.gettempdir(), f"{prefix}{uuid_str}.pdf")
        if os.path.exists(pdf_path):
            response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename="ficha-leadbook.pdf"'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Access-Control-Allow-Origin'] = '*'
            response['Content-Security-Policy'] = "frame-ancestors *"
            return response
    return Response({"error": "PDF no encontrado"}, status=status.HTTP_404_NOT_FOUND)

import mercadopago
from decouple import config
from decimal import Decimal, InvalidOperation
from django.db import transaction

MP_TEST_PRICE = Decimal('1')
MP_PRODUCTION_PRICE = Decimal('100000')
MP_PLAN_PRICES = {
    'starter': Decimal('25000'),
    'pro': Decimal('58000'),
    'scale': Decimal('125000'),
    'business': Decimal('125000'),
}

MP_PLAN_LABELS = {
    'starter': 'LeadBook Starter',
    'pro': 'LeadBook Pro',
    'scale': 'LeadBook Scale',
    'business': 'LeadBook Business',
}

MP_EXTRA_ITEMS = {
    'gemini': {'nombre': 'Contenido IA — Adicional (+1500 créditos)'},
    'elevenlabs': {'nombre': 'Voces Neurales — Adicional (+10.000 caracteres)'},
    'uploadpost': {'nombre': 'Gestor de Redes — Adicional (+10 publicaciones)'},
    'pack_completo': {'nombre': 'Pack Completo — Todos los recursos'},
}

MP_EXTRA_SERVICES = {
    'extra_gemini': ['gemini'],
    'extra_elevenlabs': ['elevenlabs'],
    'extra_uploadpost': ['uploadpost'],
    'extra_pack_completo': ['gemini', 'elevenlabs', 'uploadpost'],
}


def _mp_mode():
    mode = config('MP_MODE', default='production').strip().lower()
    return 'test' if mode == 'test' else 'production'


def _mp_access_token():
    return config('MP_ACCESS_TOKEN', default='').strip()


def _mp_public_key():
    return config('MP_PUBLIC_KEY', default='').strip()


def _mp_unit_price(plan=None):
    if _mp_mode() == 'test':
        return MP_TEST_PRICE
    if plan in MP_PLAN_PRICES:
        return MP_PLAN_PRICES[plan]
    return MP_TEST_PRICE if _mp_mode() == 'test' else MP_PRODUCTION_PRICE


def _mp_sdk():
    token = _mp_access_token()
    if not token:
        raise ValueError('Mercado Pago access token no configurado')
    return mercadopago.SDK(token)


def _mp_frontend_url():
    return config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app').rstrip('/')


def _mp_notification_url():
    backend_url = config('BACKEND_URL', default='http://localhost:8000').rstrip('/')
    return f'{backend_url}/api/mp/webhook/'


def _mp_decimal(value):
    try:
        return Decimal(str(value or '0'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _mp_pago_status(mp_status):
    if mp_status in {'approved', 'authorized'}:
        return 'approved'
    if mp_status in {'refunded', 'charged_back'}:
        return 'refunded'
    if mp_status in {'pending', 'in_process', 'in_mediation'}:
        return 'pending'
    return 'rejected'


def _mp_available_stock_missing(user, services):
    from .models import APIKey, Servicio

    missing = []
    for service_name in services:
        servicio = Servicio.objects.filter(nombre=service_name, activo=True).first()
        if not servicio:
            missing.append(service_name)
            continue

        available = APIKey.objects.filter(
            servicio=servicio,
            status='available',
        ).exclude(
            assignments__user=user,
            assignments__servicio=servicio,
        ).exists()
        if not available:
            missing.append(service_name)
    return missing


def _mp_create_preference(preference_data):
    preference_response = _mp_sdk().preference().create(preference_data)
    if preference_response.get('status') == 201:
        response = preference_response.get('response', {})
        init_point = response.get('init_point') or response.get('sandbox_init_point')
        amount = ((preference_data.get('items') or [{}])[0] or {}).get('unit_price')
        return {
            'init_point': init_point,
            'checkout_url': init_point,
            'preference_id': response.get('id'),
            'mode': _mp_mode(),
            'amount': str(amount if amount is not None else _mp_unit_price()),
        }
    print(f"MP Error: {preference_response}")
    return None


def _mp_webhook_event(request):
    event_type = request.data.get('type') or request.data.get('topic') or request.query_params.get('type') or request.query_params.get('topic')
    action = request.data.get('action') or request.query_params.get('action') or ''
    data = request.data.get('data') if isinstance(request.data, dict) else None
    data_id = (data.get('id') if isinstance(data, dict) else None) or request.data.get('id') or request.query_params.get('id') or request.query_params.get('data.id')
    return str(event_type or ''), str(action or ''), str(data_id or '')


def _mp_fetch_payment(payment_id):
    response = requests.get(
        f'https://api.mercadopago.com/v1/payments/{payment_id}',
        headers={'Authorization': f'Bearer {_mp_access_token()}'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _mp_notify(user, tipo, titulo, mensaje):
    try:
        crear_notificacion(user, tipo, titulo, mensaje)
    except Exception as exc:
        logger.warning(f'[MP] No se pudo crear notificación: {exc}')


def _mp_assign_paid_extra(agent, tipo, pago):
    from .models import AdminAlert, Servicio, UserAPIAssignment
    from .services.pool_service import APIPoolService

    assigned = []
    missing = []
    for service_name in MP_EXTRA_SERVICES.get(tipo, []):
        servicio = Servicio.objects.filter(nombre=service_name, activo=True).first()
        if not servicio:
            missing.append(service_name)
            continue

        exists = UserAPIAssignment.objects.filter(
            user=agent,
            servicio=servicio,
            pago=pago,
            is_primary=False,
            activo=True,
        ).exists()
        if exists:
            continue

        assignment = APIPoolService.add_extra_key(agent, service_name, pago=pago)
        if assignment:
            print(
                f"[MP] extra assigned user={agent.email} service={service_name} "
                f"payment={pago.mp_payment_id} key_id={assignment.apikey_id}",
                flush=True,
            )
            assigned.append(service_name)
        else:
            missing.append(service_name)

    if assigned:
        _mp_notify(
            agent,
            'api_extra_asignada',
            'Recurso adicional activado',
            f"Se activó tu recurso adicional: {', '.join(assigned)}.",
        )

    if missing:
        AdminAlert.objects.create(
            tipo='assign_failed',
            severidad='critical',
            titulo=f'Pago aprobado sin stock extra — {agent.email}',
            mensaje=f"Pago {pago.mp_payment_id} aprobado, pero faltó stock para: {', '.join(missing)}.",
            related_user=agent,
        )
        _mp_notify(
            agent,
            'pago_aprobado',
            'Pago aprobado en revisión',
            'Recibimos tu pago. Estamos activando el recurso adicional y te avisaremos cuando esté disponible.',
        )

    return assigned, missing


def _mp_process_payment(payment_data):
    from .models import Agent, Pago

    external_ref = str(payment_data.get('external_reference') or '')
    print(
        f"[MP] processing payment id={payment_data.get('id')} "
        f"status={payment_data.get('status')} external_reference={external_ref}",
        flush=True,
    )
    if '|' not in external_ref:
        return {'status': 'ignored', 'reason': 'external_reference_missing'}

    user_id, tipo = external_ref.split('|', 1)
    if tipo in MP_PLAN_LABELS:
        tipo = f'plan_{tipo}'

    valid_tipos = {f'plan_{plan}' for plan in MP_PLAN_LABELS} | set(MP_EXTRA_SERVICES)
    if tipo not in valid_tipos:
        return {'status': 'ignored', 'reason': 'invalid_type'}

    agent = Agent.objects.get(id=int(user_id))
    mp_payment_id = str(payment_data.get('id') or '')
    mp_status = str(payment_data.get('status') or '')
    pago_status = _mp_pago_status(mp_status)
    amount = _mp_decimal(payment_data.get('transaction_amount'))
    currency = str(payment_data.get('currency_id') or 'ARS')[:10]

    with transaction.atomic():
        pago, _ = Pago.objects.select_for_update().get_or_create(
            mp_payment_id=mp_payment_id,
            defaults={
                'user': agent,
                'tipo': tipo,
                'mp_status': pago_status,
                'monto': amount,
                'moneda': currency,
                'external_reference': external_ref,
                'datos_mp': payment_data,
            },
        )

        pago.user = pago.user or agent
        pago.tipo = tipo
        pago.mp_status = pago_status
        pago.monto = amount
        pago.moneda = currency
        pago.external_reference = external_ref
        pago.datos_mp = payment_data
        pago.procesado_en = timezone.now()
        pago.save(update_fields=[
            'user', 'tipo', 'mp_status', 'monto', 'moneda',
            'external_reference', 'datos_mp', 'procesado_en'
        ])

        if pago_status != 'approved':
            print(f"[MP] payment recorded id={mp_payment_id} status={pago_status}", flush=True)
            return {'status': 'recorded', 'mp_status': pago_status}

        if tipo.startswith('extra_'):
            assigned, missing = _mp_assign_paid_extra(agent, tipo, pago)
            print(
                f"[MP] extra payment processed id={mp_payment_id} tipo={tipo} "
                f"assigned={assigned} missing={missing}",
                flush=True,
            )
            return {'status': 'processed', 'assigned': assigned, 'missing': missing}

        plan = tipo.replace('plan_', '', 1)
        agent.plan_nombre = plan
        agent.plan_activo = True
        agent.plan_seleccionado = True
        agent.save(update_fields=['plan_nombre', 'plan_activo', 'plan_seleccionado'])
        from .services.pool_service import assign_apis_to_agent
        assign_apis_to_agent(agent)
        _mp_notify(agent, 'pago_aprobado', 'Plan activado', f'Tu plan {plan} ya está activo.')
        print(f"[MP] plan payment processed id={mp_payment_id} user={agent.email} plan={plan}", flush=True)
        return {'status': 'processed', 'plan': plan}

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout(request):
    plan = request.data.get('plan')
    ciclo = request.data.get('ciclo', 'monthly')

    if plan not in MP_PLAN_LABELS:
        return Response({"error": "Plan inválido"}, status=400)

    precio = _mp_unit_price(plan)
    nombre = f"{MP_PLAN_LABELS[plan]} ({'Anual' if ciclo == 'annual' else 'Mensual'})"
    frontend_url = _mp_frontend_url()

    preference_data = {
        "items": [{
            "id": f"{plan}_{ciclo}",
            "title": nombre,
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(precio)
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/pago-exitoso?plan={plan}",
            "failure": f"{frontend_url}/pago-fallido",
            "pending": f"{frontend_url}/pago-pendiente"
        },
        "auto_return": "approved",
        "notification_url": _mp_notification_url(),
        "external_reference": f"{request.user.id}|plan_{plan}",
        "metadata": {
            "user_id": request.user.id,
            "tipo": f"plan_{plan}",
            "mp_mode": _mp_mode(),
        },
    }

    try:
        response_data = _mp_create_preference(preference_data)
    except Exception as exc:
        logger.exception(f'[MP] Error creando checkout plan: {exc}')
        response_data = None

    if response_data:
        return Response(response_data)
    return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout_api_extra(request):
    """Genera link de pago para comprar una API adicional."""
    servicio = request.data.get('servicio', 'gemini')

    if servicio not in MP_EXTRA_ITEMS:
        return Response({"error": "Servicio inválido"}, status=400)

    tipo = f'extra_{servicio}'
    missing_stock = _mp_available_stock_missing(request.user, MP_EXTRA_SERVICES[tipo])
    if missing_stock:
        return Response({
            "error": "Sin stock disponible para este recurso",
            "servicios_sin_stock": missing_stock,
        }, status=409)

    item = MP_EXTRA_ITEMS[servicio]
    precio = _mp_unit_price()
    frontend_url = _mp_frontend_url()

    preference_data = {
        "items": [{
            "id": tipo,
            "title": item['nombre'],
            "description": f"Uso adicional permanente mensual de {item['nombre']}. Se suma a tu límite actual.",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(precio)
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/dashboard?extra=exitoso&servicio={servicio}",
            "failure": f"{frontend_url}/precios?extra=fallido",
            "pending": f"{frontend_url}/dashboard?extra=pendiente"
        },
        "auto_return": "approved",
        "notification_url": _mp_notification_url(),
        "external_reference": f"{request.user.id}|{tipo}",
        "metadata": {
            "user_id": request.user.id,
            "tipo": tipo,
            "servicio": servicio,
            "mp_mode": _mp_mode(),
        },
    }

    try:
        response_data = _mp_create_preference(preference_data)
    except Exception as exc:
        logger.exception(f'[MP] Error creando checkout extra: {exc}')
        response_data = None

    if response_data:
        return Response(response_data)
    return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    from .models import WebhookLog

    topic, action, data_id = _mp_webhook_event(request)
    body_payload = request.data
    if hasattr(body_payload, 'dict'):
        body_payload = body_payload.dict()
    elif isinstance(body_payload, dict):
        body_payload = dict(body_payload)
    else:
        body_payload = {}
    payload = {
        'body': body_payload,
        'query': request.query_params.dict(),
    }
    webhook_log = WebhookLog.objects.create(
        fuente='mercadopago',
        event_id=data_id or None,
        event_type=topic or action or None,
        payload=payload,
    )
    print(f"[MP] webhook received topic={topic} action={action} data_id={data_id}", flush=True)

    is_payment_event = topic == 'payment' or action.startswith('payment')
    if not data_id or not is_payment_event:
        webhook_log.status = 'ignored'
        webhook_log.procesado_en = timezone.now()
        webhook_log.save(update_fields=['status', 'procesado_en'])
        print(f"[MP] webhook ignored topic={topic} action={action} data_id={data_id}", flush=True)
        return Response({"status": "ok"})

    try:
        payment_data = _mp_fetch_payment(data_id)
        result = _mp_process_payment(payment_data)
        webhook_log.status = 'processed' if result.get('status') != 'ignored' else 'ignored'
        webhook_log.procesado_en = timezone.now()
        webhook_log.save(update_fields=['status', 'procesado_en'])
        print(f"[MP] webhook processed data_id={data_id} result={result}", flush=True)
        return Response({"status": "ok", "result": result})
    except Exception as e:
        webhook_log.status = 'error'
        webhook_log.error = str(e)
        webhook_log.procesado_en = timezone.now()
        webhook_log.save(update_fields=['status', 'error', 'procesado_en'])
        logger.exception(f"[MP] Error webhook: {e}")
        print(f"[MP] webhook error data_id={data_id} error={e}", flush=True)
        return Response({"status": "error"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def plan_status(request):
    from .models import Servicio, UserAPIQuota
    from .plan_utils import LIMITES

    user = request.user
    plan = user.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])
    now = timezone.now()
    listados_mes = UsageLog.objects.filter(agent=user, tipo='property', fecha__year=now.year, fecha__month=now.month).count()
    videos_used = UsageLog.objects.filter(agent=user, tipo='video', fecha__year=now.year, fecha__month=now.month).count()
    uploadpost_quota = None
    uploadpost = Servicio.objects.filter(nombre='uploadpost').first()
    if uploadpost:
        uploadpost_quota = UserAPIQuota.objects.filter(user=user, servicio=uploadpost).first()

    return Response({
        "plan_nombre": plan,
        "plan_activo": user.plan_activo,
        "plan_seleccionado": user.plan_seleccionado,
        "properties_per_month": limites['properties'],
        "video_generations": limites['videos'],
        "auto_posts_per_month": limites.get('auto_posts'),
        "auto_posting_unlimited": limites.get('auto_posts') is None,
        "properties_used": listados_mes,
        "videos_used": videos_used,
        "auto_posts_used": uploadpost_quota.requests_this_month if uploadpost_quota else 0,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seleccionar_plan_free(request):
    user = request.user
    user.plan_nombre = 'free'
    user.plan_activo = True
    user.plan_seleccionado = True
    user.save()
    return Response({"ok": True, "plan": "free"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_plan_info_mp(request):
    from .plan_utils import LIMITES
    from .models import UsageLog
    agent = request.user
    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])
    now = timezone.now()
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=now.year, creado_en__month=now.month
    ).count()
    return Response({
        "plan_nombre": plan,
        "mp_public_key": _mp_public_key(),
        "mp_mode": _mp_mode(),
        "uso_actual": {
            "properties_used": listados_mes,
            "ai_used": ai_used,
            "images_used": images_used,
            "videos_used": videos_used
        },
        "limites": {
            "properties_per_month": limites['properties'],
            "ai_generations": limites['ai'],
            "image_generations": limites['images'],
            "video_generations": limites['videos'],
            "auto_posts_per_month": limites.get('auto_posts'),
            "auto_posting_unlimited": limites.get('auto_posts') is None,
        }
    })


import secrets
import hashlib
from django.core.mail import send_mail
from datetime import timedelta


@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp(request):
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)

    recent = OTPCode.objects.filter(
        email=email,
        creado_en__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    if recent >= 3:
        return Response({"error": "Demasiados intentos. Esperá 15 minutos."}, status=429)

    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)

    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at
    )

    # Envío del OTP robusto: intenta Celery asíncrono; si falla o no hay broker,
    # cae a envío síncrono en el request. Así funciona en Railway sin worker.
    import sys
    from django.conf import settings

    # Log de diagnóstico MUY visible en Railway
    print(f"[EMAIL] Intentando enviar a {email}", flush=True)
    print(
        f"[EMAIL] DIAG backend={settings.EMAIL_BACKEND} "
        f"host={settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
        f"user_set={bool(settings.EMAIL_HOST_USER)} "
        f"pass_set={bool(settings.EMAIL_HOST_PASSWORD)} "
        f"eager={getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True)}",
        flush=True,
    )
    sys.stdout.flush()

    sent_mode = None
    try:
        from .tasks import send_otp_email_async

        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            # Eager: ejecutar la task sincronamente sin broker
            send_otp_email_async(email, code)
            sent_mode = 'sync-eager'
        else:
            # Intentar enviar al broker Celery (Redis)
            send_otp_email_async.delay(email, code)
            sent_mode = 'celery-queued'
        print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
    except Exception as e_celery:
        # Broker caído, sin Redis, o cualquier otro problema: fallback sync
        print(f"[EMAIL] ERROR al enviar (celery path): {type(e_celery).__name__}: {str(e_celery)}", flush=True)
        print(f"[EMAIL] Intentando fallback sync a {email}", flush=True)
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
            sent_mode = 'sync-fallback'
            print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
        except Exception as e_sync:
            print(f"[EMAIL] ERROR al enviar: {str(e_sync)}", flush=True)
            import traceback
            traceback.print_exc()
            sent_mode = f'error:{type(e_sync).__name__}'

    sys.stdout.flush()
    return Response({"mensaje": "Código enviado", "email": email, "_mode": sent_mode})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('code', '').strip()

    if not email or not code:
        return Response({"error": "Email y código requeridos"}, status=400)

    otp = OTPCode.objects.filter(
        email=email,
        verified=False
    ).order_by('-creado_en').first()

    if not otp:
        return Response({"error": "Código inválido o ya utilizado"}, status=400)

    if otp.is_expired():
        return Response({"error": "Código expirado. Pedí uno nuevo."}, status=400)

    if otp.attempts >= 5:
        return Response({"error": "Demasiados intentos. Pedí un nuevo código."}, status=429)

    # Verificar hash ANTES de incrementar attempts para no penalizar el intento correcto
    code_hash = OTPCode.hash_code(code)
    if otp.code_hash != code_hash:
        otp.attempts += 1
        otp.save()
        intentos_restantes = 5 - otp.attempts
        return Response({"error": f"Código incorrecto. {intentos_restantes} intentos restantes."}, status=400)

    # Código correcto
    otp.verified = True
    otp.save()

    return Response({"verificado": True, "email": email})


@api_view(['POST'])
@permission_classes([AllowAny])
def recuperar_password(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "No encontramos una cuenta con ese email"}, status=404)
    
    import secrets
    import hashlib
    from datetime import timedelta
    from django.utils import timezone
    
    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at,
        tipo="recuperacion"
    )

    # Envío robusto con fallback síncrono (idéntico a send_otp)
    try:
        from django.conf import settings
        from .tasks import send_otp_email_async
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            send_otp_email_async(email, code)
        else:
            send_otp_email_async.delay(email, code)
    except Exception as e_celery:
        print(f"[OTP-RECOV] Celery falló ({e_celery}). Fallback sync.")
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
        except Exception as e_sync:
            print(f"[OTP-RECOV] ERROR envío síncrono: {e_sync}")

    return Response({"mensaje": "Código enviado", "email": email}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def confirmar_recuperacion(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('codigo', '').strip()
    nueva_password = request.data.get('nueva_password', '')
    
    if not email or not code or not nueva_password:
        return Response({"error": "Faltan datos requeridos"}, status=400)
    
    otp = OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        verified=False
    ).order_by('-creado_en').first()
    
    if not otp:
        return Response({"error": "Código inválido"}, status=400)
    if otp.is_expired():
        return Response({"error": "Código expirado"}, status=400)
    if not otp.is_valid(code):
        return Response({"error": "Código incorrecto"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "Usuario no encontrado"}, status=404)
    
    user.set_password(nueva_password)
    user.save()
    
    otp.verified = True
    otp.save()
    
    return Response({"mensaje": "Contraseña actualizada correctamente"}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_terminos(request):
    """Devuelve los Términos y Condiciones vigentes"""
    try:
        terminos = TerminosCondiciones.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = TerminosCondicionesSerializer(terminos)
        return Response(serializer.data)
    except TerminosCondiciones.DoesNotExist:
        return Response({"error": "Términos no disponibles"}, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_politica_privacidad(request):
    """Devuelve la Política de Privacidad vigente"""
    try:
        politica = PoliticaPrivacidad.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = PoliticaPrivacidadSerializer(politica)
        return Response(serializer.data)
    except PoliticaPrivacidad.DoesNotExist:
        return Response({"error": "Política de privacidad no disponible"}, status=404)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def amenidades_presets(request):
    from .models import AmenidadPreset
    agente = request.user
    if request.method == 'GET':
        presets = AmenidadPreset.objects.filter(agente=agente)
        return Response({'presets': [p.nombre for p in presets]})
    
    if request.method == 'POST':
        nombre = request.data.get('nombre', '').strip()
        if not nombre:
            return Response({'error': 'Nombre requerido'}, status=400)
        preset, created = AmenidadPreset.objects.get_or_create(
            agente=agente, nombre=nombre
        )
        return Response({
            'nombre': preset.nombre, 
            'created': created
        }, status=201 if created else 200)


FIELD_PRESET_ALLOWED_FIELDS = {
    'tipoPropiedad', 'operacion', 'pais', 'idioma', 'ciudad', 'direccion',
    'moneda', 'precio', 'recamaras', 'banos', 'superficieConstruida',
    'superficieTerreno', 'estacionamientos', 'pisosNiveles',
    'superficieCubierta', 'superficieTotal', 'niveles',
}


def _serialize_field_preset(preset):
    return {
        'id': preset.id,
        'field': preset.field,
        'value': preset.value,
        'label': preset.label or preset.value,
        'metadata': preset.metadata or {},
        'usage_count': preset.usage_count,
        'last_used_at': preset.last_used_at.isoformat() if preset.last_used_at else None,
    }


def _upsert_field_preset(user, raw):
    from .models import UserFieldPreset

    field = str((raw or {}).get('field') or '').strip()
    value = str((raw or {}).get('value') or '').strip()
    if field not in FIELD_PRESET_ALLOWED_FIELDS or not value:
        return None

    label = str((raw or {}).get('label') or value).strip()[:255]
    metadata = (raw or {}).get('metadata') if isinstance((raw or {}).get('metadata'), dict) else {}

    preset, created = UserFieldPreset.objects.get_or_create(
        user=user,
        field=field,
        value=value[:255],
        defaults={
            'label': label,
            'metadata': metadata,
            'last_used_at': timezone.now(),
        },
    )
    if not created:
        preset.label = label or preset.label
        preset.metadata = {**(preset.metadata or {}), **metadata}
        preset.usage_count += 1
        preset.last_used_at = timezone.now()
        preset.save(update_fields=['label', 'metadata', 'usage_count', 'last_used_at', 'updated_at'])
    return preset


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def field_presets_collection(request):
    from .models import UserFieldPreset

    if request.method == 'GET':
        raw_fields = request.query_params.get('fields', '')
        fields = [f.strip() for f in raw_fields.split(',') if f.strip()]
        fields = [f for f in fields if f in FIELD_PRESET_ALLOWED_FIELDS]
        try:
            limit = min(max(int(request.query_params.get('limit', 8) or 8), 1), 30)
        except (TypeError, ValueError):
            limit = 8

        qs = UserFieldPreset.objects.filter(user=request.user)
        if fields:
            qs = qs.filter(field__in=fields)
        qs = qs.order_by('field', '-usage_count', '-last_used_at')

        grouped = {field: [] for field in fields}
        items = []
        counts = {}
        for preset in qs:
            count = counts.get(preset.field, 0)
            if count >= limit:
                continue
            serialized = _serialize_field_preset(preset)
            grouped.setdefault(preset.field, []).append(serialized)
            items.append(serialized)
            counts[preset.field] = count + 1

        return Response({'presets': grouped, 'items': items})

    payload_items = request.data.get('items') if isinstance(request.data, dict) else None
    if not isinstance(payload_items, list):
        payload_items = [request.data]

    saved = []
    for raw in payload_items:
        preset = _upsert_field_preset(request.user, raw if isinstance(raw, dict) else {})
        if preset:
            saved.append(_serialize_field_preset(preset))
    return Response({'presets': saved}, status=status.HTTP_201_CREATED if saved else status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def field_preset_detail(request, preset_id):
    from .models import UserFieldPreset

    deleted, _ = UserFieldPreset.objects.filter(id=preset_id, user=request.user).delete()
    if not deleted:
        return Response({'error': 'Preset no encontrado'}, status=404)
    return Response({'ok': True})

from django.utils import timezone
from datetime import timedelta

ADMIN_KEY = config('ADMIN_KEY', default='')

def check_admin(request):
    return request.headers.get('X-Admin-Key') == ADMIN_KEY

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats(request):
    """
    Dashboard de administración: Métricas globales y estado detallado de las APIs asignadas.
    """
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from django.utils import timezone
    from datetime import timedelta

    ahora = timezone.now()
    hoy = ahora - timedelta(hours=24)
    semana = ahora - timedelta(days=7)
    
    from .models import Agent, Listado
    
    total = Agent.objects.count()
    activos_hoy = Agent.objects.filter(
        last_login__gte=hoy).count()
    activos_semana = Agent.objects.filter(
        last_login__gte=semana).count()
    nuevos_hoy = Agent.objects.filter(
        fecha_registro__gte=hoy).count()
    nuevos_semana = Agent.objects.filter(
        fecha_registro__gte=semana).count()
    
    distribucion = {}
    for plan in ['free','starter','pro','scale','business']:
        distribucion[plan] = Agent.objects.filter(
            plan_nombre=plan).count()
    
    try:
        total_listados = Listado.objects.count()
    except:
        total_listados = 0
    
    return Response({
        "total_usuarios": total,
        "activos_hoy": activos_hoy,
        "activos_semana": activos_semana,
        "nuevos_hoy": nuevos_hoy,
        "nuevos_semana": nuevos_semana,
        "distribucion_planes": distribucion,
        "total_listados": total_listados
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios(request):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    try:
        from .models import Agent, Listado
        incluir_eliminados = request.query_params.get('incluir_eliminados') in ('1', 'true', 'True')
        agentes_qs = Agent.objects.all().order_by('-fecha_registro')
        if not incluir_eliminados:
            try:
                agentes_qs = agentes_qs.filter(eliminado_en__isnull=True)
            except Exception as e:
                import sys
                print(f"[admin_usuarios] WARN filter eliminado_en fallo: {e}", file=sys.stderr, flush=True)
        
        resultado = []
        for a in agentes_qs:
            try:
                listados = Listado.objects.filter(agente=a).count()
            except:
                listados = 0
            
            resultado.append({
                "id": a.id,
                "email": a.email,
                "nombre": getattr(a, 'nombre', ''),
                "agencia": getattr(a, 'agencia', '') or getattr(a, 'nombre_inmobiliaria', ''),
                "plan_nombre": getattr(a, 'plan_nombre', 'free'),
                "plan_activo": getattr(a, 'plan_activo', True),
                "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
                "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
                "listados_count": listados,
                "pais": getattr(a, 'pais', ''),
                "nicho": getattr(a, 'nicho', ''),
            })
        return Response({"usuarios": resultado})
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return Response({"error": "internal", "detail": str(e)[:300]}, status=500)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_eliminar_usuario(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.delete()
        return Response({"mensaje": "Usuario eliminado"})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_cambiar_plan(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    nuevo_plan = request.data.get('plan')
    planes_validos = ['free','starter','pro','scale','business']
    
    if nuevo_plan not in planes_validos:
        return Response({"error": "Plan inválido"}, status=400)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.plan_nombre = nuevo_plan
        agent.save()
        return Response({
            "mensaje": f"Plan actualizado a {nuevo_plan}",
            "plan": nuevo_plan
        })
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    agent = request.user
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from .models import Listado, UsageLog
    from .plan_utils import LIMITES

    listados = Listado.objects.filter(agente=agent)
    property_usage = UsageLog.objects.filter(agent=agent, tipo='property')
    listados_este_mes = property_usage.filter(fecha__gte=start_of_month).count()
    total_generados = property_usage.count()
    videos_creados = listados.aggregate(total=Sum('videos_creados'))['total'] or 0

    listados_recientes = [
        _serialize_listing_summary(listado)
        for listado in listados.order_by('-creado_en')[:8]
    ]

    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])

    # Uso actual del mes (via UsageLog)
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()

    return Response({
        'nombre_inmobiliaria': getattr(agent, 'nombre_inmobiliaria', None),
        'logo_url': getattr(agent, 'logo_url', None),
        'listados_este_mes': listados_este_mes,
        'total_generados': total_generados,
        'videos_creados': videos_creados,
        'conexiones_activas': 0,
        'listados_recientes': listados_recientes,
        'plan': plan,
        'plan_limites': {
            'properties_per_month': limites['properties'],
            'ai_generations': limites['ai'],
            'image_generations': limites['images'],
            'video_generations': limites['videos'],
            'auto_posts_per_month': limites.get('auto_posts'),
            'auto_posting_unlimited': limites.get('auto_posts') is None,
            'branding': plan not in ('free',),
        },
        'uso_actual': {
            'properties_used': listados_este_mes,
            'ai_used': ai_used,
            'images_used': images_used,
            'videos_used': videos_used,
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    """Todos los listados del sistema"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Listado
    listados = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    data = [{
        "id": l.id,
        "titulo": l.titulo,
        "tipo": l.tipo_propiedad,
        "ciudad": l.ciudad,
        "precio": str(l.precio) if l.precio else None,
        "agente_email": l.agente.email,
        "agente_nombre": l.agente.nombre,
        "video_status": l.video_status,
        "creado_en": l.creado_en.strftime('%Y-%m-%d %H:%M') if l.creado_en else ''
    } for l in listados]
    return Response({"listados": data, "total": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    """Stats de assets generados"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import GeneratedAsset
    total = GeneratedAsset.objects.count()
    por_tipo = {}
    for tipo in ['PDF', 'VIDEO', 'EMAIL', 'SOCIAL']:
        por_tipo[tipo] = GeneratedAsset.objects.filter(asset_type=tipo).count()
    por_status = {}
    for status in ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED']:
        por_status[status] = GeneratedAsset.objects.filter(status=status).count()
    return Response({
        "total": total,
        "por_tipo": por_tipo,
        "por_status": por_status
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    """Historial de pagos, planes y recursos extra."""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from django.db.models import Count, Sum
    from .models import Pago, UserAPIAssignment, WebhookLog

    pagos = Pago.objects.select_related('user').order_by('-creado_en')[:200]
    data = []
    for pago in pagos:
        asignaciones = UserAPIAssignment.objects.filter(
            pago=pago,
            activo=True,
        ).select_related('servicio', 'apikey')
        servicios = [a.servicio.nombre for a in asignaciones]
        data.append({
            "id": pago.id,
            "email": pago.user.email if pago.user else '',
            "nombre": pago.user.nombre if pago.user else '',
            "plan": pago.user.plan_nombre if pago.user else '',
            "plan_activo": pago.user.plan_activo if pago.user else False,
            "tipo": pago.tipo,
            "tipo_label": pago.get_tipo_display(),
            "es_extra": pago.tipo.startswith('extra_'),
            "mp_status": pago.mp_status,
            "monto": str(pago.monto),
            "moneda": pago.moneda,
            "mp_payment_id": pago.mp_payment_id,
            "external_reference": pago.external_reference or '',
            "servicios_asignados": servicios,
            "keys_asignadas": asignaciones.count(),
            "fecha_registro": pago.creado_en.strftime('%Y-%m-%d %H:%M') if pago.creado_en else '',
            "procesado_en": pago.procesado_en.strftime('%Y-%m-%d %H:%M') if pago.procesado_en else '',
        })

    resumen_tipo = dict(Pago.objects.values_list('tipo').annotate(total=Count('id')))
    total_aprobado = Pago.objects.filter(mp_status='approved').aggregate(total=Sum('monto'))['total'] or 0
    webhooks = WebhookLog.objects.filter(fuente='mercadopago').order_by('-recibido_en')[:25]

    return Response({
        "pagos": data,
        "total_pagos": Pago.objects.count(),
        "total_aprobado": str(total_aprobado),
        "resumen_tipo": resumen_tipo,
        "webhooks": [{
            "id": w.id,
            "event_id": w.event_id or '',
            "event_type": w.event_type or '',
            "status": w.status,
            "error": w.error or '',
            "recibido_en": w.recibido_en.strftime('%Y-%m-%d %H:%M') if w.recibido_en else '',
            "procesado_en": w.procesado_en.strftime('%Y-%m-%d %H:%M') if w.procesado_en else '',
        } for w in webhooks],
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    """Detalle completo de un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent, Listado
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    listados = Listado.objects.filter(agente=a).order_by('-creado_en')
    return Response({
        "id": a.id,
        "email": a.email,
        "nombre": a.nombre,
        "agencia": a.agencia or '',
        "telefono": a.telefono or '',
        "pais": a.pais or '',
        "nicho": a.nicho or '',
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "is_active": a.is_active,
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
        "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
        "total_listados": listados.count(),
        "listados_recientes": [{
            "titulo": l.titulo,
            "tipo": l.tipo_propiedad,
            "ciudad": l.ciudad,
            "creado_en": l.creado_en.strftime('%Y-%m-%d') if l.creado_en else ''
        } for l in listados[:10]]
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_suspender_usuario(request, user_id):
    """Suspender o reactivar un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    if request.method != 'POST':
        return Response({"error": "Method not allowed"}, status=405)
    from .models import Agent
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    a.is_active = not a.is_active
    a.save()
    estado = "suspendido" if not a.is_active else "reactivado"
    return Response({"ok": True, "estado": estado, "is_active": a.is_active})

import requests as http_requests

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def conexiones_init(request):
    """
    Crea perfil en UploadPost para el usuario y devuelve 
    la URL segura para conectar sus redes sociales.
    """
    import traceback, sys
    try:
        from django.conf import settings
        from api.pool_manager import get_api_key
        import os
        
        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_init] user={user.email} username={username}", flush=True)
        
        # 1. Key del bundle/pool del usuario
        api_key = get_api_key(user, 'uploadpost')
        
        # 2. Fallback: key global del .env de producción
        if not api_key:
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOAD_POST_API_KEY', '')
            ) or None
            if api_key:
                print(f"[conexiones_init] Usando UPLOADPOST_API_KEY global para {user.email}", flush=True)
        
        if not api_key:
            print(f"[conexiones_init] Sin key uploadpost para {user.email}. Plan={getattr(user, 'plan_nombre', 'free')}", flush=True)
            return Response({
                "success": False,
                "error": "Tu cuenta no tiene una API de publicación asignada. Contactá a soporte."
            }, status=400)
        
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        # PASO 1: Crear perfil (si no existe)
        create_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        print(f"[conexiones_init] create_profile status={create_resp.status_code}", flush=True)
        # 200 o 409 (ya existe) son aceptables
        if create_resp.status_code not in [200, 201, 409]:
            err_text = create_resp.text[:200]
            if "PROFILE_LIMIT_REACHED" in err_text or "limit of 2 profiles" in err_text:
                return Response({
                    "success": False,
                    "error": "Alcanzaste el límite de cuentas vinculadas de tu plan actual. Para conectar más redes sociales, por favor mejorá a un Plan Pro."
                }, status=400)
                
            return Response({
                "success": False,
                "error": f"Error al vincular: {err_text}"
            }, status=500)
        
        platform = request.data.get('platform')
        
        jwt_payload = {
            "username": username,
            "redirect_url": f"{settings.FRONTEND_URL}/conexiones",
            "logo_image": "https://res.cloudinary.com/dpqgbgilw/image/upload/leadbook_logo",
            "connect_title": "Conectá tus redes sociales",
            "connect_description": "Conectá tus cuentas para publicar automáticamente con LeadBook",
            "show_calendar": True
        }
        # Si viene una plataforma específica, pre-seleccionarla en el wizard de UploadPost
        if platform:
            jwt_payload["platform"] = platform
            
        jwt_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users/generate-jwt",
            headers=headers,
            json=jwt_payload,
            timeout=10
        )
        print(f"[conexiones_init] generate_jwt status={jwt_resp.status_code}", flush=True)
        if jwt_resp.status_code != 200:
            return Response({
                "success": False,
                "error": f"Error generando URL: {jwt_resp.text[:200]}"
            }, status=500)
        
        data = jwt_resp.json()
        return Response({
            "success": True,
            "access_url": data.get("access_url"),
            "username": username
        })
    except Exception as e:
        print(f"[conexiones_init] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "error": f"Error interno del servidor: {str(e)[:200]}"
        }, status=500)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def conexiones_eliminar(request):
    """
    Elimina el perfil del usuario en UploadPost (desvincula todas las redes y libera el límite de la API).
    """
    try:
        from api.pool_manager import get_api_key
        user = request.user
        username = f"leadbook_{user.id}"
        api_key = get_api_key(user, 'uploadpost')
        
        if not api_key:
            return Response({"success": False, "error": "No se encontró API Key vinculada para este usuario"}, status=400)
            
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        resp = http_requests.delete(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        
        if resp.status_code in [200, 204]:
            return Response({"success": True, "message": "Perfil eliminado. Podés volver a vincular tus cuentas."})
        else:
            return Response({"success": False, "error": f"Error al eliminar: {resp.text[:200]}"}, status=400)
            
    except Exception as e:
        return Response({"success": False, "error": f"Error interno: {str(e)[:100]}"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conexiones_estado(request):
    """
    Devuelve las redes sociales conectadas del usuario consultando UploadPost.
    Siempre devuelve JSON — nunca HTML.
    """
    import traceback, sys, os
    try:
        from api.pool_manager import get_api_key
        from django.conf import settings

        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_estado] user={user.email} username={username}", flush=True)

        # 1. Key del pool del usuario
        api_key = get_api_key(user, 'uploadpost')

        # 2. Fallback a key global de .env
        if not api_key:
            api_key = (
                getattr(settings, 'UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOADPOST_API_KEY', '') or
                os.environ.get('UPLOAD_POST_API_KEY', '')
            ) or None
            if api_key:
                print(f"[conexiones_estado] Usando key global para {user.email}", flush=True)

        if not api_key:
            print(f"[conexiones_estado] Sin key uploadpost para {user.email}", flush=True)
            return Response({"success": True, "redes": [], "conectado": False})

        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }

        # ESTRATEGIA 1: Endpoint específico del usuario (más preciso)
        perfil = None
        resp_individual = http_requests.get(
            f"https://api.upload-post.com/api/uploadposts/users/{username}",
            headers=headers,
            timeout=10
        )
        print(f"[conexiones_estado] GET /users/{username} → status={resp_individual.status_code}", flush=True)

        if resp_individual.status_code == 200:
            try:
                perfil = resp_individual.json()
                print(f"[conexiones_estado] perfil individual={perfil}", flush=True)
            except Exception:
                perfil = None

        # ESTRATEGIA 2: Listar todos y buscar (fallback)
        if not perfil:
            resp_list = http_requests.get(
                "https://api.upload-post.com/api/uploadposts/users",
                headers=headers,
                timeout=10
            )
            print(f"[conexiones_estado] GET /users list → status={resp_list.status_code}", flush=True)
            if resp_list.status_code == 200:
                try:
                    raw = resp_list.json()
                    print(f"[conexiones_estado] raw list response (first 500 chars)={str(raw)[:500]}", flush=True)
                    # Normalizar a lista
                    if isinstance(raw, list):
                        usuarios = raw
                    elif isinstance(raw, dict):
                        usuarios = raw.get('users') or raw.get('data') or raw.get('results') or []
                    else:
                        usuarios = []
                    perfil = next(
                        (u for u in usuarios if u.get("username") == username),
                        None
                    )
                except Exception as parse_err:
                    print(f"[conexiones_estado] Error parseando lista: {parse_err}", flush=True)

        if not perfil:
            print(f"[conexiones_estado] Perfil '{username}' no encontrado en UploadPost", flush=True)
            return Response({"success": True, "redes": [], "conectado": False, "username": username})

        # Obtener el objeto de redes.
        # UploadPost devuelve {"success": true, "profile": {"social_accounts": {"instagram": {...}, "tiktok": ""}}}
        if "profile" in perfil:
            social_accounts = perfil["profile"].get("social_accounts", {})
        else:
            social_accounts = perfil.get("social_accounts", {})

        print(f"[conexiones_estado] social_accounts={social_accounts}", flush=True)

        redes_normalizadas = []
        
        # Iterar sobre las claves del diccionario (ej: "instagram", "tiktok")
        if isinstance(social_accounts, dict):
            for platform, data in social_accounts.items():
                # Si el valor está vacío (ej: ""), significa que no está conectado
                if not data:
                    continue
                    
                # Si es un dict, extraer la info
                if isinstance(data, dict):
                    # Ignorar si requiere reconexión
                    if data.get("reauth_required") is True:
                        continue
                        
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data.get("handle") or data.get("display_name") or data.get("username") or "",
                        "status": "connected"
                    })
                elif isinstance(data, str) and data:
                    # Por si acaso devuelve un string no vacío
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data,
                        "status": "connected"
                    })

        return Response({
            "success": True,
            "conectado": len(redes_normalizadas) > 0,
            "redes": redes_normalizadas,
            "username": username,
            "total": len(redes_normalizadas)
            # Removemos debug_raw_perfil porque ya vimos la estructura
        })

    except Exception as e:
        print(f"[conexiones_estado] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "redes": [],
            "conectado": False,
            "error": f"Error interno: {str(e)[:200]}"
        }, status=500)



# ============================================================
# DEBUG / DIAGNÓSTICO — endpoints seguros (no exponen secretos)
# Uso: curl https://tuback.up.railway.app/api/v1/debug/email-check/
# ============================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_uploadpost(request, username):
    """
    Endpoint temporal para ver la estructura exacta que devuelve UploadPost
    para un usuario específico.
    """
    import os
    from django.conf import settings
    
    api_key = (
        getattr(settings, 'UPLOADPOST_API_KEY', '') or
        os.environ.get('UPLOADPOST_API_KEY', '') or
        os.environ.get('UPLOAD_POST_API_KEY', '')
    )
    
    if not api_key:
        return Response({"error": "No global UPLOADPOST_API_KEY"}, status=500)
        
    headers = {
        "Authorization": f"Apikey {api_key}",
        "Content-Type": "application/json"
    }
    
    # Probar endpoint individual
    resp1 = http_requests.get(
        f"https://api.upload-post.com/api/uploadposts/users/{username}",
        headers=headers,
        timeout=10
    )
    
    # Probar endpoint lista
    resp2 = http_requests.get(
        "https://api.upload-post.com/api/uploadposts/users",
        headers=headers,
        timeout=10
    )
    
    list_data = None
    if resp2.status_code == 200:
        try:
            raw = resp2.json()
            if isinstance(raw, list): usuarios = raw
            elif isinstance(raw, dict): usuarios = raw.get('users') or raw.get('data') or raw.get('results') or []
            else: usuarios = []
            list_data = next((u for u in usuarios if u.get("username") == username), None)
        except: pass
        
    return Response({
        "target_username": username,
        "strategy_1_individual": {
            "status": resp1.status_code,
            "data": resp1.json() if resp1.status_code == 200 else resp1.text[:200]
        },
        "strategy_2_list": {
            "status": resp2.status_code,
            "found_in_list": list_data
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_email_check(request):
    """
    Devuelve metadata de la config de email sin exponer la password.
    Sirve para verificar si las env vars GMAIL_USER y GMAIL_APP_PASSWORD
    están cargadas en Railway (o cualquier entorno).
    """
    from django.conf import settings
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''

    # Enmascarar el user (mostrar solo primeros/últimos chars)
    def mask(s, head=3, tail=3):
        if not s:
            return None
        if len(s) <= head + tail:
            return "*" * len(s)
        return f"{s[:head]}***{s[-tail:]}"

    import os
    provider    = (os.environ.get("EMAIL_PROVIDER") or getattr(settings, "EMAIL_PROVIDER", "") or "gmail").strip().lower()
    resend_key  = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "") or ""
    resend_from = os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or ""

    # Verdict operativo unificado
    if provider == "resend":
        if resend_key:
            verdict = "RESEND-OK-listo-para-enviar"
        else:
            verdict = "RESEND-seleccionado-pero-falta-RESEND_API_KEY"
    else:
        if bool(host_user) and bool(host_pass):
            verdict = "SMTP-OK-listo-para-enviar"
        else:
            verdict = "CONSOLE-BACKEND-emails-NO-saldran-cargar-GMAIL_APP_PASSWORD"

    return Response({
        "EMAIL_PROVIDER": provider,
        "EMAIL_BACKEND": getattr(settings, 'EMAIL_BACKEND', None),
        "EMAIL_HOST": getattr(settings, 'EMAIL_HOST', None),
        "EMAIL_PORT": getattr(settings, 'EMAIL_PORT', None),
        "EMAIL_USE_SSL": getattr(settings, 'EMAIL_USE_SSL', None),
        "EMAIL_USE_TLS": getattr(settings, 'EMAIL_USE_TLS', None),
        "DEFAULT_FROM_EMAIL": getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        "GMAIL_USER_set": bool(host_user),
        "GMAIL_USER_masked": mask(host_user),
        "GMAIL_APP_PASSWORD_set": bool(host_pass),
        "GMAIL_APP_PASSWORD_len": len(host_pass),
        "RESEND_API_KEY_set": bool(resend_key),
        "RESEND_API_KEY_len": len(resend_key),
        "RESEND_FROM": resend_from or None,
        "CELERY_TASK_ALWAYS_EAGER": getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', None),
        "DEBUG": getattr(settings, 'DEBUG', None),
        "verdict": verdict,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def debug_email_send(request):
    """
    Dispara un envío SMTP REAL y SINCRÓNICO de prueba.
    Body JSON: {"email": "destino@mail.com"}  (acepta también "to")
    Devuelve exactamente lo que pasó, incluyendo error SMTP completo si falla.

    IMPORTANTE: En producción deberías proteger este endpoint con
    X-Admin-Key antes de dejarlo abierto. Aquí queda AllowAny para debug rápido.
    """
    import traceback, socket, smtplib, ssl, time
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    # Aceptar "email" o "to" (compatibilidad)
    destino = (request.data.get('email') or request.data.get('to') or '').strip().lower()
    if not destino:
        return Response({"error": "falta campo 'email' con el email destino"}, status=400)

    # Provider opcional — si se pasa "resend", probamos Resend sin tocar env vars
    forced_provider = (request.data.get('provider') or '').strip().lower()
    if forced_provider == 'resend':
        import os, traceback
        try:
            from .tasks import _send_via_resend
        except Exception as e_imp:
            return Response({
                "ok": False, "stage": "import-resend",
                "error_type": type(e_imp).__name__, "error": str(e_imp),
            }, status=500)
        print(f"[DEBUG-EMAIL] Forzando envío via RESEND a {destino}", flush=True)
        subject = "LeadBook — prueba de email (Resend, debug)"
        text_body = "Este es un email de prueba enviado por /api/v1/debug/email-send/ (provider=resend)."
        html_body = (
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code> "
            "(<b>provider=resend</b>).</p><p>Si lo estás leyendo, Resend funciona desde este servidor.</p>"
        )
        try:
            ok, detalle = _send_via_resend(destino, subject, text_body, html_body)
            return Response({
                "ok": ok,
                "stage": "resend",
                "result": detalle,
                "destino": destino,
                "provider": "resend",
                "RESEND_API_KEY_set": bool(os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")),
                "RESEND_FROM": os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or None,
            }, status=200 if ok else 500)
        except Exception as e_res:
            return Response({
                "ok": False, "stage": "resend",
                "error_type": type(e_res).__name__, "error": str(e_res),
                "traceback": traceback.format_exc()[-1500:],
            }, status=500)

    host      = getattr(settings, 'EMAIL_HOST', '')
    port      = getattr(settings, 'EMAIL_PORT', 0)
    use_ssl   = getattr(settings, 'EMAIL_USE_SSL', False)
    use_tls   = getattr(settings, 'EMAIL_USE_TLS', False)
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', host_user)

    info = {
        "destino": destino,
        "backend": settings.EMAIL_BACKEND,
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
        "user_set": bool(host_user),
        "user_masked": (host_user[:3] + "***" + host_user[-3:]) if host_user else None,
        "pass_set": bool(host_pass),
        "pass_len": len(host_pass),
        "from": from_addr,
    }

    print(f"[DEBUG-EMAIL] Disparando envío de test a {destino} — host={host}:{port} ssl={use_ssl} tls={use_tls}", flush=True)

    # Guardas tempranas
    if not host_user or not host_pass:
        return Response({
            "ok": False,
            "stage": "env-vars",
            "error": "GMAIL_USER o GMAIL_APP_PASSWORD no están cargadas en el entorno",
            **info,
        }, status=500)

    # 1) Prueba de conectividad TCP pura
    t0 = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=15)
        sock.close()
        tcp_ok = True
        tcp_ms = int((time.time() - t0) * 1000)
    except Exception as e_tcp:
        return Response({
            "ok": False,
            "stage": "tcp-connect",
            "error_type": type(e_tcp).__name__,
            "error": str(e_tcp),
            "hint": "Railway no puede abrir el puerto SMTP. Gmail en la nube suele fallar aquí → migrar a Resend.",
            **info,
        }, status=500)

    # 2) Handshake SMTP + login con smtplib directo para capturar respuesta exacta del server
    smtp_debug = {"tcp_ok": tcp_ok, "tcp_ms": tcp_ms}
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            if use_tls:
                smtp.starttls(context=ctx)
        ehlo_code, ehlo_msg = smtp.ehlo()
        smtp_debug["ehlo_code"] = ehlo_code
        smtp_debug["ehlo_msg"] = (ehlo_msg or b"").decode(errors="ignore")[:200]

        smtp.login(host_user, host_pass)
        smtp_debug["login"] = "ok"
        smtp.quit()
    except smtplib.SMTPAuthenticationError as e_auth:
        return Response({
            "ok": False,
            "stage": "smtp-auth",
            "error_type": "SMTPAuthenticationError",
            "smtp_code": e_auth.smtp_code,
            "smtp_error": (e_auth.smtp_error or b"").decode(errors="ignore"),
            "hint": "Gmail rechazó la autenticación. Si el app password es correcto y el usuario tiene 2FA, probablemente Google está bloqueando IPs de Railway → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)
    except Exception as e_smtp:
        return Response({
            "ok": False,
            "stage": "smtp-handshake",
            "error_type": type(e_smtp).__name__,
            "error": str(e_smtp),
            "traceback": traceback.format_exc()[-1500:],
            "hint": "Falló el handshake SSL/TLS con Gmail. Probablemente Railway bloquea → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)

    # 3) Si llegamos acá, SMTP está OK. Enviamos el mail real.
    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=host, port=port,
            username=host_user, password=host_pass,
            use_ssl=use_ssl, use_tls=use_tls,
            fail_silently=False,
            timeout=30,
        )
        msg = EmailMultiAlternatives(
            subject="LeadBook — prueba de email (debug)",
            body="Este es un email de prueba enviado por /api/v1/debug/email-send/.\nSi lo estás leyendo, SMTP funciona desde este servidor.",
            from_email=from_addr,
            to=[destino],
            connection=connection,
        )
        msg.attach_alternative(
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code>.</p>"
            "<p>Si lo estás leyendo, <b>SMTP funciona</b> desde este servidor.</p>",
            "text/html",
        )
        sent = msg.send(fail_silently=False)
        return Response({
            "ok": True,
            "stage": "sent",
            "sent_count": sent,
            "debug": smtp_debug,
            **info,
            "nota": "Si 'sent_count'=1 Gmail aceptó el mensaje. Revisá inbox y spam del destino.",
        })
    except Exception as e_send:
        return Response({
            "ok": False,
            "stage": "send-message",
            "error_type": type(e_send).__name__,
            "error": str(e_send),
            "traceback": traceback.format_exc()[-1500:],
            "debug": smtp_debug,
            **info,
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_pdf_view(request, listado_id):
    """
    Sirve el PDF desde Cloudinary actuando como proxy para evitar errores 401/ACL.
    Si el PDF es local (fallback), redirige a la URL local.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        
        # Buscar URL en los datos del listado
        res = listado.datos_extra.get('resultados', {}) if listado.datos_extra else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data
        
        if not pdf_url:
            return Response({"error": "URL de PDF no encontrada"}, status=404)

        # Si es URL local, redirigir directamente al endpoint que sirve el archivo
        if not pdf_url.startswith('http'):
            from django.shortcuts import redirect
            absolute_url = request.build_absolute_uri(pdf_url)
            if 'localhost' not in absolute_url and '127.0.0.1' not in absolute_url:
                absolute_url = absolute_url.replace('http://', 'https://')
            return redirect(absolute_url)

        # Petición interna a Cloudinary
        response = requests.get(pdf_url, stream=True, timeout=30)
        
        if response.status_code != 200:
            return Response({
                "error": f"Cloudinary respondió con error {response.status_code}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        django_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='application/pdf'
        )
        django_response['Content-Disposition'] = f'inline; filename="ficha_leadbook_{listado_id}.pdf"'
        return django_response

    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def descargar_pdf(request, listado_id):
    try:
        from .models import Listado
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        listado = get_object_or_404(Listado, id=listado_id, agente=request.user)
        datos = listado.datos_extra or {}
        pdf_data = datos.get('resultados', {}).get('pdf', {})
        html_content = pdf_data.get('html', '') if isinstance(pdf_data, dict) else ''
        if not html_content:
            return Response({"error": "No hay PDF generado para este listado"}, status=404)
        from api.services.render_engine import render_html_to_pdf
        pdf_bytes = render_html_to_pdf(html_content)
        if not pdf_bytes:
            return Response({"error": "Error al generar PDF"}, status=500)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ficha_leadbook_{listado_id}.pdf"'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        logger.error(f"Error en descargar_pdf: {e}")
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_listado_zip(request, pk):
    listado = get_object_or_404(Listado, id=pk, agente=request.user)
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    resultados = datos.get('resultados') if isinstance(datos.get('resultados'), dict) else {}

    def _guess_extension(url, content_type=''):
        ct = (content_type or '').lower()
        if 'pdf' in ct:
            return '.pdf'
        if 'png' in ct:
            return '.png'
        if 'jpeg' in ct or 'jpg' in ct:
            return '.jpg'
        if 'webp' in ct:
            return '.webp'
        if 'mp4' in ct:
            return '.mp4'

        raw = str(url or '').split('?')[0].strip().lower()
        for ext in ('.pdf', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.webm'):
            if raw.endswith(ext):
                return ext
        return '.bin'

    def _add_remote_file(zf, folder, filename_base, source_url):
        if not source_url or not str(source_url).startswith('http'):
            return None

        raw_bytes, content_type = _download_remote_asset(source_url)
        if not raw_bytes:
            return None

        ext = _guess_extension(source_url, content_type)
        clean_base = re.sub(r'[^a-zA-Z0-9_\-]', '_', filename_base)
        zip_path = f"{folder}/{clean_base}{ext}"
        zf.writestr(zip_path, raw_bytes)
        return zip_path

    zip_buffer = io.BytesIO()
    now_iso = timezone.now().isoformat()

    with zipfile.ZipFile(zip_buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        # --- PDF ---
        pdf_data = resultados.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else (pdf_data if isinstance(pdf_data, str) else '')
        pdf_html = pdf_data.get('html', '') if isinstance(pdf_data, dict) else ''

        pdf_saved_path = _add_remote_file(zf, 'PDF', 'ficha', pdf_url)
        if not pdf_saved_path and pdf_html:
            try:
                from api.services.render_engine import render_html_to_pdf
                pdf_bytes = render_html_to_pdf(pdf_html)
                if pdf_bytes:
                    zf.writestr('PDF/ficha.pdf', pdf_bytes)
                    pdf_saved_path = 'PDF/ficha.pdf'
            except Exception:
                pdf_saved_path = None

        if pdf_html:
            zf.writestr('PDF/ficha.html', pdf_html)

        # --- POST ---
        post_data = resultados.get('post', {})
        post_url = post_data.get('url') if isinstance(post_data, dict) else (post_data if isinstance(post_data, str) else '')
        post_caption = post_data.get('caption') if isinstance(post_data, dict) else ''
        _add_remote_file(zf, 'POST', 'post', post_url)
        if post_caption:
            zf.writestr('POST/caption.txt', str(post_caption).strip())

        # --- STORY ---
        story_data = resultados.get('story', {})
        story_url = story_data.get('url') if isinstance(story_data, dict) else (story_data if isinstance(story_data, str) else '')
        story_caption = story_data.get('caption') if isinstance(story_data, dict) else ''
        _add_remote_file(zf, 'STORY', 'story', story_url)
        if story_caption:
            zf.writestr('STORY/caption.txt', str(story_caption).strip())

        # --- CARRUSEL ---
        carrusel_data = resultados.get('carrusel', {})
        carrusel_slides = carrusel_data.get('slides') if isinstance(carrusel_data, dict) else []
        carrusel_caption = carrusel_data.get('caption') if isinstance(carrusel_data, dict) else ''
        if isinstance(carrusel_slides, list):
            for idx, slide in enumerate(carrusel_slides, start=1):
                slide_url = slide.get('url') if isinstance(slide, dict) else slide
                _add_remote_file(zf, 'CARRUSEL', f'slide_{idx:02d}', slide_url)
        if carrusel_caption:
            zf.writestr('CARRUSEL/caption.txt', str(carrusel_caption).strip())

        # --- EMAIL (solo HTML por requerimiento) ---
        email_data = resultados.get('email', {})
        if isinstance(email_data, dict) and email_data.get('html'):
            zf.writestr('EMAIL/email.html', str(email_data.get('html')))

        # --- VIDEO ---
        if listado.video_url:
            _add_remote_file(zf, 'VIDEO', 'video', listado.video_url)

        template_id = (
            (resultados.get('pdf') or {}).get('template_id') if isinstance(resultados.get('pdf'), dict) else None
        ) or (
            (resultados.get('post') or {}).get('template_id') if isinstance(resultados.get('post'), dict) else None
        ) or (
            (resultados.get('story') or {}).get('template_id') if isinstance(resultados.get('story'), dict) else None
        ) or (
            (resultados.get('carrusel') or {}).get('template_id') if isinstance(resultados.get('carrusel'), dict) else None
        ) or (
            (resultados.get('email') or {}).get('template_id') if isinstance(resultados.get('email'), dict) else None
        ) or datos.get('template_id')

        resumen = {
            'listado': {
                'id': listado.id,
                'titulo': listado.titulo,
                'tipo_propiedad': listado.tipo_propiedad,
                'operacion': listado.operacion,
                'ciudad': listado.ciudad,
                'precio': listado.precio,
                'moneda': listado.moneda,
                'video_url': listado.video_url,
                'video_status': listado.video_status,
            },
            'template_id': _normalize_template_id(template_id),
            'generated_at': now_iso,
            'included_formats': {
                'pdf': bool(pdf_url or pdf_html),
                'post': bool(post_url),
                'story': bool(story_url),
                'carrusel': bool(carrusel_slides),
                'email': bool(isinstance(email_data, dict) and email_data.get('html')),
                'video': bool(listado.video_url),
            },
            'captions': {
                'post_chars': len(str(post_caption or '')),
                'story_chars': len(str(story_caption or '')),
                'carrusel_chars': len(str(carrusel_caption or '')),
            },
        }
        zf.writestr('METADATA/resumen.json', json.dumps(resumen, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="leadbook_listado_{listado.id}.zip"'
    return response

@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_pdf_thumbnail_view(request, listado_id):
    """
    Genera una vista previa (imagen) de la primera página del PDF vía proxy.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        res = listado.datos_extra.get('resultados', {}) if listado.datos_extra else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data

        if not pdf_url or not pdf_url.startswith('http') or 'res.cloudinary.com' not in pdf_url:
            from django.shortcuts import redirect
            return redirect('https://placehold.co/400x600/111111/FFFFFF/png?text=Vista+Previa\\nNo+Disponible')

        thumb_url = pdf_url.replace('.pdf', '.jpg')
        if '/upload/' in thumb_url:
            thumb_url = thumb_url.replace('/upload/', '/upload/w_600,h_800,c_fill,pg_1/')

        response = requests.get(thumb_url, stream=True, timeout=15)
        
        if response.status_code != 200:
            return Response({"error": "No se pudo generar miniatura"}, status=404)

        return StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='image/jpeg'
        )

    except Exception as e:
        return Response({"error": str(e)}, status=500)

from django.shortcuts import get_object_or_404
from django.http import HttpResponse

@api_view(['GET'])
def generar_html(request, pk):
    from .models import Listado
    listado = get_object_or_404(Listado, pk=pk)
    data = listado.datos_extra or {}
    context, temp_files, _, _, _ = construir_contexto_pdf(data, listado.agente, request)
    
    from django.template.loader import render_to_string
    try:
        html_string = render_to_string('pdf/property_brochure_html.html', context)
        # Limpiar temp files ya que no generamos PDF
        import os
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        return HttpResponse(html_string, content_type='text/html')
    except Exception as e:
        import traceback
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        return HttpResponse(f"Error generando HTML: {str(e)}<br><pre>{traceback.format_exc()}</pre>", content_type='text/html', status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_escena(request):
    """Regenera el texto de UNA escena específica usando el mismo tono/voz del usuario."""
    data = request.data
    nombre_escena = data.get('nombre_escena', 'Escena')
    indice_escena = data.get('indice_escena', 0)
    total_escenas = data.get('total_escenas', 4)

    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    voz = data.get('voz', 'femenina')
    tono = data.get('tono', 'profesional')
    tipo_video = data.get('tipoVideo', 'reel')
    contexto_adicional = data.get('contextoAdicional', '')

    tono_map = {
        'profesional': 'profesional y formal, transmite confianza',
        'lujo': 'de lujo y exclusividad, sofisticado, usa vocabulario refinado',
        'energetico': 'dinámico y energético, usa frases cortas e impactantes',
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])
    narrador = 'firme, directo, con autoridad' if voz == 'masculina' else 'cálido, cercano, invitador'
    tipo_video_raw = str(tipo_video or '').strip().lower()
    tipo_video_norm = {
        'tour_narrado': 'tour',
        'tour-narrado': 'tour',
        'reel_rapido': 'reel',
        'reel-rapido': 'reel',
    }.get(tipo_video_raw, tipo_video_raw if tipo_video_raw in ('tour', 'reel') else 'reel')
    reglas_palabras = {
        'tour': {'min': 24, 'max': 55},
        'reel': {'min': 6, 'max': 18},
    }[tipo_video_norm]
    contexto_extra = f"\nEnfoque adicional: {contexto_adicional}" if contexto_adicional else ''

    prompt = f"""Sos un copywriter inmobiliario experto.
Generá SOLO el texto para la escena "{nombre_escena}" (escena {indice_escena + 1} de {total_escenas}) de un video inmobiliario.

PROPIEDAD: {tipo} en {operacion} | {ciudad} | {moneda} {precio}
TONO: {tono_instrucciones}
NARRADOR: {narrador}{contexto_extra}

REQUISITOS:
- Entre {reglas_palabras['min']} y {reglas_palabras['max']} palabras
- El texto es para narración en voz en off, debe sonar natural al hablar
- No pongas el nombre de la escena, solo el texto a narrar
- Responde SOLO el texto, sin JSON, sin comillas, sin explicaciones"""

    try:
        result = call_gemini_api(prompt, agente=request.user)
        if not result:
            return Response({"error": "No se pudo generar texto"}, status=503)
        return Response({"texto": result.strip()})
    except GeminiQuotaExhaustedError as e:
        return Response({"error": "cuota_ia_agotada", "mensaje": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_fotos_listado(request):
    """
    Sube fotos de propiedad (portada y galería) a Cloudinary a través del pool del backend.
    """
    data = request.data
    portada_b64 = data.get('portadaUrl')
    fotos_b64 = data.get('fotosRecorrido', [])
    listado_id = data.get('listado_id')

    user_id = request.user.id
    response_data = {
        'portadaUrl': None,
        'fotosRecorrido': []
    }

    try:
        from api.services.almacenamiento import AlmacenamientoCloudinary
        
        if portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('data:image'):
            print(f"[UPLOAD] portada_b64 tipo: {type(portada_b64).__name__}, es base64: {bool(portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('data:image'))}")
            obj = AlmacenamientoCloudinary.guardar_foto_propiedad(portada_b64, user_id, listado_id, tipo_foto='portada')
            print(f"[UPLOAD] get_mejor_cuenta resultado: {AlmacenamientoCloudinary.get_mejor_cuenta()}")
            print(f"[UPLOAD] resultado upload portada: {obj}")
            if obj:
                response_data['portadaUrl'] = obj
            else:
                response_data['portadaUrl'] = portada_b64 # Fallback
        elif isinstance(portada_b64, dict):
            response_data['portadaUrl'] = portada_b64
        elif portada_b64 and isinstance(portada_b64, str) and portada_b64.startswith('http'):
            response_data['portadaUrl'] = portada_b64
            
        for i, foto in enumerate(fotos_b64):
            if foto and isinstance(foto, str) and foto.startswith('data:image'):
                obj = AlmacenamientoCloudinary.guardar_foto_propiedad(foto, user_id, listado_id, tipo_foto='galeria', indice=i)
                if obj:
                    response_data['fotosRecorrido'].append(obj)
            elif isinstance(foto, dict):
                response_data['fotosRecorrido'].append(foto)
            elif foto and isinstance(foto, str) and foto.startswith('http'):
                response_data['fotosRecorrido'].append(foto)

        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error al subir fotos de listado: {e}")
        return Response({"error": str(e)}, status=500)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_notificaciones(request):
    from .models import Notificacion
    notifs = Notificacion.objects.filter(usuario=request.user)[:20]
    data = [{
        'id': n.id,
        'tipo': n.tipo,
        'titulo': n.titulo,
        'mensaje': n.mensaje,
        'leida': n.leida,
        'creada_en': n.creada_en.isoformat(),
    } for n in notifs]
    no_leidas = Notificacion.objects.filter(usuario=request.user, leida=False).count()
    return Response({'notificaciones': data, 'no_leidas': no_leidas})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_notificacion_leida(request, notif_id):
    from .models import Notificacion
    notif = Notificacion.objects.filter(id=notif_id, usuario=request.user).first()
    if notif:
        notif.leida = True
        notif.save()
    return Response({'ok': True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def marcar_todas_leidas(request):
    from .models import Notificacion
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    return Response({'ok': True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estado_cuota_ia(request):
    from .models import UserAPIQuota, Suscripcion
    try:
        quota = UserAPIQuota.objects.get(user=request.user, servicio__nombre='gemini')
        quota.maybe_reset_daily()
        quota.recalcular_limite(plan=request.user.plan_nombre)
        if quota.is_blocked:
            quota.is_blocked = False
            quota.blocked_reason = None
            quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])
        agotada = False
        usado = quota.requests_today
        limite = quota.user_daily_limit
    except UserAPIQuota.DoesNotExist:
        agotada = False
        usado = 0
        limite = 1500
    
    try:
        suscripcion = request.user.suscripcion
        ai_used = suscripcion.ai_used
    except:
        ai_used = usado

    return Response({
        'agotada': agotada,
        'usado': ai_used,
        'limite': limite,
        'porcentaje': min(100, int((ai_used / limite) * 100)) if limite > 0 else 0
    })

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def debug_quota(request):
    from .models import UserAPIAssignment, UserAPIQuota
    
    if request.method == 'POST':
        from .models import UserAPIQuota
        # Desbloquear todos los usuarios cuyo uso actual es menor al límite
        desbloqueados = 0
        for q in UserAPIQuota.objects.filter(is_blocked=True):
            if q.requests_today < q.user_daily_limit:
                q.is_blocked = False
                q.save()
                desbloqueados += 1
        # Corregir límites stale según plan + extras activos.
        for q in UserAPIQuota.objects.select_related('user', 'servicio'):
            q.recalcular_limite(plan=q.user.plan_nombre)
        
        return Response({'desbloqueados': desbloqueados})

    quotas = list(UserAPIQuota.objects.select_related('servicio').values(
        'user_id', 'servicio__nombre', 'user_daily_limit', 'user_monthly_limit',
        'requests_today', 'is_blocked'
    ))
    assignments = UserAPIAssignment.objects.filter(activo=True).select_related('user', 'servicio', 'apikey')
    keys_info = []
    for a in assignments:
        k = a.apikey
        if k:
            keys_info.append({
                'user': a.user.email,
                'service': a.servicio.nombre,
                'key_id': k.id,
                'daily_limit': k.google_daily_limit,
                'monthly_limit': k.google_monthly_limit,
                'status': k.status
            })
    return Response({'quotas': quotas, 'keys': keys_info})
