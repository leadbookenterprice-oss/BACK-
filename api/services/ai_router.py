import time

import requests


AI_ROOT_CONFIG_KEY = 'ai_root_content'
DEFAULT_AI_ROOT = {'provider': 'cerebras', 'model': 'gpt-oss-120b'}
UNUSABLE_KEY_STATUSES = {'dead', 'disabled', 'exhausted'}

AI_ROOT_CATALOG = [
    {
        'provider': 'cerebras',
        'label': 'Cerebras',
        'adapter': 'cerebras',
        'enabled': True,
        'models': [
            {'model': 'gpt-oss-120b', 'label': 'GPT OSS 120B'},
            {'model': 'zai-glm-4.7', 'label': 'ZAI GLM 4.7'},
        ],
    },
    {
        'provider': 'groq',
        'label': 'Groq',
        'adapter': 'groq',
        'enabled': True,
        'models': [
            {'model': 'llama-3.3-70b-versatile', 'label': 'Llama 3.3 70B Versatile'},
            {'model': 'llama-3.1-8b-instant', 'label': 'Llama 3.1 8B Instant'},
        ],
    },
    {
        'provider': 'gemini',
        'label': 'Gemini',
        'adapter': 'gemini',
        'enabled': False,
        'disabled_reason': 'Gemini esta deshabilitado como root de contenido.',
        'models': [
            {'model': 'gemini-2.5-flash-lite', 'label': 'Gemini 2.5 Flash Lite'},
        ],
    },
]


def _normalize(value):
    return str(value or '').strip().lower()


def _catalog_item(provider):
    provider = _normalize(provider)
    return next((item for item in AI_ROOT_CATALOG if item['provider'] == provider), None)


def _catalog_model(item, model):
    model = str(model or '').strip()
    return next((entry for entry in item.get('models', []) if entry.get('model') == model), None)


def _active_key_queryset(provider):
    from api.models import APIKey

    return (
        APIKey.objects
        .filter(servicio__nombre__iexact=provider)
        .exclude(status__in=UNUSABLE_KEY_STATUSES)
        .order_by('id')
    )


def _active_key_count(provider):
    try:
        return _active_key_queryset(provider).count()
    except Exception:
        return 0


def _first_active_key(provider):
    return _active_key_queryset(provider).first()


def get_ai_root_config():
    from api.models import ConfiguracionSistema

    cfg = ConfiguracionSistema.objects.filter(clave=AI_ROOT_CONFIG_KEY).first()
    data = cfg.datos if cfg and isinstance(cfg.datos, dict) else {}
    provider = _normalize(data.get('provider') or (cfg.valor.split(':', 1)[0] if cfg and cfg.valor and ':' in cfg.valor else None))
    model = str(data.get('model') or (cfg.valor.split(':', 1)[1] if cfg and cfg.valor and ':' in cfg.valor else '')).strip()

    item = _catalog_item(provider)
    if not item or not _catalog_model(item, model):
        return dict(DEFAULT_AI_ROOT)
    return {'provider': provider, 'model': model}


def _model_payload(provider_item, model_entry, active_keys):
    if not provider_item.get('enabled'):
        reason = provider_item.get('disabled_reason') or 'Adapter no disponible'
        return {
            **model_entry,
            'selectable': False,
            'status': 'Adapter no disponible',
            'reason': reason,
        }
    if active_keys <= 0:
        return {
            **model_entry,
            'selectable': False,
            'status': 'Sin keys',
            'reason': 'No hay keys activas para este proveedor.',
        }
    return {
        **model_entry,
        'selectable': True,
        'status': 'Activo',
        'reason': '',
    }


def build_ai_root_payload():
    current = get_ai_root_config()
    providers = []
    for item in AI_ROOT_CATALOG:
        active_keys = _active_key_count(item['provider'])
        models = [_model_payload(item, model, active_keys) for model in item.get('models', [])]
        selectable = any(model.get('selectable') for model in models)
        if not item.get('enabled'):
            status = 'Adapter no disponible'
            reason = item.get('disabled_reason') or 'Adapter no disponible'
        elif active_keys <= 0:
            status = 'Sin keys'
            reason = 'No hay keys activas para este proveedor.'
        else:
            status = 'Activo'
            reason = ''
        providers.append({
            'provider': item['provider'],
            'label': item['label'],
            'adapter': item['adapter'],
            'enabled': bool(item.get('enabled')),
            'active_keys': active_keys,
            'selectable': selectable,
            'status': status,
            'reason': reason,
            'models': models,
        })

    current_provider = next((provider for provider in providers if provider['provider'] == current['provider']), None)
    current_model = None
    if current_provider:
        current_model = next((model for model in current_provider['models'] if model['model'] == current['model']), None)

    return {
        'current': {
            **current,
            'available': bool(current_model and current_model.get('selectable')),
            'status': (current_model or {}).get('status') or 'Sin configurar',
            'reason': (current_model or {}).get('reason') or '',
        },
        'providers': providers,
        'default': dict(DEFAULT_AI_ROOT),
    }


def validate_ai_root(provider, model):
    provider = _normalize(provider)
    model = str(model or '').strip()
    payload = build_ai_root_payload()
    provider_payload = next((item for item in payload['providers'] if item['provider'] == provider), None)
    if not provider_payload:
        return False, 'Proveedor no soportado como root IA.', payload
    model_payload = next((item for item in provider_payload.get('models', []) if item.get('model') == model), None)
    if not model_payload:
        return False, 'Modelo no soportado para este proveedor.', payload
    if not model_payload.get('selectable'):
        return False, model_payload.get('reason') or provider_payload.get('reason') or 'Root IA no disponible.', payload
    return True, '', payload


def save_ai_root_config(provider, model, updated_by='admin'):
    from api.models import ConfiguracionSistema

    ok, message, _payload = validate_ai_root(provider, model)
    if not ok:
        raise ValueError(message)

    provider = _normalize(provider)
    model = str(model or '').strip()
    ConfiguracionSistema.objects.update_or_create(
        clave=AI_ROOT_CONFIG_KEY,
        defaults={
            'valor': f'{provider}:{model}',
            'datos': {
                'provider': provider,
                'model': model,
                'updated_by': str(updated_by or 'admin'),
            },
        },
    )
    return {'provider': provider, 'model': model}


def call_configured_ai(prompt, agente=None, **kwargs):
    root = get_ai_root_config()
    provider = root['provider']
    model = root['model']
    call_kwargs = dict(kwargs)
    call_kwargs.pop('model', None)
    metadata = dict(call_kwargs.get('metadata') or {})
    metadata.update({'ai_root_provider': provider, 'ai_root_model': model})
    call_kwargs['metadata'] = metadata
    call_kwargs['allow_model_fallback'] = False

    if provider == 'cerebras':
        from api.ai_services import call_cerebras_api

        return call_cerebras_api(prompt, agente=agente, model=model, **call_kwargs)
    if provider == 'groq':
        from api.ai_services import call_groq_api

        return call_groq_api(prompt, model=model, **call_kwargs)

    from api.ai_services import APIKeyUnavailableError
    raise APIKeyUnavailableError(
        'El root IA configurado no tiene adapter disponible.',
        provider=provider,
        scope='router',
    )


def _extract_chat_text(data):
    choices = data.get('choices') if isinstance(data, dict) else None
    if not choices:
        return ''
    message = (choices[0] or {}).get('message') or {}
    return str(message.get('content') or '').strip()


def test_ai_root(provider=None, model=None, prompt=None):
    root = {'provider': _normalize(provider), 'model': str(model or '').strip()}
    if not root['provider'] or not root['model']:
        root = get_ai_root_config()

    ok, message, payload = validate_ai_root(root['provider'], root['model'])
    if not ok:
        raise ValueError(message)

    key_obj = _first_active_key(root['provider'])
    if not key_obj:
        raise ValueError('No hay key activa para testear este root IA.')

    test_prompt = prompt or 'Responde en una frase corta: LeadBook IA operativa.'
    headers = {
        'Authorization': f'Bearer {key_obj.api_key}',
        'Content-Type': 'application/json',
    }
    body = {
        'model': root['model'],
        'messages': [{'role': 'user', 'content': test_prompt}],
        'temperature': 0.2,
    }
    if root['provider'] == 'groq':
        body['max_tokens'] = 80
    else:
        body['max_completion_tokens'] = 80
    endpoint = {
        'cerebras': 'https://api.cerebras.ai/v1/chat/completions',
        'groq': 'https://api.groq.com/openai/v1/chat/completions',
    }.get(root['provider'])
    if not endpoint:
        raise ValueError('Adapter no disponible para test.')

    started_at = time.time()
    response = requests.post(endpoint, json=body, headers=headers, timeout=30)
    elapsed_ms = int((time.time() - started_at) * 1000)
    if response.status_code != 200:
        raise RuntimeError(f'{root["provider"]} test fallo ({response.status_code}): {response.text[:300]}')

    data = response.json() if response.content else {}
    text = _extract_chat_text(data)
    return {
        'status': 'ok',
        'provider': root['provider'],
        'model': root['model'],
        'api_key_id': key_obj.id,
        'active_keys': next((item for item in payload['providers'] if item['provider'] == root['provider']), {}).get('active_keys', 0),
        'elapsed_ms': elapsed_ms,
        'response_preview': text[:300],
    }
