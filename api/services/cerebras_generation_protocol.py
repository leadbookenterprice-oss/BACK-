import json

from django.utils import timezone

from api.models import CerebrasUsageLog
from api.services.ai_limits import build_limits_snapshot
from api.services.cerebras_slots import estimate_cerebras_tokens
from api.services.template_contracts import (
    build_pdf_contract_text,
    get_template_contract,
    normalize_template_id,
)


PROTOCOL_VERSION = 'leadbook.generation_protocol.v1'
PLANNER_PRIMARY_MODEL = 'zai-glm-4.7'
PLANNER_FALLBACK_MODEL = 'gpt-oss-120b'
PLANNER_TASK = 'generation_plan'
PLANNER_MAX_COMPLETION_TOKENS = 2400
DEFAULT_OUTPUTS = ('pdf', 'post', 'story', 'carrusel', 'email')


def _safe_text(value, max_chars=600):
    text = str(value or '').strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + '...'


def _get_any(payload, *keys, default=''):
    if not isinstance(payload, dict):
        return default
    for key in keys:
        value = payload.get(key)
        if value not in (None, ''):
            return value
    return default


def _clean_list(value, limit=8, max_chars=260):
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            direct = item.get('secure_url') or item.get('url') or item.get('src') or item.get('public_id')
            text = _safe_text(direct or item, max_chars=max_chars)
        else:
            text = _safe_text(item, max_chars=max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _resolve_provider(run, payload):
    metadata = run.metadata if run and isinstance(run.metadata, dict) else {}
    raw = (
        _get_any(payload, 'ai_provider', 'aiProvider', 'provider', default='')
        or metadata.get('ai_provider')
        or metadata.get('ai_root_provider')
        or 'cerebras'
    )
    provider = str(raw or '').strip().lower()
    return 'nvidia' if provider in {'nim', 'nvidia_nim'} else provider


def build_listing_protocol_context(run, payload=None, user=None):
    payload = payload if isinstance(payload, dict) else {}
    listado = run.listado if run else None
    datos = listado.datos_extra if listado and isinstance(listado.datos_extra, dict) else {}
    merged = {**datos, **payload}

    template_id = normalize_template_id(
        _get_any(merged, 'template_id', 'templateId', 'selectedTemplateId', 'template', default='')
    ) or normalize_template_id((run.metadata or {}).get('selected_template') if run else None) or 'tech_modern'
    contract = get_template_contract(template_id) or get_template_contract('tech_modern')

    photos = _clean_list(
        _get_any(
            merged,
            'fotos_recorrido_raw',
            'fotos_recorrido',
            'fotos',
            'imagenes',
            'galeria',
            'photos',
            default=[],
        ),
        limit=8,
    )
    cover_url = _safe_text(_get_any(merged, 'portada_url', 'portadaUrl', 'foto_portada', 'cover_url', default=''), 360)

    return {
        'listing': {
            'id': listado.id if listado else _get_any(merged, 'listado_id', 'listadoId', default=''),
            'title': _safe_text(_get_any(merged, 'titulo', default=getattr(listado, 'titulo', '')), 220),
            'type': _safe_text(_get_any(merged, 'tipo_propiedad', 'tipoPropiedad', default=getattr(listado, 'tipo_propiedad', '')), 120),
            'operation': _safe_text(_get_any(merged, 'operacion', default=getattr(listado, 'operacion', 'venta')), 80),
            'city': _safe_text(_get_any(merged, 'ciudad', default=getattr(listado, 'ciudad', '')), 120),
            'neighborhood': _safe_text(_get_any(merged, 'barrio', default=getattr(listado, 'barrio', '')), 120),
            'price': _safe_text(_get_any(merged, 'precio', default=getattr(listado, 'precio', '')), 80),
            'currency': _safe_text(_get_any(merged, 'moneda', default=getattr(listado, 'moneda', 'USD')), 20),
            'bedrooms': _safe_text(_get_any(merged, 'recamaras', 'habitaciones', default=''), 40),
            'bathrooms': _safe_text(_get_any(merged, 'banos', 'banios', default=''), 40),
            'covered_area': _safe_text(_get_any(merged, 'superficie_cubierta', 'superficieCubierta', default=''), 60),
            'total_area': _safe_text(_get_any(merged, 'superficie_total', 'superficieTotal', default=getattr(listado, 'metros_cuadrados', '') or ''), 60),
            'parking': _safe_text(_get_any(merged, 'estacionamientos', 'cocheras', default=''), 40),
            'description': _safe_text(_get_any(merged, 'descripcion', 'description', 'contextoAdicional', 'notasAdicionales', default=''), 1400),
            'amenities': _clean_list(_get_any(merged, 'amenidades', 'amenities', default=[]), limit=14, max_chars=120),
        },
        'media': {
            'cover_url': cover_url,
            'gallery_urls': photos,
        },
        'agent': {
            'name': _safe_text(getattr(user, 'nombre', '') or _get_any(merged, 'agente_nombre', default=''), 160),
            'email': _safe_text(getattr(user, 'email', '') or _get_any(merged, 'agente_email', default=''), 180),
            'phone': _safe_text(getattr(user, 'telefono', '') or _get_any(merged, 'agente_telefono', default=''), 80),
            'agency': _safe_text(getattr(user, 'nombre_inmobiliaria', '') or _get_any(merged, 'agencia_nombre', default=''), 180),
        },
        'template': {
            'id': contract['id'],
            'name': contract['name'],
            'base_layout': contract['base_layout'],
            'style': contract['style'],
            'colors': contract['colors'],
            'fonts': contract['fonts'],
            'contract_text': build_pdf_contract_text(contract['id']),
            'brand_template_id': (run.metadata or {}).get('brand_template_id') if run else None,
        },
        'requested_outputs': list(DEFAULT_OUTPUTS),
    }


def build_local_generation_protocol(run, payload=None, user=None, *, provider=None, planner_status='local'):
    context = build_listing_protocol_context(run, payload=payload, user=user)
    provider_key = provider or _resolve_provider(run, payload or {})
    model = PLANNER_PRIMARY_MODEL if provider_key == 'cerebras' else ''
    return {
        'version': PROTOCOL_VERSION,
        'created_at': timezone.now().isoformat(),
        'provider': provider_key,
        'planner': {
            'status': planner_status,
            'primary_model': PLANNER_PRIMARY_MODEL,
            'fallback_model': PLANNER_FALLBACK_MODEL,
            'model_used': model,
        },
        'listing_context': context['listing'],
        'media': context['media'],
        'template': context['template'],
        'requested_outputs': context['requested_outputs'],
        'creative_direction': {
            'tone': 'premium_real_estate',
            'positioning': 'clear, concrete, conversion-oriented',
            'avoid': ['generic copy', 'invented facts', 'extra templates', 'video instructions'],
        },
        'asset_instructions': {
            'pdf': 'Use the selected template contract and all required PDF sections.',
            'post': 'Create a feed-ready caption and visual aligned with the template.',
            'story': 'Create a short premium story caption aligned with the same angle.',
            'carrusel': 'Use one coherent narrative across slides and caption.',
            'email': 'Create a professional client email without inventing contact data.',
        },
        'phases': ['plan', *DEFAULT_OUTPUTS],
        'limits_snapshot': build_limits_snapshot(provider_key, model, estimated_tokens=0),
    }


def _planner_system_prompt():
    return (
        'Sos el planner tecnico de LeadBook. Devolves solo JSON valido, sin markdown. '
        'Tu tarea es convertir un listado inmobiliario y un contrato visual en un protocolo '
        'unico para generar PDF, post, story, carrusel y email. No inventes datos.'
    )


def _planner_user_prompt(context):
    schema = {
        'version': PROTOCOL_VERSION,
        'creative_direction': {
            'tone': 'string',
            'positioning': 'string',
            'main_angle': 'string',
            'avoid': ['string'],
        },
        'asset_instructions': {
            'pdf': 'string',
            'post': 'string',
            'story': 'string',
            'carrusel': 'string',
            'email': 'string',
        },
        'requested_outputs': list(DEFAULT_OUTPUTS),
    }
    return (
        'Genera el protocolo JSON para esta propiedad. El protocolo debe servir como '
        'hoja de ruta unica para todas las piezas, sin generar los assets finales.\n\n'
        f'CONTEXTO:\n{json.dumps(context, ensure_ascii=False)}\n\n'
        f'ESQUEMA OBLIGATORIO:\n{json.dumps(schema, ensure_ascii=False)}\n\n'
        'Reglas: mantener el template indicado, respetar colores hardcodeados del contrato, '
        'no incluir video, no crear mas de una propiedad, no devolver texto fuera del JSON.'
    )


def _extract_json_object(raw):
    text = str(raw or '').strip()
    if text.startswith('```json'):
        text = text[7:].strip()
    if text.startswith('```'):
        text = text[3:].strip()
    if text.endswith('```'):
        text = text[:-3].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        parsed = json.loads(text[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    return None


def _last_planner_model_used(run):
    if not run:
        return ''
    log = (
        CerebrasUsageLog.objects
        .filter(run_id=run.id, task=PLANNER_TASK, success=True)
        .order_by('-creado_en', '-id')
        .first()
    )
    return log.model if log else ''


def _merge_ai_protocol(base_protocol, ai_protocol, *, model_used='', estimated_tokens=0):
    protocol = dict(base_protocol)
    protocol['planner'] = {
        **(protocol.get('planner') or {}),
        'status': 'ai_generated',
        'primary_model': PLANNER_PRIMARY_MODEL,
        'fallback_model': PLANNER_FALLBACK_MODEL,
        'model_used': model_used or PLANNER_PRIMARY_MODEL,
    }
    for key in ('creative_direction', 'asset_instructions', 'requested_outputs'):
        value = ai_protocol.get(key)
        if value:
            protocol[key] = value
    protocol['version'] = PROTOCOL_VERSION
    protocol['limits_snapshot'] = build_limits_snapshot(
        'cerebras',
        protocol['planner']['model_used'],
        estimated_tokens=estimated_tokens,
    )
    return protocol


def create_generation_protocol(run, payload=None, user=None):
    provider = _resolve_provider(run, payload or {})
    base_protocol = build_local_generation_protocol(run, payload=payload, user=user, provider=provider)
    if provider != 'cerebras':
        return base_protocol

    context = build_listing_protocol_context(run, payload=payload, user=user)
    system_prompt = _planner_system_prompt()
    user_prompt = _planner_user_prompt(context)
    estimated_tokens = estimate_cerebras_tokens(
        user_prompt,
        system_prompt=system_prompt,
        max_completion_tokens=PLANNER_MAX_COMPLETION_TOKENS,
    )

    from api.ai_services import call_cerebras_api

    raw = call_cerebras_api(
        user_prompt,
        agente=user,
        model=PLANNER_PRIMARY_MODEL,
        allow_model_fallback=True,
        system_prompt=system_prompt,
        temperature=0.25,
        top_p=0.9,
        max_completion_tokens=PLANNER_MAX_COMPLETION_TOKENS,
        task=PLANNER_TASK,
        listado_id=run.listado_id if run else None,
        generation_run_id=run.id if run else None,
        generation_step='plan',
        metadata={
            'protocol_version': PROTOCOL_VERSION,
            'planner_primary_model': PLANNER_PRIMARY_MODEL,
            'planner_fallback_model': PLANNER_FALLBACK_MODEL,
            'limits_snapshot': build_limits_snapshot('cerebras', PLANNER_PRIMARY_MODEL, estimated_tokens=estimated_tokens),
        },
    )
    model_used = _last_planner_model_used(run) or PLANNER_PRIMARY_MODEL
    try:
        ai_protocol = _extract_json_object(raw)
    except Exception:
        ai_protocol = None
    if not ai_protocol:
        fallback = dict(base_protocol)
        fallback['planner'] = {
            **(fallback.get('planner') or {}),
            'status': 'local_after_invalid_ai_json',
            'model_used': model_used,
            'raw_response_preview': _safe_text(raw, 900),
        }
        fallback['limits_snapshot'] = build_limits_snapshot('cerebras', model_used, estimated_tokens=estimated_tokens)
        return fallback
    return _merge_ai_protocol(base_protocol, ai_protocol, model_used=model_used, estimated_tokens=estimated_tokens)


def protocol_prompt_fragment(protocol, step_name):
    if not isinstance(protocol, dict):
        return ''
    creative = protocol.get('creative_direction') or {}
    instructions = protocol.get('asset_instructions') or {}
    template = protocol.get('template') or {}
    step_instruction = instructions.get(step_name) or ''
    fragment = {
        'template_id': template.get('id'),
        'template_colors': template.get('colors') or {},
        'creative_direction': creative,
        'step_instruction': step_instruction,
    }
    return (
        '\n\nPROTOCOLO GLOBAL DE GENERACION:\n'
        f'{json.dumps(fragment, ensure_ascii=False)}\n'
        'Usa este protocolo como direccion de consistencia. No inventes datos fuera del listado.\n'
    )
