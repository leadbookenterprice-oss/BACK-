import time

import requests


AI_ROOT_CONFIG_KEY = 'ai_root_content'
DEFAULT_AI_ROOT = {'provider': 'cerebras', 'model': 'gpt-oss-120b'}
UNUSABLE_KEY_STATUSES = {'dead', 'disabled', 'exhausted'}
PROVIDER_ALIASES = {
    'cerebras': 'cerebras',
    'groq': 'groq',
    'gemini': 'gemini',
    'google': 'gemini',
    'google_gemini': 'gemini',
    'nvidia': 'nvidia',
    'nvidia_nim': 'nvidia',
    'nim': 'nvidia',
}

AI_ROOT_CATALOG = [
    {
        'provider': 'cerebras',
        'label': 'Cerebras',
        'adapter': 'cerebras',
        'enabled': True,
        'default_model': 'gpt-oss-120b',
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
        'default_model': 'llama-3.1-8b-instant',
        'models': [
            {'model': 'llama-3.3-70b-versatile', 'label': 'Llama 3.3 70B Versatile'},
            {'model': 'llama-3.1-8b-instant', 'label': 'Llama 3.1 8B Instant'},
        ],
    },
    {
        'provider': 'gemini',
        'label': 'Gemini',
        'adapter': 'gemini',
        'enabled': True,
        'default_model': 'gemini-2.5-flash-lite',
        'models': [
            {'model': 'gemini-2.5-flash-lite', 'label': 'Gemini 2.5 Flash Lite'},
        ],
    },
    {
        'provider': 'nvidia',
        'label': 'NVIDIA',
        'adapter': 'nvidia',
        'enabled': True,
        'default_model': 'meta/llama-3.1-70b-instruct',
        'models': [
            {'model': 'meta/llama-3.1-70b-instruct', 'label': 'Llama 3.1 70B Instruct'},
        ],
    },
]


def _normalize(value):
    return str(value or '').strip().lower()


def normalize_provider(value):
    return PROVIDER_ALIASES.get(_normalize(value), _normalize(value))


def _catalog_item(provider):
    provider = normalize_provider(provider)
    return next((item for item in AI_ROOT_CATALOG if item['provider'] == provider), None)


def _catalog_model(item, model):
    model = str(model or '').strip()
    return next((entry for entry in item.get('models', []) if entry.get('model') == model), None)


def _active_key_queryset(provider):
    from api.models import APIKey

    provider = normalize_provider(provider)
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
    provider = normalize_provider(data.get('provider') or (cfg.valor.split(':', 1)[0] if cfg and cfg.valor and ':' in cfg.valor else None))
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
    provider = normalize_provider(provider)
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

    provider = normalize_provider(provider)
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


def get_provider_default_model(provider):
    item = _catalog_item(provider)
    if not item:
        return ''
    default_model = item.get('default_model')
    if default_model:
        return default_model
    models = item.get('models') or []
    return str((models[0] or {}).get('model') or '').strip() if models else ''


def build_public_ai_providers_payload():
    root_payload = build_ai_root_payload()
    public_providers = []
    for provider in root_payload.get('providers', []):
        if not provider.get('selectable'):
            continue
        public_providers.append({
            'provider': provider['provider'],
            'label': provider.get('label') or provider['provider'].title(),
            'selectable': True,
            'status': provider.get('status') or 'Activo',
        })

    current_provider = normalize_provider((root_payload.get('current') or {}).get('provider'))
    if not any(item['provider'] == current_provider for item in public_providers):
        current_provider = public_providers[0]['provider'] if public_providers else ''

    return {
        'current': current_provider,
        'providers': public_providers,
    }


def provider_is_available(provider):
    provider = normalize_provider(provider)
    return any(
        item.get('provider') == provider and item.get('selectable')
        for item in build_ai_root_payload().get('providers', [])
    )


def resolve_requested_ai_provider(data):
    if not isinstance(data, dict):
        return ''
    raw = (
        data.get('ai_provider')
        or data.get('aiProvider')
        or data.get('provider')
        or data.get('generation_provider')
        or data.get('generationProvider')
        or data.get('ai_root_provider')
        or data.get('aiRootProvider')
    )
    if not raw:
        generation_model = str(data.get('generation_model') or data.get('generationModel') or '').strip()
        if ':' in generation_model:
            raw = generation_model.split(':', 1)[0]
    return normalize_provider(raw)


def resolve_available_ai_provider(data=None):
    requested = resolve_requested_ai_provider(data or {})
    if requested and provider_is_available(requested):
        return requested

    root_payload = build_public_ai_providers_payload()
    current = root_payload.get('current')
    if current:
        return current
    return ''


def call_configured_ai(prompt, agente=None, **kwargs):
    call_kwargs = dict(kwargs)
    requested_provider = resolve_requested_ai_provider(call_kwargs)
    if requested_provider and provider_is_available(requested_provider):
        provider = requested_provider
        model = get_provider_default_model(provider)
    else:
        root = get_ai_root_config()
        provider = root['provider']
        model = root['model']

    call_kwargs.pop('model', None)
    call_kwargs.pop('ai_provider', None)
    call_kwargs.pop('aiProvider', None)
    call_kwargs.pop('generation_provider', None)
    call_kwargs.pop('generationProvider', None)
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
    if provider == 'gemini':
        from api.ai_services import call_gemini_api

        return call_gemini_api(prompt, agente=agente, model=model, **call_kwargs)
    if provider == 'nvidia':
        from api.ai_services import call_nim_model

        system_prompt = str(call_kwargs.get('system_prompt') or '').strip()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        return call_nim_model(full_prompt, model_id=model)

    from api.ai_services import APIKeyUnavailableError
    raise APIKeyUnavailableError(
        'El root IA configurado no tiene adapter disponible.',
        provider=provider,
        scope='router',
    )


def _extract_chat_text(data):
    choices = data.get('choices') if isinstance(data, dict) else None
    if not choices:
        candidates = data.get('candidates') if isinstance(data, dict) else None
        parts = (((candidates or [{}])[0].get('content') or {}).get('parts') or [])
        return str((parts[0] or {}).get('text') or '').strip() if parts else ''
    message = (choices[0] or {}).get('message') or {}
    return str(message.get('content') or '').strip()


def test_ai_root(provider=None, model=None, prompt=None):
    root = {'provider': normalize_provider(provider), 'model': str(model or '').strip()}
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
    if root['provider'] == 'gemini':
        endpoint = f'https://generativelanguage.googleapis.com/v1beta/models/{root["model"]}:generateContent?key={key_obj.api_key}'
        headers = {'Content-Type': 'application/json'}
        body = {
            'contents': [{'parts': [{'text': test_prompt}]}],
            'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 80},
        }
    else:
        body = {
            'model': root['model'],
            'messages': [{'role': 'user', 'content': test_prompt}],
            'temperature': 0.2,
        }
        if root['provider'] in {'groq', 'nvidia'}:
            body['max_tokens'] = 80
        else:
            body['max_completion_tokens'] = 80
        endpoint = {
            'cerebras': 'https://api.cerebras.ai/v1/chat/completions',
            'groq': 'https://api.groq.com/openai/v1/chat/completions',
            'nvidia': 'https://integrate.api.nvidia.com/v1/chat/completions',
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
