import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from decouple import config
from django.conf import settings
from django.utils import timezone


logger = logging.getLogger(__name__)

NVIDIA_FREE_MODELS_CONFIG_KEY = 'nvidia_free_models'
NVIDIA_MODELS_ENDPOINT = 'https://integrate.api.nvidia.com/v1/models'
NVIDIA_UNUSABLE_KEY_STATUSES = {'dead', 'disabled', 'exhausted'}


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value == 0:
            return False
        if value == 1:
            return True
        return None
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'y', 'free', 'available'}:
        return True
    if text in {'0', 'false', 'no', 'n', 'paid', 'unavailable'}:
        return False
    return None


def _iter_dicts(*values):
    for value in values:
        if isinstance(value, dict):
            yield value


def _extract_models(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ('data', 'models', 'items', 'results'):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload] if payload.get('id') else []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _model_id(item: Dict[str, Any]) -> str:
    return str(
        item.get('id')
        or item.get('model')
        or item.get('name')
        or item.get('model_id')
        or item.get('modelId')
        or ''
    ).strip()


def _label_for_model(model_id: str, item: Optional[Dict[str, Any]] = None) -> str:
    item = item or {}
    explicit = str(item.get('label') or item.get('display_name') or item.get('displayName') or '').strip()
    if explicit:
        return explicit
    tail = model_id.rsplit('/', 1)[-1]
    return tail.replace('-', ' ').replace('_', ' ').title()


def _pricing_is_free(pricing: Any):
    if pricing in (None, '', {}):
        return None
    if isinstance(pricing, str):
        text = pricing.strip().lower()
        if 'free' in text:
            return True
        if any(term in text for term in ('paid', 'price', 'credit', '$')):
            return False
        return None
    if isinstance(pricing, (int, float)):
        return pricing == 0
    if isinstance(pricing, dict):
        values = []
        for key, value in pricing.items():
            key_text = str(key).lower()
            if 'free' in key_text:
                flag = _as_bool(value)
                if flag is not None:
                    return flag
            if isinstance(value, (int, float)):
                values.append(float(value))
            elif isinstance(value, str):
                stripped = value.strip().replace('$', '')
                try:
                    values.append(float(stripped))
                except ValueError:
                    flag = _as_bool(value)
                    if flag is not None:
                        return flag
        if values:
            return all(value == 0 for value in values)
    return None


def _explicit_free_flag(item: Dict[str, Any]):
    flag_keys = (
        'free',
        'is_free',
        'isFree',
        'free_endpoint',
        'freeEndpoint',
        'has_free_endpoint',
        'hasFreeEndpoint',
        'free_endpoint_available',
        'freeEndpointAvailable',
    )
    nested = (
        item,
        item.get('metadata'),
        item.get('meta'),
        item.get('details'),
        item.get('capabilities'),
        item.get('nvidia'),
    )
    for container in _iter_dicts(*nested):
        for key in flag_keys:
            if key not in container:
                continue
            flag = _as_bool(container.get(key))
            if flag is not None:
                return flag
    for container in _iter_dicts(*nested):
        for key in ('pricing', 'price', 'cost', 'billing'):
            if key in container:
                priced = _pricing_is_free(container.get(key))
                if priced is not None:
                    return priced
    return None


def _is_free_or_accessible_model(item: Dict[str, Any]) -> bool:
    explicit = _explicit_free_flag(item)
    if explicit is not None:
        return bool(explicit)
    # NVIDIA's OpenAI-compatible /v1/models endpoint returns the models available
    # to the supplied key. When no pricing metadata is present, treat them as
    # free/accessible for this account and keep the raw metadata for auditing.
    return True


def _compact_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    keep = {}
    for key in (
        'object',
        'owned_by',
        'ownedBy',
        'created',
        'created_at',
        'createdAt',
        'description',
        'context_length',
        'contextLength',
        'max_context_length',
        'maxContextLength',
        'max_model_len',
        'maxModelLen',
        'input_modalities',
        'output_modalities',
        'pricing',
        'free',
        'is_free',
        'free_endpoint',
        'freeEndpoint',
    ):
        if key in item:
            keep[key] = item[key]
    return keep


def normalize_nvidia_models(payload: Any) -> List[Dict[str, Any]]:
    seen = set()
    normalized = []
    for item in _extract_models(payload):
        model_id = _model_id(item)
        if not model_id or model_id in seen:
            continue
        if not _is_free_or_accessible_model(item):
            continue
        seen.add(model_id)
        normalized.append({
            'model': model_id,
            'id': model_id,
            'label': _label_for_model(model_id, item),
            'free_endpoint': True,
            'selectable': True,
            'metadata': _compact_metadata(item),
        })
    normalized.sort(key=lambda model: model['model'])
    return normalized


def _get_nvidia_discovery_key(explicit_key: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    if explicit_key:
        return explicit_key, {'source': 'explicit', 'api_key_id': None}

    from api.models import APIKey

    key_obj = (
        APIKey.objects
        .filter(servicio__nombre__iexact='nvidia')
        .exclude(status__in=NVIDIA_UNUSABLE_KEY_STATUSES)
        .order_by('requests_today', 'id')
        .first()
    )
    if key_obj:
        return key_obj.api_key, {'source': 'pool', 'api_key_id': key_obj.id}

    env_key = getattr(settings, 'NVIDIA_API_KEY', '') or config('NVIDIA_API_KEY', default='')
    env_key = str(env_key or '').strip()
    if env_key:
        return env_key, {'source': 'settings', 'api_key_id': None}

    return '', {'source': 'missing', 'api_key_id': None}


def get_cached_nvidia_free_models() -> Dict[str, Any]:
    from api.models import ConfiguracionSistema

    cfg = ConfiguracionSistema.objects.filter(clave=NVIDIA_FREE_MODELS_CONFIG_KEY).first()
    if not cfg or not isinstance(cfg.datos, dict):
        return {
            'provider': 'nvidia',
            'status': 'empty',
            'models': [],
            'count': 0,
        }
    data = dict(cfg.datos)
    models = data.get('models') if isinstance(data.get('models'), list) else []
    data['models'] = models
    data['count'] = len(models)
    return data


def get_cached_nvidia_model_entries() -> List[Dict[str, Any]]:
    cached = get_cached_nvidia_free_models()
    entries = []
    for item in cached.get('models') or []:
        model_id = str(item.get('model') or item.get('id') or '').strip()
        if not model_id:
            continue
        entries.append({
            'model': model_id,
            'label': str(item.get('label') or _label_for_model(model_id)).strip(),
            'free_endpoint': True,
            'source': 'nvidia_discovery',
            'metadata': item.get('metadata') if isinstance(item.get('metadata'), dict) else {},
        })
    return entries


def discover_nvidia_free_models(api_key: Optional[str] = None, requested_by: str = 'system') -> Dict[str, Any]:
    from api.models import ConfiguracionSistema

    key, key_meta = _get_nvidia_discovery_key(api_key)
    now = timezone.now()
    endpoint = config('NVIDIA_MODELS_ENDPOINT', default=NVIDIA_MODELS_ENDPOINT).strip() or NVIDIA_MODELS_ENDPOINT
    timeout = config('NVIDIA_MODELS_DISCOVERY_TIMEOUT', default=30, cast=int)

    if not key:
        cached = get_cached_nvidia_free_models()
        payload = {
            **cached,
            'provider': 'nvidia',
            'status': 'missing_key',
            'last_error': 'No hay NVIDIA API key disponible para discovery.',
            'last_failed_at': now.isoformat(),
            'endpoint': endpoint,
            'requested_by': requested_by,
        }
        ConfiguracionSistema.objects.update_or_create(
            clave=NVIDIA_FREE_MODELS_CONFIG_KEY,
            defaults={'valor': str(payload.get('count', 0)), 'datos': payload},
        )
        return payload

    headers = {'Authorization': f'Bearer {key}'}
    try:
        response = requests.get(endpoint, headers=headers, timeout=timeout)
        status_code = response.status_code
        response.raise_for_status()
        raw_payload = response.json() if response.content else {}
    except Exception as exc:
        logger.exception('[NVIDIA] No se pudo descubrir catalogo de modelos')
        cached = get_cached_nvidia_free_models()
        payload = {
            **cached,
            'provider': 'nvidia',
            'status': 'error',
            'last_error': str(exc)[:500],
            'last_failed_at': now.isoformat(),
            'endpoint': endpoint,
            'requested_by': requested_by,
            **key_meta,
        }
        ConfiguracionSistema.objects.update_or_create(
            clave=NVIDIA_FREE_MODELS_CONFIG_KEY,
            defaults={'valor': str(payload.get('count', 0)), 'datos': payload},
        )
        return payload

    models = normalize_nvidia_models(raw_payload)
    payload = {
        'provider': 'nvidia',
        'status': 'ok',
        'endpoint': endpoint,
        'source': 'nvidia_models_api',
        'requested_by': requested_by,
        'fetched_at': now.isoformat(),
        'raw_count': len(_extract_models(raw_payload)),
        'count': len(models),
        'models': models,
        **key_meta,
    }
    ConfiguracionSistema.objects.update_or_create(
        clave=NVIDIA_FREE_MODELS_CONFIG_KEY,
        defaults={'valor': str(len(models)), 'datos': payload},
    )
    return payload
