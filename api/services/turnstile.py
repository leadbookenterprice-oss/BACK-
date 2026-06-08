import logging

import requests
from django.conf import settings

VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
logger = logging.getLogger(__name__)


class TurnstileError(Exception):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def is_turnstile_required():
    return bool(getattr(settings, 'TURNSTILE_REQUIRED', False))


def validate_turnstile_token(token, remoteip=None):
    if not is_turnstile_required():
        return None

    secret = (getattr(settings, 'TURNSTILE_SECRET_KEY', '') or '').strip()
    if not secret:
        logger.error('TURNSTILE_REQUIRED=True but TURNSTILE_SECRET_KEY is empty')
        raise TurnstileError(
            'turnstile_unavailable',
            'La verificacion anti-bot no esta disponible. Intenta de nuevo en unos minutos.',
            status_code=503,
        )

    token = (token or '').strip()
    if not token:
        raise TurnstileError(
            'turnstile_required',
            'Completa la verificacion anti-bot para continuar.',
            status_code=400,
        )

    payload = {'secret': secret, 'response': token}
    if remoteip:
        payload['remoteip'] = remoteip

    try:
        response = requests.post(VERIFY_URL, data=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning('Turnstile siteverify request failed: %s', exc)
        raise TurnstileError(
            'turnstile_unavailable',
            'No pudimos validar la verificacion anti-bot. Intenta de nuevo.',
            status_code=503,
        )
    except ValueError:
        logger.warning('Turnstile siteverify returned non-json response')
        raise TurnstileError(
            'turnstile_unavailable',
            'No pudimos validar la verificacion anti-bot. Intenta de nuevo.',
            status_code=503,
        )

    if not data.get('success'):
        logger.info('Turnstile validation rejected token: %s', data.get('error-codes') or [])
        raise TurnstileError(
            'turnstile_invalid',
            'La verificacion anti-bot expiro o no es valida. Intenta otra vez.',
            status_code=400,
        )

    return data
