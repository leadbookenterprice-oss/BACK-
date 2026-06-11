from datetime import timedelta
from functools import lru_cache

import yaml
from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone


AI_LIMITS_CONFIG_PATH = settings.BASE_DIR / 'api' / 'config' / 'ai_limits.yml'


class ProviderLimitExceeded(Exception):
    def __init__(
        self,
        message,
        *,
        provider='generic',
        model='',
        scope='model',
        quota_state='soft_rate_limited',
        retry_after_seconds=None,
        limit_key='',
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.scope = scope
        self.quota_state = quota_state
        self.retry_after_seconds = retry_after_seconds
        self.limit_key = limit_key


def _safe_int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=1)
def load_ai_limits_config():
    try:
        with open(AI_LIMITS_CONFIG_PATH, 'r', encoding='utf-8') as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    providers = data.get('providers')
    if not isinstance(providers, dict):
        data['providers'] = {}
    return data


def get_provider_limit_config(provider):
    provider_key = str(provider or '').strip().lower()
    providers = load_ai_limits_config().get('providers') or {}
    config = providers.get(provider_key) or {}
    return config if isinstance(config, dict) else {}


def get_model_limit_config(provider, model):
    provider_config = get_provider_limit_config(provider)
    model_key = str(model or '').strip()
    models = provider_config.get('models') or {}
    model_config = models.get(model_key) or {}
    if not isinstance(model_config, dict):
        model_config = {}
    default_limits = provider_config.get('default_limits') or {}
    limits = dict(default_limits if isinstance(default_limits, dict) else {})
    limits.update(model_config.get('limits') or {})
    return {
        **model_config,
        'limits': limits,
    }


def build_limits_snapshot(provider, model, *, estimated_tokens=0):
    config = load_ai_limits_config()
    provider_config = get_provider_limit_config(provider)
    model_config = get_model_limit_config(provider, model)
    return {
        'config_version': config.get('version'),
        'config_updated_at': config.get('updated_at'),
        'provider': str(provider or '').strip().lower(),
        'model': str(model or '').strip(),
        'estimated_tokens': max(_safe_int(estimated_tokens, 0), 0),
        'limits': model_config.get('limits') or {},
        'label': model_config.get('label') or '',
        'tier': model_config.get('tier') or '',
        'role': model_config.get('role') or '',
        'source': config.get('source') or {},
        'observed_at': timezone.now().isoformat(),
    }


def _window_start(window, now):
    if window == 'minute':
        return now - timedelta(minutes=1)
    if window == 'hour':
        return now - timedelta(hours=1)
    if window == 'day':
        return now - timedelta(days=1)
    return now


def _cerebras_usage_for_window(model, window, now):
    from api.models import CerebrasUsageLog

    queryset = CerebrasUsageLog.objects.filter(
        creado_en__gte=_window_start(window, now),
    )
    if model:
        queryset = queryset.filter(model=model)
    aggregate = queryset.aggregate(
        requests=Count('id'),
        tokens=Sum('charged_tokens'),
        estimated=Sum('estimated_tokens'),
    )
    return {
        'requests': _safe_int(aggregate.get('requests'), 0),
        'tokens': max(
            _safe_int(aggregate.get('tokens'), 0),
            _safe_int(aggregate.get('estimated'), 0),
        ),
    }


def _raise_limit(provider, model, key, retry_after_seconds, message):
    raise ProviderLimitExceeded(
        message,
        provider=provider,
        model=model,
        scope='model',
        quota_state='soft_rate_limited',
        retry_after_seconds=retry_after_seconds,
        limit_key=key,
    )


def preflight_ai_request(provider, model, *, estimated_tokens=0, now=None):
    provider_key = str(provider or '').strip().lower()
    model_key = str(model or '').strip()
    estimated_tokens = max(_safe_int(estimated_tokens, 0), 0)
    model_config = get_model_limit_config(provider_key, model_key)
    limits = model_config.get('limits') or {}
    if not limits:
        return build_limits_snapshot(provider_key, model_key, estimated_tokens=estimated_tokens)

    for key in ('tokens_per_minute', 'tokens_per_hour', 'tokens_per_day'):
        limit = _safe_int(limits.get(key), 0)
        if limit > 0 and estimated_tokens > limit:
            raise ProviderLimitExceeded(
                f'La request estimada ({estimated_tokens} tokens) supera {key}={limit} para {provider_key}/{model_key}.',
                provider=provider_key,
                model=model_key,
                scope='request',
                quota_state='hard_exhausted',
                retry_after_seconds=None,
                limit_key=key,
            )

    if provider_key != 'cerebras':
        return build_limits_snapshot(provider_key, model_key, estimated_tokens=estimated_tokens)

    now = now or timezone.now()
    windows = (
        ('minute', 60),
        ('hour', 3600),
        ('day', 24 * 3600),
    )
    for window, retry_after in windows:
        usage = _cerebras_usage_for_window(model_key, window, now)
        request_limit = _safe_int(limits.get(f'requests_per_{window}'), 0)
        token_limit = _safe_int(limits.get(f'tokens_per_{window}'), 0)
        if request_limit > 0 and usage['requests'] + 1 > request_limit:
            _raise_limit(
                provider_key,
                model_key,
                f'requests_per_{window}',
                retry_after,
                f'Cerebras {model_key} alcanzo el limite local de requests por {window}.',
            )
        if token_limit > 0 and usage['tokens'] + estimated_tokens > token_limit:
            _raise_limit(
                provider_key,
                model_key,
                f'tokens_per_{window}',
                retry_after,
                f'Cerebras {model_key} alcanzo el limite local de tokens por {window}.',
            )

    return build_limits_snapshot(provider_key, model_key, estimated_tokens=estimated_tokens)
