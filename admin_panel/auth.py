import hashlib

from decouple import config
from django.conf import settings
from django.core import signing
from django.utils.crypto import constant_time_compare
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


ADMIN_SESSION_SALT = 'leadbook.admin.session.v1'
DEFAULT_ADMIN_EMAIL = 'admin@leadbook.com.ar'


def _configured_email():
    return config('ADMIN_DASH_EMAIL', default=DEFAULT_ADMIN_EMAIL).strip().lower()


def _configured_password():
    return config('ADMIN_DASH_PASSWORD', default='')


def _configured_password_hash():
    return (
        config('ADMIN_DASH_PASSWORD_SHA256', default='')
        or config('ADMIN_DASH_PASSWORD_HASH', default='')
    ).strip().lower()


def _session_ttl_seconds():
    hours = config('ADMIN_SESSION_TTL_HOURS', default=8, cast=int)
    return max(1, min(hours, 24)) * 3600


def admin_credentials_configured():
    return bool(_configured_email() and (_configured_password() or _configured_password_hash()))


def validate_admin_credentials(email, password):
    expected_email = _configured_email()
    supplied_email = str(email or '').strip().lower()
    supplied_password = str(password or '')
    if not expected_email or not supplied_email or not supplied_password:
        return False
    if not constant_time_compare(supplied_email, expected_email):
        return False

    plain_password = _configured_password()
    if plain_password and constant_time_compare(supplied_password, plain_password):
        return True

    password_hash = _configured_password_hash()
    if password_hash:
        password_hash = password_hash.removeprefix('sha256$')
        supplied_hash = hashlib.sha256(supplied_password.encode('utf-8')).hexdigest()
        return constant_time_compare(supplied_hash, password_hash)
    return False


def admin_session_user(email=None):
    admin_email = (email or _configured_email()).strip().lower()
    return {
        'id': 'admin-session',
        'email': admin_email,
        'nombre': 'LeadBook Admin',
        'is_staff': True,
        'is_admin_session': True,
    }


def make_admin_session_token(email=None):
    payload = {
        'kind': 'admin_session',
        'email': (email or _configured_email()).strip().lower(),
    }
    return signing.dumps(payload, salt=ADMIN_SESSION_SALT, compress=True)


def validate_admin_session_token(token):
    raw_token = str(token or '').strip()
    if not raw_token:
        return None
    try:
        payload = signing.loads(
            raw_token,
            salt=ADMIN_SESSION_SALT,
            max_age=_session_ttl_seconds(),
        )
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict) or payload.get('kind') != 'admin_session':
        return None
    email = str(payload.get('email') or '').strip().lower()
    if not email or not constant_time_compare(email, _configured_email()):
        return None
    return payload


def get_admin_session_payload(request):
    payload = getattr(request, '_leadbook_admin_session_payload', None)
    if payload:
        return payload
    token = request.headers.get('X-Admin-Session', '')
    payload = validate_admin_session_token(token)
    if payload:
        request._leadbook_admin_session_payload = payload
    return payload


def _admin_key_is_valid(request):
    from django.utils.crypto import constant_time_compare as compare

    admin_key = config('ADMIN_KEY', default='')
    supplied_key = request.headers.get('X-Admin-Key', '')
    return bool(
        getattr(settings, 'ALLOW_ADMIN_KEY_AUTH', False)
        and admin_key
        and supplied_key
        and compare(supplied_key, admin_key)
    )


def is_admin_request(request):
    if get_admin_session_payload(request):
        return True
    if _admin_key_is_valid(request):
        return True
    try:
        user = request.user
    except Exception:
        return False
    return bool(user and user.is_authenticated and user.is_staff)


def current_admin_identity(request):
    payload = get_admin_session_payload(request)
    if payload:
        return admin_session_user(payload.get('email'))
    try:
        user = request.user
    except Exception:
        user = None
    if user and user.is_authenticated and user.is_staff:
        return {
            'id': user.id,
            'email': user.email,
            'nombre': getattr(user, 'nombre', '') or user.email,
            'is_staff': True,
            'is_admin_session': False,
        }
    if _admin_key_is_valid(request):
        return admin_session_user()
    return None


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_session_login(request):
    if not admin_credentials_configured():
        return Response({
            'error': 'admin_credentials_not_configured',
            'message': 'Configura ADMIN_DASH_EMAIL y ADMIN_DASH_PASSWORD en el backend.',
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    email = request.data.get('email')
    password = request.data.get('password')
    if not validate_admin_credentials(email, password):
        return Response({
            'error': 'invalid_admin_credentials',
            'message': 'Credenciales admin invalidas.',
        }, status=status.HTTP_401_UNAUTHORIZED)

    admin_email = str(email or '').strip().lower()
    token = make_admin_session_token(admin_email)
    return Response({
        'access': token,
        'token_type': 'admin_session',
        'expires_in': _session_ttl_seconds(),
        'user': admin_session_user(admin_email),
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_session_profile(request):
    if not is_admin_request(request):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(current_admin_identity(request))
