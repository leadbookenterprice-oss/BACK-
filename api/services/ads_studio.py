import json
import re
from datetime import datetime, timezone


DEFAULT_AD_OBJECTIVE = 'generar leads calificados para una propiedad inmobiliaria'
DEFAULT_TONE = 'profesional, claro y persuasivo'
MAX_VARIANTS = 8


def normalize_ads_request(payload):
    payload = payload if isinstance(payload, dict) else {}
    property_data = (
        payload.get('data')
        or payload.get('datos')
        or payload.get('property')
        or payload.get('property_data')
        or {}
    )
    if not isinstance(property_data, dict):
        property_data = {}

    count = payload.get('cantidad_variantes') or payload.get('cantidad') or payload.get('variants') or 3
    try:
        count = int(count)
    except Exception:
        count = 3
    count = max(1, min(count, MAX_VARIANTS))

    params = {
        'objetivo': _clean(payload.get('objetivo') or payload.get('objective') or DEFAULT_AD_OBJECTIVE),
        'tono': _clean(payload.get('tono') or payload.get('tone') or DEFAULT_TONE),
        'presupuesto': _clean(payload.get('presupuesto') or payload.get('budget') or ''),
        'cantidad_variantes': count,
        'idioma': _clean(payload.get('idioma') or property_data.get('idioma') or 'es'),
    }
    return property_data, params


def build_meta_ads_prompt(property_data, params):
    compact_property = _compact_property_data(property_data)
    count = params['cantidad_variantes']
    return f"""Genera {count} variantes de anuncios para Meta Ads (Facebook/Instagram) para esta propiedad inmobiliaria.

Datos de propiedad en JSON:
{json.dumps(compact_property, ensure_ascii=False, indent=2)}

Parametros:
- Objetivo: {params['objetivo']}
- Tono: {params['tono']}
- Presupuesto estimado: {params['presupuesto'] or 'no informado'}
- Idioma: {params['idioma']}

Reglas:
- Responder SOLO JSON valido, sin markdown.
- Crear variantes realmente distintas para test A/B.
- No inventar datos duros que no esten en la propiedad.
- Evitar promesas engañosas o claims discriminatorios.
- Mantener primary_text entre 220 y 520 caracteres.
- Headline maximo 55 caracteres.
- Description maximo 90 caracteres.
- CTA debe ser uno de: Más información, Enviar mensaje, Contactar, Reservar visita, Ver detalles.

Formato exacto:
{{
  "variants": [
    {{
      "primary_text": "...",
      "headline": "...",
      "description": "...",
      "cta": "...",
      "hook": "...",
      "segmento_sugerido": "..."
    }}
  ]
}}"""


def parse_meta_ads_response(raw_text, expected_count):
    parsed = _parse_json_object(raw_text)
    if not parsed:
        raise ValueError('La IA no devolvio JSON valido para Ads Studio.')
    variants = parsed.get('variants') or parsed.get('variantes') or []
    if not isinstance(variants, list):
        raise ValueError('La respuesta de Ads Studio no contiene una lista de variantes.')

    normalized = []
    for item in variants:
        if not isinstance(item, dict):
            continue
        variant = {
            'primary_text': _limit(_clean(item.get('primary_text') or item.get('texto_principal')), 700),
            'headline': _limit(_clean(item.get('headline') or item.get('titulo')), 80),
            'description': _limit(_clean(item.get('description') or item.get('descripcion')), 120),
            'cta': _limit(_clean(item.get('cta') or item.get('CTA')), 40),
            'hook': _limit(_clean(item.get('hook') or item.get('gancho')), 160),
            'segmento_sugerido': _limit(_clean(item.get('segmento_sugerido') or item.get('segmento') or item.get('audiencia')), 180),
        }
        if variant['primary_text'] and variant['headline']:
            if not variant['cta']:
                variant['cta'] = 'Más información'
            normalized.append(variant)
        if len(normalized) >= expected_count:
            break

    if not normalized:
        raise ValueError('La IA no devolvio variantes utilizables.')
    return normalized


def build_ads_result(variants, params, *, listado_id=None):
    return {
        'ok': True,
        'listado_id': listado_id,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'params': params,
        'variants': variants,
    }


def _compact_property_data(data):
    allowed_keys = [
        'titulo', 'descripcion', 'precio', 'moneda', 'operacion', 'tipo_propiedad', 'tipoPropiedad',
        'ciudad', 'direccion', 'recamaras', 'banos', 'superficie_total', 'superficieTotal',
        'superficie_cubierta', 'superficieCubierta', 'estacionamientos', 'amenidades', 'fotos',
        'fotosRecorrido', 'portadaUrl', 'url', 'landing_url', 'importUrl',
    ]
    compact = {}
    for key in allowed_keys:
        value = data.get(key) if isinstance(data, dict) else None
        if value in (None, '', [], {}):
            continue
        if isinstance(value, list):
            compact[key] = value[:12]
        else:
            compact[key] = value
    return compact


def _parse_json_object(text):
    source = str(text or '').strip()
    cleaned = re.sub(r'^\s*```(?:json)?\s*', '', source, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.IGNORECASE).strip()
    candidates = [source, cleaned]
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
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            continue
    return None


def _clean(value):
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()


def _limit(value, max_length):
    return value[:max_length].rstrip() if value and len(value) > max_length else value
