import logging

import requests
from django.utils import timezone


logger = logging.getLogger(__name__)

CEREBRAS_MODELS_URL = 'https://api.cerebras.ai/v1/models'
CEREBRAS_DEFAULT_MODELS_CASCADE = ['gpt-oss-120b', 'zai-glm-4.7']
CEREBRAS_MODEL_LABELS = {
    'gpt-oss-120b': 'GPT OSS 120B',
    'zai-glm-4.7': 'ZAI GLM 4.7',
}


class CerebrasModelSyncError(Exception):
    pass


def normalize_cerebras_models(payload):
    if not isinstance(payload, dict):
        return []
    raw_models = payload.get('data')
    if not isinstance(raw_models, list):
        raw_models = payload.get('models')
    if not isinstance(raw_models, list):
        return []

    discovered = []
    seen = set()
    for item in raw_models:
        if isinstance(item, dict):
            model_id = item.get('id') or item.get('model') or item.get('name')
        else:
            model_id = item
        model_id = str(model_id or '').strip()
        if not model_id or model_id in seen:
            continue
        discovered.append(model_id)
        seen.add(model_id)

    known = [model for model in CEREBRAS_DEFAULT_MODELS_CASCADE if model in seen]
    unknown = [model for model in discovered if model not in CEREBRAS_DEFAULT_MODELS_CASCADE]
    return known + unknown


def cerebras_model_entries(model_ids):
    return [
        {
            'model': model_id,
            'label': CEREBRAS_MODEL_LABELS.get(model_id) or model_id,
        }
        for model_id in model_ids
    ]


def fetch_cerebras_models(api_key, *, timeout=12):
    response = requests.get(
        CEREBRAS_MODELS_URL,
        headers={'Authorization': f'Bearer {api_key}'},
        timeout=timeout,
    )
    if not (200 <= response.status_code < 300):
        detail = str(getattr(response, 'text', '') or '')[:500]
        raise CerebrasModelSyncError(f'Cerebras models HTTP {response.status_code}: {detail}')
    try:
        payload = response.json()
    except ValueError as exc:
        raise CerebrasModelSyncError('Cerebras models response is not valid JSON') from exc
    models = normalize_cerebras_models(payload)
    if not models:
        raise CerebrasModelSyncError('Cerebras models response did not include model ids')
    return models


def _clean_supported_models(value):
    if not isinstance(value, list):
        return []
    cleaned = []
    seen = set()
    for item in value:
        model_id = str(item or '').strip()
        if not model_id or model_id in seen:
            continue
        cleaned.append(model_id)
        seen.add(model_id)
    known = [model for model in CEREBRAS_DEFAULT_MODELS_CASCADE if model in seen]
    unknown = [model for model in cleaned if model not in CEREBRAS_DEFAULT_MODELS_CASCADE]
    return known + unknown


def sync_cerebras_key_models(key_obj, *, timeout=12):
    if not key_obj or not getattr(key_obj, 'api_key', None):
        raise CerebrasModelSyncError('Missing Cerebras API key')
    try:
        models = fetch_cerebras_models(key_obj.api_key, timeout=timeout)
    except Exception as exc:
        error_message = str(exc)[:1000]
        key_obj.models_last_error = error_message
        key_obj.save(update_fields=['models_last_error', 'updated_at'])
        raise

    return store_cerebras_key_models(key_obj, models)


def store_cerebras_key_models(key_obj, models):
    models = _clean_supported_models(models)
    if not models:
        raise CerebrasModelSyncError('Cerebras models response did not include model ids')
    now = timezone.now()
    key_obj.supported_models = models
    key_obj.models_last_synced_at = now
    key_obj.models_last_error = ''
    key_obj.save(update_fields=['supported_models', 'models_last_synced_at', 'models_last_error', 'updated_at'])
    return models


def get_cerebras_key_model_cascade(key_obj, *, sync_if_missing=True):
    models = _clean_supported_models(getattr(key_obj, 'supported_models', None))
    if models:
        return models
    if sync_if_missing and getattr(key_obj, 'pk', None):
        try:
            return sync_cerebras_key_models(key_obj)
        except Exception as exc:
            logger.warning(
                '[CEREBRAS] No se pudo sincronizar modelos para key_id=%s: %s',
                getattr(key_obj, 'pk', None),
                exc,
            )
    return list(CEREBRAS_DEFAULT_MODELS_CASCADE)


def get_active_cerebras_model_entries():
    try:
        from api.models import APIKey

        keys = (
            APIKey.objects
            .filter(servicio__nombre__iexact='cerebras')
            .exclude(status__in=['dead', 'disabled', 'exhausted'])
        )
        ordered = []
        seen = set()
        for key in keys:
            for model_id in _clean_supported_models(key.supported_models):
                if model_id not in seen:
                    ordered.append(model_id)
                    seen.add(model_id)
        if ordered:
            return cerebras_model_entries(ordered)
    except Exception:
        logger.exception('[CEREBRAS] No se pudo resolver catalogo de modelos activos')
    return cerebras_model_entries(CEREBRAS_DEFAULT_MODELS_CASCADE)
