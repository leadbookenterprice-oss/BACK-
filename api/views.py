from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Sum
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
from api.services.almacenamiento import AlmacenamientoCloudinary
import logging

logger = logging.getLogger(__name__)

from .models import (
    GeneratedAsset, Listado, OTPCode, ComercialAgentProfile,
    AgentAssociation,
    TerminosCondiciones, PoliticaPrivacidad
)
from .serializers import (
    RegisterSerializer, GeneratedAssetSerializer,
    TerminosCondicionesSerializer, PoliticaPrivacidadSerializer,
    ComercialAgentProfileSerializer,
)
from .tasks import run_asset_generation
from .ai_services import call_groq_api, call_gemini_api, smart_call, GeminiQuotaExhaustedError
from .utils import crear_notificacion
from django.template.loader import render_to_string
from .services.render_engine import render_html_to_image
from .plan_utils import puede_generar, incrementar_uso

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


def _template_catalog_payload():
    items = []
    for template_id in TEMPLATE_IDS:
        meta = TEMPLATE_CATALOG.get(template_id, {})
        items.append({
            'id': template_id,
            'name': meta.get('name', template_id.replace('_', ' ').title()),
            'description': meta.get('description', ''),
            'colors': meta.get('colors', {}),
            'fonts': meta.get('fonts', {}),
        })
    return {'templates': items}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def templates_catalog(request):
    return Response(_template_catalog_payload(), status=status.HTTP_200_OK)


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


def _select_template_id(data, listado_obj=None, listado_id_hint=None):
    payload_template = _extract_template_id_from_payload(data)
    if payload_template:
        return payload_template

    listado_template = _template_id_from_listado(listado_obj)
    if listado_template:
        return listado_template

    if listado_id_hint:
        return _deterministic_template_id(listado_id_hint)

    if listado_obj and getattr(listado_obj, 'id', None):
        return _deterministic_template_id(listado_obj.id)

    return random.choice(TEMPLATE_IDS)


def _resolve_cloudinary_asset_url(value):
    if isinstance(value, dict):
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


def _collect_property_images(data):
    portada = data.get('portadaUrl') if isinstance(data, dict) else None
    fotos = data.get('fotosRecorrido', []) if isinstance(data, dict) else []
    if not isinstance(fotos, list):
        fotos = []

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
        if resolved and resolved not in seen:
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

    payload_logo = payload.get('logoAgenciaUrl') or payload.get('logo_url')
    profile_photo = (default_profile.foto_url if default_profile else '') or ''

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

    agency_name = (
        payload.get('agenciaNombre')
        or payload.get('agencia_nombre')
        or getattr(user, 'nombre_inmobiliaria', '')
        or getattr(user, 'agencia', '')
        or 'Agencia'
    )

    logo_url = payload_logo or getattr(user, 'logo_url', '') or ''

    return {
        'agente_nombre': str(agent_name).strip(),
        'agente_rol': str(agent_role).strip(),
        'agente_email': str(agent_email).strip(),
        'agente_telefono': str(agent_phone).strip(),
        'agencia_nombre': str(agency_name).strip(),
        'logo_url': str(logo_url).strip(),
        'agente_foto_url': str(profile_photo).strip(),
        'default_agent_profile': default_profile,
    }


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
            "Si queres fotos, ficha completa y coordinar visita, escribinos ahora y te asesoramos en minutos."
        )
    if formato == 'carrusel':
        return (
            f"{tipo} en {ciudad}: una oportunidad real para {operacion} con propuesta premium y excelente ubicacion. "
            f"Precio publicado: {moneda} {precio}. La propiedad ofrece {specs}, ambientes luminosos y funcionales para vivir o invertir. "
            "Escribinos para enviarte toda la informacion y coordinar visita. #RealEstate #Inmobiliaria #Inversion"
        )
    return (
        f"{tipo} en {ciudad} en {operacion}, pensada para quienes buscan ubicacion, calidad y rentabilidad. "
        f"Precio de referencia: {moneda} {precio}. Con {specs}, esta propiedad combina diseno, comodidad y una excelente proyeccion de valor. "
        "Contactanos para recibir la ficha completa, resolver dudas y coordinar visita personalizada. "
        "#RealEstate #Inmobiliaria #Propiedades #Inversion"
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
    min_chars_map = {'post': 650, 'story': 280, 'carrusel': 620}
    max_chars_map = {'post': 2200, 'story': 500, 'carrusel': 2200}

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
                "\nCTA",
                "Escribinos para recibir la ficha completa, comparativa de mercado y coordinar visita.",
                "#RealEstate #InversionInmobiliaria #Propiedades #TuNuevoHogar",
            ]
        else:
            extension_blocks = [
                "\nDETALLES CLAVE",
                f"• {operacion} de {tipo} en {ciudad}.",
                f"• Valor de referencia: {moneda} {precio}.",
                "• Balance entre calidad constructiva, ubicación y proyección de valor.",
                "\nENFOQUE COMERCIAL",
                "Esta propiedad se posiciona como una alternativa sólida para quien busca decidir con información clara y respaldo profesional.",
                "\nSIGUIENTE PASO",
                "Escribinos para enviarte la ficha técnica completa, videos, disponibilidad y agendar visita personalizada.",
                "#RealEstate #Propiedades #Inmobiliaria #Inversion",
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

def generar_qr_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import urllib.parse, urllib.request, base64
    # Limpiar teléfono: solo dígitos
    tel_limpio = ''.join(filter(str.isdigit, str(telefono)))
    # Si no empieza con código de país, asumir Argentina (+54)
    if tel_limpio and not tel_limpio.startswith('54'):
        tel_limpio = '54' + tel_limpio
    # Armar mensaje profesional
    detalle = f"{tipo_propiedad} en {ciudad}".strip(' en') if tipo_propiedad or ciudad else "propiedad"
    precio_str = f" por {moneda} {precio}" if precio else ""
    op_str = f" en {operacion.lower()}" if operacion else ""
    mensaje = f"Hola! Me interesa {detalle}{op_str}{precio_str}. ¿Podés darme más información?"
    # Armar URL de WhatsApp
    wa_url = f"https://wa.me/{tel_limpio}?text={urllib.parse.quote(mensaje)}"
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
            'min_total_words': 100,
            'max_total_words': 185,
            'scene_min_words': 12,
            'scene_max_words': 30,
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
            return False, f"Escenas insuficientes: {len(escenas)}/{rules['required_scenes']}"

        limited = escenas[:rules['required_scenes']]
        total_words = sum(_count_words(e.get('texto', '')) for e in limited)
        too_short = [
            idx + 1
            for idx, escena in enumerate(limited)
            if _count_words(escena.get('texto', '')) < max(4, rules['scene_min_words'] - 2)
        ]

        if too_short:
            return False, f"Escenas demasiado cortas: {too_short}"

        if total_words < rules['min_total_words']:
            return False, f"Palabras insuficientes: {total_words}/{rules['min_total_words']}"

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
        listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
        total_generados = listados.count()
        
        videos_creados = listados.aggregate(total_videos=Sum('videos_creados'))['total_videos'] or 0

        listados_recientes_qs = listados.order_by('-creado_en')[:5].values(
            'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en', 'datos_extra', 'video_url', 'video_status'
        )
        listados_recientes = []
        for item in listados_recientes_qs:
            item['datos'] = item.pop('datos_extra', {})
            listados_recientes.append(item)

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

from .services.instagram_service import publicar_post, publicar_story, publicar_carrusel, publicar_media_upload_api
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
            agente=user
        )
        
        if result.get('success'):
            # --- Añadir tracking manual de uso para UploadPost ---
            try:
                from api.pool_manager import get_api_key
                from api.models import APIKey
                from django.utils import timezone
                key_str = get_api_key(user, 'uploadpost')
                if key_str:
                    k = APIKey.objects.filter(api_key=key_str).first()
                    if k:
                        k.requests_today += 1
                        k.requests_this_month += 1
                        k.total_requests += 1
                        k.last_used_at = timezone.now()
                        k.save()
            except Exception as trk_e:
                print(f"[UploadPost Tracking Error]: {trk_e}")
            # -----------------------------------------------------
            
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_carrusel(request):
    """Genera 5 imagenes de carrusel y un caption con Gemini."""
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

        template_id = _select_template_id(data, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_carousel = TEMPLATE_CAROUSEL_MAP.get(template_id, TEMPLATE_CAROUSEL_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)

        if listado_obj:
            _persist_template_id(listado_obj, template_id, source='carrusel')

        images_pool = _collect_property_images(data)
        if not images_pool:
            images_to_use = [None] * 5
        else:
            images_to_use = [images_pool[i % len(images_pool)] for i in range(5)]

        recamaras = data.get('recamaras') or 'N/D'
        banos = data.get('banos') or 'N/D'
        superficie = data.get('superficieCubierta') or data.get('superficieTotal') or 'N/D'

        slides_urls = []
        slides_content = [
            {
                "headline": data.get('tipoPropiedad', 'Propiedad'),
                "subheadline": f"Una oportunidad unica en {data.get('ciudad', '')}",
            },
            {
                "headline": "Espacios",
                "subheadline": f"{recamaras} hab | {banos} banos para vivir con comodidad.",
            },
            {
                "headline": "Detalles",
                "subheadline": f"{superficie} m2 pensados para tu estilo de vida.",
            },
            {
                "headline": "Inversion",
                "subheadline": f"{data.get('operacion', 'Venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.",
            },
            {
                "headline": "Contacto",
                "subheadline": "Agenda tu visita y asegura esta propiedad hoy.",
            },
        ]

        for i in range(5):
            context = {
                "portada_url": images_to_use[i],
                "headline": slides_content[i]["headline"],
                "subheadline": slides_content[i]["subheadline"],
                "slide_number": i + 1,
                "total_slides": 5,
                "logo_url": branding.get('logo_url', ''),
                "operacion": data.get('operacion', 'Venta'),
                "agente_nombre": branding.get('agente_nombre', ''),
                "agente_telefono": branding.get('agente_telefono', ''),
                "agente_email": branding.get('agente_email', ''),
                "agente_rol": branding.get('agente_rol', 'Asesor Comercial'),
                "agencia_nombre": branding.get('agencia_nombre', ''),
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

            html_content = render_to_string(template_carousel, context)
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

        prompt_text = f"Escribí un caption para un carrusel de Instagram de una propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Enfocado en vender el estilo de vida y llamar a la acción. Usá emojis y hashtags."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario digital.", agente=user)
        caption = _sanitize_caption_text(caption)
        caption = _ensure_caption_length(caption, data, formato='carrusel')

        if listado_obj:
            actualizar_resultados_listado(
                listado_obj,
                'carrusel',
                {
                    "slides": slides_urls,
                    "caption": caption,
                    "template_id": template_id,
                },
            )

        if user.is_authenticated:
            incrementar_uso(user, 'image')

        return Response({
            "slides": slides_urls,
            "caption": caption,
            "template_id": template_id,
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus créditos de generación de contenido se agotaron. Se resetean automáticamente a medianoche.'
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
        data = []
        for listado in listados:
            data.append({
                'id': listado.id,
                'titulo': listado.titulo,
                'tipo_propiedad': listado.tipo_propiedad,
                'ciudad': listado.ciudad,
                'precio': listado.precio,
                'creado_en': listado.creado_en,
                'videos_creados': listado.videos_creados,
                'video_url': listado.video_url,
                'video_status': listado.video_status,
                'datos': listado.datos_extra
            })
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
        ciudad = payload.get('ciudad', '')
        precio = str(payload.get('precio', ''))
        
        # Guardamos en datos_extra el payload limpio
        listado = Listado.objects.create(
            agente=user,
            titulo=titulo,
            tipo_propiedad=tipo_propiedad,
            ciudad=ciudad,
            precio=precio,
            datos_extra=payload
        )
        
        incrementar_uso(user, 'property')
        
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
            return Response({
                "id": listado.id,
                "titulo": listado.titulo,
                "tipo_propiedad": listado.tipo_propiedad,
                "ciudad": listado.ciudad,
                "precio": listado.precio,
                "video_url": listado.video_url,
                "video_status": listado.video_status,
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
            listado.datos_extra = data['datos']
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
    logo_val_raw = branding.get('logo_url', '')
    logo_url = resolver_imagen(logo_val_raw)

    portada_val_raw = data.get('portadaUrl', '')
    fotos_raw = data.get('fotosRecorrido', [])

    fotos_limpias = []
    for f in fotos_raw:
        if isinstance(f, dict):
            if f.get('public_id') and f != logo_val_raw:
                fotos_limpias.append(f)
        elif isinstance(f, str) and f and f != logo_val_raw:
            fotos_limpias.append(f)

    # Si la portada viene vacía o es igual al logo, usar la primera foto real de la propiedad
    if not portada_val_raw or portada_val_raw == logo_val_raw:
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
        'portada_url_raw':    portada_url or '',
        'fotos_recorrido_raw': fotos_recorrido_urls,
        'logo_url_raw':       logo_url or '',
        'agente_nombre':      agente_nombre,
        'agente_telefono':    agente_telefono,
        'agente_email':       agente_email,
        'agente_rol':         agente_rol,
        'agente_foto_url':    agente_foto_url,
        'agencia_nombre':     agencia_nombre,
        'qr_code':            qr_base64_,
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

        template_id = _select_template_id(data, listado_obj=listado_obj, listado_id_hint=listado_id_hint)

        context['listado_id'] = listado_id_hint
        context['template_id'] = template_id

        logger.info(
            "[PDF] generar_pdf listado_id=%s template_id=%s user_id=%s",
            listado_id_hint,
            template_id,
            request.user.id,
        )

        if listado_obj:
            _persist_template_id(listado_obj, template_id, source='pdf')

        try:
            html_string = generar_html_desde_template(context, request.user)
        except Exception as e:
            print(f"[PDF] Error en sistema de templates: {e}. Usando fallback Gemini.")
            html_string = generar_html_gemini(context, request.user)
            
        if not html_string:
            print("[PDF] Fallback: Gemini falló, usando render_to_string estático")
            html_string = render_to_string('pdf/property_brochure_html.html', context)

        # ─── Conversión a PDF Real con Playwright ────────────────────────────
        pdf_url = None
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
                    if not listado_obj.datos_extra:
                        listado_obj.datos_extra = {}
                    if 'resultados' not in listado_obj.datos_extra:
                        listado_obj.datos_extra['resultados'] = {}

                    listado_obj.datos_extra['resultados']['pdf'] = {
                        "html": html_string,
                        "url": pdf_url,
                        "template_id": template_id,
                    }
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
            "listado_id": listado_id_hint,
            "template_id": template_id,
        }, status=status.HTTP_200_OK)

    except GeminiQuotaExhaustedError as e:
        try:
            from .models import UserAPIQuota, Servicio
            servicio_obj = Servicio.objects.filter(nombre='gemini').first()
            if servicio_obj:
                quota, _ = UserAPIQuota.objects.get_or_create(
                    user=request.user,
                    servicio=servicio_obj,
                    defaults={'daily_limit': 1500, 'monthly_limit': 1500}
                )
                quota.is_blocked = True
                quota.requests_today = quota.daily_limit
                quota.save()
        except Exception as quota_err:
            logger.warning(f"[PDF] No se pudo actualizar UserAPIQuota: {quota_err}")
        crear_notificacion(
            request.user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus créditos de generación de contenido se agotaron. Se resetean automáticamente a medianoche.'
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

        template_id = _select_template_id(data, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_post = TEMPLATE_POST_MAP.get(template_id, TEMPLATE_POST_MAP['dubai_night'])

        if listado_obj:
            _persist_template_id(listado_obj, template_id, source='post')

        html_content = render_to_string(template_post, context)
        print(f"[POST] Template elegido: {template_post}")
        image_stream = render_html_to_image(html_content, 1080, 1350)

        prompt_text = f"Escribí un caption para Instagram sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 2200 caracteres, usá hashtags y emojis."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)
        caption = _sanitize_caption_text(caption)
        caption = _ensure_caption_length(caption, data, formato='post')

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
        }, status=status.HTTP_200_OK)
    except GeminiQuotaExhaustedError as e:
        try:
            from .models import UserAPIQuota, Servicio
            servicio_obj = Servicio.objects.filter(nombre='gemini').first()
            if servicio_obj:
                quota, _ = UserAPIQuota.objects.get_or_create(
                    user=request.user,
                    servicio=servicio_obj,
                    defaults={'daily_limit': 1500, 'monthly_limit': 1500}
                )
                quota.is_blocked = True
                quota.requests_today = quota.daily_limit
                quota.save()
        except Exception as quota_err:
            logger.warning(f"[POST] No se pudo actualizar UserAPIQuota: {quota_err}")
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

        template_id = _select_template_id(data, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_story = TEMPLATE_STORY_MAP.get(template_id, TEMPLATE_STORY_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)

        if listado_obj:
            _persist_template_id(listado_obj, template_id, source='story')

        images_pool = _collect_property_images(data)
        story_cover = images_pool[0] if images_pool else _resolve_cloudinary_asset_url(data.get('portadaUrl'))

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
        image_stream = render_html_to_image(html_content, 1080, 1920)

        prompt_text = f"Escribí un texto para Instagram Story sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 500 caracteres, enfocado en llamar la atención rápido."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)
        caption = _sanitize_caption_text(caption, max_chars=500)
        caption = _ensure_caption_length(caption, data, formato='story')

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
        }, status=status.HTTP_200_OK)
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

        template_id = _select_template_id(data, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_email = TEMPLATE_EMAIL_MAP.get(template_id, TEMPLATE_EMAIL_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)

        if listado_obj:
            _persist_template_id(listado_obj, template_id, source='email')

        images_pool = _collect_property_images(data)
        email_cover = images_pool[0] if images_pool else _resolve_cloudinary_asset_url(data.get('portadaUrl'))
        template_meta = TEMPLATE_CATALOG.get(template_id, {})
        
        prompt_text = f"""
Redacta el cuerpo de un email profesional para ofrecer esta propiedad a un cliente interesado.
Tipo: {data.get('tipoPropiedad', 'Propiedad')}
Ciudad: {data.get('ciudad', '')}
Precio: {data.get('precio', '')}
Operación: {data.get('operacion', 'venta')}
Agente: {branding.get('agente_nombre', '')}
Agencia: {branding.get('agencia_nombre', '')}

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
            "portada_url": email_cover,
            "logo_url": branding.get('logo_url', ''),
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
        parsed["html"] = premium_html
        parsed["template_id"] = template_id
        
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
from datetime import datetime, timedelta

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout(request):
    plan = request.data.get('plan')
    ciclo = request.data.get('ciclo', 'monthly')
    
    planes = {
        'starter': {'nombre': 'LeadBook Starter', 'precio_mensual': 70000, 'precio_anual': 52500},
        'pro': {'nombre': 'LeadBook Pro', 'precio_mensual': 161000, 'precio_anual': 120750},
        'scale': {'nombre': 'LeadBook Scale', 'precio_mensual': 270000, 'precio_anual': 202500},
        'business': {'nombre': 'LeadBook Business', 'precio_mensual': 542000, 'precio_anual': 406500},
    }
    
    if plan not in planes:
        return Response({"error": "Plan inválido"}, status=400)
    
    plan_data = planes[plan]
    precio = plan_data['precio_anual'] if ciclo == 'annual' else plan_data['precio_mensual']
    nombre = f"{plan_data['nombre']} ({'Anual' if ciclo == 'annual' else 'Mensual'})"
    
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
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
        "external_reference": f"{request.user.id}|{plan}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        print(f"MP Error: {preference_response}")
        return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout_api_extra(request):
    """Genera link de pago para comprar una API adicional de Gemini"""
    servicio = request.data.get('servicio', 'gemini')
    
    PRECIOS_EXTRA = {
        'gemini':       {'nombre': 'Contenido IA — Adicional (+1500 créditos)',     'precio': 1},
        'elevenlabs':   {'nombre': 'Voces Neurales — Adicional (+10.000 caracteres)', 'precio': 1},
        'uploadpost':   {'nombre': 'Gestor de Redes — Adicional (+10 publicaciones)', 'precio': 1},
        'pack_completo':{'nombre': 'Pack Completo — Todos los recursos',              'precio': 1},
    }
    
    if servicio not in PRECIOS_EXTRA:
        return Response({"error": "Servicio inválido"}, status=400)
    
    item = PRECIOS_EXTRA[servicio]
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
    preference_data = {
        "items": [{
            "id": f"extra_{servicio}",
            "title": item['nombre'],
            "description": f"Uso adicional permanente mensual de {item['nombre']}. Se suma a tu límite actual.",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(item['precio'])
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/dashboard?extra=exitoso&servicio={servicio}",
            "failure": f"{frontend_url}/precios?extra=fallido",
            "pending": f"{frontend_url}/dashboard?extra=pendiente"
        },
        "auto_return": "approved",
        "external_reference": f"{request.user.id}|extra_{servicio}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    topic = request.data.get('type')
    data_id = request.data.get('data', {}).get('id')
    
    if not data_id:
        return Response({"status": "ok"})
    
    try:
        import requests as req
        headers = {"Authorization": f"Bearer {config('MP_ACCESS_TOKEN')}"}
        
        if topic == 'payment':
            response = req.get(
                f"https://api.mercadopago.com/v1/payments/{data_id}",
                headers=headers
            )
        elif topic == 'subscription_preapproval':
            response = req.get(
                f"https://api.mercadopago.com/preapproval/{data_id}",
                headers=headers
            )
        else:
            return Response({"status": "ok"})
        
        data = response.json()
        status = data.get("status")
        external_ref = data.get("external_reference", "")
        
        if status in ["approved", "authorized"] and "|" in external_ref:
            user_id, tipo = external_ref.split("|", 1)
            from .models import Agent
            try:
                agent = Agent.objects.get(id=int(user_id))
                if tipo.startswith('extra_'):
                    # Compra de API adicional
                    if tipo == 'extra_pack_completo':
                        for svc in ['gemini', 'elevenlabs', 'uploadpost']:
                            keys_ya_usadas = BundleAPIExtra.objects.filter(
                                usuario=agent, servicio=svc, activa=True
                            ).values_list('api_key_id', flat=True)
                            key_disponible = APIKey.objects.filter(
                                servicio=svc, status__in=['available', 'active']
                            ).exclude(id__in=keys_ya_usadas).first()
                            if key_disponible:
                                BundleAPIExtra.objects.create(
                                    usuario=agent, api_key=key_disponible,
                                    servicio=svc, activa=True, pago_id=str(data_id)
                                )
                                from .models import UserAPIQuota
                                quota, _ = UserAPIQuota.objects.get_or_create(user=agent, servicio=Servicio.objects.get(nombre=svc))
                                quota.is_blocked = False
                                # Incrementos específicos por servicio
                                inc = 1500 if svc == 'gemini' else 10000 if svc == 'elevenlabs' else 10
                                quota.monthly_limit = (quota.monthly_limit or (1500 if svc=='gemini' else 10000 if svc=='elevenlabs' else 10)) + inc
                                quota.daily_limit = (quota.daily_limit or (1500 if svc=='gemini' else 10000 if svc=='elevenlabs' else 10)) + inc
                                quota.save()
                        print(f"[MP] Pack completo asignado: user {user_id}")
                    else:
                        servicio = tipo.replace('extra_', '')
                        from .models import APIKey, BundleAPIExtra
                        # Buscar una APIKey disponible del servicio que no esté asignada como extra
                        keys_ya_usadas = BundleAPIExtra.objects.filter(
                            usuario=agent, servicio=servicio, activa=True
                        ).values_list('api_key_id', flat=True)
                        key_disponible = APIKey.objects.filter(
                            servicio=servicio,
                            status__in=['available', 'active']
                        ).exclude(id__in=keys_ya_usadas).first()
                        
                        if key_disponible:
                            BundleAPIExtra.objects.create(
                                usuario=agent, api_key=key_disponible,
                                servicio=servicio, activa=True, pago_id=str(data_id)
                            )
                            # Actualizar el límite en UserAPIQuota
                            from .models import UserAPIQuota
                            quota, _ = UserAPIQuota.objects.get_or_create(user=agent, servicio=Servicio.objects.get(nombre=servicio))
                            quota.is_blocked = False
                            # Aumentar límites (mensual y diario)
                            inc = 1500 if servicio == 'gemini' else 10000 if servicio == 'elevenlabs' else 10
                            quota.monthly_limit = (quota.monthly_limit or inc) + inc
                            quota.daily_limit = (quota.daily_limit or inc) + inc
                            quota.save()
                            print(f"[MP] API extra asignada: user {user_id} → {servicio} extra")
                        else:
                            print(f"[MP] No hay APIKey disponible para {servicio}")
                else:
                    # Compra de plan normal
                    agent.plan_nombre = tipo
                    agent.plan_activo = True
                    agent.save()
                    print(f"[MP] Plan actualizado: user {user_id} → {tipo}")



            except Agent.DoesNotExist:
                print(f"[MP] Usuario no encontrado: {user_id}")
    except Exception as e:
        print(f"[MP] Error webhook: {e}")
    
    return Response({"status": "ok"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def plan_status(request):
    user = request.user
    return Response({
        "plan_nombre": user.plan_nombre,
        "plan_activo": user.plan_activo,
        "plan_seleccionado": user.plan_seleccionado,
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
        "mp_public_key": settings.MP_PUBLIC_KEY,
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
            "video_generations": limites['videos']
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
    
    from .models import Agent, APIKey, UserAPIQuota, APIBundleAssignment
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
    listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
    total_generados = listados.count()
    videos_creados = listados.aggregate(total=Sum('videos_creados'))['total'] or 0

    listados_recientes = list(listados.order_by('-creado_en')[:5].values(
        'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en'
    ))

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
    """Historial de pagos/planes"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent
    agentes_pagos = Agent.objects.exclude(
        plan_nombre='free'
    ).order_by('-fecha_registro')
    data = [{
        "email": a.email,
        "nombre": a.nombre,
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "mp_customer_id": a.mp_customer_id or '',
        "mp_subscription_id": a.mp_subscription_id or '',
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d') if a.fecha_registro else ''
    } for a in agentes_pagos]
    return Response({"pagos": data, "total_pagos": len(data)})

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
    tipo_video_norm = str(tipo_video or '').strip().lower()
    es_reel = tipo_video_norm in ('reel', 'reel_rapido', 'reel-rapido')
    palabras = '7-14' if es_reel else '14-24'
    contexto_extra = f"\nEnfoque adicional: {contexto_adicional}" if contexto_adicional else ''

    prompt = f"""Sos un copywriter inmobiliario experto.
Generá SOLO el texto para la escena "{nombre_escena}" (escena {indice_escena + 1} de {total_escenas}) de un video inmobiliario.

PROPIEDAD: {tipo} en {operacion} | {ciudad} | {moneda} {precio}
TONO: {tono_instrucciones}
NARRADOR: {narrador}{contexto_extra}

REQUISITOS:
- Exactamente {palabras} palabras
- El texto es para narración en voz en off, debe sonar natural al hablar
- No pongas el nombre de la escena, solo el texto a narrar
- Responde SOLO el texto, sin JSON, sin comillas, sin explicaciones"""

    try:
        result = call_gemini_api(prompt, agente=request.user)
        if not result:
            return Response({"error": "No se pudo generar texto"}, status=503)
        return Response({"texto": result.strip()})
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
        agotada = quota.is_blocked
        usado = quota.requests_today
        limite = quota.daily_limit
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
    from .models import UserAPIQuota, APIKey, APIBundleAssignment
    
    if request.method == 'POST':
        from .models import UserAPIQuota
        # Desbloquear todos los usuarios cuyo uso actual es menor al límite
        desbloqueados = 0
        for q in UserAPIQuota.objects.filter(is_blocked=True):
            if q.requests_today < q.daily_limit:
                q.is_blocked = False
                q.save()
                desbloqueados += 1
        # Corregir límites incorrectos por servicio
        UserAPIQuota.objects.filter(servicio__nombre='uploadpost', user_daily_limit__gt=100).update(user_daily_limit=10)
        UserAPIQuota.objects.filter(servicio__nombre='gemini', user_daily_limit__lt=100).update(user_daily_limit=1500)
        
        # Reset extras de prueba (pago_id = 'manual_admin')
        from .models import BundleAPIExtra
        extras_borradas = BundleAPIExtra.objects.filter(pago_id='manual_admin').delete()
        print(f"[DEBUG] Extras de prueba borradas: {extras_borradas}")
        
        return Response({'desbloqueados': desbloqueados})
    
    quotas = list(UserAPIQuota.objects.values(
        'user_id', 'service', 'daily_limit', 'monthly_limit', 
        'requests_today', 'is_blocked'
    ))
    assignments = APIBundleAssignment.objects.filter(activo=True).select_related('usuario', 'bundle__key_gemini')
    keys_info = []
    for a in assignments:
        k = a.bundle.key_gemini if a.bundle else None
        if k:
            keys_info.append({
                'user': a.usuario.email,
                'key_id': k.id,
                'daily_limit': k.daily_limit,
                'monthly_limit': k.monthly_limit,
                'status': k.status
            })
    return Response({'quotas': quotas, 'keys': keys_info})
