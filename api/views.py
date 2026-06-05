from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models import Sum
from django.db import transaction
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
import base64
from datetime import timedelta
import html as html_lib
import unicodedata
from functools import wraps
from api.services.almacenamiento import AlmacenamientoCloudinary
import logging

logger = logging.getLogger(__name__)

from .models import (
    GeneratedAsset, Listado, OTPCode, ComercialAgentProfile,
    AgentMediaAsset, UserContentPreference,
    BrandTemplate, BrandTemplateRevision, default_template_tokens,
    AgentAssociation, CRMClient, SocialPublicationLog,
    TerminosCondiciones, PoliticaPrivacidad, UsageLog, AccessCode, AdminAlert
)
from .serializers import (
    RegisterSerializer, GeneratedAssetSerializer,
    TerminosCondicionesSerializer, PoliticaPrivacidadSerializer,
    ComercialAgentProfileSerializer, BrandTemplateSerializer,
    BrandTemplateRevisionSerializer, AgentMediaAssetSerializer,
    UserContentPreferenceSerializer, CRMClientSerializer,
)
from .tasks import run_asset_generation
from .ai_services import (
    APIKeyUnavailableError,
    ElevenLabsQuotaExhaustedError,
    ElevenLabsRateLimitedError,
    GeminiQuotaExhaustedError,
    GeminiRateLimitedError,
    normalize_elevenlabs_voice_choice,
    smart_call,
)
from .utils import crear_notificacion
from django.template.loader import render_to_string
from .services.render_engine import render_html_to_image
from .plan_utils import (
    puede_generar,
    incrementar_uso,
    registrar_uso,
    get_free_trial_status,
    get_plan_block_payload,
    get_pro_feature_block_payload,
)
from .services.ads_studio import (
    build_ads_result,
    build_meta_ads_prompt,
    normalize_ads_request,
    parse_meta_ads_response,
)
from .services.listing_extractor import ExtractorError, extract_listing_from_url
from .services.content_generation import (
    CONTENT_PACK_STEPS,
    extract_generation_run_id,
    extract_generation_step,
    mark_generation_step,
    mark_generation_step_from_exception,
    serialize_generation_run,
    start_or_resume_generation_run,
    get_generation_run_for_user,
)


def require_active_plan(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        block_payload = get_plan_block_payload(request.user)
        if block_payload:
            return Response(block_payload, status=status.HTTP_402_PAYMENT_REQUIRED)
        return view_func(request, *args, **kwargs)
    return wrapper


def active_plan_block_response(request):
    block_payload = get_plan_block_payload(request.user)
    if block_payload:
        return Response(block_payload, status=status.HTTP_402_PAYMENT_REQUIRED)
    return None


def _is_data_url(value):
    return isinstance(value, str) and value.strip().lower().startswith('data:')


def _allow_legacy_base64_media():
    return config('ALLOW_LEGACY_BASE64_MEDIA', default=False, cast=bool)


def _is_hard_quota_error(exc):
    return str(getattr(exc, 'quota_state', '')).strip().lower() == 'hard_exhausted'


def _notify_quota_exhausted(user, exc, quota_state, provider, scope, source=None):
    if quota_state != 'hard_exhausted':
        return
    if not user or not getattr(user, 'is_authenticated', False):
        return

    try:
        from .models import Notificacion
        cutoff = timezone.now() - timedelta(minutes=30)
        already_notified = Notificacion.objects.filter(
            usuario=user,
            tipo='quota_agotada',
            creada_en__gte=cutoff,
        ).exists()
        if already_notified:
            return

        crear_notificacion(
            user,
            'quota_agotada',
            'Alcanzaste el 100% de tu uso de IA',
            'Tus creditos de IA se agotaron por ahora. El reset es automatico; tambien podes comprar mas usos si necesitas seguir generando.',
        )
        logger.info(
            '[QUOTA] Notificacion quota_agotada user_id=%s provider=%s scope=%s source=%s exc=%s',
            getattr(user, 'id', None),
            provider,
            scope,
            source or 'unknown',
            exc.__class__.__name__,
        )
    except Exception:
        logger.exception('[QUOTA] No se pudo crear notificacion de cuota agotada')


def _quota_error_response(exc, fallback_status=status.HTTP_429_TOO_MANY_REQUESTS, user=None, source=None):
    quota_state = str(getattr(exc, 'quota_state', '') or 'hard_exhausted').strip().lower()
    provider = str(getattr(exc, 'provider', '') or 'generic').strip().lower()
    scope = str(getattr(exc, 'scope', '') or 'provider').strip().lower()
    retry_after_seconds = getattr(exc, 'retry_after_seconds', None)

    error_code = 'cuota_ia_agotada' if quota_state == 'hard_exhausted' else 'ia_rate_limited'
    payload = {
        'error': error_code,
        'mensaje': str(exc),
        'quota_state': quota_state,
        'provider': provider,
        'scope': scope,
        'retry_after_seconds': retry_after_seconds,
    }

    _notify_quota_exhausted(user, exc, quota_state, provider, scope, source=source)

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    if isinstance(exc, APIKeyUnavailableError):
        status_code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if quota_state == 'soft_rate_limited'
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
    elif fallback_status:
        status_code = fallback_status
    return Response(payload, status=status_code)


def _generation_payload_context(data, fallback_step):
    run_id = extract_generation_run_id(data)
    step_name = extract_generation_step(data, fallback_step) or fallback_step
    return run_id, step_name


def _mark_generation_running(data, fallback_step):
    run_id, step_name = _generation_payload_context(data, fallback_step)
    mark_generation_step(run_id, step_name, 'running')
    return run_id, step_name


def _mark_generation_done(run_id, step_name, result=None):
    mark_generation_step(run_id, step_name, 'done', result=result or {})


def _mark_generation_failed(run_id, step_name, exc_or_message, *, error_code='step_failed'):
    if not run_id or step_name not in CONTENT_PACK_STEPS:
        return
    if isinstance(exc_or_message, (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError)):
        mark_generation_step_from_exception(run_id, step_name, exc_or_message)
        return
    mark_generation_step(
        run_id,
        step_name,
        'failed',
        error_code=error_code,
        error_message=str(exc_or_message or ''),
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def start_content_generation_pack(request, pk):
    listado = get_object_or_404(Listado, pk=pk, agente=request.user)
    selected_template = (
        request.data.get('template_id')
        or request.data.get('brand_template_id')
        or request.data.get('selectedTemplateId')
        if isinstance(request.data, dict)
        else None
    )
    metadata = {
        'source': 'frontend-new',
        'selected_template': str(selected_template or ''),
        'video_included': False,
    }
    run, reservation = start_or_resume_generation_run(request.user, listado, metadata=metadata)
    payload = {
        'success': run.status not in {'waiting_slot', 'failed'},
        'run': serialize_generation_run(run),
        'retry_after_seconds': reservation.get('retry_after_seconds'),
        'quota_state': getattr(reservation.get('error'), 'quota_state', None),
        'scope': getattr(reservation.get('error'), 'scope', None),
        'provider': 'cerebras',
    }
    if reservation.get('error'):
        http_status = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if getattr(reservation['error'], 'quota_state', '') == 'soft_rate_limited'
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        payload['mensaje'] = str(reservation['error'])
        payload['error'] = 'ia_rate_limited' if http_status == status.HTTP_429_TOO_MANY_REQUESTS else 'api_key_unavailable'
        return Response(payload, status=http_status)
    return Response(payload, status=status.HTTP_201_CREATED if reservation.get('created') else status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def content_generation_run_detail(request, run_id):
    run = get_generation_run_for_user(request.user, run_id)
    if not run:
        return Response({'error': 'generation_run_not_found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({'success': True, 'run': serialize_generation_run(run)}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def retry_content_generation_run(request, run_id):
    run = get_generation_run_for_user(request.user, run_id)
    if not run:
        return Response({'error': 'generation_run_not_found'}, status=status.HTTP_404_NOT_FOUND)
    listado = run.listado
    run, reservation = start_or_resume_generation_run(request.user, listado, metadata={'retry_run_id': run_id})
    if reservation.get('error'):
        return Response({
            'success': False,
            'run': serialize_generation_run(run),
            'error': 'ia_rate_limited',
            'mensaje': str(reservation['error']),
            'provider': 'cerebras',
            'scope': getattr(reservation['error'], 'scope', None),
            'quota_state': getattr(reservation['error'], 'quota_state', None),
            'retry_after_seconds': reservation.get('retry_after_seconds'),
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    return Response({'success': True, 'run': serialize_generation_run(run)}, status=status.HTTP_200_OK)


def _build_generation_run_payload(run, incoming=None, step_name=''):
    listado = run.listado
    payload = {}
    if isinstance(listado.datos_extra, dict):
        payload.update(listado.datos_extra)
    if isinstance(incoming, dict):
        nested = incoming.get('payload') if isinstance(incoming.get('payload'), dict) else {}
        payload.update(nested)
        payload.update({key: value for key, value in incoming.items() if key != 'payload'})

    payload.update({
        'listado_id': listado.id,
        'listadoId': listado.id,
        'titulo': payload.get('titulo') or listado.titulo,
        'tipoPropiedad': payload.get('tipoPropiedad') or listado.tipo_propiedad,
        'tipo_propiedad': payload.get('tipo_propiedad') or listado.tipo_propiedad,
        'operacion': payload.get('operacion') or listado.operacion,
        'ciudad': payload.get('ciudad') or listado.ciudad,
        'barrio': payload.get('barrio') or listado.barrio or '',
        'precio': payload.get('precio') or listado.precio,
        'moneda': payload.get('moneda') or listado.moneda,
        'generation_run_id': run.id,
        'generationRunId': run.id,
        'generation_step': step_name,
        'generationStep': step_name,
    })
    if listado.metros_cuadrados and not payload.get('superficieTotal'):
        payload['superficieTotal'] = listado.metros_cuadrados
    selected_template = (run.metadata or {}).get('selected_template')
    if selected_template and not payload.get('template_id'):
        payload['template_id'] = selected_template
        payload['selectedTemplateId'] = selected_template
    return payload


def _validate_generated_pdf_html(html_string, context):
    html_text = str(html_string or '')
    lower_html = html_text.lower()
    errors = []
    if '<html' not in lower_html or '</html>' not in lower_html:
        errors.append('html_document_missing')
    web_nav_terms = ('<nav', 'inicio', 'propiedades', 'blog', 'menu')
    if any(term in lower_html for term in web_nav_terms) and 'leadbook-pdf' not in lower_html:
        errors.append('looks_like_web_page')

    description = str(context.get('descripcion') or '').strip()
    if description and not any(term in lower_html for term in ('descripcion', 'descripción', 'description')):
        errors.append('description_section_missing')

    amenities = context.get('amenidades')
    if amenities and isinstance(amenities, (list, tuple)) and not any(term in lower_html for term in ('amenidad', 'amenities', 'comodidad')):
        errors.append('amenities_section_missing')

    gallery = context.get('fotos_recorrido') or []
    if gallery and '<img' not in lower_html:
        errors.append('gallery_images_missing')
    return errors


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def advance_content_generation_run(request, run_id):
    run = get_generation_run_for_user(request.user, run_id)
    if not run:
        return Response({'error': 'generation_run_not_found'}, status=status.HTTP_404_NOT_FOUND)

    if run.status in {'done', 'cancelled'}:
        return Response({'success': True, 'run': serialize_generation_run(run), 'already_complete': True})

    if run.status in {'pending', 'waiting_slot'} or not run.api_key_id:
        run, reservation = start_or_resume_generation_run(
            request.user,
            run.listado,
            metadata={'advance_run_id': run.id, **(run.metadata or {})},
        )
        if reservation.get('error'):
            return Response({
                'success': False,
                'run': serialize_generation_run(run),
                'error': 'ia_rate_limited',
                'mensaje': str(reservation['error']),
                'provider': 'cerebras',
                'scope': getattr(reservation['error'], 'scope', None),
                'quota_state': getattr(reservation['error'], 'quota_state', None),
                'retry_after_seconds': reservation.get('retry_after_seconds'),
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

    steps = list(run.steps.all().order_by('order', 'id'))
    next_step = next((step for step in steps if step.status != 'done'), None)
    if not next_step:
        mark_generation_step(run.id, CONTENT_PACK_STEPS[-1], 'done')
        refreshed = get_generation_run_for_user(request.user, run.id)
        return Response({'success': True, 'run': serialize_generation_run(refreshed), 'already_complete': True})

    if next_step.status in {'running', 'uploading'}:
        return Response({
            'success': False,
            'error': 'generation_step_in_progress',
            'step': next_step.step,
            'run': serialize_generation_run(run),
        }, status=status.HTTP_409_CONFLICT)

    step_views = {
        'pdf': generar_pdf,
        'post': generar_imagen_post,
        'story': generar_imagen_story,
        'carrusel': generar_carrusel,
        'email': generar_email,
    }
    step_view = step_views.get(next_step.step)
    if not step_view:
        return Response({'error': 'generation_step_not_supported', 'step': next_step.step}, status=status.HTTP_400_BAD_REQUEST)

    from rest_framework.test import APIRequestFactory, force_authenticate

    payload = _build_generation_run_payload(run, request.data, next_step.step)
    factory = APIRequestFactory()
    internal_request = factory.post('/api/internal/generation-step/', payload, format='json')
    force_authenticate(internal_request, user=request.user)
    response = step_view(internal_request)

    refreshed = get_generation_run_for_user(request.user, run.id)
    response_data = getattr(response, 'data', None)
    return Response({
        'success': 200 <= getattr(response, 'status_code', 500) < 300,
        'step': next_step.step,
        'step_response': response_data,
        'run': serialize_generation_run(refreshed or run),
    }, status=getattr(response, 'status_code', status.HTTP_500_INTERNAL_SERVER_ERROR))


def _safe_persisted_media_url(value):
    """Nunca devolver blobs data: desde campos persistidos."""
    if _is_data_url(value):
        return None
    return value


def _find_blocked_media_data_uri(value, path='payload'):
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered.startswith(('data:image', 'data:video', 'data:audio', 'data:application/pdf')):
            return path
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_blocked_media_data_uri(item, f'{path}[{index}]')
            if found:
                return found
        return None
    if isinstance(value, dict):
        for key, item in value.items():
            found = _find_blocked_media_data_uri(item, f'{path}.{key}')
            if found:
                return found
        return None
    return None


def require_pro_feature(feature):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            block_response = active_plan_block_response(request)
            if block_response:
                return block_response
            pro_payload = get_pro_feature_block_payload(request.user, feature=feature)
            if pro_payload:
                return Response(pro_payload, status=status.HTTP_403_FORBIDDEN)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def _reject_blocked_media_data_uri(payload, payload_label='payload'):
    if _allow_legacy_base64_media():
        return None
    blocked_path = _find_blocked_media_data_uri(payload, payload_label)
    if not blocked_path:
        return None
    return Response(
        {
            'error': 'invalid_media_payload',
            'mensaje': 'Formato data: no permitido. Subi archivo o URL remota.',
            'blocked_path': blocked_path,
            'allow_legacy_base64_media': False,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _parse_media_ref_input(value):
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.startswith('{') or trimmed.startswith('['):
            try:
                return json.loads(trimmed)
            except Exception:
                return value
    return value


def _upload_profile_data_image(value, user_id):
    if not _is_data_url(value):
        return value
    if not _allow_legacy_base64_media():
        return None
    try:
        header, payload = value.split(',', 1)
        if not header.lower().startswith('data:image'):
            return None
        raw = base64.b64decode(payload, validate=True)
        if len(raw) > 8 * 1024 * 1024:
            return None
        return AlmacenamientoCloudinary.guardar_avatar(io.BytesIO(raw), user_id=user_id)
    except Exception as exc:
        logger.warning("No se pudo subir imagen de perfil desde data URL: %s", exc)
        return None


def _resolve_profile_logo_input(data, user):
    present, value = _extract_first_present(data, 'logo_url', 'logoUrl')
    if not present:
        return False, None, None
    if value in (None, ''):
        return True, value, None
    uploaded = _upload_profile_data_image(value, user.id)
    if _is_data_url(value) and not uploaded:
        return True, None, Response(
            {'error': 'invalid_logo', 'message': 'No se pudo subir el logo a Cloudinary.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(uploaded, str) and uploaded.startswith('http'):
        return True, uploaded, None
    if isinstance(value, str) and value.startswith('http'):
        return True, value, None
    return True, None, None


def _notify_admin_trial_token_request(access_code_obj, email):
    """Registra el pedido de token y avisa al dashboard admin en tiempo real."""
    try:
        from .tracking import emit_ws_event

        alert = AdminAlert.objects.create(
            tipo='trial_token_request',
            severidad='info',
            titulo='Nuevo token solicitado',
            mensaje=f'Se solicitó un token de acceso para {email}.',
        )

        payload = {
            'kind': 'trial_token_request',
            'severity': 'info',
            'message': f'Nuevo token solicitado para {email}',
            'user_email': email,
            'details': {
                'alert_id': alert.id,
                'access_code_id': access_code_obj.id,
                'access_code': access_code_obj.code,
                'trial_days': access_code_obj.trial_days,
                'assigned_email': access_code_obj.assigned_email,
            },
        }

        transaction.on_commit(lambda: emit_ws_event({'type': 'trial_token_request', 'data': payload}))
        transaction.on_commit(
            lambda: emit_ws_event({
                'type': 'stats_update',
                'data': {
                    'pendingAlerts': AdminAlert.objects.filter(is_read=False).count(),
                },
            })
        )
    except Exception:
        logger.exception('[TRIAL_TOKEN] No se pudo notificar al dashboard admin')

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
    
    listado.datos_extra['resultados'][tipo] = _sanitize_listing_storage_value(resultado)
    listado.save(update_fields=['datos_extra'])


DEFAULT_USER_SETTINGS = {
    'notify_email': False,
    'notify_generation': False,
    'auto_save_drafts': True,
    'show_tips': True,
    'dark_mode': True,
    'glass_effects': True,
    'locale': 'auto',
    'timezone': 'America/Argentina/Buenos_Aires',
}

SUPPORTED_USER_LOCALES = {'auto', 'es', 'en', 'pt'}


def _coerce_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _normalize_user_settings(raw_settings=None, base_settings=None):
    merged = dict(DEFAULT_USER_SETTINGS)
    if isinstance(base_settings, dict):
        merged.update({k: v for k, v in base_settings.items() if v is not None})
    if isinstance(raw_settings, str):
        try:
            raw_settings = json.loads(raw_settings)
        except Exception:
            raw_settings = {}
    if not isinstance(raw_settings, dict):
        raw_settings = {}

    boolean_keys = {
        'notify_email',
        'notify_generation',
        'auto_save_drafts',
        'show_tips',
        'dark_mode',
        'glass_effects',
    }
    text_keys = {'locale', 'timezone'}

    for key in boolean_keys:
        if key in raw_settings:
            merged[key] = _coerce_bool(raw_settings.get(key))

    for key in text_keys:
        if key in raw_settings:
            value = raw_settings.get(key)
            normalized_value = str(value).strip() if value is not None else DEFAULT_USER_SETTINGS[key]
            if key == 'locale':
                normalized_value = normalized_value.lower()
                if normalized_value not in SUPPORTED_USER_LOCALES:
                    normalized_value = DEFAULT_USER_SETTINGS[key]
            merged[key] = normalized_value

    for key, value in raw_settings.items():
        if key not in merged:
            merged[key] = value

    merged['locale'] = str(merged.get('locale') or DEFAULT_USER_SETTINGS['locale']).strip().lower()
    if merged['locale'] not in SUPPORTED_USER_LOCALES:
        merged['locale'] = DEFAULT_USER_SETTINGS['locale']

    return merged


TEMPLATE_IDS = (
    'costa_serena',
    'oliva_natural',
    'terracota_suave',
    'brisa_calida',
    'arena_clara',
    'dubai_night',
    'beverly_hills',
    'manhattan',
    'mediterraneo',
    'tech_modern',
)

TEMPLATE_CATALOG = {
    'costa_serena': {
        'name': 'Costa Serena',
        'description': 'Mediterraneo luminoso con azules costeros y arena suave.',
        'colors': {
            'primary': '#2f5d73',
            'secondary': '#4d7f96',
            'accent': '#d3a45f',
            'background': '#f5f1ea',
            'text': '#23333b',
        },
        'fonts': {
            'display': 'Libre Baskerville',
            'body': 'Lato',
            'mono': 'Lato',
        },
    },
    'oliva_natural': {
        'name': 'Oliva Natural',
        'description': 'Residencial calido con tonos olivo y acento piedra.',
        'colors': {
            'primary': '#5c6d4a',
            'secondary': '#7f8f66',
            'accent': '#c89a58',
            'background': '#f7f3ea',
            'text': '#2f3426',
        },
        'fonts': {
            'display': 'Cormorant Garamond',
            'body': 'Lato',
            'mono': 'Lato',
        },
    },
    'terracota_suave': {
        'name': 'Terracota Suave',
        'description': 'Tonos tierra elegantes para una comunicacion acogedora.',
        'colors': {
            'primary': '#7a4a36',
            'secondary': '#9a654e',
            'accent': '#d79a63',
            'background': '#f6eee7',
            'text': '#3a281f',
        },
        'fonts': {
            'display': 'Libre Baskerville',
            'body': 'DM Sans',
            'mono': 'DM Sans',
        },
    },
    'brisa_calida': {
        'name': 'Brisa Calida',
        'description': 'Estilo mediterraneo comercial con clima claro y amable.',
        'colors': {
            'primary': '#46606b',
            'secondary': '#6f8892',
            'accent': '#e0ad67',
            'background': '#fbf7f0',
            'text': '#24343a',
        },
        'fonts': {
            'display': 'Playfair Display',
            'body': 'Lato',
            'mono': 'DM Sans',
        },
    },
    'arena_clara': {
        'name': 'Arena Clara',
        'description': 'Minimal calido con acentos dorados suaves.',
        'colors': {
            'primary': '#6b5b49',
            'secondary': '#8a785f',
            'accent': '#cda66d',
            'background': '#f9f5ee',
            'text': '#332a20',
        },
        'fonts': {
            'display': 'Cormorant Garamond',
            'body': 'DM Sans',
            'mono': 'DM Sans',
        },
    },
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

TEMPLATE_FILE_BASE = {
    'costa_serena': 'mediterraneo',
    'oliva_natural': 'beverly_hills',
    'terracota_suave': 'dubai_night',
    'brisa_calida': 'manhattan',
    'arena_clara': 'tech_modern',
}

TEMPLATE_POST_MAP = {
    template_id: f"renders/post_{TEMPLATE_FILE_BASE.get(template_id, template_id)}.html"
    for template_id in TEMPLATE_IDS
}

TEMPLATE_STORY_MAP = {
    template_id: f"renders/story_{TEMPLATE_FILE_BASE.get(template_id, template_id)}.html"
    for template_id in TEMPLATE_IDS
}

TEMPLATE_CAROUSEL_MAP = {
    template_id: f"renders/carousel_{TEMPLATE_FILE_BASE.get(template_id, template_id)}.html"
    for template_id in TEMPLATE_IDS
}

TEMPLATE_EMAIL_MAP = {
    template_id: f"emails/marketing_{TEMPLATE_FILE_BASE.get(template_id, template_id)}.html"
    for template_id in TEMPLATE_IDS
}

MAX_CAROUSEL_GALLERY_IMAGES = 8


SYSTEM_FONT_IMPORT_MAP = {
    'Playfair Display': 'Playfair Display',
    'Bebas Neue': 'Bebas Neue',
    'Inter': 'Inter',
    'DM Sans': 'DM Sans',
    'Space Mono': 'Space Mono',
    'Cormorant Garamond': 'Cormorant Garamond',
    'Oswald': 'Oswald',
    'Source Sans 3': 'Source Sans 3',
    'Source Serif 4': 'Source Serif 4',
    'Libre Baskerville': 'Libre Baskerville',
    'Lato': 'Lato',
    'Space Grotesk': 'Space Grotesk',
}


TEMPLATE_TOKEN_OPTIONS = {
    'fonts': list(SYSTEM_FONT_IMPORT_MAP.keys()),
    'palette_fields': [
        {'key': 'primary', 'label': 'Primario'},
        {'key': 'secondary', 'label': 'Secundario'},
        {'key': 'accent', 'label': 'Acento'},
        {'key': 'background', 'label': 'Fondo'},
        {'key': 'text', 'label': 'Texto'},
    ],
    'layout_styles': [
        {'id': 'editorial', 'label': 'Editorial elegante'},
        {'id': 'dark_luxury', 'label': 'Lujo oscuro'},
        {'id': 'minimal_light', 'label': 'Minimalista claro'},
        {'id': 'urban_strong', 'label': 'Urbano fuerte'},
        {'id': 'mediterranean_warm', 'label': 'Mediterraneo calido'},
        {'id': 'tech_modern', 'label': 'Tech moderno'},
        {'id': 'commercial_direct', 'label': 'Comercial directo'},
    ],
    'density': [
        {'id': 'compact', 'label': 'Compacto'},
        {'id': 'comfortable', 'label': 'Comodo'},
        {'id': 'spacious', 'label': 'Espaciado'},
    ],
    'border_radius': [
        {'id': 'none', 'label': 'Sin bordes'},
        {'id': 'soft', 'label': 'Suave'},
        {'id': 'medium', 'label': 'Medio'},
        {'id': 'strong', 'label': 'Fuerte'},
    ],
    'image_treatment': [
        {'id': 'normal', 'label': 'Normal'},
        {'id': 'dark', 'label': 'Oscuro'},
        {'id': 'warm', 'label': 'Calido'},
        {'id': 'black_white', 'label': 'Blanco y negro'},
        {'id': 'high_contrast', 'label': 'Alto contraste'},
    ],
    'layout_positions': [
        {'id': 'top_left', 'label': 'Arriba izquierda'},
        {'id': 'top_right', 'label': 'Arriba derecha'},
        {'id': 'bottom_left', 'label': 'Abajo izquierda'},
        {'id': 'bottom_right', 'label': 'Abajo derecha'},
    ],
    'copy_tones': [
        {'id': 'premium', 'label': 'Premium'},
        {'id': 'profesional', 'label': 'Profesional'},
        {'id': 'lujo', 'label': 'Lujo'},
        {'id': 'minimal', 'label': 'Minimal'},
    ],
}

LAYOUT_POSITIONS = {'top_left', 'top_right', 'bottom_left', 'bottom_right'}
BLOCKED_CUSTOM_CSS = ('<', '>', '@import', 'javascript:', 'expression(', '</style', '</')


def _safe_layout_position(value, fallback):
    return value if value in LAYOUT_POSITIONS else fallback


def _sanitize_template_custom_css(value):
    if not isinstance(value, str):
        return ''
    css = value.strip()[:4000]
    lowered = css.lower()
    if any(token in lowered for token in BLOCKED_CUSTOM_CSS) or re.search(r'url\s*\(', lowered):
        return ''
    return css


def _corner_position_css(selector, position, z_index=24):
    safe_position = _safe_layout_position(position, 'bottom_right')
    vertical, horizontal = safe_position.split('_', 1)
    vertical_prop = 'top' if vertical == 'top' else 'bottom'
    horizontal_prop = 'left' if horizontal == 'left' else 'right'
    return (
        f"{selector}{{position:absolute!important;{vertical_prop}:var(--lb-pos-y,64px)!important;"
        f"{horizontal_prop}:var(--lb-pos-x,64px)!important;z-index:{z_index}!important;margin:0!important;}}"
    )


def _build_template_gemini_instructions(template_name, base_template_id, tokens):
    tokens = _resolve_brand_template_tokens(tokens)
    palette = tokens.get('palette') or {}
    typography = tokens.get('typography') or {}
    copy = tokens.get('copy') or {}
    layout = tokens.get('layout') or {}
    hashtags = ' '.join(copy.get('hashtags') or [])
    return (
        f"Template personalizado: {template_name or 'Template de marca'}\n"
        f"Base visual: {base_template_id or 'tech_modern'}\n"
        "Respetar estos tokens de marca al generar copy, HTML o narrativa visual.\n"
        f"Colores: primario {palette.get('primary')}, secundario {palette.get('secondary')}, "
        f"acento {palette.get('accent')}, fondo {palette.get('background')}, texto {palette.get('text')}.\n"
        f"Tipografias: titulares {typography.get('display')}, cuerpo {typography.get('body')}, mono/acento {typography.get('mono')}.\n"
        f"Layout: estilo {layout.get('style', 'tech_modern')}, densidad {layout.get('density', 'comfortable')}, "
        f"bordes {layout.get('border_radius', 'medium')}, tratamiento de imagen {layout.get('image_treatment', 'normal')}, "
        f"logo {layout.get('logo_position')}, agente {layout.get('agent_block_position')}, QR {layout.get('qr_position')}.\n"
        f"Copy: tono {copy.get('tone')}, emojis {copy.get('emoji_density')}, CTA {copy.get('cta_style')}, hashtags {hashtags}.\n"
        "No inventar una identidad distinta. Mantener el HTML estructural y adaptar textos al estilo anterior."
    )


def _template_options_payload():
    return {
        'base_templates': [
            {
                'id': template_id,
                'label': meta.get('name', template_id.replace('_', ' ').title()),
                'description': meta.get('description', ''),
                'colors': meta.get('colors', {}),
                'fonts': meta.get('fonts', {}),
                'default_tokens': _default_tokens_for_base_template(template_id),
            }
            for template_id, meta in TEMPLATE_CATALOG.items()
        ],
        'token_options': TEMPLATE_TOKEN_OPTIONS,
        'default_tokens': default_template_tokens(),
        'default_tokens_by_base': {
            template_id: _default_tokens_for_base_template(template_id)
            for template_id in TEMPLATE_IDS
        },
    }


def _template_catalog_payload(user=None):
    system_items = []
    for template_id in TEMPLATE_IDS:
        meta = TEMPLATE_CATALOG.get(template_id, {})
        system_items.append({
            'id': template_id,
            'type': 'system',
            'name': meta.get('name', template_id.replace('_', ' ').title()),
            'description': meta.get('description', ''),
            'colors': meta.get('colors', {}),
            'fonts': meta.get('fonts', {}),
            'base_template_id': template_id,
            'brand_template_id': None,
        })

    custom_items = []
    if user and getattr(user, 'id', None):
        templates = BrandTemplate.objects.filter(owner=user, is_active=True).order_by('-is_default', '-updated_at')
        for tpl in templates:
            published = tpl.revisions.filter(status='published').order_by('-revision').first()
            tokens = published.tokens_json if published and isinstance(published.tokens_json, dict) else default_template_tokens()
            custom_items.append({
                'id': f'custom:{tpl.id}',
                'type': 'custom',
                'name': tpl.name,
                'description': tpl.description or f"Basado en {tpl.base_template_id.replace('_', ' ').title()}",
                'colors': (tokens.get('palette') or {}),
                'fonts': (tokens.get('typography') or {}),
                'base_template_id': tpl.base_template_id,
                'brand_template_id': tpl.id,
                'is_default': tpl.is_default,
                'published_revision': published.revision if published else None,
            })

    return {
        'templates': custom_items + system_items,
        'custom_templates': custom_items,
        'system_templates': system_items,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def templates_catalog(request):
    return Response(_template_catalog_payload(request.user), status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brand_templates_options(request):
    return Response(_template_options_payload(), status=status.HTTP_200_OK)


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


def _parse_brand_template_id(value):
    if value in (None, ''):
        return None

    raw = str(value).strip()
    if raw.startswith('custom:'):
        raw = raw.split(':', 1)[1]
    elif raw.startswith('custom-'):
        raw = raw.split('-', 1)[1]

    try:
        parsed = int(raw)
        return parsed if parsed > 0 else None
    except Exception:
        return None


def _extract_brand_template_id_from_payload(data):
    if not isinstance(data, dict):
        return None

    direct = _parse_brand_template_id(
        data.get('brand_template_id')
        or data.get('brandTemplateId')
    )
    if direct:
        return direct

    return _parse_brand_template_id(data.get('template_id') or data.get('templateId') or data.get('template'))


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


def _build_font_import_url(typography):
    if not isinstance(typography, dict):
        return ''
    fonts = typography.get('google_fonts') if isinstance(typography.get('google_fonts'), list) else []
    clean = []
    for font in fonts:
        mapped = SYSTEM_FONT_IMPORT_MAP.get(font)
        if mapped and mapped not in clean:
            clean.append(mapped)
    if not clean:
        return ''
    parts = [f"family={font.replace(' ', '+')}:wght@400;500;700" for font in clean]
    return f"https://fonts.googleapis.com/css2?{'&'.join(parts)}&display=swap"


def _deep_merge_dict(base, override):
    result = dict(base or {})
    if not isinstance(override, dict):
        return result

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result.get(key), value)
        else:
            result[key] = value
    return result


def _pick_template_font(value, fallback):
    candidates = []
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split('/')]
    elif isinstance(value, (list, tuple)):
        candidates = [str(part).strip() for part in value]
    for candidate in candidates:
        if candidate in SYSTEM_FONT_IMPORT_MAP:
            return candidate
    return fallback if fallback in SYSTEM_FONT_IMPORT_MAP else 'DM Sans'


def _default_tokens_for_base_template(base_template_id):
    template_id = _normalize_template_id(base_template_id) or 'tech_modern'
    tokens = default_template_tokens()
    meta = TEMPLATE_CATALOG.get(template_id, TEMPLATE_CATALOG['tech_modern'])
    colors = meta.get('colors') if isinstance(meta.get('colors'), dict) else {}
    fonts = meta.get('fonts') if isinstance(meta.get('fonts'), dict) else {}

    palette = tokens.get('palette', {}).copy()
    for key in ('primary', 'secondary', 'accent', 'background', 'text'):
        if colors.get(key):
            palette[key] = colors[key]
    palette['surface'] = colors.get('secondary') or palette.get('surface') or palette.get('background')
    palette['muted_text'] = '#b8b0a0' if template_id == 'dubai_night' else palette.get('muted_text', '#8fb1d1')
    palette['border'] = colors.get('accent') or colors.get('secondary') or palette.get('border', '#1d3e5d')
    palette['overlay'] = 'rgba(0,0,0,0.72)' if template_id in {'dubai_night', 'manhattan'} else palette.get('overlay', 'rgba(0,0,0,0.65)')

    display_font = _pick_template_font(fonts.get('display'), tokens['typography']['display'])
    body_font = _pick_template_font(fonts.get('body'), tokens['typography']['body'])
    mono_font = _pick_template_font(fonts.get('mono'), tokens['typography']['mono'])

    style_map = {
        'costa_serena': 'mediterranean_warm',
        'oliva_natural': 'mediterranean_warm',
        'terracota_suave': 'mediterranean_warm',
        'brisa_calida': 'mediterranean_warm',
        'arena_clara': 'mediterranean_warm',
        'dubai_night': 'dark_luxury',
        'beverly_hills': 'editorial',
        'manhattan': 'urban_strong',
        'mediterraneo': 'mediterranean_warm',
        'tech_modern': 'tech_modern',
    }
    image_map = {
        'costa_serena': 'warm',
        'oliva_natural': 'warm',
        'terracota_suave': 'warm',
        'brisa_calida': 'warm',
        'arena_clara': 'warm',
        'dubai_night': 'dark',
        'beverly_hills': 'normal',
        'manhattan': 'high_contrast',
        'mediterraneo': 'warm',
        'tech_modern': 'normal',
    }

    tokens['palette'] = palette
    tokens['typography'] = {
        **tokens.get('typography', {}),
        'display': display_font,
        'body': body_font,
        'mono': mono_font,
        'google_fonts': list(dict.fromkeys([display_font, body_font, mono_font])),
    }
    tokens['layout'] = {
        **tokens.get('layout', {}),
        'style': style_map.get(template_id, 'tech_modern'),
        'image_treatment': image_map.get(template_id, 'normal'),
    }
    return _resolve_brand_template_tokens(tokens)


def _resolve_brand_template_tokens(tokens):
    source = tokens if isinstance(tokens, dict) else default_template_tokens()
    fallback = default_template_tokens()

    palette = source.get('palette') if isinstance(source.get('palette'), dict) else {}
    typography = source.get('typography') if isinstance(source.get('typography'), dict) else {}
    emoji = source.get('emoji') if isinstance(source.get('emoji'), dict) else {}
    copy = source.get('copy') if isinstance(source.get('copy'), dict) else {}
    layout = source.get('layout') if isinstance(source.get('layout'), dict) else {}
    components = source.get('components') if isinstance(source.get('components'), dict) else {}
    formats = source.get('formats') if isinstance(source.get('formats'), dict) else {}

    merged = {
        'schema_version': 2,
        'palette': {
            'primary': palette.get('primary') or fallback['palette']['primary'],
            'secondary': palette.get('secondary') or fallback['palette']['secondary'],
            'accent': palette.get('accent') or fallback['palette']['accent'],
            'background': palette.get('background') or fallback['palette']['background'],
            'surface': palette.get('surface') or fallback['palette'].get('surface', fallback['palette']['secondary']),
            'text': palette.get('text') or fallback['palette']['text'],
            'muted_text': palette.get('muted_text') or fallback['palette'].get('muted_text', '#8fb1d1'),
            'border': palette.get('border') or fallback['palette'].get('border', fallback['palette']['secondary']),
            'overlay': palette.get('overlay') or fallback['palette'].get('overlay', 'rgba(0,0,0,0.65)'),
        },
        'typography': {
            'display': typography.get('display') or fallback['typography']['display'],
            'body': typography.get('body') or fallback['typography']['body'],
            'mono': typography.get('mono') or fallback['typography']['mono'],
            'google_fonts': typography.get('google_fonts') or fallback['typography']['google_fonts'],
            'title_transform': typography.get('title_transform') or fallback['typography'].get('title_transform', 'uppercase'),
            'letter_spacing': typography.get('letter_spacing') or fallback['typography'].get('letter_spacing', 'normal'),
        },
        'emoji': {
            'headline': emoji.get('headline') or fallback['emoji']['headline'],
            'price': emoji.get('price') or fallback['emoji']['price'],
            'location': emoji.get('location') or fallback['emoji']['location'],
            'cta': emoji.get('cta') or fallback['emoji']['cta'],
        },
        'copy': {
            'tone': copy.get('tone') or fallback['copy']['tone'],
            'emoji_density': copy.get('emoji_density') or fallback['copy']['emoji_density'],
            'cta_style': copy.get('cta_style') or fallback['copy']['cta_style'],
            'hashtags': copy.get('hashtags') or fallback['copy'].get('hashtags', []),
        },
        'layout': {
            'logo_position': layout.get('logo_position') or fallback['layout']['logo_position'],
            'agent_block_position': layout.get('agent_block_position') or fallback['layout']['agent_block_position'],
            'qr_position': layout.get('qr_position') or fallback['layout']['qr_position'],
            'style': layout.get('style') or fallback['layout'].get('style', 'tech_modern'),
            'density': layout.get('density') or fallback['layout'].get('density', 'comfortable'),
            'border_radius': layout.get('border_radius') or fallback['layout'].get('border_radius', 'medium'),
            'image_treatment': layout.get('image_treatment') or fallback['layout'].get('image_treatment', 'normal'),
            'custom_css': _sanitize_template_custom_css(layout.get('custom_css') or fallback['layout'].get('custom_css', '')),
        },
        'components': _deep_merge_dict(fallback.get('components', {}), components),
        'formats': _deep_merge_dict(fallback.get('formats', {}), formats),
    }
    merged['typography']['font_import_url'] = _build_font_import_url(merged['typography'])
    return merged


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


def _get_default_brand_template(user):
    if not user or not getattr(user, 'id', None):
        return None
    return BrandTemplate.objects.filter(owner=user, is_active=True, is_default=True).first()


def _resolve_template_selection(data, user, listado_obj=None, listado_id_hint=None):
    payload_brand_template_id = _extract_brand_template_id_from_payload(data)
    payload_template_id = _extract_template_id_from_payload(data)

    brand_template = None
    
    # If the user explicitly selects a system template, we do NOT override it with a brand template default
    is_explicit_system_template = payload_template_id in TEMPLATE_IDS
    
    if not is_explicit_system_template:
        if payload_brand_template_id:
            brand_template = BrandTemplate.objects.filter(
                id=payload_brand_template_id,
                owner=user,
                is_active=True,
            ).first()

        if not brand_template and listado_obj and listado_obj.brand_template_id:
            candidate = listado_obj.brand_template
            if candidate and candidate.owner_id == user.id and candidate.is_active:
                brand_template = candidate

        if not brand_template:
            brand_template = _get_default_brand_template(user)

    published_revision = None
    tokens = None
    template_instructions = ''
    if brand_template:
        published_revision = brand_template.revisions.filter(status='published').order_by('-revision').first()
        if published_revision:
            tokens = _resolve_brand_template_tokens(published_revision.tokens_json)
            template_instructions = (
                published_revision.gemini_instructions
                or _build_template_gemini_instructions(brand_template.name, brand_template.base_template_id, tokens)
            )

    if brand_template:
        template_id = brand_template.base_template_id
    elif payload_template_id:
        template_id = payload_template_id
    else:
        listado_template = _template_id_from_listado(listado_obj)
        if listado_template:
            template_id = listado_template
        elif listado_id_hint:
            template_id = _deterministic_template_id(listado_id_hint)
        elif listado_obj and getattr(listado_obj, 'id', None):
            template_id = _deterministic_template_id(listado_obj.id)
        else:
            template_id = random.choice(TEMPLATE_IDS)

    return {
        'template_id': template_id,
        'brand_template': brand_template,
        'brand_template_revision': published_revision,
        'template_tokens': tokens,
        'template_instructions': template_instructions,
    }


def _persist_template_selection(listado, selection, source=''):
    if not listado or not isinstance(selection, dict):
        return

    template_id = selection.get('template_id')
    brand_template = selection.get('brand_template')
    brand_template_revision = selection.get('brand_template_revision')

    _persist_template_id(listado, template_id, source=source)

    updates = []
    listado.brand_template = brand_template
    updates.append('brand_template')
    listado.brand_template_revision = brand_template_revision
    updates.append('brand_template_revision')

    if not isinstance(listado.datos_extra, dict):
        listado.datos_extra = {}
    datos = listado.datos_extra
    resultados = datos.get('resultados') if isinstance(datos.get('resultados'), dict) else {}
    meta = resultados.get('template_meta') if isinstance(resultados.get('template_meta'), dict) else {}
    meta['template_source'] = 'custom' if brand_template else 'system'
    meta['brand_template_id'] = brand_template.id if brand_template else None
    meta['brand_template_revision'] = brand_template_revision.revision if brand_template_revision else None
    meta['updated_at'] = timezone.now().isoformat()
    if source:
        meta['last_source'] = source
    resultados['template_meta'] = meta
    datos['resultados'] = resultados
    listado.datos_extra = datos
    updates.append('datos_extra')
    listado.save(update_fields=updates)


def _apply_template_tokens_to_html(html, template_id, template_tokens):
    if not html or not isinstance(template_tokens, dict):
        return html

    themed = str(html)
    palette = template_tokens.get('palette') or {}
    typography = template_tokens.get('typography') or {}
    layout = template_tokens.get('layout') or {}
    components = template_tokens.get('components') or {}

    base_meta = TEMPLATE_CATALOG.get(template_id, {})
    base_colors = base_meta.get('colors') if isinstance(base_meta.get('colors'), dict) else {}
    for key in ('primary', 'secondary', 'accent', 'background', 'text'):
        old_val = base_colors.get(key)
        new_val = palette.get(key)
        if old_val and new_val and old_val != new_val:
            themed = themed.replace(str(old_val), str(new_val))

    font_import_url = typography.get('font_import_url') or ''
    display_font = typography.get('display') or 'DM Sans'
    body_font = typography.get('body') or display_font
    mono_font = typography.get('mono') or body_font
    title_transform = typography.get('title_transform') or 'uppercase'
    letter_spacing_value = {
        'tight': '-0.04em',
        'normal': '0',
        'wide': '0.08em',
    }.get(typography.get('letter_spacing'), '0')
    logo_position = _safe_layout_position(layout.get('logo_position'), 'top_right')
    agent_position = _safe_layout_position(layout.get('agent_block_position'), 'bottom_left')
    qr_position = _safe_layout_position(layout.get('qr_position'), 'bottom_right')
    logo_order = (-1, 1) if logo_position == 'top_left' else (2, 1)
    layout_css = (
        "body{--lb-pos-x:64px;--lb-pos-y:64px;}"
        ".top,.top-section{display:flex!important;}"
        f".top .lb-brand-lockup,.top-section .lb-brand-lockup{{order:{logo_order[0]}!important;}}"
        f".top .badge,.top-section .badge{{order:{logo_order[1]}!important;}}"
    )
    if logo_position.startswith('bottom'):
        layout_css += _corner_position_css('.lb-brand-lockup', logo_position, 28)
    if qr_position.startswith('top'):
        layout_css += _corner_position_css('.qr-box,.qr-block,.qr-container', qr_position, 26)
    if agent_position.startswith('top'):
        layout_css += _corner_position_css('.agent-info,.agent-box', agent_position, 25)
    if agent_position.startswith('bottom') and qr_position.startswith('bottom'):
        layout_css += (
            ".agent-row,.footer,.contact-strip{flex-direction:row-reverse!important;}"
            if agent_position == 'bottom_right' or qr_position == 'bottom_left'
            else ".agent-row,.footer,.contact-strip{flex-direction:row!important;}"
        )
    elif agent_position.startswith('bottom'):
        layout_css += (
            ".agent-info,.agent-box{margin-left:auto!important;text-align:right!important;align-items:flex-end!important;}"
            if agent_position == 'bottom_right'
            else ".agent-info,.agent-box{margin-right:auto!important;text-align:left!important;align-items:flex-start!important;}"
        )
    elif qr_position.startswith('bottom'):
        layout_css += (
            ".qr-box,.qr-block,.qr-container{margin-left:auto!important;}"
            if qr_position == 'bottom_right'
            else ".qr-box,.qr-block,.qr-container{margin-right:auto!important;}"
        )
    radius_map = {'none': '0', 'soft': '8px', 'medium': '16px', 'strong': '28px'}
    density_map = {'compact': '0.85', 'comfortable': '1', 'spacious': '1.15'}
    image_filter_map = {
        'normal': 'none',
        'dark': 'brightness(.72) saturate(.95)',
        'warm': 'sepia(.18) saturate(1.15) brightness(.98)',
        'black_white': 'grayscale(1) contrast(1.08)',
        'high_contrast': 'contrast(1.18) saturate(1.18)',
    }
    layout_css += (
        f".hero img,.bg,.bg-image,.galeria-foto,.gallery-item{{filter:{image_filter_map.get(layout.get('image_treatment'), 'none')} !important;}}"
        f".stat,.stat-item,.price-box,.precio-box,.qr-block img,.amenidad-chip{{border-radius:{radius_map.get(layout.get('border_radius'), '16px')} !important;}}"
        f".content,.bottom,.bottom-section,.descripcion,.amenidades,.galeria{{gap:calc(20px * {density_map.get(layout.get('density'), '1')}) !important;}}"
    )
    hero_tokens = components.get('hero') if isinstance(components.get('hero'), dict) else {}
    price_tokens = components.get('price') if isinstance(components.get('price'), dict) else {}
    stats_tokens = components.get('stats') if isinstance(components.get('stats'), dict) else {}
    contact_tokens = components.get('contact') if isinstance(components.get('contact'), dict) else {}
    overlay_strength = {
        'none': 'rgba(0,0,0,0)',
        'soft': 'rgba(0,0,0,.32)',
        'medium': 'rgba(0,0,0,.58)',
        'strong': 'rgba(0,0,0,.78)',
    }.get(hero_tokens.get('overlay_strength'), None)
    if overlay_strength:
        layout_css += f".overlay,.hero-overlay{{background:linear-gradient(0deg,{overlay_strength} 0%,rgba(0,0,0,.24) 60%,rgba(0,0,0,.08) 100%)!important;}}"
    if hero_tokens.get('show_badge') is False:
        layout_css += ".badge,.badge-operacion{display:none!important;}"
    price_size = {'small': '.84', 'medium': '1', 'large': '1.22', 'xlarge': '1.42'}.get(price_tokens.get('size'), '1')
    layout_css += f".price-box,.precio-valor,.price-value{{transform:scale({price_size});transform-origin:left center;}}"
    if stats_tokens.get('show_icons') is False:
        layout_css += ".stat-icon,.pdf-inline-icon{display:none!important;}"
    if contact_tokens.get('show_qr') is False:
        layout_css += ".qr-box,.qr-container,.qr-block{display:none!important;}"
    if contact_tokens.get('show_agent_photo') is False:
        layout_css += ".agent-avatar,.agent-photo,.lb-agent-photo{display:none!important;}"
    custom_css = _sanitize_template_custom_css(layout.get('custom_css'))
    if custom_css:
        layout_css += custom_css

    style_block = (
        '<style id="brand-template-overrides">'
        f":root{{--brand-primary:{palette.get('primary', '#0d47a1')};"
        f"--brand-secondary:{palette.get('secondary', '#1565c0')};"
        f"--brand-accent:{palette.get('accent', '#00e5ff')};"
        f"--brand-bg:{palette.get('background', '#081421')};"
        f"--brand-text:{palette.get('text', '#e8f3ff')};"
        f"--brand-surface:{palette.get('surface', '#0d1b2a')};"
        f"--brand-muted-text:{palette.get('muted_text', '#8fb1d1')};"
        f"--brand-border:{palette.get('border', '#1d3e5d')};"
        f"--primario:{palette.get('primary', '#0d47a1')};"
        f"--secundario:{palette.get('secondary', '#1565c0')};"
        f"--acento:{palette.get('accent', '#00e5ff')};"
        f"--accent:{palette.get('accent', '#00e5ff')};}}"
        f"body{{font-family:'{body_font}',sans-serif !important;}}"
        f"h1,h2,h3,.title,.headline,.hero-titulo{{font-family:'{display_font}',sans-serif !important;text-transform:{title_transform}!important;letter-spacing:{letter_spacing_value}!important;}}"
        f".badge,.stat-label,.agent-role,.qr-label,.mono{{font-family:'{mono_font}',sans-serif !important;}}"
        f"{layout_css}"
        '</style>'
    )

    link_block = f'<link rel="stylesheet" href="{font_import_url}">' if font_import_url else ''
    injection = f'{link_block}{style_block}'

    if '</head>' in themed:
        themed = themed.replace('</head>', f'{injection}</head>', 1)
    else:
        themed = f'{injection}{themed}'

    return themed


def _inject_agent_photo_html(html, photo_url):
    if not html or not photo_url:
        return html
    photo = str(photo_url).strip()
    if not photo.startswith('http'):
        return html
    css = (
        '<style id="agent-photo-overrides">'
        '.lb-agent-photo{width:72px;height:72px;border-radius:50%;object-fit:cover;display:block;'
        'border:3px solid var(--accent,var(--acento,#00d4ff));margin-bottom:10px;background:#111;}'
        '.agent-info,.agent-box{align-items:flex-start;}'
        '.agent-box .lb-agent-photo{width:58px;height:58px;margin-bottom:6px;}'
        '</style>'
    )
    img = f'<img src="{photo}" alt="Foto agente" class="lb-agent-photo">'
    out = html.replace('</head>', f'{css}</head>', 1) if '</head>' in html else f'{css}{html}'
    for marker in ('<div class="agent-info">', '<div class="agent-box">'):
        if marker in out:
            return out.replace(marker, f'{marker}{img}', 1)
    return out


def _select_template_id(data, listado_obj=None, listado_id_hint=None, user=None):
    effective_user = user or getattr(listado_obj, 'agente', None)
    return _resolve_template_selection(data, effective_user, listado_obj, listado_id_hint).get('template_id')


def _resolve_cloudinary_asset_url(value):
    if isinstance(value, dict):
        if value.get('secure_url') and isinstance(value.get('secure_url'), str):
            return value.get('secure_url').strip()
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


def _resolve_listing_cover_frame(data):
    if not isinstance(data, dict):
        return ''

    resultados = data.get('resultados') if isinstance(data.get('resultados'), dict) else {}
    pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}

    pdf_candidates = [
        pdf_result.get('cover_frame_url'),
        pdf_result.get('cover_url'),
        pdf_result.get('thumbnail_url'),
        pdf_result.get('image_url'),
        data.get('dashboard_image_url'),
    ]
    for candidate in pdf_candidates:
        resolved = _resolve_cloudinary_asset_url(candidate)
        if resolved:
            return resolved

    candidates = [
        data.get('portadaUrl'),
        data.get('portada_url'),
        data.get('fotoPortada'),
        data.get('fotoportada'),
    ]

    gallery = data.get('fotosRecorrido') or data.get('fotos_recorrido') or []
    if isinstance(gallery, list) and gallery:
        candidates.append(gallery[0])

    candidates.extend([
        data.get('cover_frame_url'),
        data.get('coverFrameUrl'),
    ])

    for candidate in candidates:
        resolved = _resolve_cloudinary_asset_url(candidate)
        if resolved:
            return resolved
    return ''


def _render_and_store_pdf_cover(listado, html):
    if not listado or not html:
        return ''
    try:
        from api.services.almacenamiento import AlmacenamientoCloudinary

        cover_stream = render_html_to_image(html, 1200, 800)
        cover_url = AlmacenamientoCloudinary.guardar_pdf_cover(
            cover_stream,
            user_id=listado.agente_id,
            listado_id=listado.id,
        )
        return cover_url or ''
    except Exception as exc:
        logger.warning('[PDF] No se pudo generar portada para dashboard listado=%s: %s', getattr(listado, 'id', None), exc)
        return ''


def _ensure_listing_pdf_cover_frame(listado):
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    resultados = datos.get('resultados') if isinstance(datos.get('resultados'), dict) else {}
    pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}

    existing = ''
    for key in ('cover_frame_url', 'cover_url', 'thumbnail_url', 'image_url'):
        existing = _resolve_cloudinary_asset_url(pdf_result.get(key))
        if existing:
            break
    if existing:
        if datos.get('dashboard_image_url') != existing or datos.get('cover_frame_url') != existing:
            datos['dashboard_image_url'] = existing
            datos['cover_frame_url'] = existing
            listado.datos_extra = datos
            listado.save(update_fields=['datos_extra'])
        return existing

    html = pdf_result.get('html')
    cover_url = _render_and_store_pdf_cover(listado, html)
    if cover_url:
        pdf_result['cover_frame_url'] = cover_url
        pdf_result['cover_url'] = cover_url
        resultados['pdf'] = pdf_result
        datos['resultados'] = resultados
        datos['dashboard_image_url'] = cover_url
        datos['cover_frame_url'] = cover_url
        listado.datos_extra = datos
        listado.save(update_fields=['datos_extra'])
    return cover_url


def _ensure_listing_cover_frame(listado):
    datos = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
    cover_url = _resolve_listing_cover_frame(datos)
    if cover_url and datos.get('cover_frame_url') != cover_url:
        datos['cover_frame_url'] = cover_url
        listado.datos_extra = datos
        listado.save(update_fields=['datos_extra'])
    return cover_url


def _resolve_pdf_cover_from_data(data):
    if not isinstance(data, dict):
        return ''
    resultados = data.get('resultados') if isinstance(data.get('resultados'), dict) else {}
    pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}
    for key in ('cover_frame_url', 'cover_url', 'thumbnail_url', 'image_url'):
        resolved = _resolve_cloudinary_asset_url(pdf_result.get(key))
        if resolved:
            return resolved
    return ''


def _merge_listing_extra_preserving_covers(existing, incoming):
    existing = existing if isinstance(existing, dict) else {}
    merged = incoming.copy() if isinstance(incoming, dict) else {}

    existing_resultados = existing.get('resultados') if isinstance(existing.get('resultados'), dict) else {}
    incoming_resultados = merged.get('resultados') if isinstance(merged.get('resultados'), dict) else None
    if existing_resultados:
        merged['resultados'] = (
            _deep_merge_dict(existing_resultados, incoming_resultados)
            if incoming_resultados is not None
            else existing_resultados
        )

    for key in ('portadaUrl', 'portada_url', 'fotoPortada', 'fotoportada', 'fotosRecorrido', 'fotos_recorrido'):
        if not merged.get(key) and existing.get(key):
            merged[key] = existing[key]

    existing_pdf_cover = _resolve_pdf_cover_from_data(existing)
    incoming_pdf_cover = _resolve_pdf_cover_from_data(merged)
    if existing_pdf_cover and not incoming_pdf_cover:
        resultados = merged.get('resultados') if isinstance(merged.get('resultados'), dict) else {}
        pdf_result = resultados.get('pdf') if isinstance(resultados.get('pdf'), dict) else {}
        pdf_result['cover_frame_url'] = existing_pdf_cover
        pdf_result['cover_url'] = pdf_result.get('cover_url') or existing_pdf_cover
        resultados['pdf'] = pdf_result
        merged['resultados'] = resultados

    cover_url = _resolve_listing_cover_frame(merged) or _resolve_listing_cover_frame(existing)
    if cover_url:
        merged['dashboard_image_url'] = cover_url
        merged['cover_frame_url'] = cover_url
    return merged


def _sanitize_listing_storage_value(value):
    """Evita guardar blobs/base64 pesados dentro de Postgres JSONField."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(('data:image', 'data:video', 'data:audio', 'data:application/pdf')):
            return None
        return _repair_mojibake_text(value)
    if isinstance(value, list):
        cleaned = [_sanitize_listing_storage_value(item) for item in value]
        return [item for item in cleaned if item is not None]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key == 'html' and isinstance(item, str) and len(item) > 20000:
                continue
            sanitized = _sanitize_listing_storage_value(item)
            if sanitized is not None:
                cleaned[key] = sanitized
        return cleaned
    return value


def _sanitize_listing_payload_for_storage(payload):
    if not isinstance(payload, dict):
        return {}
    return _sanitize_listing_storage_value(payload)


def _repair_listing_response_value(value):
    """Repara texto corrupto al devolver listados viejos sin eliminar HTML ni assets."""
    if isinstance(value, str):
        return _repair_mojibake_text(value)
    if isinstance(value, list):
        return [_repair_listing_response_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_listing_response_value(item) for key, item in value.items()}
    return value


def _listing_generated_formats(listado, datos):
    resultados = datos.get('resultados') if isinstance(datos.get('resultados'), dict) else {}
    formats = []
    for key in ('pdf', 'post', 'story', 'carrusel', 'email'):
        value = resultados.get(key)
        if not value:
            continue
        if key == 'carrusel' and isinstance(value, dict):
            if value.get('slides') or value.get('url'):
                formats.append(key)
            continue
        if isinstance(value, dict):
            if value.get('url') or value.get('html') or value.get('caption'):
                formats.append(key)
            continue
        formats.append(key)
    if getattr(listado, 'video_url', None) or getattr(listado, 'video_status', '') in {'done', 'ready'}:
        formats.append('video')
    return formats


def _serialize_listing_summary(listado):
    cover_url = _ensure_listing_pdf_cover_frame(listado) or _ensure_listing_cover_frame(listado)
    datos = _repair_listing_response_value(listado.datos_extra if isinstance(listado.datos_extra, dict) else {})
    return {
        'id': listado.id,
        'titulo': listado.titulo,
        'tipo_propiedad': listado.tipo_propiedad,
        'operacion': listado.operacion,
        'ciudad': listado.ciudad,
        'precio': listado.precio,
        'moneda': listado.moneda,
        'creado_en': listado.creado_en,
        'videos_creados': listado.videos_creados,
        'video_url': listado.video_url,
        'video_status': listado.video_status,
        'dashboard_image_url': cover_url,
        'cover_frame_url': cover_url,
        'fotoportada': cover_url,
        'formatos_generados': _listing_generated_formats(listado, datos),
        'datos': datos,
    }


def _resolve_primary_property_image(data):
    if not isinstance(data, dict):
        return ''

    for key in ('portadaUrl', 'portada_url', 'fotoPortada', 'fotoportada'):
        resolved = _resolve_cloudinary_asset_url(data.get(key))
        if resolved:
            return resolved
    return ''


def _looks_like_property_image(value):
    """Evita que portada/galeria del listado se usen como logo o avatar."""
    if isinstance(value, dict):
        raw = ' '.join(
            str(value.get(key) or '')
            for key in ('public_id', 'url', 'secure_url')
        )
    else:
        raw = str(value or '')

    normalized = raw.replace('\\', '/').lower()
    if not normalized:
        return False

    property_markers = (
        '/listado_',
        'listado_',
        '/galeria',
        'galeria_',
        '/portada',
        'tipo_foto=galeria',
        'tipo_foto=portada',
    )
    return any(marker in normalized for marker in property_markers)


def _resolve_brand_asset_url(value):
    if not value or _looks_like_property_image(value):
        return ''

    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.startswith('data:'):
            return ''
        if cleaned.startswith('http'):
            return re.sub(r's--[^/]+--/', '', cleaned)
        return ''

    resolved = _resolve_cloudinary_asset_url(value)
    if resolved and not _looks_like_property_image(resolved):
        return resolved
    return ''


def _inject_agency_logo_fallback(html, logo_url, agency_name):
    if logo_url or not agency_name or '<div></div>' not in html:
        return html

    safe_agency = html_lib.escape(str(agency_name).strip())
    if not safe_agency:
        return html

    css = (
        '<style id="agency-logo-fallback">'
        '.agency-logo-text{max-width:260px;color:var(--accent,var(--acento,#c9a84c));'
        'font-family:Inter,DM Sans,Arial,sans-serif;font-size:24px;font-weight:900;'
        'line-height:1.05;letter-spacing:3px;text-transform:uppercase;text-align:right;}'
        '</style>'
    )
    out = html.replace('</head>', f'{css}</head>', 1) if '</head>' in html else f'{css}{html}'
    return out.replace('<div></div>', f'<div class="agency-logo-text">{safe_agency}</div>', 1)


def _inject_agency_brand_lockup(html, logo_url, agency_name):
    if not html:
        return html

    safe_agency = html_lib.escape(str(agency_name or '').strip())
    if not safe_agency:
        return html

    has_lockup = 'class="lb-brand-lockup"' in html or "class='lb-brand-lockup'" in html

    css = (
        '<style id="agency-brand-lockup">'
        '.lb-brand-lockup{display:flex!important;align-items:center!important;gap:14px!important;'
        'max-width:420px!important;min-height:62px!important;padding:8px 14px!important;'
        'border-radius:999px!important;background:rgba(0,0,0,.28)!important;'
        'border:1px solid rgba(255,255,255,.14)!important;backdrop-filter:blur(10px)!important;}'
        '.lb-brand-lockup .logo,.lb-brand-logo{width:58px!important;height:58px!important;'
        'max-width:58px!important;max-height:58px!important;border-radius:999px!important;'
        'object-fit:contain!important;padding:6px!important;background:rgba(255,255,255,.92)!important;'
        'filter:none!important;flex:0 0 auto!important;}'
        '.lb-brand-name{display:block!important;max-width:300px!important;color:var(--accent,var(--acento,#c9a84c))!important;'
        'font-family:Inter,DM Sans,Arial,sans-serif!important;font-size:22px!important;font-weight:900!important;'
        'line-height:1.05!important;letter-spacing:.6px!important;text-transform:uppercase!important;'
        'text-align:left!important;text-shadow:0 2px 14px rgba(0,0,0,.35)!important;}'
        '</style>'
    )
    out = html
    if 'id="agency-brand-lockup"' not in out:
        out = out.replace('</head>', f'{css}</head>', 1) if '</head>' in out else f'{css}{out}'

    if has_lockup:
        return out

    logo_pattern = re.compile(r'(<img\b(?=[^>]*class=["\'][^"\']*\blogo\b[^"\']*["\'])(?=[^>]*src=["\'][^"\']+["\'])[^>]*>)', re.IGNORECASE)
    match = logo_pattern.search(out)
    if match:
        logo_img = match.group(1)
        lockup = f'<div class="lb-brand-lockup">{logo_img}<span class="lb-brand-name">{safe_agency}</span></div>'
        return out[:match.start()] + lockup + out[match.end():]

    if '<div></div>' in out:
        return out.replace('<div></div>', f'<div class="lb-brand-lockup"><span class="lb-brand-name">{safe_agency}</span></div>', 1)

    return out


def _collect_property_images(data):
    portada = _resolve_primary_property_image(data)
    fotos = data.get('fotosRecorrido', []) if isinstance(data, dict) else []
    if not isinstance(fotos, list):
        fotos = []

    excluded = set()
    for key in ('logoAgenciaUrl', 'logo_url', 'logoUrl', 'agencyLogo', 'agenteFotoUrl', 'agente_foto_url'):
        resolved_brand = _resolve_brand_asset_url(data.get(key)) if isinstance(data, dict) else ''
        if resolved_brand:
            excluded.add(resolved_brand)

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
        if resolved and resolved not in seen and resolved not in excluded:
            seen.add(resolved)
            urls.append(resolved)
    return urls


def resolve_listing_media(listado, payload):
    """Fuente unica de media: portada + galeria desde payload o SQL."""
    data = payload.copy() if isinstance(payload, dict) else {}
    stored = listado.datos_extra if listado and isinstance(listado.datos_extra, dict) else {}

    if not data.get('portadaUrl') and stored.get('portadaUrl'):
        data['portadaUrl'] = stored.get('portadaUrl')
    if not data.get('fotosRecorrido') and stored.get('fotosRecorrido'):
        data['fotosRecorrido'] = stored.get('fotosRecorrido')

    gallery = data.get('fotosRecorrido') or []
    if not isinstance(gallery, list):
        gallery = [gallery]
    data['fotosRecorrido'] = [item for item in gallery if item]
    return data


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


def _format_phone_display(value):
    raw = str(value or '').strip()
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ''

    if raw.startswith('+'):
        normalized = f'+{digits}'
    else:
        normalized = f'+{digits}'

    country = ''
    area = ''
    local = ''

    if digits.startswith('54') and len(digits) >= 10:
        country = '54'
        rest = digits[2:]
        if rest.startswith('9') and len(rest) > 5:
            rest = rest[1:]
        if len(rest) >= 10:
            area = rest[:4]
            local = rest[4:]
        elif len(rest) >= 8:
            area = rest[:3]
            local = rest[3:]
        else:
            local = rest

    if country and area and local:
        return f'+{country} {area} {local}'
    return normalized


def _build_agent_contact_html(phone, email):
    phone_value = str(phone or '').strip()
    email_value = str(email or '').strip()
    parts = []

    if phone_value:
        phone_display = _format_phone_display(phone_value) or phone_value
        parts.append(
            f'<a href="tel:{html_lib.escape(phone_value)}">{html_lib.escape(phone_display)}</a>'
        )

    if email_value:
        parts.append(
            f'<a href="mailto:{html_lib.escape(email_value)}">{html_lib.escape(email_value)}</a>'
        )

    return ' &nbsp;·&nbsp; '.join(parts)


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


def _agency_name_clean_and_key(value):
    import unicodedata

    clean = re.sub(r'\s+', ' ', str(value or '').strip())
    if not clean:
        return None, None
    folded = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode('ascii')
    return clean, folded.lower()


def _website_clean_and_key(value):
    from urllib.parse import urlparse

    clean = str(value or '').strip()
    if not clean:
        return None, None

    candidate = clean if re.match(r'^[a-z][a-z0-9+.-]*://', clean, re.I) else f'https://{clean}'
    parsed = urlparse(candidate)
    host = parsed.netloc or parsed.path.split('/')[0]
    host = host.split('@')[-1].split(':')[0].strip().strip('.').lower()
    if host.startswith('www.'):
        host = host[4:]
    return clean, host or clean.lower()


def _extract_first_present(data, *keys):
    for key in keys:
        if key in data:
            return True, data.get(key)
    return False, None


def _validate_unique_agency_identity(user, *, agency_name=None, website=None, account_type=None):
    from .models import Agent

    errors = {}
    clean_name, agency_key = _agency_name_clean_and_key(agency_name)
    clean_website, website_key = _website_clean_and_key(website)
    candidates = Agent.objects.exclude(id=user.id).only('id', 'email', 'agencia', 'nombre_inmobiliaria', 'sitio_web')
    effective_account_type = str(account_type or getattr(user, 'agencia', '') or '').strip().lower()

    if agency_key and effective_account_type == 'agency':
        agency_candidates = candidates.filter(agencia__iexact='agency').exclude(nombre_inmobiliaria__isnull=True).exclude(nombre_inmobiliaria='')
        for candidate in agency_candidates:
            _, candidate_key = _agency_name_clean_and_key(candidate.nombre_inmobiliaria)
            if candidate_key == agency_key:
                logger.warning(
                    '[AgencyIdentity] nombre_inmobiliaria conflict user=%s candidate=%s candidate_email=%s candidate_agencia=%s',
                    getattr(user, 'id', None), candidate.id, candidate.email, candidate.agencia,
                )
                errors['nombre_inmobiliaria'] = 'Ya existe una cuenta de agencia con ese nombre de inmobiliaria.'
                break

    if website_key:
        for candidate in candidates.exclude(sitio_web__isnull=True).exclude(sitio_web=''):
            _, candidate_key = _website_clean_and_key(candidate.sitio_web)
            if candidate_key == website_key:
                logger.warning(
                    '[AgencyIdentity] sitio_web conflict user=%s candidate=%s candidate_email=%s candidate_agencia=%s',
                    getattr(user, 'id', None), candidate.id, candidate.email, candidate.agencia,
                )
                errors['sitio_web'] = 'Ya existe una cuenta con ese sitio web.'
                break

    if errors:
        message = ' '.join(errors.values())
        return Response({
            'error': 'agency_identity_conflict',
            'message': message or 'Ya existe una cuenta registrada con esa inmobiliaria o sitio web.',
            'errors': errors,
        }, status=status.HTTP_409_CONFLICT), clean_name, clean_website

    return None, clean_name, clean_website


def _resolve_branding_payload(data, user):
    payload = data if isinstance(data, dict) else {}
    default_profile = _get_default_commercial_agent(user)

    payload_logo = (
        payload.get('logoAgenciaUrl')
        or payload.get('logo_url')
        or payload.get('logoUrl')
        or payload.get('agencyLogo')
        or payload.get('agenciaLogoUrl')
    )
    active_asset = None
    if default_profile:
        active_asset = default_profile.media_assets.filter(kind='agent_photo', is_active=True).order_by('-uploaded_at').first()

    profile_photo = (
        (active_asset.secure_url if active_asset else '')
        or payload.get('agenteFotoUrl')
        or payload.get('agente_foto_url')
        or (default_profile.foto_url if default_profile else '')
        or payload_logo
        or getattr(user, 'logo_url', '')
        or ''
    )

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
    agent_contact_html = _build_agent_contact_html(agent_phone, agent_email)

    agency_name = (
        payload.get('agenciaNombre')
        or payload.get('agencia_nombre')
        or getattr(user, 'nombre_inmobiliaria', '')
        or getattr(user, 'agencia', '')
        or 'Agencia'
    )

    logo_url = (
        _resolve_brand_asset_url(payload_logo)
        or _resolve_brand_asset_url(getattr(user, 'logo_url', ''))
    )
    agent_photo_url = _resolve_brand_asset_url(profile_photo)

    return {
        'agente_nombre': str(agent_name).strip(),
        'agente_rol': str(agent_role).strip(),
        'agente_email': str(agent_email).strip(),
        'agente_telefono': str(agent_phone).strip(),
        'agencia_nombre': str(agency_name).strip(),
        'logo_url': str(logo_url or '').strip(),
        'agente_foto_url': str(agent_photo_url or '').strip(),
        'agente_contacto_html': agent_contact_html,
        'agente_foto_asset': active_asset.as_cloudinary_ref() if active_asset else None,
        'default_agent_profile': default_profile,
    }


def _normalize_hashtags(value):
    if not value:
        return []
    raw_items = re.split(r'[\s,]+', value) if isinstance(value, str) else value
    if not isinstance(raw_items, list):
        return []
    tags = []
    for item in raw_items:
        tag = str(item or '').strip()
        if not tag:
            continue
        tag = tag if tag.startswith('#') else f'#{tag}'
        tag = re.sub(r'[^#\wÃƒÆ’Ã†â€™Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚ÂÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚ÂºÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¼ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±]', '', tag)
        if len(tag) > 1 and tag not in tags:
            tags.append(tag[:50])
    return tags[:35]


def _hashtag_from_text(value):
    text = str(value or '').strip()
    if not text:
        return ''
    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r'[^A-Za-z0-9]+', ' ', ascii_text).strip().title().replace(' ', '')
    return f'#{cleaned[:48]}' if cleaned else ''


def _build_dynamic_hashtags(data, formato='post'):
    data = data if isinstance(data, dict) else {}
    tipo = data.get('tipoPropiedad') or data.get('tipo_propiedad') or ''
    ciudad = data.get('ciudad') or ''
    pais = data.get('pais') or ''
    operacion = str(data.get('operacion') or '').strip().lower()

    tags = [
        '#RealEstate', '#Inmobiliaria', '#Propiedades', '#BienesRaices',
        '#InversionInmobiliaria', '#OportunidadInmobiliaria', '#PropiedadPremium',
        '#LuxuryRealEstate', '#RealEstateMarketing', '#BrokerInmobiliario',
        '#AgenteInmobiliario', '#ListadoInmobiliario', '#TourInmobiliario',
        '#VentaInmobiliaria', '#CompraInteligente', '#InversionSegura',
        '#MercadoInmobiliario', '#RealEstateLatam', '#LeadBook',
    ]

    for candidate in (tipo, ciudad, pais):
        tag = _hashtag_from_text(candidate)
        if tag:
            tags.append(tag)

    tipo_tag = _hashtag_from_text(tipo)
    if tipo_tag:
        suffix = 'EnAlquiler' if any(word in operacion for word in ('alquiler', 'renta', 'rent')) else 'EnVenta'
        tags.append(f'{tipo_tag}{suffix}'[:50])

    ciudad_tag = _hashtag_from_text(ciudad)
    if ciudad_tag:
        tags.extend([f'{ciudad_tag}RealEstate'[:50], f'#VivirEn{ciudad_tag[1:]}'[:50]])

    if formato == 'carrusel':
        tags.extend(['#CarruselInmobiliario', '#DeslizaParaVer', '#FichaInmobiliaria'])
    elif formato == 'story':
        tags.extend(['#InstagramStories', '#ConsultaPorWhatsApp', '#DisponibleAhora'])
    else:
        tags.extend(['#InstagramRealEstate', '#PostInmobiliario', '#AgendaTuVisita'])

    normalized = _normalize_hashtags(tags)
    return normalized[:32]


def _resolve_content_preferences(user, template_tokens=None, payload=None):
    payload = payload if isinstance(payload, dict) else {}
    tokens_copy = (template_tokens or {}).get('copy') if isinstance(template_tokens, dict) else {}
    try:
        prefs = getattr(user, 'content_preferences', None)
    except Exception:
        prefs = None

    hashtags = (
        payload.get('hashtags')
        or (tokens_copy or {}).get('hashtags')
        or (prefs.hashtags if prefs else None)
        or [
            '#RealEstate', '#Inmobiliaria', '#Propiedades', '#BienesRaices',
            '#InversionInmobiliaria', '#PropiedadPremium', '#LuxuryRealEstate',
            '#OportunidadInmobiliaria', '#AgenteInmobiliario', '#AgendaTuVisita',
        ]
    )
    emoji_density = (
        payload.get('emoji_density')
        or (tokens_copy or {}).get('emoji_density')
        or (prefs.emoji_density if prefs else 'medium')
    )
    use_emojis = payload.get('use_emojis')
    if use_emojis is None:
        use_emojis = (prefs.use_emojis if prefs else True)

    tone = payload.get('tone') or (tokens_copy or {}).get('tone') or (prefs.tone if prefs else 'premium')
    return {
        'hashtags': _normalize_hashtags(hashtags),
        'emoji_density': emoji_density if emoji_density in {'none', 'low', 'medium', 'high'} else 'medium',
        'use_emojis': bool(use_emojis),
        'tone': tone,
    }


CAPTION_STYLE_LIBRARY = [
    {
        "id": "storytelling",
        "name": "Storytelling y Emocional",
        "instructions": (
            "- Enfoque Narrativo/Emocional: Centrado en la experiencia de vida, el hogar, la calidez, la familia, "
            "el estilo de vida y las sensaciones/experiencias que evoca habitar este espacio. Evitá sonar frío "
            "o como una simple lista de datos. Hacé que el lector se imagine viviendo allí y disfrutando el lugar."
        ),
    },
    {
        "id": "commercial",
        "name": "Comercial de Alto Impacto",
        "instructions": (
            "- Enfoque Comercial Directo: Centrado en las características de valor de la propiedad (especificaciones técnicas, "
            "distribución, materiales premium, amenities, diseño funcional y precio de oportunidad). Sé directo, "
            "claro y sumamente persuasivo, destacando por qué es una excelente compra en términos de confort y estatus."
        ),
    },
    {
        "id": "investment",
        "name": "Oportunidad de Inversión",
        "instructions": (
            "- Enfoque de Inversión e Inversores: Centrado en la rentabilidad (ROI), plusvalía, la ubicación estratégica premium, "
            "seguridad del capital, exclusividad, escasez en el mercado inmobiliario y el valor de la propiedad como activo "
            "financiero inteligente. Usá un tono sofisticado, exclusivo y con foco en la solidez del negocio inmobiliario."
        ),
    },
]


def _get_caption_generation_count(listado_obj, formato='post'):
    if not listado_obj or not isinstance(getattr(listado_obj, 'datos_extra', None), dict):
        return 0

    resultados = listado_obj.datos_extra.get('resultados') if isinstance(listado_obj.datos_extra.get('resultados'), dict) else {}
    resultado = resultados.get(formato) if isinstance(resultados.get(formato), dict) else {}
    raw_count = resultado.get('caption_generation_count', 0)
    try:
        return int(raw_count or 0)
    except Exception:
        return 0


def _get_random_caption_style_instructions(listado_obj=None, formato='post'):
    import random

    styles = CAPTION_STYLE_LIBRARY
    if not styles:
        return {
            'id': 'storytelling',
            'name': 'Storytelling y Emocional',
            'instructions': '',
        }

    if listado_obj:
        last_count = _get_caption_generation_count(listado_obj, formato=formato)
        resultados = listado_obj.datos_extra.get('resultados') if isinstance(getattr(listado_obj, 'datos_extra', None), dict) else {}
        current = resultados.get(formato) if isinstance(resultados.get(formato), dict) else {}
        last_style_id = current.get('caption_style_id')
        style_ids = [style['id'] for style in styles]
        if last_style_id in style_ids:
            selected = styles[(style_ids.index(last_style_id) + 1) % len(styles)]
            return selected
        return styles[last_count % len(styles)]

    return random.choice(styles)


def _caption_preference_prompt(prefs):
    emoji_text = 'sin emojis' if not prefs.get('use_emojis') or prefs.get('emoji_density') == 'none' else f"emojis densidad {prefs.get('emoji_density')}"
    hashtags = ' '.join(prefs.get('hashtags') or [])
    template_instructions = str(prefs.get('template_instructions') or '').strip()
    extra = f" Instrucciones del template personalizado: {template_instructions}" if template_instructions else ''
    return f"Tono {prefs.get('tone', 'premium')}; {emoji_text}; usar estos hashtags base si aplican y sumar hashtags especificos de ciudad, propiedad, inversion y lifestyle: {hashtags}.{extra}"


def _attach_template_instructions_to_prefs(prefs, selection):
    prefs = dict(prefs or {})
    if isinstance(selection, dict) and selection.get('template_instructions'):
        prefs['template_instructions'] = selection.get('template_instructions')
    return prefs


def _apply_caption_preferences(caption, prefs, max_chars=2200, data=None, formato='post'):
    text = str(caption or '').strip()
    tag_pool = []
    tag_pool.extend(prefs.get('hashtags') or [])
    tag_pool.extend(_build_dynamic_hashtags(data or {}, formato=formato))
    tags = [tag for tag in _normalize_hashtags(tag_pool) if tag not in text]
    if tags:
        selected = []
        for tag in tags[:32]:
            candidate = ' '.join(selected + [tag])
            if len(text) + len(candidate) + 2 > max_chars:
                break
            selected.append(tag)
        if selected:
            text = f"{text}\n\n{' '.join(selected)}".strip()
    if not prefs.get('use_emojis') or prefs.get('emoji_density') == 'none':
        text = re.sub(r'[\U0001F300-\U0001FAFF\U00002700-\U000027BF]+', '', text).strip()
    return text[:max_chars].rstrip()


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


def _is_safe_remote_asset_url(url, allowed_hosts=None, allow_any_host=False, allowed_schemes=None):
    try:
        import ipaddress
        import socket
        from urllib.parse import urlparse
        from django.conf import settings

        parsed = urlparse(str(url or '').strip())
        schemes = set(allowed_schemes or ('https',))
        if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password:
            return False

        hostname = parsed.hostname.lower().rstrip('.')
        allowed = [] if allow_any_host else (allowed_hosts or getattr(settings, 'REMOTE_ASSET_ALLOWED_HOSTS', ['res.cloudinary.com']))
        allowed = {str(host).lower().rstrip('.') for host in allowed if str(host).strip()}
        if not allow_any_host and allowed and not any(hostname == host or hostname.endswith(f'.{host}') for host in allowed):
            return False

        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False


def _download_remote_asset(
    url,
    timeout=25,
    max_bytes=20 * 1024 * 1024,
    *,
    allow_any_host=False,
    allowed_hosts=None,
    allowed_schemes=None,
    content_type_prefixes=None,
    max_redirects=3,
):
    allowed_schemes = allowed_schemes or ('https',)
    if not _is_safe_remote_asset_url(url, allowed_hosts=allowed_hosts, allow_any_host=allow_any_host, allowed_schemes=allowed_schemes):
        return None, None
    try:
        current_url = str(url or '').strip()
        response = None
        for _ in range(max_redirects + 1):
            response = requests.get(current_url, timeout=timeout, stream=True, allow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                next_url = response.headers.get('location')
                if not next_url:
                    return None, None
                from urllib.parse import urljoin
                current_url = urljoin(current_url, next_url)
                if not _is_safe_remote_asset_url(current_url, allowed_hosts=allowed_hosts, allow_any_host=allow_any_host, allowed_schemes=allowed_schemes):
                    return None, None
                continue
            break
        if response is None:
            return None, None
        if response.status_code != 200:
            return None, None

        content_type = response.headers.get('content-type', '').lower()
        if content_type_prefixes and not any(content_type.startswith(prefix) for prefix in content_type_prefixes):
            return None, None
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return None, None
            chunks.append(chunk)
        return b''.join(chunks), content_type
    except Exception:
        return None, None


def _sanitize_caption_text(raw_text, max_chars=2200):
    if not raw_text:
        return ''

    text = _repair_mojibake_text(raw_text).strip()
    text = re.sub(r"```(?:json|markdown|text)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    text = text.replace("**", "")
    text = re.sub(r'^\s*---+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*#{1,6}\s*', '', text, flags=re.MULTILINE)

    intro_patterns = [
        r'^\s*[!ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡]*\s*absolutamente[!ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¡\s\-,:.]*',
        r'^\s*(opci[oÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³]n|option)\s*\d+\s*(?:\([^\)]*\))?\s*[:\-ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ.]*\s*',
        r'^\s*(aqui|aquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­)\s+tienes\s+un\s+caption[^:\n]{0,180}:\s*',
        r'^\s*(aqui|aquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­)\s+tienes[^:\n]{0,180}:\s*',
        r'^\s*te\s+comparto\s+un\s+caption[^:\n]{0,180}:\s*',
    ]
    for pattern in intro_patterns:
        text = re.sub(pattern, '', text, count=1, flags=re.IGNORECASE)

    meta_prefix = re.compile(
        r'^\s*(caption|copy|salida|output|explicacion|explicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n|nota|instrucciones|observaciones?)\s*:\s*',
        flags=re.IGNORECASE,
    )

    def _is_meta_paragraph(paragraph):
        p = str(paragraph or '').strip().lower()
        if not p:
            return False
        meta_signals = (
            'aqui tienes',
            'aquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ tienes',
            'caption optimizado',
            'caption para instagram',
            'disenado para captar',
            'diseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±ado para captar',
            'te comparto el caption',
            'este caption',
            'copia optimizada',
            'i can process',
            'i cannot process',
            "i can't process",
            'as an ai',
            'como modelo de ia',
            'no puedo procesar',
        )
        return any(signal in p for signal in meta_signals)

    cleaned_lines = []
    for line in text.splitlines():
        current = line.strip()
        if not current:
            cleaned_lines.append('')
            continue

        current = re.sub(r'^\s*[-*ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢]+\s*', '', current)
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


def _caption_needs_fallback(text):
    lowered = str(text or '').strip().lower()
    if not lowered:
        return True
    bad_signals = (
        'i can process',
        'i cannot process',
        "i can't process",
        'i am unable',
        "i'm unable",
        'as an ai',
        'cannot access',
        'no puedo procesar',
        'no puedo acceder',
        'como modelo de ia',
        'opcion 1',
        'opciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n 1',
        'option 1',
    )
    return any(signal in lowered for signal in bad_signals)


def _finalize_caption_text(raw_text, data, formato='post', prefs=None, max_chars=2200):
    caption = _sanitize_caption_text(_repair_mojibake_text(raw_text), max_chars=max_chars)
    if _caption_needs_fallback(caption):
        caption = ''
    caption = _ensure_caption_length(caption, data, formato=formato)
    if prefs:
        caption = _apply_caption_preferences(caption, prefs, max_chars=max_chars, data=data, formato=formato)
    caption = _repair_mojibake_text(caption)
    return caption[:max_chars].rstrip()


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
            "Si queres fotos, ficha completa y coordinar visita, escribinos ahora y te asesoramos en minutos. "
            "#DisponibleAhora #ConsultaPorWhatsApp #Propiedades #RealEstate"
        )
    if formato == 'carrusel':
        return (
            f"{tipo} en {ciudad}: una oportunidad real para {operacion} con propuesta premium y excelente ubicacion. "
            f"Precio publicado: {moneda} {precio}. La propiedad ofrece {specs}, ambientes luminosos y funcionales para vivir o invertir. "
            "Desliza el carrusel para ver recorrido, diferenciales y datos clave antes de decidir. "
            "Escribinos para enviarte toda la informacion, disponibilidad actualizada y coordinar visita. "
            "#RealEstate #Inmobiliaria #Inversion #BienesRaices #PropiedadPremium #CarruselInmobiliario"
        )
    return (
        f"{tipo} en {ciudad} en {operacion}, pensada para quienes buscan ubicacion, calidad y rentabilidad. "
        f"Precio de referencia: {moneda} {precio}. Con {specs}, esta propiedad combina diseno, comodidad y una excelente proyeccion de valor. "
        "Ideal para compradores e inversores que valoran informacion clara, buen asesoramiento y una decision segura. "
        "Contactanos para recibir la ficha completa, resolver dudas, revisar condiciones comerciales y coordinar visita personalizada. "
        "#RealEstate #Inmobiliaria #Propiedades #Inversion #BienesRaices #PropiedadPremium #AgendaTuVisita"
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


def _get_leadbook_logo_url():
    configured = config('LEADBOOK_LOGO_URL', default='').strip()
    if configured.startswith('http'):
        return configured
    return 'https://res.cloudinary.com/dpqgbgilw/image/upload/v1/leadbook/branding/leadbook_logo.png'


def _ensure_caption_length(text, data, formato='post'):
    caption = str(text or '').strip()
    min_chars_map = {'post': 1100, 'story': 380, 'carrusel': 1150}
    max_chars_map = {'post': 2200, 'story': 650, 'carrusel': 2200}

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
                f"{operacion} ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· {tipo} en {ciudad}",
                f"Precio de referencia: {moneda} {precio}.",
                "Ideal para quienes priorizan ubicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, distribuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n funcional y potencial de valorizaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
                "Escribinos por WhatsApp y te enviamos ficha completa, recorrido y disponibilidad actualizada.",
                "#Propiedades #Inmobiliaria #Oportunidad",
            ]
        elif formato == 'carrusel':
            extension_blocks = [
                "\nDESTACADOS",
                f"ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ {operacion} de {tipo} en {ciudad}.",
                f"ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Precio publicado: {moneda} {precio}.",
                "ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Propuesta ideal para vivir bien o invertir con estrategia.",
                "\nPOR QUE VALE LA PENA",
                "ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ UbicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n competitiva frente a opciones similares de la zona.",
                "ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ DistribuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n pensada para comodidad, funcionalidad y estilo.",
                "ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Potencial de renta y valorizaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n a mediano plazo.",
                "ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Contenido visual pensado para evaluar la propiedad con mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s claridad antes de visitar.",
                "\nCTA",
                "Escribinos para recibir la ficha completa, comparativa de mercado, disponibilidad y coordinar visita privada.",
                "#RealEstate #InversionInmobiliaria #Propiedades #BienesRaices #PropiedadPremium #CarruselInmobiliario #AgendaTuVisita #LuxuryRealEstate",
            ]
        else:
            extension_blocks = [
                "\nDETALLES CLAVE",
                f"ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ {operacion} de {tipo} en {ciudad}.",
                f"ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Valor de referencia: {moneda} {precio}.",
                "ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Balance entre calidad constructiva, ubicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y proyecciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de valor.",
                "\nENFOQUE COMERCIAL",
                "Esta propiedad se posiciona como una alternativa sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³lida para quien busca decidir con informaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n clara y respaldo profesional.",
                "AdemÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s, permite comunicar valor desde el primer contacto: ubicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, estilo de vida, potencial de inversiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y una propuesta concreta para avanzar sin vueltas.",
                "\nSIGUIENTE PASO",
                "Escribinos para enviarte la ficha tÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©cnica completa, videos, disponibilidad y agendar visita personalizada.",
                "#RealEstate #Propiedades #Inmobiliaria #Inversion #BienesRaices #PropiedadPremium #OportunidadInmobiliaria #AgendaTuVisita #LuxuryRealEstate #BrokerInmobiliario",
            ]

        extension_blocks = [_repair_mojibake_text(block) for block in extension_blocks]
        for block in extension_blocks:
            if len(caption) >= min_chars:
                break
            separator = "\n\n" if caption else ""
            caption = f"{caption}{separator}{block}".strip()

    if len(caption) > max_chars:
        caption = caption[:max_chars].rstrip()

    return _repair_mojibake_text(caption)

LIMITES_PLAN = {
    'free':     {'listados_mes': 10},
    'starter':  {'listados_mes': 40},
    'pro':      {'listados_mes': 150},
    'scale':    {'listados_mes': 999999},
    'business': {'listados_mes': 999999},
}

def verificar_limite_plan(agent):
    from datetime import datetime
    plan = getattr(agent, 'plan_nombre', 'starter')
    limite = LIMITES_PLAN.get(plan, LIMITES_PLAN['starter'])
    
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

def generar_whatsapp_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import urllib.parse
    # Limpiar telÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fono: solo dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­gitos
    raw_phone = str(telefono or '').strip()
    tel_limpio = ''.join(filter(str.isdigit, raw_phone))
    # Si no viene en E.164, asumir Argentina (+54) por compatibilidad histÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³rica.
    if tel_limpio and not raw_phone.startswith('+') and not tel_limpio.startswith('54'):
        tel_limpio = '54' + tel_limpio
    if not tel_limpio:
        return ''
    # Armar mensaje profesional
    detalle = f"{tipo_propiedad} en {ciudad}".strip(' en') if tipo_propiedad or ciudad else "propiedad"
    precio_str = f" por {moneda} {precio}" if precio else ""
    op_str = f" en {operacion.lower()}" if operacion else ""
    mensaje = f"Hola! Me interesa {detalle}{op_str}{precio_str}. ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¿PodÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s darme mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s informaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n?"
    # Armar URL de WhatsApp
    return f"https://wa.me/{tel_limpio}?text={urllib.parse.quote(mensaje)}"


def generar_qr_url(telefono, tipo_propiedad='', ciudad='', operacion='', precio='', moneda=''):
    import qrcode
    wa_url = generar_whatsapp_url(telefono, tipo_propiedad, ciudad, operacion, precio, moneda)
    if not wa_url:
        return ''
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(wa_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        logger.exception("[QR] No se pudo generar QR local")
        return ''


_MOJIBAKE_REPLACEMENTS = (
    ('ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â·', '·'),
    ('Ãƒâ€šÃ‚Â·', '·'),
    ('â€™', "'"),
    ('â€˜', "'"),
    ('â€œ', '"'),
    ('â€\x9d', '"'),
    ('â€', '"'),
    ('â€“', '-'),
    ('â€”', '-'),
    ('â€¦', '...'),
    ('Â·', '·'),
    ('Â ', ' '),
    ('Â', ''),
)


def _apply_mojibake_replacements(text):
    for broken, fixed in _MOJIBAKE_REPLACEMENTS:
        text = text.replace(broken, fixed)
    return text


def _repair_mojibake_text(value):
    """Repara texto UTF-8 que fue decodificado como cp1252/latin1 una o más veces."""
    text = str(value or '')
    if not text:
        return ''

    try:
        from ftfy import fix_text
        for _ in range(6):
            fixed = fix_text(text)
            if fixed == text:
                break
            text = fixed
    except Exception:
        # Si la dependencia no está disponible, no arriesgamos una transcodificación destructiva.
        pass

    text = _apply_mojibake_replacements(text)
    text = re.sub(
        r'(?:&nbsp;|\xa0)\s*[ÃÂÆƒâ€š™Å¡‚"\'`]*·[ÃÂÆƒâ€š™Å¡‚"\'`]*\s*(?:&nbsp;|\xa0)',
        ' &nbsp;·&nbsp; ',
        text,
    )
    return text


def _sanitize_generated_email_html(raw_html):
    html_text = _repair_mojibake_text(raw_html).strip()
    if not html_text:
        return ''

    html_text = re.sub(r'(?is)<(script|style|iframe|object|embed|svg|math|form|input|button|meta|link)[^>]*>.*?</\1>', '', html_text)
    html_text = re.sub(r'(?is)<a\b[^>]*>(.*?)</a>', r'\1', html_text)
    html_text = re.sub(r'(?is)</?(html|head|body)[^>]*>', '', html_text)
    html_text = re.sub(r'(?is)\s(?:on\w+|style|srcdoc|formaction|xlink:href)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', '', html_text)
    html_text = re.sub(r'(?i)(?:javascript:|vbscript:|data:text/html)', '', html_text)
    html_text = re.sub(r'(?i)\b(?:mailto:|tel:|https?://|www\.)\S+', '', html_text)
    html_text = re.sub(r'(?i)href\s*=\s*["\']?(?:mailto:|tel:|https?://|www\.)[^"\'>\s]+["\']?', '', html_text)
    html_text = re.sub(r'(?is)<(?!/?(?:p|br|strong|b|em|i|ul|ol|li|span|div)\b)[^>]+>', '', html_text)
    html_text = re.sub(r'(?is)<(p|strong|b|em|i|ul|ol|li|span|div)\b[^>]*>', r'<\1>', html_text)
    html_text = re.sub(r'(?i)\b[\w.+-]+@[\w-]+\.[\w.-]+\b', '', html_text)
    html_text = re.sub(r'>\s+<', '><', html_text)
    html_text = re.sub(r'\s{2,}', ' ', html_text)
    return _repair_mojibake_text(html_text).strip()


def _sanitize_generated_email_text(raw_text):
    text = re.sub(r'(?is)<[^>]+>', ' ', _repair_mojibake_text(raw_text))
    text = re.sub(r'(?i)\b(?:mailto:|tel:|https?://|www\.)\S+', '', text)
    text = re.sub(r'(?i)\b[\w.+-]+@[\w-]+\.[\w.-]+\b', '', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return _repair_mojibake_text(text).strip()

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from api.models import BannedIP, Agent

REFRESH_COOKIE_NAME = 'leadbook_refresh'


def _refresh_cookie_options():
    from django.conf import settings
    secure = not getattr(settings, 'DEBUG', False)
    return {
        'httponly': True,
        'secure': secure,
        'samesite': 'None' if secure else 'Lax',
        'path': '/',
        'max_age': 7 * 24 * 60 * 60,
    }


def _set_refresh_cookie(response, refresh_token):
    if refresh_token:
        response.set_cookie(REFRESH_COOKIE_NAME, str(refresh_token), **_refresh_cookie_options())
    return response


def _delete_refresh_cookie(response):
    response.delete_cookie(REFRESH_COOKIE_NAME, path='/', samesite=_refresh_cookie_options()['samesite'])
    return response


class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        data = request.data.copy()
        if not data.get('refresh'):
            data['refresh'] = request.COOKIES.get(REFRESH_COOKIE_NAME, '')
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        refresh_token = data.get('refresh')
        try:
            token = RefreshToken(refresh_token)
            user_id = token.payload.get('user_id')
            user = Agent.objects.all_including_deleted().filter(id=user_id).first()
            if not user or getattr(user, 'eliminado_en', None) or not getattr(user, 'is_active', False):
                try:
                    token.blacklist()
                except Exception:
                    pass
                code = 'account_deleted' if not user or getattr(user, 'eliminado_en', None) else 'account_inactive'
                response = Response({
                    'detail': 'La cuenta fue eliminada o ya no esta activa.',
                    'code': code,
                }, status=status.HTTP_401_UNAUTHORIZED)
                return _delete_refresh_cookie(response)
        except Exception:
            pass

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        refresh = response.data.get('refresh') if getattr(response, 'data', None) else None
        if refresh:
            _set_refresh_cookie(response, refresh)
            response.data.pop('refresh', None)
        return response

class CustomTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'detail': 'Tu IP ha sido bloqueada. Contacta al soporte.'}, status=status.HTTP_403_FORBIDDEN)

        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            refresh = response.data.get('refresh')
            if refresh:
                _set_refresh_cookie(response, refresh)
                response.data.pop('refresh', None)
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

@api_view(['POST'])
@permission_classes([AllowAny])
def request_trial_token(request):
    return Response({
        "error": "trial_token_request_disabled",
        "message": "Los tokens gratis solo pueden ser generados desde el Admin Dashboard.",
    }, status=status.HTTP_410_GONE)

    from django.conf import settings
    from .tasks import send_otp_email_async
    email = str(request.data.get('email') or '').strip().lower()
    logger.info("[TRIAL_TOKEN] request_trial_token solicitado email=%s", email)

    if not email:
        return Response({
            "error": "email_required",
            "message": "IngresÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ un email para recibir el cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo.",
        }, status=status.HTTP_400_BAD_REQUEST)

    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return Response({
            "error": "invalid_email",
            "message": "IngresÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ un email vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido para el envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o de respaldo.",
        }, status=status.HTTP_400_BAD_REQUEST)

    if email and Agent.objects.filter(email=email).exists():
        return Response({
            "error": "email_taken",
            "message": "Este email ya estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ asociado a una cuenta existente.",
        }, status=status.HTTP_409_CONFLICT)

    # Generar cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo de acceso
    code = AccessCode.generate_code()
    trial_days = 30
    access_code_obj = AccessCode.objects.create(
        code=code,
        trial_days=trial_days,
        assigned_phone=None,
        assigned_email=email or None,
        notes=f"Solicitado token por email={email or '-'}",
    )
    _notify_admin_trial_token_request(access_code_obj, email)

    # Enviar token por email usando el sender robusto de OTP
    sent = False
    send_error = None
    channel = None
    email_error = None
    try:
        logger.info("[TRIAL_TOKEN] enviando email via send_otp_email_async a=%s", email)
        # Se ejecuta sync para no depender de worker en este paso.
        result = send_otp_email_async(email, code)
        result_str = str(result or '').lower()
        if result_str.startswith('sent:'):
            sent = True
            channel = 'email'
        else:
            email_error = str(result)
            send_error = email_error
    except Exception as e:
        email_error = str(e)
        send_error = email_error

    logger.info(
        "[TRIAL_TOKEN] envio email=%s sent=%s channel=%s error=%s",
        email,
        sent,
        channel,
        send_error,
    )

    response_data = {
        "sent": sent,
        "message": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo enviado por email." if channel == 'email' else "No se pudo enviar el cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo por email.",
        "trial_days": trial_days,
        "email": email or None,
        "channel": channel,
    }

    if send_error:
        response_data["send_error"] = send_error
    if email_error:
        response_data["email_error"] = email_error

    if settings.DEBUG:
        response_data["code"] = code

    if not sent:
        return Response(response_data, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(response_data)
@api_view(['POST'])
@permission_classes([AllowAny])
def validate_access_code(request):
    code = str(request.data.get('access_code') or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{6}', code):
        return Response({
            "valid": False,
            "error": "access_code_required",
            "message": "IngresÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ un codigo promocional valido de 6 caracteres.",
        }, status=status.HTTP_400_BAD_REQUEST)

    access_code = AccessCode.objects.filter(code=code).first()
    if not access_code or not access_code.can_redeem():
        return Response({
            "valid": False,
            "error": "access_code_invalid",
            "message": "El codigo no existe, ya fue usado o no esta disponible.",
        }, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        "valid": True,
        "access_code": code,
        "trial_days": access_code.trial_days or 30,
    })


class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        from datetime import timedelta
        from django.utils import timezone
        email = request.data.get('email', '').strip().lower()
        signup_type = str(request.data.get('signup_type') or 'free').strip().lower()
        if signup_type not in ('free', 'paid'):
            signup_type = 'free'
        access_code_raw = str(request.data.get('access_code') or '').strip().upper()
        if signup_type == 'free' and not re.fullmatch(r'[A-Z0-9]{6}', access_code_raw):
            return Response({
                "error": "access_code_required",
                "message": "Necesitas un codigo de acceso valido para activar la prueba Starter.",
            }, status=status.HTTP_400_BAD_REQUEST)
        
        ip = get_client_ip(request)
        if BannedIP.objects.filter(ip_address=ip).exists():
            return Response({'error': 'Tu IP ha sido bloqueada. No podÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s crear cuentas.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Verificar blacklist de emails baneados permanentemente
        from .models import Agent, BannedEmail
        if BannedEmail.objects.filter(email=email).exists():
            return Response({"error": "Esta cuenta ha sido inhabilitada permanentemente. No podÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s registrarte con este email."}, status=403)
        
        # Validar email duplicado
        if Agent.objects.filter(email=email).exists():
            return Response({"error": "Este email ya estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ registrado. ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¿Olvidaste tu contraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a?"}, status=400)

        # Validar telÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fono duplicado (si se envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a)
        telefono_raw = str(request.data.get('telefono') or '').strip()
        if telefono_raw:
            digits_only = re.sub(r'\D', '', telefono_raw)
            if digits_only:
                if not telefono_raw.startswith('+') and digits_only.startswith('54'):
                    telefono_normalizado = '+' + digits_only
                elif not telefono_raw.startswith('+'):
                    telefono_normalizado = '+54' + digits_only
                else:
                    telefono_normalizado = telefono_raw

                if Agent.objects.filter(telefono=telefono_normalizado).exists():
                    return Response({
                        "error": "phone_taken",
                        "message": "Este nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºmero de telÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fono ya estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ asociado a una cuenta existente.",
                    }, status=status.HTTP_409_CONFLICT)

        otp_verificado = OTPCode.objects.filter(
            email=email,
            verified=True,
            creado_en__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        if not otp_verificado:
            return Response({"error": "DebÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s verificar tu email primero"}, status=400)

        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                access_code = None
                if signup_type == 'free':
                    access_code = AccessCode.objects.select_for_update().filter(code=access_code_raw).first()
                    if not access_code or not access_code.can_redeem(email=email):
                        return Response({
                            "error": "access_code_invalid",
                            "message": "El codigo de acceso no existe, ya fue usado o no esta disponible.",
                        }, status=status.HTTP_400_BAD_REQUEST)

                user = serializer.save()
                now_ts = timezone.now()
                if signup_type == 'free':
                    user.plan_nombre = 'starter'
                    trial_ends_at = now_ts + timedelta(days=access_code.trial_days or 30)
                    user.plan_activo = True
                    user.plan_seleccionado = True
                    user.free_trial_started_at = now_ts
                    user.free_trial_ends_at = trial_ends_at
                else:
                    user.plan_nombre = 'starter'
                    user.plan_activo = False
                    user.plan_seleccionado = False
                    user.free_trial_started_at = None
                    user.free_trial_ends_at = None
                user.last_login_ip = ip
                user.last_login_user_agent = request.META.get('HTTP_USER_AGENT', '')
                user.save(update_fields=[
                    'plan_nombre', 'plan_activo', 'plan_seleccionado',
                    'free_trial_started_at', 'free_trial_ends_at',
                    'last_login_ip', 'last_login_user_agent', 'updated_at',
                ])

                if access_code:
                    access_code.is_active = False
                    access_code.redeemed_by = user
                    access_code.redeemed_at = now_ts
                    access_code.save(update_fields=['is_active', 'redeemed_by', 'redeemed_at', 'updated_at'])

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

                refresh = RefreshToken.for_user(user)
                response = Response({
                    'access': str(refresh.access_token),
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'nombre': user.nombre,
                        'is_staff': user.is_staff,
                        'plan_nombre': user.plan_nombre,
                        'plan_activo': user.plan_activo,
                        'plan_seleccionado': user.plan_seleccionado,
                        'free_trial_started_at': user.free_trial_started_at,
                        'free_trial_ends_at': user.free_trial_ends_at,
                        'signup_type': signup_type,
                        'requires_payment': signup_type == 'paid',
                    },
                }, status=status.HTTP_201_CREATED)
                return _set_refresh_cookie(response, str(refresh))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME)
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                logger.info("No se pudo blacklistear refresh token durante logout")
        response = Response(status=status.HTTP_205_RESET_CONTENT)
        return _delete_refresh_cookie(response)


def _blacklist_refresh_tokens_for_user(user):
    try:
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
    except Exception:
        return 0

    blacklisted = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        if created:
            blacklisted += 1
    return blacklisted


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def _legacy_cambiar_password_current_password(request):
    current_password = request.data.get('current_password') or ''
    new_password = request.data.get('new_password') or ''

    if not current_password or not new_password:
        return Response({"error": "ContraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a actual y nueva contraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a requeridas"}, status=status.HTTP_400_BAD_REQUEST)
    if not request.user.check_password(current_password):
        return Response({"error": "La contraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a actual no es correcta"}, status=status.HTTP_400_BAD_REQUEST)
    if len(new_password) < 8:
        return Response({"error": "La nueva contraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a debe tener al menos 8 caracteres"}, status=status.HTTP_400_BAD_REQUEST)
    if current_password == new_password:
        return Response({"error": "La nueva contraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a debe ser distinta a la actual"}, status=status.HTTP_400_BAD_REQUEST)

    request.user.set_password(new_password)
    request.user.save(update_fields=['password', 'updated_at'])

    # Invalidamos refresh tokens anteriores y emitimos uno nuevo para mantener esta sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n activa.
    blacklisted = _blacklist_refresh_tokens_for_user(request.user)
    refresh = RefreshToken.for_user(request.user)
    response = Response({
        "mensaje": "ContraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a actualizada correctamente",
        "access": str(refresh.access_token),
        "sessions_closed": blacklisted,
    }, status=status.HTTP_200_OK)
    return _set_refresh_cookie(response, str(refresh))


def _password_validation_error(new_password, user):
    if not new_password:
        return Response({"error": "Nueva contrasena requerida"}, status=status.HTTP_400_BAD_REQUEST)
    if len(new_password) < 8:
        return Response({"error": "La nueva contrasena debe tener al menos 8 caracteres"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        from django.contrib.auth.password_validation import validate_password
        validate_password(new_password, user=user)
    except Exception as exc:
        return Response({
            "error": "password_insegura",
            "detalle": list(getattr(exc, 'messages', [str(exc)])),
        }, status=status.HTTP_400_BAD_REQUEST)
    return None


def _password_changed_response(user):
    blacklisted = _blacklist_refresh_tokens_for_user(user)
    refresh = RefreshToken.for_user(user)
    response = Response({
        "mensaje": "Contrasena actualizada correctamente",
        "access": str(refresh.access_token),
        "sessions_closed": blacklisted,
    }, status=status.HTTP_200_OK)
    return _set_refresh_cookie(response, str(refresh))


def _create_and_send_recovery_otp(email, debug_email=None):
    from django.conf import settings
    import secrets

    recent = OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        creado_en__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    if recent >= 3:
        return Response({"error": "Demasiados intentos. Espera 15 minutos."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    code = str(secrets.randbelow(900000) + 100000)
    OTPCode.objects.create(
        email=email,
        code_hash=OTPCode.hash_code(code),
        expires_at=timezone.now() + timedelta(minutes=10),
        tipo="recuperacion",
    )

    sent_mode = None
    try:
        from .tasks import send_otp_email_async
        sent_mode = str(send_otp_email_async(email, code))
        print(f"[OTP-RECOV] Resultado envio a {email}: {sent_mode}", flush=True)
    except Exception as exc:
        print(f"[OTP-RECOV] ERROR envio: {type(exc).__name__}: {exc}", flush=True)
        sent_mode = f'error:{type(exc).__name__}'

    if not str(sent_mode or '').startswith('sent:'):
        return Response({
            "error": "email_send_failed",
            "message": "No se pudo enviar el codigo por email. Intenta de nuevo en unos minutos.",
            "email": debug_email if settings.DEBUG else None,
            "_mode": sent_mode if settings.DEBUG else None,
        }, status=status.HTTP_502_BAD_GATEWAY)

    return None


def _find_latest_recovery_otp(email):
    return OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        verified=False
    ).order_by('-creado_en').first()


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cambiar_password(request):
    current_password = request.data.get('current_password') or ''
    new_password = request.data.get('new_password') or ''
    codigo = (request.data.get('codigo') or request.data.get('code') or '').strip()

    if codigo:
        validation_error = _password_validation_error(new_password, request.user)
        if validation_error:
            return validation_error
        if request.user.check_password(new_password):
            return Response({"error": "La nueva contrasena debe ser distinta a la actual"}, status=status.HTTP_400_BAD_REQUEST)

        otp = _find_latest_recovery_otp(request.user.email)
        if not otp:
            return Response({"error": "Codigo invalido o ya utilizado"}, status=status.HTTP_400_BAD_REQUEST)
        if otp.is_expired():
            return Response({"error": "Codigo expirado. Pedi uno nuevo."}, status=status.HTTP_400_BAD_REQUEST)
        if otp.attempts >= 5:
            return Response({"error": "Demasiados intentos. Pedi un nuevo codigo."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        if not otp.is_valid(codigo):
            otp.attempts += 1
            otp.save(update_fields=['attempts'])
            return Response({"error": "Codigo incorrecto"}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save(update_fields=['password', 'updated_at'])
        otp.verified = True
        otp.save(update_fields=['verified'])
        return _password_changed_response(request.user)

    if not current_password or not new_password:
        return Response({"error": "Contrasena actual y nueva contrasena requeridas"}, status=status.HTTP_400_BAD_REQUEST)
    if not request.user.check_password(current_password):
        return Response({"error": "La contrasena actual no es correcta"}, status=status.HTTP_400_BAD_REQUEST)
    validation_error = _password_validation_error(new_password, request.user)
    if validation_error:
        return validation_error
    if current_password == new_password:
        return Response({"error": "La nueva contrasena debe ser distinta a la actual"}, status=status.HTTP_400_BAD_REQUEST)

    request.user.set_password(new_password)
    request.user.save(update_fields=['password', 'updated_at'])
    return _password_changed_response(request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def password_change_code(request):
    email = (request.user.email or '').strip().lower()
    if not email:
        return Response({"error": "Tu cuenta no tiene email asociado"}, status=status.HTTP_400_BAD_REQUEST)

    send_error = _create_and_send_recovery_otp(email, debug_email=email)
    if send_error:
        return send_error
    return Response({"mensaje": "Codigo enviado a tu email"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_all(request):
    blacklisted = _blacklist_refresh_tokens_for_user(request.user)
    response = Response({"mensaje": "Sesiones cerradas", "sessions_closed": blacklisted}, status=status.HTTP_200_OK)
    return _delete_refresh_cookie(response)

class PropertyViewSet(viewsets.ModelViewSet):
    """Stub ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Property fue eliminado en v2.0. Se mantiene para compatibilidad con el router."""
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
@require_active_plan
def generar_guion(request):
    import json as _json
    data = request.data
    blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
    if blocked_media_response:
        return blocked_media_response
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
            'min_total_words': 190,
            'max_total_words': 330,
            'scene_min_words': 24,
            'scene_max_words': 55,
            'scene_style': '2 a 3 frases por escena, con descripcion sensorial y argumento comercial concreto',
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
            'scene_style': '1 frase breve por escena, directa y de alto impacto',
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
    tipo_lower = str(tipo).lower()
    is_land = any(x in tipo_lower for x in ['terreno', 'lote', 'lot', 'land'])
    ciudad = data.get('ciudad', '')
    pais = data.get('pais', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    recamaras = str(data.get('recamaras', '') or data.get('habitaciones', ''))
    banos = str(data.get('banos', '') or data.get('bathrooms', ''))
    voz = normalize_elevenlabs_voice_choice(data.get('voz', 'femenina'))
    tono = data.get('tono', 'profesional')
    contexto_adicional = data.get('contextoAdicional', '')

    tono_map = {
        'profesional': 'profesional y formal, transmite confianza sin sonar rigido',
        'lujo': 'sofisticado, aspiracional y sensorial',
        'energetico': 'dinamico, directo y de alto impacto',
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])

    narrador_map = {
        'masculina': 'voz masculina: firme, segura y confiable',
        'femenina': 'voz femenina: calida, cercana y profesional',
        'energetica': 'voz energetica: vibrante, directa y de alto impacto',
        'lujosa': 'voz lujosa: pausada, sofisticada, sensorial y aspiracional',
        'personalizada': 'voz personalizada: respetar el estilo indicado por el usuario',
    }
    narrador_instrucciones = narrador_map.get(voz, narrador_map['femenina'])

    contexto_extra = f"\nENFOQUE ADICIONAL: {contexto_adicional}" if contexto_adicional else ''
    scene_names_hint = ', '.join(rules['scene_names'])

    def _fallback_escenas():
        if tipo_video == 'tour':
            if is_land:
                return [
                    {'nombre': 'Gancho', 'texto': f'Conocé este {tipo} en {ciudad}, una oportunidad para evaluar con calma por ubicación, superficie y potencial de desarrollo.', 'icono': '📈'},
                    {'nombre': 'Ubicación', 'texto': f'El entorno de {ciudad} permite pensar en un proyecto con buena conexión, servicios cercanos y proyección de valorización.', 'icono': '📍'},
                    {'nombre': 'Superficie', 'texto': f'La superficie disponible abre posibilidades para construir, invertir o planificar un desarrollo adaptado a tus objetivos.', 'icono': '📐'},
                    {'nombre': 'Potencial', 'texto': 'Es una alternativa interesante para quien busca tierra con margen de crecimiento y visión de mediano plazo.', 'icono': '💡'},
                    {'nombre': 'Inversión', 'texto': f'Con un valor de referencia de {moneda} {precio}, este terreno puede convertirse en una decisión estratégica.', 'icono': '📈'},
                    {'nombre': 'Recorrido', 'texto': 'Recorrerlo permite entender mejor sus accesos, orientación, entorno inmediato y posibilidades reales de uso.', 'icono': '🚶'},
                    {'nombre': 'Cierre', 'texto': 'Escribinos para recibir más información, resolver dudas y coordinar una visita personalizada al lugar.', 'icono': '📞'},
                ]
            return [
                {'nombre': 'Gancho', 'texto': f'Bienvenido a esta {tipo} en {ciudad}, una propiedad pensada para disfrutarse desde el primer recorrido.', 'icono': '🏠'},
                {'nombre': 'Fachada y entorno', 'texto': 'La primera impresión combina presencia, ubicación y una propuesta visual clara para vivir o invertir.', 'icono': '🌇'},
                {'nombre': 'Zona social', 'texto': 'Los espacios principales ofrecen amplitud, circulación cómoda y una atmósfera ideal para compartir cada día.', 'icono': '🛋️'},
                {'nombre': 'Cocina y detalles', 'texto': 'La distribución acompaña una vida práctica, con detalles que elevan la experiencia y simplifican la rutina.', 'icono': '🍳'},
                {'nombre': 'Habitaciones', 'texto': f'Cuenta con {recamaras or "varios"} dormitorios y {banos or "baños funcionales"}, pensados para descanso, privacidad y confort.', 'icono': '🛏️'},
                {'nombre': 'Beneficio de inversion', 'texto': f'Por {moneda} {precio}, esta propiedad reúne ubicación, prestaciones y potencial de valorización.', 'icono': '📈'},
                {'nombre': 'Cierre con CTA', 'texto': 'Contactanos para recibir la ficha completa y coordinar una visita personalizada.', 'icono': '📞'},
            ]

        if is_land:
            return [
                {'nombre': 'Gancho', 'texto': f'{tipo} en {ciudad}: una oportunidad concreta para invertir o desarrollar.', 'icono': 'ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡'},
                {'nombre': 'Potencial', 'texto': 'Superficie, ubicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y proyecciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n se combinan para pensar un proyecto con valor futuro.', 'icono': 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€šÃ‚Â'},
                {'nombre': 'UbicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n', 'texto': f'En {ciudad}, con entorno y conectividad para evaluar una decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n estratÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©gica.', 'icono': 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€šÃ‚Â'},
                {'nombre': 'CTA', 'texto': f'Valor de referencia {moneda} {precio}. Escribinos y coordinamos una visita.', 'icono': 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€¦Ã‚Â¾'},
            ]
        return [
            {'nombre': 'Gancho', 'texto': f'{tipo} en {ciudad}: una propiedad que destaca desde el primer vistazo.', 'icono': 'ÃƒÆ’Ã‚Â¢Ãƒâ€¦Ã‚Â¡Ãƒâ€šÃ‚Â¡'},
            {'nombre': 'Diferencial', 'texto': f'{recamaras or "Ambientes"} dormitorios, {banos or "baÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±os"} y espacios pensados para vivir mejor.', 'icono': 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€šÃ‚ÂÃƒâ€šÃ‚Â '},
            {'nombre': 'UbicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n', 'texto': f'UbicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ctica en {ciudad}, cerca de servicios y puntos clave.', 'icono': 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€šÃ‚Â'},
            {'nombre': 'CTA', 'texto': f'Precio {moneda} {precio}. Consultanos hoy y coordinamos una visita.', 'icono': 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œÃƒâ€¦Ã‚Â¾'},
        ]

    def _fallback_response(reason):
        escenas = _fallback_escenas()
        return Response({
            'escenas': escenas,
            'tipo_video': tipo_video,
            'source': 'fallback',
            'meta': {
                'reason': reason,
                'required_scenes': rules['required_scenes'],
                'actual_scenes': len(escenas),
                'actual_total_words': sum(_count_words(e.get('texto', '')) for e in escenas),
            },
        }, status=status.HTTP_200_OK)

    prompt = f"""Sos copywriter inmobiliario experto en videos cortos para redes.
Genera un guion para formato {tipo_video.upper()}.
{'Enfocate en inversiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, superficie, ubicaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, potencial de desarrollo y valorizaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n. No menciones recÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡maras ni ambientes si es terreno/lote.' if is_land else ''}

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
- Estilo por escena: {rules['scene_style']}
- Escenas sugeridas (orden recomendado): {scene_names_hint}
- No repitas frases entre escenas
- Salida SOLO en JSON valido (sin markdown, sin texto extra)

FORMATO:
{{"escenas": [
  {{"nombre":"...","texto":"...","icono":"ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â½Ãƒâ€šÃ‚Â¬"}}
]}}
"""

    def _count_words(text):
        return len(re.findall(r"\b[\w\u00C0-\u017F']+\b", str(text), flags=re.UNICODE))

    def _clean_scene_text(text):
        cleaned = str(text or '').strip()
        cleaned = cleaned.replace('**', '')
        cleaned = re.sub(r'^\s*[-*ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢]+\s*', '', cleaned)
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
                icono = _clean_scene_text(escena.get('icono') or 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â½Ãƒâ€šÃ‚Â¬')
            elif isinstance(escena, str):
                texto = _clean_scene_text(escena)
                nombre = f'Escena {idx}'
                icono = 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â½Ãƒâ€šÃ‚Â¬'
            else:
                continue

            if texto:
                normalized.append({
                    'nombre': nombre or f'Escena {idx}',
                    'texto': texto,
                    'icono': icono[:2] if icono else 'ÃƒÆ’Ã‚Â°Ãƒâ€¦Ã‚Â¸Ãƒâ€¦Ã‚Â½Ãƒâ€šÃ‚Â¬',
                })

        return normalized

    def _validate_escenas(escenas):
        if len(escenas) < rules['required_scenes']:
            return False, f"Escenas insuficientes: {len(escenas)}/{rules['required_scenes']}", None

        limited = escenas[:rules['required_scenes']]
        total_words = sum(_count_words(e.get('texto', '')) for e in limited)
        too_short = [
            idx + 1
            for idx, escena in enumerate(limited)
            if _count_words(escena.get('texto', '')) < max(4, rules['scene_min_words'] - 2)
        ]

        if too_short:
            return False, f"Escenas demasiado cortas: {too_short}", None

        if total_words < rules['min_total_words']:
            return False, f"Palabras insuficientes: {total_words}/{rules['min_total_words']}", None

        return True, '', {
            'escenas': limited,
            'total_words': total_words,
        }

    def _repair_with_cerebras(raw_text, reason):
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
            future = ex.submit(
                smart_call,
                repair_prompt,
                retries=1,
                agente=request.user,
                task='video_script',
                listado_id=data.get('listado_id') or data.get('listadoId'),
            )
            return future.result(timeout=25)

    try:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(
                smart_call,
                prompt,
                retries=1,
                agente=request.user,
                task='video_script',
                listado_id=data.get('listado_id') or data.get('listadoId'),
            )
            raw_response = future.result(timeout=25)
    except APIKeyUnavailableError as e:
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_guion')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        return _quota_error_response(e, user=request.user, source='generar_guion')
    except Exception as e:
        logger.exception("Error llamando Cerebras en generar_guion")
        return _fallback_response(f'cerebras_no_disponible: {str(e)[:180]}')

    if not raw_response:
        return _fallback_response('cerebras_sin_respuesta')

    attempts = [str(raw_response).strip()]
    final_validation = None
    final_reason = 'sin detalle'

    for attempt_idx in range(2):
        candidate_text = attempts[-1]
        parsed = _parse_json_flexible(candidate_text)

        if parsed is None:
            final_reason = 'Cerebras no devolvio JSON parseable'
            if attempt_idx == 0:
                try:
                    repaired = _repair_with_cerebras(candidate_text, final_reason)
                    if repaired:
                        attempts.append(str(repaired).strip())
                        continue
                except APIKeyUnavailableError as e:
                    return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_texto_escena')
                except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
                    return _quota_error_response(e, user=request.user, source='generar_texto_escena')
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
                repaired = _repair_with_cerebras(_json.dumps({'escenas': escenas}, ensure_ascii=False), reason)
                if repaired:
                    attempts.append(str(repaired).strip())
                    continue
            except APIKeyUnavailableError as e:
                return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_texto_escena')
            except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
                return _quota_error_response(e, user=request.user, source='generar_texto_escena')
            except Exception:
                pass

    if not final_validation:
        return _fallback_response(f'respuesta_ia_invalida: {final_reason}')

    escenas_finales = final_validation['escenas']
    total_words = final_validation['total_words']

    from .plan_utils import registrar_uso
    registrar_uso(request.user, 'ai')
    return Response(
        {
            'escenas': escenas_finales,
            'tipo_video': tipo_video,
            'source': 'cerebras',
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
@require_active_plan
def generar_listado(request):
    # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
    # if not puede_generar(request.user, 'ai'):
    #     return Response({
    #         "error": "limite_alcanzado", 
    #         "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)
            
    prompt_text = request.data.get("prompt", "")
    if not prompt_text:
        return Response({"error": "No prompt provided. Please pass a 'prompt' field in the JSON body."}, status=status.HTTP_400_BAD_REQUEST)
        
    system_prompt = "Sos un as copywriter de real estate. EscribÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ descripciones profesionales, persuasivas y completas (listados) para propiedades en venta o alquiler en espaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±ol."

    result = smart_call(prompt_text, retries=1, agente=request.user, system_prompt=system_prompt, task='listing_description')
    if not result:
        return Response({
            "error": "IA no disponible",
            "detalle": "Cerebras no devolvio respuesta."
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
        property_usage = UsageLog.objects.filter(agent=user, tipo='property')
        listados_este_mes = property_usage.filter(fecha__gte=start_of_month).count()
        total_generados = property_usage.count()
        
        videos_creados = listados.aggregate(total_videos=Sum('videos_creados'))['total_videos'] or 0

        listados_recientes = [
            _serialize_listing_summary(listado)
            for listado in listados.order_by('-creado_en')[:8]
        ]

        susc = get_suscripcion(user)
        plan = susc.plan
        from .plan_utils import get_daily_listing_quota
        daily_listing_quota = get_daily_listing_quota(user)

        return Response({
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": _safe_persisted_media_url(getattr(user, 'logo_url', None)),
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
            },
            "daily_listing_quota": daily_listing_quota,
        })

class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        default_agent = _get_default_commercial_agent(user)
        asociados = AgentAssociation.objects.filter(agente=user).select_related('asociado')
        settings_data = _normalize_user_settings(getattr(user, 'settings', None))
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": _safe_persisted_media_url(getattr(user, 'logo_url', None)),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token_set": bool(getattr(user, 'meta_access_token', None)),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "settings": settings_data,
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
            "requires_payment": user.plan_activo is False,
        })

    def put(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        data = request.data

        agency_present, agency_value = _extract_first_present(data, 'nombre_inmobiliaria', 'nombreInmobiliaria')
        website_present, website_value = _extract_first_present(data, 'sitio_web', 'sitioWeb')
        if agency_present or website_present:
            conflict_response, clean_agency_name, clean_website = _validate_unique_agency_identity(
                user,
                agency_name=agency_value if agency_present else None,
                website=website_value if website_present else None,
                account_type=data.get('agencia', getattr(user, 'agencia', '')),
            )
            if conflict_response:
                return conflict_response

        if agency_present:
            user.nombre_inmobiliaria = clean_agency_name

        logo_present, logo_value, logo_error = _resolve_profile_logo_input(data, user)
        if logo_error:
            return logo_error
        if logo_present:
            user.logo_url = logo_value

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
        if website_present:
            user.sitio_web = clean_website
        if 'bio' in data:
            user.bio = data['bio']
        if 'settings' in data:
            user.settings = _normalize_user_settings(data.get('settings'), getattr(user, 'settings', None))
            
        user.save()

        default_agent = _get_default_commercial_agent(user)
        asociados = AgentAssociation.objects.filter(agente=user).select_related('asociado')
        settings_data = _normalize_user_settings(getattr(user, 'settings', None))
        return Response({
            "message": "Perfil actualizado exitosamente",
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "agencia": getattr(user, 'agencia', None),
            "logo_url": _safe_persisted_media_url(getattr(user, 'logo_url', None)),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "meta_access_token_set": bool(getattr(user, 'meta_access_token', None)),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "settings": settings_data,
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

    # --- Accept flexible field names from frontend ---
    incoming = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
    # Map common frontend key variants
    _alias_map = {
        'name': 'nombre',
        'role': 'rol',
        'phone': 'telefono_e164',
        'telefono': 'telefono_e164',
        'photo_url': 'foto_url',
        'fotoUrl': 'foto_url',
    }
    for alias, canonical in _alias_map.items():
        if alias in incoming and canonical not in incoming:
            incoming[canonical] = incoming.pop(alias)

    # Default nombre to user's name when missing
    if not incoming.get('nombre'):
        incoming['nombre'] = getattr(request.user, 'nombre', None) or request.user.email.split('@')[0]

    serializer = ComercialAgentProfileSerializer(data=incoming)
    serializer.is_valid(raise_exception=True)

    from django.db import IntegrityError
    try:
        with transaction.atomic():
            created = serializer.save(owner=request.user)

            if created.is_default:
                ComercialAgentProfile.objects.filter(owner=request.user, activo=True).exclude(id=created.id).update(is_default=False)
            elif not ComercialAgentProfile.objects.filter(owner=request.user, activo=True, is_default=True).exclude(id=created.id).exists():
                created.is_default = True
                created.save(update_fields=['is_default'])
    except IntegrityError as exc:
        if 'unique_default_commercial_agent_per_owner' in str(exc):
            # Another default already exists — retry without is_default
            logger.warning(f"[CommercialAgent] UniqueConstraint hit for user {request.user.id}, retrying without is_default")
            incoming['is_default'] = False
            serializer = ComercialAgentProfileSerializer(data=incoming)
            serializer.is_valid(raise_exception=True)
            with transaction.atomic():
                created = serializer.save(owner=request.user)
        else:
            logger.exception(f"[CommercialAgent] IntegrityError creating agent for user {request.user.id}")
            return Response({'error': 'Error de integridad al crear agente comercial.', 'detail': str(exc)[:200]}, status=status.HTTP_409_CONFLICT)

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


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def commercial_agent_photo(request, agent_id):
    profile = get_object_or_404(ComercialAgentProfile, id=agent_id, owner=request.user, activo=True)

    if request.method == 'DELETE':
        assets = profile.media_assets.filter(kind='agent_photo', is_active=True)
        for asset in assets:
            try:
                destroy_kwargs = {'resource_type': asset.resource_type or 'image'}
                for key_obj in AlmacenamientoCloudinary._get_pool_keys():
                    creds = AlmacenamientoCloudinary._parse_cloudinary_url(key_obj.api_key)
                    if creds and creds.get('cloud_name') == asset.cloud_name:
                        destroy_kwargs.update(creds)
                        break
                cloudinary.uploader.destroy(asset.public_id, **destroy_kwargs)
            except Exception as e:
                logger.warning(f"[AgentPhoto] No se pudo eliminar Cloudinary {asset.public_id}: {e}")
        assets.update(is_active=False)
        profile.foto_url = ''
        profile.save(update_fields=['foto_url', 'updated_at'])
        return Response({'ok': True, 'agent': ComercialAgentProfileSerializer(profile).data}, status=status.HTTP_200_OK)

    file_obj = request.FILES.get('file') or request.FILES.get('foto') or request.FILES.get('avatar')
    if not file_obj:
        return Response({'error': 'Archivo requerido en campo file.'}, status=status.HTTP_400_BAD_REQUEST)
    content_type = str(getattr(file_obj, 'content_type', '') or '').lower()
    if content_type and not content_type.startswith('image/'):
        return Response({'error': 'El archivo debe ser una imagen.'}, status=status.HTTP_400_BAD_REQUEST)

    metadata = AlmacenamientoCloudinary.guardar_avatar_metadata(file_obj, user_id=request.user.id)
    if not metadata or not metadata.get('public_id'):
        return Response({'error': 'No se pudo subir la foto del agente.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    profile.media_assets.filter(kind='agent_photo', is_active=True).update(is_active=False)
    asset = AgentMediaAsset.objects.create(
        owner=request.user,
        profile=profile,
        kind='agent_photo',
        cloud_name=metadata.get('cloud_name') or metadata.get('cloudinary_account') or '',
        public_id=metadata.get('public_id') or '',
        resource_type=metadata.get('resource_type') or 'image',
        secure_url=metadata.get('secure_url') or metadata.get('url') or '',
        bytes=metadata.get('bytes') or 0,
        format=metadata.get('format') or '',
        folder=metadata.get('folder') or '',
        original_filename=getattr(file_obj, 'name', '') or metadata.get('original_filename') or '',
        version=metadata.get('version') or '',
    )
    profile.foto_url = asset.secure_url or metadata.get('url') or ''
    profile.save(update_fields=['foto_url', 'updated_at'])
    return Response({
        'ok': True,
        'asset': AgentMediaAssetSerializer(asset).data,
        'agent': ComercialAgentProfileSerializer(profile).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
@require_pro_feature('organic_content')
def content_preferences_detail(request):
    prefs, _ = UserContentPreference.objects.get_or_create(owner=request.user)
    if request.method == 'GET':
        return Response(UserContentPreferenceSerializer(prefs).data, status=status.HTTP_200_OK)
    serializer = UserContentPreferenceSerializer(prefs, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(owner=request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@require_pro_feature('crm')
def crm_clients_collection(request):
    if request.method == 'GET':
        clients = CRMClient.objects.filter(owner=request.user).order_by('-updated_at')
        estado = request.query_params.get('estado')
        if estado:
            clients = clients.filter(estado=estado)
        serializer = CRMClientSerializer(clients, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = CRMClientSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    created = serializer.save(owner=request.user)
    return Response(CRMClientSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@require_pro_feature('crm')
def crm_client_detail(request, client_id):
    client = get_object_or_404(CRMClient, id=client_id, owner=request.user)

    if request.method == 'GET':
        return Response(CRMClientSerializer(client).data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        client.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = CRMClientSerializer(client, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save(owner=request.user)
    return Response(CRMClientSerializer(updated).data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def brand_templates_collection(request):
    if request.method == 'GET':
        templates = BrandTemplate.objects.filter(owner=request.user, is_active=True).order_by('-is_default', '-updated_at')
        serializer = BrandTemplateSerializer(templates, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = BrandTemplateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        created = serializer.save(owner=request.user)

        initial_tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
        if bool(request.data.get('use_base_tokens', False)) or not isinstance(initial_tokens, dict):
            initial_tokens = _default_tokens_for_base_template(created.base_template_id)
        else:
            initial_tokens = _resolve_brand_template_tokens(initial_tokens)
        initial_instructions = str(request.data.get('gemini_instructions') or '').strip()
        if not initial_instructions:
            initial_instructions = _build_template_gemini_instructions(created.name, created.base_template_id, initial_tokens)

        revision_serializer = BrandTemplateRevisionSerializer(data={
            'template': created.id,
            'tokens_json': initial_tokens,
            'gemini_instructions': initial_instructions,
            'status': 'published',
            'notes': 'Revision inicial',
        })
        revision_serializer.is_valid(raise_exception=True)
        revision_serializer.save(template=created, created_by=request.user)

        if created.is_default:
            BrandTemplate.objects.filter(owner=request.user, is_active=True).exclude(id=created.id).update(is_default=False)
        elif not BrandTemplate.objects.filter(owner=request.user, is_active=True, is_default=True).exclude(id=created.id).exists():
            created.is_default = True
            created.save(update_fields=['is_default'])

    return Response(BrandTemplateSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_clone(request):
    source_id = request.data.get('source_template_id') or request.data.get('sourceTemplateId')
    base_template_id = _normalize_template_id(request.data.get('base_template_id') or request.data.get('baseTemplateId')) or 'tech_modern'
    name = str(request.data.get('name') or 'Template duplicado').strip()[:120]
    description = request.data.get('description') or ''

    tokens = None
    if source_id:
        source_template = BrandTemplate.objects.filter(id=_parse_brand_template_id(source_id), owner=request.user, is_active=True).first()
        if source_template:
            published = source_template.revisions.filter(status='published').order_by('-revision').first()
            tokens = published.tokens_json if published else None
            base_template_id = source_template.base_template_id
    if not isinstance(tokens, dict):
        tokens = _default_tokens_for_base_template(base_template_id)
    instructions = str(request.data.get('gemini_instructions') or '').strip()

    created = BrandTemplate.objects.create(
        owner=request.user,
        name=name,
        description=description,
        base_template_id=base_template_id,
        is_default=bool(request.data.get('is_default', False)),
    )
    BrandTemplateRevision.objects.create(
        template=created,
        tokens_json=tokens,
        gemini_instructions=instructions or _build_template_gemini_instructions(name, base_template_id, tokens),
        status='published',
        created_by=request.user,
        notes='Clonado desde panel',
    )
    if created.is_default:
        BrandTemplate.objects.filter(owner=request.user, is_active=True).exclude(id=created.id).update(is_default=False)
    return Response(BrandTemplateSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def brand_template_detail(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user)

    if request.method == 'GET':
        return Response(BrandTemplateSerializer(template).data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        was_default = template.is_default
        template.is_active = False
        template.is_default = False
        template.save(update_fields=['is_active', 'is_default'])
        if was_default:
            fallback = BrandTemplate.objects.filter(owner=request.user, is_active=True).order_by('-updated_at').first()
            if fallback:
                fallback.is_default = True
                fallback.save(update_fields=['is_default'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = BrandTemplateSerializer(template, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    if updated.is_default:
        BrandTemplate.objects.filter(owner=request.user, is_active=True).exclude(id=updated.id).update(is_default=False)
    return Response(BrandTemplateSerializer(updated).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_set_default(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    BrandTemplate.objects.filter(owner=request.user, is_active=True, is_default=True).exclude(id=template.id).update(is_default=False)
    template.is_default = True
    template.save(update_fields=['is_default'])
    return Response({'ok': True, 'default_template': BrandTemplateSerializer(template).data}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def brand_template_revisions_collection(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)

    if request.method == 'GET':
        revisions = template.revisions.order_by('-revision')
        serializer = BrandTemplateRevisionSerializer(revisions, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    serializer = BrandTemplateRevisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    status_value = serializer.validated_data.get('status', 'draft')
    instructions = serializer.validated_data.get('gemini_instructions') or ''
    if not instructions:
        instructions = _build_template_gemini_instructions(
            template.name,
            template.base_template_id,
            serializer.validated_data.get('tokens_json') or default_template_tokens(),
        )
    created = serializer.save(template=template, created_by=request.user, status='draft', gemini_instructions=instructions)

    if status_value == 'published':
        template.revisions.filter(status='published').exclude(id=created.id).update(status='archived')
        created.status = 'published'
        created.save(update_fields=['status'])

    return Response(BrandTemplateRevisionSerializer(created).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_publish_revision(request, template_id, revision_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    revision = get_object_or_404(BrandTemplateRevision, id=revision_id, template=template)
    template.revisions.filter(status='published').exclude(id=revision.id).update(status='archived')
    revision.status = 'published'
    revision.save(update_fields=['status'])
    return Response({'ok': True, 'revision': BrandTemplateRevisionSerializer(revision).data}, status=status.HTTP_200_OK)


def _demo_qr_image_url():
    return generar_qr_url(
        '+541123456789',
        tipo_propiedad='Casa',
        ciudad='Miami Beach',
        operacion='Venta',
        precio='850.000',
        moneda='USD',
    )


def _brand_template_demo_context():
    return {
        'portada_url': 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1400&q=80',
        'logo_url': '',
        'operacion': 'Venta',
        'ciudad': 'Miami Beach',
        'titulo': 'Residencia premium',
        'tipoPropiedad': 'Casa',
        'moneda': 'USD',
        'precio': '850.000',
        'caracteristicas': [
            {'label': 'Dorm.', 'valor': '4'},
            {'label': 'Banos', 'valor': '3'},
            {'label': 'm2', 'valor': '320'},
            {'label': 'Coch.', 'valor': '2'},
        ],
        'agente_nombre': 'Agente LeadBook',
        'agente_telefono': '+54 11 2345 6789',
        'agencia_nombre': 'LeadBook Realty',
        'qr_url': _demo_qr_image_url(),
        'leadbook_logo_url': '',
    }


def _preview_dimensions(preview_format):
    if preview_format == 'story':
        return {'width': 1080, 'height': 1920}
    if preview_format == 'email':
        return {'width': 600, 'height': 900}
    return {'width': 1080, 'height': 1350}


def _render_brand_template_preview_html(base_template_id, tokens, preview_format='post'):
    template_id = _normalize_template_id(base_template_id) or 'tech_modern'
    resolved_tokens = _resolve_brand_template_tokens(tokens or _default_tokens_for_base_template(template_id))
    preview_format = str(preview_format or 'post').strip().lower()
    demo_context = _brand_template_demo_context()

    if preview_format == 'story':
        template_file = TEMPLATE_STORY_MAP.get(template_id, TEMPLATE_STORY_MAP['tech_modern'])
        html = render_to_string(template_file, demo_context)
    elif preview_format in ('carousel', 'carrusel'):
        preview_format = 'carousel'
        template_file = TEMPLATE_CAROUSEL_MAP.get(template_id, TEMPLATE_CAROUSEL_MAP['tech_modern'])
        carousel_context = {
            **demo_context,
            'headline': 'Residencia premium',
            'subheadline': 'Venta por USD 850.000. 320 m2, 4 hab, 3 banos. Desliza para ver la galeria.',
            'slide_number': 1,
            'total_slides': 6,
        }
        html = render_to_string(template_file, carousel_context)
    elif preview_format == 'email':
        template_file = TEMPLATE_EMAIL_MAP.get(template_id, TEMPLATE_EMAIL_MAP['tech_modern'])
        email_context = {
            'asunto': 'Residencia premium disponible',
            'logo_url': demo_context.get('logo_url', ''),
            'agenciaNombre': demo_context.get('agencia_nombre', ''),
            'tipoPropiedad': demo_context.get('tipoPropiedad', ''),
            'ciudad': demo_context.get('ciudad', ''),
            'portada_url': demo_context.get('portada_url', ''),
            'html_content': '<strong>Oportunidad destacada.</strong><br>Una propiedad pensada para vivir o invertir con alto valor percibido.',
            'moneda': demo_context.get('moneda', ''),
            'precio': demo_context.get('precio', ''),
            'operacion': demo_context.get('operacion', ''),
            'agenteNombre': demo_context.get('agente_nombre', ''),
            'agenteRol': 'Asesor Comercial',
            'agenteTelefono': demo_context.get('agente_telefono', ''),
            'agenteTelefonoDisplay': demo_context.get('agente_telefono', ''),
            'agenteEmail': 'agente@leadbook.com',
            'whatsapp_url': '',
        }
        html = render_to_string(template_file, email_context)
    else:
        preview_format = 'post'
        template_file = TEMPLATE_POST_MAP.get(template_id, TEMPLATE_POST_MAP['tech_modern'])
        html = render_to_string(template_file, demo_context)

    html = _apply_template_tokens_to_html(html, template_id, resolved_tokens)
    html = _inject_agency_brand_lockup(html, demo_context.get('logo_url', ''), demo_context.get('agencia_nombre', ''))
    return html, preview_format, resolved_tokens, _preview_dimensions(preview_format)


def _parse_json_object(text):
    source = str(text or '').strip()
    candidates = [source]
    cleaned = re.sub(r'^\s*```(?:json)?\s*', '', source, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.IGNORECASE).strip()
    if cleaned and cleaned != source:
        candidates.append(cleaned)
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
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            continue
    return None


def _is_hex_color(value):
    return isinstance(value, str) and bool(re.match(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', value.strip()))


def _sanitize_template_patch(patch):
    if not isinstance(patch, dict):
        return {}
    clean = {}
    palette = patch.get('palette') if isinstance(patch.get('palette'), dict) else {}
    clean_palette = {
        key: value.strip()
        for key, value in palette.items()
        if key in {'primary', 'secondary', 'accent', 'background', 'surface', 'text', 'muted_text', 'border'} and _is_hex_color(value)
    }
    overlay = palette.get('overlay')
    if isinstance(overlay, str) and re.match(r'^(rgba?\([^)]+\)|transparent)$', overlay.strip(), flags=re.IGNORECASE):
        clean_palette['overlay'] = overlay.strip()
    if clean_palette:
        clean['palette'] = clean_palette

    typography = patch.get('typography') if isinstance(patch.get('typography'), dict) else {}
    clean_typography = {}
    for key in ('display', 'body', 'mono'):
        if typography.get(key) in SYSTEM_FONT_IMPORT_MAP:
            clean_typography[key] = typography.get(key)
    if typography.get('title_transform') in {'uppercase', 'none'}:
        clean_typography['title_transform'] = typography.get('title_transform')
    if typography.get('letter_spacing') in {'tight', 'normal', 'wide'}:
        clean_typography['letter_spacing'] = typography.get('letter_spacing')
    if clean_typography:
        fonts = [clean_typography.get(k) for k in ('display', 'body', 'mono') if clean_typography.get(k)]
        if fonts:
            clean_typography['google_fonts'] = list(dict.fromkeys(fonts))
        clean['typography'] = clean_typography

    layout = patch.get('layout') if isinstance(patch.get('layout'), dict) else {}
    layout_allowed = {
        'logo_position': LAYOUT_POSITIONS,
        'agent_block_position': LAYOUT_POSITIONS,
        'qr_position': LAYOUT_POSITIONS,
        'style': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['layout_styles']},
        'density': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['density']},
        'border_radius': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['border_radius']},
        'image_treatment': {item['id'] for item in TEMPLATE_TOKEN_OPTIONS['image_treatment']},
    }
    clean_layout = {key: value for key, value in layout.items() if key in layout_allowed and value in layout_allowed[key]}
    if clean_layout:
        clean['layout'] = clean_layout

    copy = patch.get('copy') if isinstance(patch.get('copy'), dict) else {}
    clean_copy = {}
    if copy.get('tone') in {'premium', 'profesional', 'lujo', 'minimal'}:
        clean_copy['tone'] = copy.get('tone')
    if copy.get('emoji_density') in {'none', 'low', 'medium', 'high'}:
        clean_copy['emoji_density'] = copy.get('emoji_density')
    if copy.get('cta_style') in {'whatsapp_direct', 'soft', 'strong'}:
        clean_copy['cta_style'] = copy.get('cta_style')
    if isinstance(copy.get('hashtags'), list):
        clean_copy['hashtags'] = [str(tag)[:50] for tag in copy.get('hashtags')[:20] if str(tag or '').strip()]
    if clean_copy:
        clean['copy'] = clean_copy

    components = patch.get('components') if isinstance(patch.get('components'), dict) else {}
    clean_components = {}
    hero = components.get('hero') if isinstance(components.get('hero'), dict) else {}
    clean_hero = {}
    if hero.get('overlay_strength') in {'none', 'soft', 'medium', 'strong'}:
        clean_hero['overlay_strength'] = hero.get('overlay_strength')
    if isinstance(hero.get('show_badge'), bool):
        clean_hero['show_badge'] = hero.get('show_badge')
    if clean_hero:
        clean_components['hero'] = clean_hero
    price = components.get('price') if isinstance(components.get('price'), dict) else {}
    if price.get('size') in {'small', 'medium', 'large', 'xlarge'}:
        clean_components['price'] = {'size': price.get('size')}
    stats = components.get('stats') if isinstance(components.get('stats'), dict) else {}
    if isinstance(stats.get('show_icons'), bool):
        clean_components['stats'] = {'show_icons': stats.get('show_icons')}
    contact = components.get('contact') if isinstance(components.get('contact'), dict) else {}
    clean_contact = {}
    for key in ('show_agent_photo', 'show_qr'):
        if isinstance(contact.get(key), bool):
            clean_contact[key] = contact.get(key)
    if clean_contact:
        clean_components['contact'] = clean_contact
    if clean_components:
        clean['components'] = clean_components
    return clean


def _template_ai_patch_from_message(message, current_tokens, base_template_id, user=None):
    prompt = f"""
Actua como disenador senior de templates inmobiliarios. Convierte el pedido del usuario en un JSON seguro de tokens visuales.
No generes HTML. No inventes campos fuera del schema. Responde SOLO JSON valido.

Template base: {base_template_id}
Tokens actuales:
{json.dumps(current_tokens, ensure_ascii=False)}

Pedido del usuario:
{message}

Formato exacto:
{{
  "reply": "respuesta breve para el usuario",
  "token_patch": {{}}
}}

Campos permitidos en token_patch: palette, typography, layout, components, copy.
Valores para layout.logo_position, layout.agent_block_position y layout.qr_position: top_left, top_right, bottom_left, bottom_right.
Fuentes permitidas: {', '.join(SYSTEM_FONT_IMPORT_MAP.keys())}.
Colores solo HEX. No uses HTML ni CSS libre.
"""
    try:
        raw = smart_call(prompt, retries=1, agente=user, task='ads_json')
        parsed = _parse_json_object(raw)
        if not isinstance(parsed, dict):
            return None
        patch = _sanitize_template_patch(parsed.get('token_patch') or {})
        reply = str(parsed.get('reply') or '').strip()
        if patch:
            return {'reply': reply, 'token_patch': patch}
    except (
        APIKeyUnavailableError,
        GeminiQuotaExhaustedError,
        GeminiRateLimitedError,
        ElevenLabsQuotaExhaustedError,
        ElevenLabsRateLimitedError,
    ):
        raise
    except Exception as exc:
        logger.warning("Template Studio AI patch failed: %s", exc)
    return None


def _template_patch_from_message(message):
    text = unicodedata.normalize('NFKD', str(message or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    patch = {}

    def merge(fragment):
        nonlocal patch
        patch = _deep_merge_dict(patch, fragment)

    def requested_position(keyword, default_vertical='bottom', default_horizontal='right'):
        match = re.search(rf'{re.escape(keyword)}[^,.;&]*', text)
        segment = match.group(0) if match else text
        vertical = default_vertical
        horizontal = default_horizontal
        if any(word in segment for word in ('arriba', 'superior', 'top')):
            vertical = 'top'
        if any(word in segment for word in ('abajo', 'inferior', 'bottom')):
            vertical = 'bottom'
        if 'izquierda' in segment or 'left' in segment:
            horizontal = 'left'
        if 'derecha' in segment or 'right' in segment:
            horizontal = 'right'
        return f'{vertical}_{horizontal}'

    if any(word in text for word in ('todo negro', 'full black', 'black', 'oscuro', 'negro')):
        merge({
            'palette': {
                'primary': '#000000',
                'secondary': '#080808',
                'accent': '#d6d6d6',
                'background': '#000000',
                'surface': '#111111',
                'text': '#ffffff',
                'muted_text': '#a1a1aa',
                'border': '#2a2a2a',
                'overlay': 'rgba(0,0,0,0.72)',
            },
            'layout': {'image_treatment': 'dark', 'style': 'dark_luxury'},
            'components': {'hero': {'overlay_strength': 'strong'}},
        })
    if any(word in text for word in ('dorado', 'gold', 'oro', 'luxury')):
        merge({'palette': {'accent': '#c9a84c'}, 'copy': {'tone': 'lujo'}})
    if any(word in text for word in ('rojo', 'red', 'colorado')):
        merge({'palette': {'accent': '#ef4444'}})
    if any(word in text for word in ('blanco', 'white', 'minimal', 'limpio')):
        merge({
            'palette': {
                'primary': '#111111',
                'secondary': '#f2f2f2',
                'accent': '#111111',
                'background': '#ffffff',
                'surface': '#f7f7f7',
                'text': '#111111',
                'muted_text': '#666666',
                'border': '#dddddd',
            },
            'layout': {'style': 'minimal_light', 'image_treatment': 'normal'},
        })
    if any(word in text for word in ('azul', 'blue', 'tech', 'neon')):
        merge({'palette': {'primary': '#0d47a1', 'secondary': '#1565c0', 'accent': '#00e5ff', 'background': '#081421', 'text': '#e8f3ff'}, 'layout': {'style': 'tech_modern'}})
    if any(word in text for word in ('calido', 'tierra', 'mediterraneo', 'warm')):
        merge({'palette': {'primary': '#6b4423', 'secondary': '#8b5e3c', 'accent': '#c17f3a', 'background': '#f8f4ef', 'text': '#2c2416'}, 'layout': {'style': 'mediterranean_warm', 'image_treatment': 'warm'}})

    if 'precio' in text and any(word in text for word in ('grande', 'mas grande', 'gigante', 'large')):
        merge({'components': {'price': {'size': 'large'}}})
    if 'precio' in text and any(word in text for word in ('chico', 'pequeno', 'small')):
        merge({'components': {'price': {'size': 'small'}}})
    wants_no_qr = any(phrase in text for phrase in ('sin qr', 'ocultar qr', 'no qr', 'sin codigo qr', 'sin codigo', 'quitar qr'))
    if wants_no_qr:
        merge({'components': {'contact': {'show_qr': False}}})
    wants_qr = any(phrase in text for phrase in (
        'mostrar qr', 'con qr', 'codigo qr', 'qr visible', 'quiero qr', 'tenga qr', 'incluir qr', 'activar qr'
    ))
    if wants_qr and not wants_no_qr:
        merge({'components': {'contact': {'show_qr': True}}})
    if 'sin foto agente' in text or 'ocultar agente' in text:
        merge({'components': {'contact': {'show_agent_photo': False}}})
    if 'sin iconos' in text:
        merge({'components': {'stats': {'show_icons': False}}})
    if 'con iconos' in text:
        merge({'components': {'stats': {'show_icons': True}}})

    if 'logo' in text:
        merge({'layout': {'logo_position': requested_position('logo', 'top', 'right')}})
    if 'agente' in text:
        merge({'layout': {'agent_block_position': requested_position('agente', 'bottom', 'left')}})
    if 'qr' in text:
        merge({'layout': {'qr_position': requested_position('qr', 'bottom', 'right')}})

    if any(word in text for word in ('redondo', 'rounded', 'bordes grandes')):
        merge({'layout': {'border_radius': 'strong'}})
    if any(word in text for word in ('sin bordes', 'bordes rectos', 'square')):
        merge({'layout': {'border_radius': 'none'}})
    if any(word in text for word in ('espaciado', 'aire', 'spacious')):
        merge({'layout': {'density': 'spacious'}})
    if any(word in text for word in ('compacto', 'compact')):
        merge({'layout': {'density': 'compact'}})

    if any(word in text for word in ('bebas', 'alto impacto')):
        merge({'typography': {'display': 'Bebas Neue', 'google_fonts': ['Bebas Neue', 'DM Sans', 'Space Mono']}})
    if any(word in text for word in ('editorial', 'elegante')):
        merge({'typography': {'display': 'Cormorant Garamond', 'body': 'DM Sans', 'google_fonts': ['Cormorant Garamond', 'DM Sans']}})
    if any(word in text for word in ('mayuscula', 'uppercase')):
        merge({'typography': {'title_transform': 'uppercase'}})
    if any(word in text for word in ('minuscula', 'normal case')):
        merge({'typography': {'title_transform': 'none'}})

    if not patch:
        merge({'layout': {'density': 'comfortable'}})
    return patch


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_preview(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(tokens, dict):
        published = template.revisions.filter(status='published').order_by('-revision').first()
        tokens = published.tokens_json if published and isinstance(published.tokens_json, dict) else default_template_tokens()

    preview_format = str(request.data.get('format') or request.data.get('preview_format') or 'post').strip().lower()
    html, preview_format, resolved_tokens, dimensions = _render_brand_template_preview_html(template.base_template_id, tokens, preview_format)
    instructions = str(request.data.get('gemini_instructions') or '').strip() or _build_template_gemini_instructions(
        template.name,
        template.base_template_id,
        resolved_tokens,
    )
    return Response({
        'html': html,
        'format': preview_format,
        'dimensions': dimensions,
        'tokens_json': resolved_tokens,
        'gemini_instructions': instructions,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_draft_preview(request):
    base_template_id = _normalize_template_id(request.data.get('base_template_id') or request.data.get('baseTemplateId')) or 'tech_modern'
    tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(tokens, dict):
        tokens = _default_tokens_for_base_template(base_template_id)
    preview_format = str(request.data.get('format') or request.data.get('preview_format') or 'post').strip().lower()
    html, preview_format, resolved_tokens, dimensions = _render_brand_template_preview_html(base_template_id, tokens, preview_format)
    return Response({
        'html': html,
        'format': preview_format,
        'dimensions': dimensions,
        'base_template_id': base_template_id,
        'tokens_json': resolved_tokens,
        'gemini_instructions': _build_template_gemini_instructions('Borrador de template', base_template_id, resolved_tokens),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_draft_chat(request):
    base_template_id = _normalize_template_id(request.data.get('base_template_id') or request.data.get('baseTemplateId')) or 'tech_modern'
    message = str(request.data.get('message') or '').strip()
    current_tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(current_tokens, dict):
        current_tokens = _default_tokens_for_base_template(base_template_id)
    preview_format = str(request.data.get('format') or request.data.get('preview_format') or 'post').strip().lower()

    try:
        ai_result = _template_ai_patch_from_message(message, current_tokens, base_template_id, request.user) if message else None
    except APIKeyUnavailableError as exc:
        return _quota_error_response(exc, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='brand_template_draft_chat')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as exc:
        return _quota_error_response(exc, user=request.user, source='brand_template_draft_chat')
    if ai_result:
        token_patch = ai_result.get('token_patch') or {}
        reply = ai_result.get('reply') or 'ApliquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© los cambios al borrador. RevisÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ la preview y guardÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ cuando te guste.'
    else:
        token_patch = _template_patch_from_message(message)
        reply = 'ApliquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© los cambios al borrador. RevisÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ la preview y guardÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ cuando te guste.' if message else 'Decime quÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© querÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s cambiar: colores, tipografÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­as, logo, QR, precio, bordes o estilo visual.'

    merged_tokens = _resolve_brand_template_tokens(_deep_merge_dict(current_tokens, token_patch))
    html, preview_format, merged_tokens, dimensions = _render_brand_template_preview_html(base_template_id, merged_tokens, preview_format)
    estimated_tokens = max(120, int((len(message) + len(json.dumps(current_tokens, ensure_ascii=False))) / 4)) if message else 0

    return Response({
        'reply': reply,
        'token_patch': token_patch,
        'tokens_json': merged_tokens,
        'html': html,
        'format': preview_format,
        'dimensions': dimensions,
        'base_template_id': base_template_id,
        'gemini_instructions': _build_template_gemini_instructions('Borrador de template', base_template_id, merged_tokens),
        'usage': {
            'ai_tokens_consumed': bool(message),
            'estimated_tokens': estimated_tokens,
            'note': 'Cada mensaje del chat consume tokens/creditos de IA.',
        },
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_template_chat(request, template_id):
    template = get_object_or_404(BrandTemplate, id=template_id, owner=request.user, is_active=True)
    message = str(request.data.get('message') or '').strip()
    current_tokens = request.data.get('tokens_json') if isinstance(request.data, dict) else None
    if not isinstance(current_tokens, dict):
        published = template.revisions.filter(status='published').order_by('-revision').first()
        current_tokens = published.tokens_json if published and isinstance(published.tokens_json, dict) else default_template_tokens()

    try:
        ai_result = _template_ai_patch_from_message(message, current_tokens, template.base_template_id, request.user) if message else None
    except APIKeyUnavailableError as exc:
        return _quota_error_response(exc, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='brand_template_chat')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as exc:
        return _quota_error_response(exc, user=request.user, source='brand_template_chat')
    token_patch = (ai_result or {}).get('token_patch') or _template_patch_from_message(message)
    merged_tokens = _resolve_brand_template_tokens(_deep_merge_dict(current_tokens, token_patch))
    reply = (ai_result or {}).get('reply') or 'ApliquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© los cambios al borrador. RevisÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ la preview y guardÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ la revisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n si te gusta.'
    if not message:
        reply = 'Decime quÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© querÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s cambiar: colores, tipografÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­as, logo, QR, precio, bordes o estilo visual.'

    return Response({
        'reply': reply,
        'token_patch': token_patch,
        'tokens_json': merged_tokens,
        'gemini_instructions': _build_template_gemini_instructions(template.name, template.base_template_id, merged_tokens),
    }, status=status.HTTP_200_OK)

from .services.instagram_service import (
    publicar_post,
    publicar_story,
    publicar_carrusel,
    MAX_INSTAGRAM_CAROUSEL_ITEMS,
    publicar_media_upload_api,
    consultar_uploadpost_status,
    get_upload_post_accounts,
)
from django.conf import settings

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
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

        from .tracking import record_uploadpost_publication
        media_count = len(imagenes_urls or []) if tipo == 'carrusel' else (1 if imagen_url else 0)
        record_uploadpost_publication(
            user,
            success=bool(result.get('success')),
            provider='meta',
            platform='instagram',
            media_type='carousel' if tipo == 'carrusel' else tipo,
            request_id=f"meta-{result.get('post_id')}" if result.get('post_id') else None,
            job_id=result.get('post_id'),
            status_value='completed' if result.get('success') else 'failed',
            caption=caption,
            media_count=media_count,
            payload={
                'tipo': tipo,
                'imagen_url': imagen_url,
                'imagenes_urls': imagenes_urls,
            },
            response=result,
            error_message=result.get('error'),
        )

        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def publicar_redes_sociales(request):
    """
    Endpoint unificado para publicar contenido en redes sociales vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a Upload Post API.
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
        scheduled_at_iso, scheduled_at_error = _normalize_scheduled_at_input(scheduled_at)
        if scheduled_at_error:
            return Response({"success": False, "error": scheduled_at_error}, status=status.HTTP_400_BAD_REQUEST)
        request_id = data.get('request_id')
        batch_id = data.get('batch_id')
        
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
            scheduled_at=scheduled_at_iso,
            request_id=request_id,
            batch_id=batch_id,
            agente=user
        )
        
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _extract_publish_image_url(payload):
    if not isinstance(payload, dict):
        return None
    return payload.get('image_url') or payload.get('url') or payload.get('imageUrl')


def _extract_publish_images(payload):
    if not isinstance(payload, dict):
        return []
    images = payload.get('images') or payload.get('imagenes_urls') or payload.get('imagenesUrls') or []
    if not images and payload.get('slides'):
        images = payload.get('slides')
    if isinstance(images, str):
        images = [images]

    normalized = []
    for item in images or []:
        if isinstance(item, str):
            url = item
        elif isinstance(item, dict):
            url = item.get('url') or item.get('image_url') or item.get('imageUrl')
        else:
            url = None
        if url:
            normalized.append(url)
    return normalized


def _normalize_scheduled_at_input(raw_value):
    """
    Normaliza fechas de programacion en formato ISO para UploadPost.
    Acepta:
      - 2026-05-22T19:30
      - 2026-05-22T19:30:00
      - 2026-05-22T19:30:00Z
      - 2026-05-22T19:30:00-03:00
    """
    if raw_value in (None, '', False):
        return None, None

    value = str(raw_value).strip()
    if not value:
        return None, None

    parsed = parse_datetime(value.replace('Z', '+00:00'))
    if parsed is None:
        return None, "Formato de fecha inválido. Usá ISO 8601 (ej: 2026-05-22T19:30:00-03:00)."

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())

    now = timezone.now()
    if parsed < now + timedelta(minutes=1):
        return None, "La fecha programada debe ser al menos 1 minuto en el futuro."

    return parsed.isoformat(), None


def _serialize_publication_log(log):
    return {
        'id': log.id,
        'provider': log.provider,
        'platform': log.platform,
        'media_type': log.media_type,
        'request_id': log.request_id,
        'job_id': log.job_id,
        'batch_id': log.batch_id,
        'status': log.status,
        'success': bool(log.success),
        'counted': bool(log.counted),
        'media_count': log.media_count,
        'error_message': log.error_message,
        'created_at': log.creado_en.isoformat() if log.creado_en else None,
        'updated_at': log.actualizado_en.isoformat() if log.actualizado_en else None,
        'response': log.response if isinstance(log.response, dict) else {},
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def publicar_redes_todo(request):
    """
    Publica automÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ticamente en Instagram las tres piezas principales:
    post de feed, story y carrusel. Cada pieza genera un request_id separado.
    """
    try:
        import uuid

        user = request.user
        data = request.data or {}
        batch_id = str(data.get('batch_id') or uuid.uuid4().hex[:12]).replace(' ', '-')[:64]
        scheduled_at_raw = data.get('scheduled_at')
        scheduled_at_iso, scheduled_at_error = _normalize_scheduled_at_input(scheduled_at_raw)
        if scheduled_at_error:
            return Response({
                "success": False,
                "error": scheduled_at_error,
            }, status=status.HTTP_400_BAD_REQUEST)

        accounts = get_upload_post_accounts(user)
        if accounts.get('success') and not any(str(red.get('platform')).lower() == 'instagram' for red in accounts.get('redes', [])):
            return Response({
                "success": False,
                "error": "No hay una cuenta de Instagram conectada. Conectala desde Conexiones antes de publicar."
            }, status=status.HTTP_400_BAD_REQUEST)

        post_payload = data.get('post') or {}
        story_payload = data.get('story') or {}
        carousel_payload = data.get('carousel') or data.get('carrusel') or {}

        post_image = _extract_publish_image_url(post_payload)
        story_image = _extract_publish_image_url(story_payload)
        carousel_images = _extract_publish_images(carousel_payload)
        carousel_original_count = len(carousel_images)

        missing = []
        if not post_image:
            missing.append('post')
        if not story_image:
            missing.append('story')
        if not carousel_images:
            missing.append('carousel')
        if missing:
            return Response({
                "success": False,
                "error": f"Faltan piezas para publicar: {', '.join(missing)}. RegenerÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ el contenido antes de publicar todo."
            }, status=status.HTTP_400_BAD_REQUEST)

        results = {}
        warnings = []
        if story_payload.get('caption') or story_payload.get('texto'):
            warnings.append('Instagram Stories no acepta caption por API; se publica solo la imagen de la story.')
        if carousel_original_count > MAX_INSTAGRAM_CAROUSEL_ITEMS:
            carousel_images = carousel_images[:MAX_INSTAGRAM_CAROUSEL_ITEMS]
            warnings.append(
                f"Instagram permite hasta {MAX_INSTAGRAM_CAROUSEL_ITEMS} imÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡genes por carrusel; "
                f"se publicarÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡n las primeras {MAX_INSTAGRAM_CAROUSEL_ITEMS} de {carousel_original_count}."
            )

        publish_jobs = [
            ('post', 'image', post_payload.get('caption') or post_payload.get('texto') or '', post_image, None),
            ('story', 'story', story_payload.get('caption') or story_payload.get('texto') or '', story_image, None),
            ('carousel', 'carousel', carousel_payload.get('caption') or carousel_payload.get('texto') or '', None, carousel_images),
        ]

        for key, media_type, caption, image_url, images in publish_jobs:
            request_id = f"leadbook-{user.id}-{batch_id}-{key}"
            results[key] = publicar_media_upload_api(
                media_type=media_type,
                caption=caption,
                image_url=image_url,
                images=images,
                platforms=['instagram'],
                scheduled_at=scheduled_at_iso,
                request_id=request_id,
                batch_id=batch_id,
                agente=user,
            )

        any_success = any(result.get('success') for result in results.values())
        all_success = all(result.get('success') for result in results.values())

        response_data = {
            "success": all_success,
            "partial_success": any_success and not all_success,
            "batch_id": batch_id,
            "scheduled_at": scheduled_at_iso,
            "results": results,
            "warnings": warnings,
        }
        return Response(response_data, status=status.HTTP_200_OK if any_success else status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def publicar_redes_status(request):
    result = consultar_uploadpost_status(
        request_id=request.query_params.get('request_id'),
        job_id=request.query_params.get('job_id'),
        agente=request.user,
    )
    return Response(result, status=status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def publicar_redes_logs(request):
    """
    Devuelve trazas de publicación social para inspeccionar lote/request.
    Soporta filtros por batch_id y request_id.
    """
    batch_id = str(request.query_params.get('batch_id') or '').strip()
    request_id = str(request.query_params.get('request_id') or '').strip()
    try:
        limit = max(1, min(int(request.query_params.get('limit', 30)), 120))
    except Exception:
        limit = 30

    qs = SocialPublicationLog.objects.filter(user=request.user).order_by('-creado_en')
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if request_id:
        qs = qs.filter(request_id=request_id)

    logs = list(qs[:limit])
    payload = {
        "success": True,
        "batch_id": batch_id or None,
        "request_id": request_id or None,
        "count": len(logs),
        "logs": [_serialize_publication_log(item) for item in logs],
    }
    return Response(payload, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_carrusel(request):
    """Genera carrusel narrativo con secciones editadas y galeria limpia."""
    generation_run_id = None
    generation_step_name = 'carrusel'
    try:
        user = request.user
        # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
        # if not puede_generar(user, 'image'):
        #      return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        generation_run_id, generation_step_name = _mark_generation_running(data, 'carrusel')
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        listado_id_val = data.get('listado_id') or data.get('listadoId')

        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
        data = resolve_listing_media(listado_obj, data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_carousel = TEMPLATE_CAROUSEL_MAP.get(template_id, TEMPLATE_CAROUSEL_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='carrusel')

        images_pool = _collect_property_images(data)
        gallery_source = images_pool[1:] if len(images_pool) > 1 else []
        gallery_images = gallery_source[:MAX_CAROUSEL_GALLERY_IMAGES]
        gallery_omitted = max(0, len(gallery_source) - len(gallery_images))
        tipo_propiedad = data.get('tipoPropiedad', 'Propiedad')
        tipo_norm = unicodedata.normalize('NFKD', str(tipo_propiedad or '')).encode('ascii', 'ignore').decode('ascii').lower()
        is_parking = any(token in tipo_norm for token in ('cochera', 'garage', 'garaje', 'estacionamiento', 'parking'))

        def clean_spec(value):
            value = str(value or '').strip()
            return '' if value.lower() in {'n/d', 'nd', 'none', 'null', '-'} else value

        recamaras = clean_spec(data.get('recamaras'))
        banos = clean_spec(data.get('banos'))
        superficie = clean_spec(
            data.get('superficieCubierta')
            or data.get('superficieConstruida')
            or data.get('superficieTotal')
            or data.get('superficieTerreno')
        )
        estacionamientos = clean_spec(data.get('estacionamientos'))
        amenidades = data.get('amenidades') if isinstance(data.get('amenidades'), list) else []
        amenities_text = ', '.join(amenidades[:5]) if amenidades else 'amenidades seleccionadas para vivir mejor'
        precio_val = clean_spec(data.get('precio'))
        moneda_val = clean_spec(data.get('moneda')) or 'USD'
        precio_text = f"{moneda_val} {precio_val}".strip() if precio_val else ''
        descripcion = str(data.get('descripcion') or data.get('descripcionGenerada') or '').strip()
        descripcion_corta = descripcion[:180].rstrip() if descripcion else 'Una propuesta pensada para vivir, invertir y decidir con informacion clara.'
        ubicacion_text = str(data.get('ciudad') or '').strip()
        operacion_text = data.get('operacion', 'Venta')
        carousel_gallery_logo_position = str(
            data.get('carousel_gallery_logo_position')
            or data.get('carouselGalleryLogoPosition')
            or data.get('logoPosition')
            or 'top_right'
        ).strip().lower()
        if carousel_gallery_logo_position not in {'top_left', 'top_right', 'center', 'hidden'}:
            carousel_gallery_logo_position = 'top_right'

        def build_specs_sentence():
            parts = []
            if is_parking:
                if superficie:
                    parts.append(f"{superficie} m2")
                if estacionamientos:
                    label = 'espacio' if estacionamientos == '1' else 'espacios'
                    parts.append(f"{estacionamientos} {label}")
                suffix = ', '.join(parts)
                return f"{suffix}. " if suffix else ''

            if superficie:
                parts.append(f"{superficie} m2")
            if recamaras:
                parts.append(f"{recamaras} hab")
            if banos:
                parts.append(f"{banos} banos")
            suffix = ', '.join(parts)
            return f"{suffix}. " if suffix else ''

        specs_sentence = build_specs_sentence()
        specs_prompt = specs_sentence.strip().rstrip('.') or 'Ficha comercial sin medidas residenciales genericas'

        def pick_image(index=0):
            if not images_pool:
                return None
            return images_pool[index % len(images_pool)]

        def render_clean_gallery_slide(image_url, logo_url='', logo_position='top_right'):
            logo_position = str(logo_position or 'top_right').strip().lower()
            if logo_position not in {'top_left', 'top_right', 'center', 'hidden'}:
                logo_position = 'top_right'
            logo_class = {
                'top_left': 'logo top-left',
                'top_right': 'logo top-right',
                'center': 'logo center',
            }.get(logo_position, '')
            logo_html = ''
            if logo_url and logo_position != 'hidden':
                logo_html = f'<img class="{logo_class}" src="{logo_url}" alt="Logo inmobiliaria">'
            return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ width: 1080px; height: 1350px; background: #050505; overflow: hidden; }}
  .photo {{ width: 100%; height: 100%; object-fit: contain; display: block; background: #050505; }}
  .logo {{ position: absolute; z-index: 2; width: 138px; max-height: 86px; object-fit: contain; padding: 12px; border-radius: 18px; background: rgba(255,255,255,.92); box-shadow: 0 10px 34px rgba(0,0,0,.28); }}
  .top-left {{ top: 42px; left: 42px; }}
  .top-right {{ top: 42px; right: 42px; }}
  .center {{ top: 50%; left: 50%; transform: translate(-50%, -50%); width: 180px; max-height: 112px; }}
</style>
</head>
<body>
  <img class="photo" src="{image_url}" alt="Galeria propiedad">
  {logo_html}
</body>
</html>"""

        def render_contact_slide(context):
            safe_agency = html_lib.escape(str(context.get("agencia_nombre", "") or '').strip()) or 'Agencia'
            safe_agent = html_lib.escape(str(context.get("agente_nombre", "") or '').strip()) or 'Asesor'
            safe_role = html_lib.escape(str(context.get("agente_rol", "") or 'Asesor Comercial').strip())
            if context.get('logo_url'):
                logo_html = (
                    f'<div class="brand-lockup"><img class="logo" src="{context.get("logo_url", "")}" alt="{safe_agency}">'
                    f'<span class="agency">{safe_agency}</span></div>'
                )
            else:
                logo_html = f'<div class="brand-lockup"><span class="agency">{safe_agency}</span></div>'
            agent_photo = f'<img class="agent-photo" src="{context.get("agente_foto_url", "")}" alt="{safe_agent}">' if context.get('agente_foto_url') else ''
            contact_html = str(context.get('agente_contacto_html') or '').strip()
            contact_line = f'<div class="meta">{contact_html}</div>' if contact_html else ''
            qr_html = f'<img class="qr" src="{context.get("qr_url", "")}" alt="QR WhatsApp">' if context.get('qr_url') else ''
            return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;700;900&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ width: 1080px; height: 1350px; background: radial-gradient(circle at top right, rgba(201,168,76,.28), transparent 34%), #070707; color: #f7f3e8; overflow: hidden; font-family: 'DM Sans', sans-serif; }}
  .wrap {{ width: 100%; height: 100%; padding: 88px 82px; display: flex; flex-direction: column; justify-content: space-between; }}
  .top {{ display: flex; justify-content: flex-end; align-items: center; min-height: 90px; }}
  .brand-lockup {{ display: flex; align-items: center; gap: 16px; max-width: 520px; padding: 10px 16px; border: 1px solid rgba(255,255,255,.14); border-radius: 999px; background: rgba(0,0,0,.28); }}
  .logo {{ width: 66px; height: 66px; border-radius: 999px; object-fit: contain; padding: 7px; background: rgba(255,255,255,.94); }}
  .agency {{ font-size: 22px; letter-spacing: 3px; text-transform: uppercase; color: #c9a84c; font-weight: 900; line-height: 1.05; }}
  .headline {{ font-family: 'Bebas Neue', sans-serif; font-size: 168px; line-height: .86; letter-spacing: 3px; color: #c9a84c; text-transform: uppercase; }}
  .sub {{ margin-top: 28px; max-width: 820px; font-size: 38px; line-height: 1.2; color: rgba(255,255,255,.82); }}
  .contact {{ border: 1px solid rgba(201,168,76,.42); border-radius: 28px; padding: 34px; background: rgba(255,255,255,.045); display: flex; justify-content: space-between; gap: 36px; align-items: center; }}
  .agent {{ display: flex; align-items: center; gap: 22px; min-width: 0; }}
  .agent-photo {{ width: 116px; height: 116px; border-radius: 999px; object-fit: cover; border: 3px solid #c9a84c; }}
  .name {{ font-size: 44px; line-height: 1; font-weight: 900; color: #fff; }}
  .role {{ margin-top: 10px; font-size: 17px; letter-spacing: 3px; color: rgba(255,255,255,.48); text-transform: uppercase; }}
  .meta {{ margin-top: 12px; font-size: 24px; color: #c9a84c; }}
  .qr {{ width: 190px; height: 190px; padding: 10px; background: #fff; border-radius: 18px; }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="top">{logo_html}</div>
    <main>
      <div class="headline">Contacto<br>Directo</div>
      <div class="sub">Pedi la ficha completa, disponibilidad y condiciones comerciales actualizadas.</div>
    </main>
    <section class="contact">
      <div class="agent">
        {agent_photo}
        <div>
          <div class="name">{safe_agent}</div>
          <div class="role">{safe_role} - {safe_agency}</div>
          {contact_line}
        </div>
      </div>
      {qr_html}
    </section>
  </div>
</body>
</html>"""

        hook_title = str(data.get('titulo') or f"{tipo_propiedad} en {ubicacion_text}" or tipo_propiedad).strip()
        price_sentence = f"{operacion_text} por {precio_text}." if precio_text else f"{operacion_text}."
        hook_subheadline = (
            f"{price_sentence} {specs_sentence}"
            "Desliza para ver la galeria y guarda esta oportunidad."
        )

        slides_urls = []
        slides_content = [
            {"kind": "template", "image": pick_image(0), "headline": hook_title, "subheadline": hook_subheadline},
        ]

        for image_url in gallery_images:
            slides_content.append({"kind": "gallery", "image": image_url})

        slides_content.append({
            "kind": "contact",
            "image": pick_image(0),
            "headline": "Contacto directo",
            "subheadline": "Pedi la ficha completa, disponibilidad y condiciones comerciales actualizadas.",
        })

        for i in range(len(slides_content)):
            slide = slides_content[i]
            context = {
                "portada_url": slide.get("image"),
                "headline": slide.get("headline", ""),
                "subheadline": slide.get("subheadline", ""),
                "slide_number": i + 1,
                "total_slides": len(slides_content),
                "logo_url": branding.get('logo_url', ''),
                "operacion": data.get('operacion', 'Venta'),
                "agente_nombre": branding.get('agente_nombre', ''),
                "agente_telefono": branding.get('agente_telefono', ''),
                "agente_email": branding.get('agente_email', ''),
                "agente_rol": branding.get('agente_rol', 'Asesor Comercial'),
                "agencia_nombre": branding.get('agencia_nombre', ''),
                "agente_foto_url": branding.get('agente_foto_url', ''),
                "agente_contacto_html": branding.get('agente_contacto_html', ''),
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

            if slide.get('kind') == 'gallery':
                html_content = render_clean_gallery_slide(slide.get('image'), branding.get('logo_url', ''), carousel_gallery_logo_position)
            else:
                html_content = render_to_string(template_carousel, context)
                html_content = _apply_template_tokens_to_html(html_content, template_id, selection.get('template_tokens'))
                html_content = _inject_agent_photo_html(html_content, branding.get('agente_foto_url', ''))
                html_content = _inject_agency_brand_lockup(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
                html_content = _inject_agency_logo_fallback(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
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
                    raise Exception('Almacenamiento devolviÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ None')
                slides_urls.append(url)
            except Exception as cloud_err:
                print(f"[DEBUG] ERROR Almacenamiento Slide {i+1}: {str(cloud_err)}")
                _mark_generation_failed(generation_run_id, generation_step_name, cloud_err, error_code='carrusel_upload_failed')
                return Response({"error": f"Error subiendo slide {i+1}"}, status=500)

        caption_style = _get_random_caption_style_instructions(listado_obj, formato='carrusel')
        style_id = caption_style['id']
        style_name = caption_style['name']
        style_instructions = caption_style['instructions']
        print(f"[CARRUSEL] Generando caption con estilo: {style_name}")

        prompt_text = f"""Escribi UN SOLO caption final para Instagram Carrusel, listo para publicar.
Propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}, {data.get('pais', '')}.
Operacion y precio: {data.get('operacion', 'Venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.
Detalles: {specs_prompt}. Amenities/diferenciales: {amenities_text}. Contexto: {descripcion_corta}.

Requisitos obligatorios:
- Enfoque de estilo requerido:
{style_instructions}
- 1100 a 1900 caracteres.
- Gancho con personalidad en la primera linea.
- 2 a 4 parrafos cortos, con deseo, exclusividad, inversion y beneficio concreto.
- Mencionar que el carrusel muestra recorrido/fotos reales y que conviene guardar o compartir.
- CTA claro a WhatsApp/consulta privada.
- Cerrar con 25 a 30 hashtags variados y especificos, no genericos repetidos.
- No des opciones, no uses titulos como "Opcion 1", no expliques el caption, no menciones que sos IA.
{_caption_preference_prompt(content_prefs)}"""
        prompt_text = _repair_mojibake_text(prompt_text)
        caption = smart_call(
            prompt_text,
            system_prompt="Sos un director de marketing inmobiliario digital. Devolves solo copy final listo para publicar.",
            agente=user,
            task='carousel_caption',
            listado_id=listado_id_val,
            generation_run_id=generation_run_id,
            generation_step=generation_step_name,
        )
        caption = _finalize_caption_text(caption, data, formato='carrusel', prefs=content_prefs, max_chars=2200)

        if listado_obj:
            caption_generation_count = _get_caption_generation_count(listado_obj, 'carrusel') + 1
            actualizar_resultados_listado(
                listado_obj,
                'carrusel',
                {
                    "slides": slides_urls,
                    "caption": caption,
                    "caption_style_id": style_id,
                    "caption_style_name": style_name,
                    "caption_generation_count": caption_generation_count,
                    "template_id": template_id,
                    "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                    "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                    "total_slides": len(slides_urls),
                    "gallery_used": len(gallery_images),
                    "gallery_omitted": gallery_omitted,
                    "carousel_gallery_logo_position": carousel_gallery_logo_position,
                },
            )

        if user.is_authenticated:
            incrementar_uso(user, 'image')
            crear_notificacion(
                user,
                'contenido_generado',
                'Tu carrusel ya está listo',
                'El carrusel fue generado correctamente y ya lo tenés disponible para publicar.',
            )

        response_payload = {
            "slides": slides_urls,
            "caption": caption,
            "caption_style_id": style_id,
            "caption_style_name": style_name,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
            "total_slides": len(slides_urls),
            "gallery_used": len(gallery_images),
            "gallery_omitted": gallery_omitted,
            "carousel_gallery_logo_position": carousel_gallery_logo_position,
        }
        _mark_generation_done(generation_run_id, generation_step_name, {
            "slides": slides_urls,
            "template_id": template_id,
            "total_slides": len(slides_urls),
        })
        return Response(response_payload, status=status.HTTP_200_OK)
    except APIKeyUnavailableError as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_carrusel')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, user=request.user, source='generar_carrusel')
    except Exception as exc:
        logger.exception("Error generando carrusel")
        _mark_generation_failed(generation_run_id, generation_step_name, exc, error_code='carrusel_failed')
        return Response({"error": "Error al generar carrusel"}, status=500)

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

        agency_present, agency_value = _extract_first_present(data, 'nombre_inmobiliaria', 'nombreInmobiliaria')
        website_present, website_value = _extract_first_present(data, 'sitio_web', 'sitioWeb')
        if agency_present or website_present:
            conflict_response, clean_agency_name, clean_website = _validate_unique_agency_identity(
                user,
                agency_name=agency_value if agency_present else None,
                website=website_value if website_present else None,
                account_type=data.get('agencia', getattr(user, 'agencia', '')),
            )
            if conflict_response:
                return conflict_response

        if agency_present:
            user.nombre_inmobiliaria = clean_agency_name
            
        logo_present, logo_value, logo_error = _resolve_profile_logo_input(data, user)
        if logo_error:
            return logo_error
        if logo_present:
            user.logo_url = logo_value
            
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
        if website_present:
            user.sitio_web = clean_website
        if 'bio' in data:
            user.bio = data['bio']
        if 'settings' in data:
            user.settings = _normalize_user_settings(data.get('settings'), getattr(user, 'settings', None))
            
        user.save()

        # --- Auto-create default ComercialAgentProfile if none exists ---
        default_agent = _get_default_commercial_agent(user)
        if not default_agent:
            try:
                from django.db import IntegrityError
                agent_nombre = getattr(user, 'nombre', None) or user.email.split('@')[0]
                agent_email = user.email
                agent_phone = getattr(user, 'telefono', None)
                # Normalize phone to E.164 if possible
                agent_phone_e164 = None
                if agent_phone:
                    cleaned = str(agent_phone).strip().replace(' ', '').replace('-', '')
                    if cleaned and not cleaned.startswith('+'):
                        cleaned = f'+{cleaned}'
                    import re as _re
                    if _re.match(r'^\+[1-9]\d{6,14}$', cleaned):
                        agent_phone_e164 = cleaned

                with transaction.atomic():
                    default_agent = ComercialAgentProfile.objects.create(
                        owner=user,
                        nombre=agent_nombre,
                        email=agent_email,
                        telefono_e164=agent_phone_e164,
                        foto_url=getattr(user, 'logo_url', None) or '',
                        is_default=True,
                        activo=True,
                    )
                logger.info(f"[Onboarding] Auto-created default ComercialAgentProfile {default_agent.id} for user {user.id}")
            except IntegrityError:
                # Race condition or constraint — fetch existing
                logger.warning(f"[Onboarding] IntegrityError creating default agent for user {user.id}, fetching existing")
                default_agent = _get_default_commercial_agent(user)
            except Exception as exc:
                logger.exception(f"[Onboarding] Unexpected error creating default agent for user {user.id}: {exc}")
                default_agent = None

        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": _safe_persisted_media_url(getattr(user, 'logo_url', None)),
            "telefono": getattr(user, 'telefono', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "nacionalidad": getattr(user, 'nacionalidad', None),
            "sitio_web": getattr(user, 'sitio_web', None),
            "bio": getattr(user, 'bio', None),
            "settings": _normalize_user_settings(getattr(user, 'settings', None)),
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
        if listado.video_url:
            normalized_status = 'done'
        elif normalized_status in ('queued', 'processing'):
            stale_after = int(config('VIDEO_QUEUE_PROCESSING_TIMEOUT_MINUTES', default=45)) * 60
            age_seconds = (timezone.now() - listado.updated_at).total_seconds() if listado.updated_at else 0
            if normalized_status == 'processing' and age_seconds > stale_after:
                listado.video_status = 'error'
                listado.save(update_fields=['video_status'])
                normalized_status = 'error'

        queue_position = None
        queue_meta = None
        if normalized_status == 'queued':
            from api.services.video_queue import get_video_queue_metadata, get_video_queue_position
            queue_position = get_video_queue_position(listado)
            queue_meta = get_video_queue_metadata(listado)

        return Response({
            "status": normalized_status,
            "video_url": listado.video_url,
            "video_version": (listado.datos_extra or {}).get('video_generated_at') or (listado.updated_at.isoformat() if listado.updated_at else None),
            "updated_at": listado.updated_at,
            "queue_position": queue_position,
            "queue_priority": queue_meta.get('priority') if queue_meta else None,
            "provider": queue_meta.get('provider') if queue_meta else (listado.datos_extra or {}).get('video_provider'),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class ListadosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devuelve todos los listados del usuario logueado"""
        listados = Listado.objects.filter(agente=request.user)
        data = [_serialize_listing_summary(listado) for listado in listados]
        return Response(data)

    def post(self, request):
        block = active_plan_block_response(request)
        if block:
            return block
        from .models import Agent
        from .plan_utils import build_daily_listing_limit_payload, puede_crear_listado_hoy
        user = Agent.objects.get(id=request.user.id)
        can_create_today, daily_listing_quota = puede_crear_listado_hoy(user)
        if not can_create_today:
            return Response(build_daily_listing_limit_payload(user), status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
        # puede, usados, maximo = verificar_limite_plan(user)
        # if not puede:
        #     return Response({
        #         "error": f"Alcanzaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan ({usados}/{maximo} listados este mes). ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu plan para continuar.",
        #         "limite_alcanzado": True,
        #         "usados": usados,
        #         "maximo": maximo
        #     }, status=403)
            
        data = request.data
        
        # Permitir tanto JSON plano como objeto anidado 'formData' (React)
        payload = data.get('formData') if isinstance(data, dict) and 'formData' in data else data
        if not isinstance(payload, dict):
            payload = {}
        blocked_media_response = _reject_blocked_media_data_uri(payload, 'formData')
        if blocked_media_response:
            return blocked_media_response
            
        # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
        # if not puede_generar(user, 'property'):
        #     return Response({"error": "limite_alcanzado", "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n."}, status=status.HTTP_403_FORBIDDEN)
        
        titulo = payload.get('titulo') or f"Propiedad en {payload.get('ciudad', 'Desconocida')}"
        tipo_propiedad = payload.get('tipoPropiedad', payload.get('tipo_propiedad', ''))
        operacion = payload.get('operacion', 'venta')
        ciudad = payload.get('ciudad', '')
        precio = str(payload.get('precio', ''))
        moneda = payload.get('moneda', 'USD')
        
        cover_frame_url = _resolve_listing_cover_frame(payload)
        if cover_frame_url:
            payload = {**payload, 'cover_frame_url': cover_frame_url}
        payload = _sanitize_listing_payload_for_storage(payload)

        # Guardamos en datos_extra el payload limpio
        listado = Listado.objects.create(
            agente=user,
            titulo=titulo,
            tipo_propiedad=tipo_propiedad,
            operacion=operacion,
            ciudad=ciudad,
            precio=precio,
            moneda=moneda,
            datos_extra=payload
        )
        
        registrar_uso(user, 'property')
        
        return Response({
            "mensaje": "Listado guardado", 
            "id": listado.id,
            "titulo": listado.titulo,
            "daily_listing_quota": {
                **daily_listing_quota,
                "used": daily_listing_quota["used"] + 1 if daily_listing_quota.get("limit") is not None else daily_listing_quota.get("used", 0),
                "remaining": max(0, daily_listing_quota["remaining"] - 1) if daily_listing_quota.get("remaining") is not None else None,
            }
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def extract_listado_from_url(request):
    from django.conf import settings

    if not getattr(settings, 'IMPORT_URL_ENABLED', True):
        return Response({
            'ok': False,
            'status': 'disabled',
            'source': '',
            'confidence': 0,
            'data': {},
            'media_candidates': [],
            'warnings': ['La importacion por URL no esta habilitada.'],
            'required_action': 'blocked',
            'final_url': request.data.get('url') if hasattr(request.data, 'get') else '',
        }, status=status.HTTP_403_FORBIDDEN)

    payload = request.data if hasattr(request.data, 'get') else {}
    url = payload.get('url')
    source_hint = payload.get('source_hint') or payload.get('sourceHint')
    try:
        result = extract_listing_from_url(
            url,
            pais=payload.get('pais'),
            idioma=payload.get('idioma'),
            source_hint=source_hint,
            pasted_html=payload.get('pasted_html') or payload.get('pastedHtml'),
            pasted_text=payload.get('pasted_text') or payload.get('pastedText'),
        )
        result = _maybe_enrich_imported_listing_data(result, request.user, url)
        data = result.get('data') or {}
        media_candidates = result.get('media_candidates') or data.get('fotos') or []
        return Response({
            'ok': bool(result.get('ok')),
            'extraction_id': result.get('extraction_id') or '',
            'status': result.get('status') or ('ready' if result.get('ok') else 'needs_input'),
            'source': result.get('source') or '',
            'mode': result.get('mode') or '',
            'confidence': result.get('confidence') or 0,
            'data': data,
            'media_candidates': media_candidates,
            'warnings': result.get('warnings') or [],
            'required_action': result.get('required_action') or 'none',
            'final_url': result.get('final_url') or url,
        }, status=status.HTTP_200_OK)
    except ExtractorError as exc:
        explicit_action = getattr(exc, 'required_action', None)
        action = explicit_action or 'manual_review'
        response_status = status.HTTP_200_OK if explicit_action in {'paste_html', 'manual_review', 'blocked', 'login_required'} else getattr(exc, 'status_code', status.HTTP_400_BAD_REQUEST)
        return Response({
            'ok': False,
            'extraction_id': '',
            'status': getattr(exc, 'extraction_status', None) or 'needs_input',
            'source': source_hint or '',
            'confidence': 0,
            'data': {},
            'media_candidates': [],
            'warnings': list(exc.warnings or []) + [str(exc)],
            'required_action': action,
            'final_url': url,
        }, status=response_status)
    except Exception as exc:
        logger.exception('[EXTRACTOR] fail url=%s reason=unexpected:%s', url, exc)
        return Response({
            'ok': False,
            'extraction_id': '',
            'status': 'error',
            'source': source_hint or '',
            'confidence': 0,
            'data': {},
            'media_candidates': [],
            'warnings': ['Error inesperado al extraer la URL.'],
            'required_action': 'manual_review',
            'final_url': url,
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _maybe_enrich_imported_listing_data(result, user, source_url=''):
    from django.conf import settings

    if not getattr(settings, 'IMPORT_URL_AI_ENRICHMENT_ENABLED', False):
        return result
    data = result.get('data') if isinstance(result, dict) else {}
    if not isinstance(data, dict) or not data:
        return result

    raw_context = '\n'.join(
        str(data.get(key) or '')
        for key in ('titulo', 'descripcion', 'direccion', 'ciudad', 'precio', 'moneda', 'tipo_propiedad', 'operacion')
    ).strip()
    if len(raw_context) < 40:
        return result

    prompt = f"""
Normaliza datos de una publicacion inmobiliaria importada. No generes piezas finales, solo campos limpios.
Devuelve JSON con estas claves si las podes inferir:
titulo, descripcion, tipo_propiedad, operacion, pais, ciudad, direccion, precio, moneda, recamaras, banos,
superficie_total, superficie_cubierta, estacionamientos, amenidades.

URL fuente: {source_url}
Datos extraidos:
{json.dumps(data, ensure_ascii=False)[:6000]}
"""
    try:
        raw = smart_call(
            prompt,
            retries=1,
            agente=user,
            system_prompt='Sos un asistente de limpieza de datos inmobiliarios. Respondes solo JSON valido.',
            task='listing_import_enrichment',
        )
        parsed = _parse_json_object(raw)
        if not isinstance(parsed, dict):
            return result
        allowed = {
            'titulo', 'descripcion', 'tipo_propiedad', 'operacion', 'pais', 'ciudad', 'direccion',
            'precio', 'moneda', 'recamaras', 'banos', 'superficie_total', 'superficie_cubierta',
            'estacionamientos', 'amenidades',
        }
        enriched = dict(data)
        for key in allowed:
            value = parsed.get(key)
            if value in (None, '', [], {}):
                continue
            if key == 'amenidades':
                if isinstance(value, list):
                    enriched[key] = [str(item).strip() for item in value if str(item).strip()][:20]
                continue
            if key == 'descripcion' and len(str(value)) > len(str(enriched.get(key) or '')):
                enriched[key] = _repair_mojibake_text(str(value).strip())[:2200]
                continue
            enriched.setdefault(key, _repair_mojibake_text(str(value).strip()))
        next_result = dict(result)
        next_result['data'] = enriched
        next_result['warnings'] = list(result.get('warnings') or []) + ['Datos normalizados con IA antes de la revision.']
        return next_result
    except Exception as exc:
        logger.warning('[EXTRACTOR] enrichment skipped url=%s reason=%s', source_url, exc)
        return result


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
@require_pro_feature('meta_ads')
def generate_meta_variants(request):
    payload = request.data if isinstance(request.data, dict) else {}
    listado_id = payload.get('listado_id') or payload.get('listadoId')
    listado_obj = None
    if listado_id:
        try:
            listado_obj = Listado.objects.get(id=listado_id, agente=request.user)
        except Listado.DoesNotExist:
            return Response({'ok': False, 'error': 'listado_not_found'}, status=status.HTTP_404_NOT_FOUND)

    property_data, params = normalize_ads_request(payload)
    if not property_data and listado_obj:
        property_data = listado_obj.datos_extra if isinstance(listado_obj.datos_extra, dict) else {}
    blocked_media_response = _reject_blocked_media_data_uri(property_data, 'data')
    if blocked_media_response:
        return blocked_media_response
    if not property_data:
        return Response({'ok': False, 'error': 'property_data_required'}, status=status.HTTP_400_BAD_REQUEST)

    prompt = build_meta_ads_prompt(property_data, params)
    last_parse_error = None
    for attempt in range(1, 3):
        logger.info(
            '[ADS_STUDIO] ai_attempt attempt=%s user_id=%s listado_id=%s variants=%s',
            attempt,
            request.user.id,
            listado_id or '',
            params['cantidad_variantes'],
        )
        try:
            raw = smart_call(
                prompt,
                retries=1,
                agente=request.user,
                system_prompt='Sos un performance marketer inmobiliario. Respondes solo JSON valido.',
                task='ads_json',
                listado_id=listado_id,
            )
            variants = parse_meta_ads_response(raw, params['cantidad_variantes'])
            result = build_ads_result(variants, params, listado_id=listado_obj.id if listado_obj else None)
            if listado_obj:
                actualizar_resultados_listado(listado_obj, 'meta_variants', result)
            logger.info(
                '[ADS_STUDIO] success user_id=%s listado_id=%s variants=%s',
                request.user.id,
                listado_id or '',
                len(variants),
            )
            return Response(result, status=status.HTTP_200_OK)
        except (GeminiRateLimitedError, ElevenLabsRateLimitedError) as exc:
            logger.warning('[ADS_STUDIO] soft_rate_limited user_id=%s reason=%s', request.user.id, exc)
            return _quota_error_response(exc, user=request.user, source='generate_meta_variants')
        except (GeminiQuotaExhaustedError, ElevenLabsQuotaExhaustedError) as exc:
            logger.warning('[ADS_STUDIO] hard_quota user_id=%s reason=%s', request.user.id, exc)
            return _quota_error_response(exc, user=request.user, source='generate_meta_variants')
        except APIKeyUnavailableError as exc:
            logger.warning('[ADS_STUDIO] api_key_unavailable user_id=%s reason=%s', request.user.id, exc)
            return _quota_error_response(exc, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generate_meta_variants')
        except ValueError as exc:
            last_parse_error = str(exc)
            logger.warning('[ADS_STUDIO] parse_retry attempt=%s reason=%s', attempt, exc)
            continue
        except Exception as exc:
            logger.exception('[ADS_STUDIO] fail user_id=%s reason=%s', request.user.id, exc)
            return Response({'ok': False, 'error': 'ads_generation_failed', 'message': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'ok': False,
        'error': 'ads_generation_unparseable',
        'message': last_parse_error or 'No se pudieron generar variantes validas.',
    }, status=status.HTTP_502_BAD_GATEWAY)

class ListadoDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk, agente=request.user)
            cover_url = _ensure_listing_pdf_cover_frame(listado) or _ensure_listing_cover_frame(listado)
            datos_extra = _repair_listing_response_value(listado.datos_extra if isinstance(listado.datos_extra, dict) else {})
            return Response({
                "id": listado.id,
                "titulo": listado.titulo,
                "tipo_propiedad": listado.tipo_propiedad,
                "operacion": listado.operacion,
                "ciudad": listado.ciudad,
                "precio": listado.precio,
                "moneda": listado.moneda,
                "video_url": listado.video_url,
                "video_status": listado.video_status,
                "dashboard_image_url": cover_url,
                "cover_frame_url": cover_url,
                "fotoportada": cover_url,
                "formatos_generados": _listing_generated_formats(listado, datos_extra),
                "datos": datos_extra
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

        # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Eliminar assets de Cloudinary antes de borrar el registro ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
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

        # Fotos de galerÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a
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

        # Eliminar en Cloudinary ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â fallo individual no interrumpe la operaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
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

        # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Borrar el registro de PostgreSQL ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
        listado.delete()
        return Response({"mensaje": "Listado eliminado"}, status=status.HTTP_200_OK)


    def put(self, request, pk):
        block = active_plan_block_response(request)
        if block:
            return block
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para modificar este listado"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data
        if 'datos' in data:
            blocked_media_response = _reject_blocked_media_data_uri(data.get('datos'), 'datos')
            if blocked_media_response:
                return blocked_media_response
            datos = _merge_listing_extra_preserving_covers(listado.datos_extra, data['datos'])
            listado.datos_extra = _sanitize_listing_payload_for_storage(datos)
        if 'video_url' in data:
            listado.video_url = data['video_url']
        if 'video_status' in data:
            listado.video_status = data['video_status']
        
        listado.save()
        return Response({"mensaje": "Listado actualizado"}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_video(request, pk):
    """Dispara la generaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de video asincronamente"""
    try:
        from django.conf import settings
        import threading
        listado = Listado.objects.get(id=pk, agente=request.user)
        payload_datos = request.data.get('datos') if isinstance(request.data, dict) else None
        if isinstance(payload_datos, dict):
            blocked_media_response = _reject_blocked_media_data_uri(payload_datos, 'datos')
            if blocked_media_response:
                return blocked_media_response
            datos = _merge_listing_extra_preserving_covers(listado.datos_extra, payload_datos)
            datos = resolve_listing_media(listado, datos)
            blocked_media_response = _reject_blocked_media_data_uri(datos, 'datos')
            if blocked_media_response:
                return blocked_media_response
            listado.datos_extra = _sanitize_listing_payload_for_storage(datos)

        video_provider = config('VIDEO_PROVIDER', default='leadbook_sync').strip().lower()
        from api.services.video_queue import get_video_queue_position, mark_video_queued
        queue_meta = mark_video_queued(listado, video_provider)

        default_generation_mode = 'thread' if settings.DEBUG else 'celery'
        generation_mode = config('VIDEO_GENERATION_MODE', default=default_generation_mode).strip().lower()

        # El request solo encola. El procesador toma 1 video a la vez y ordena por plan.
        if generation_mode != 'celery' or getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
            logger.info("[VIDEO] Dispatch thread listado_id=%s mode=%s eager=%s", pk, generation_mode, getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False))
            from api.tasks import process_video_queue
            threading.Thread(target=process_video_queue, daemon=True).start()
        else:
            logger.info("[VIDEO] Dispatch celery listado_id=%s mode=%s eager=%s", pk, generation_mode, getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False))
            from api.tasks import process_video_queue_task
            async_result = process_video_queue_task.delay()
            logger.info("[VIDEO] Celery task enviada listado_id=%s task_id=%s", pk, getattr(async_result, 'id', None))

            # Fallback opcional: si no hay worker vivo, usar thread para no dejar el video clavado en queued.
            # Mantener desactivado por defecto en prod para evitar OOM del contenedor web.
            fallback_thread = config('VIDEO_FALLBACK_TO_THREAD_IF_NO_WORKER', default=False, cast=bool)
            if fallback_thread:
                try:
                    from subzero_core.celery import app as celery_app
                    inspect = celery_app.control.inspect(timeout=1)
                    pings = inspect.ping() or {}
                    if not pings:
                        logger.warning("[VIDEO] No Celery workers responded to ping; using thread fallback listado_id=%s", pk)
                        from api.tasks import process_video_queue
                        threading.Thread(target=process_video_queue, daemon=True).start()
                except Exception as ping_err:
                    logger.warning("[VIDEO] Worker ping failed (%s); using thread fallback listado_id=%s", ping_err, pk)
                    from api.tasks import process_video_queue
                    threading.Thread(target=process_video_queue, daemon=True).start()

        return Response({
            "status": "queued",
            "mensaje": "El video quedÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ en cola y se procesarÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ segÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºn prioridad del plan",
            "id": pk,
            "provider": video_provider,
            "queue_position": get_video_queue_position(listado),
            "queue_priority": queue_meta.get('priority'),
            "mode": generation_mode if generation_mode == 'celery' else 'thread',
        })
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)

def construir_contexto_pdf(data, user, request=None):
    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Extraer hint de listado para el almacenamiento ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
    listado_id_hint  = data.get('listado_id') or data.get('listadoId')

    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Helpers de imÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡genes para WeasyPrint ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
    temp_files = []

    def resolver_imagen(val, tipo='portada', indice=0):
        if not val: return None
        
        if isinstance(val, dict):
            from api.services.almacenamiento import AlmacenamientoCloudinary
            return AlmacenamientoCloudinary.obtener_url_foto(val) or _resolve_cloudinary_asset_url(val)
            
        if isinstance(val, str):
            if val.startswith('http'):
                return val
            if val.startswith('data:'):
                if not _allow_legacy_base64_media():
                    logger.warning(
                        "[MEDIA] Data URL rechazada en resolver_imagen (ALLOW_LEGACY_BASE64_MEDIA=False) tipo=%s listado_id=%s",
                        tipo,
                        listado_id_hint,
                    )
                    return None
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



    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Extraer campos normalizados ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
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

    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Procesar imÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡genes (base64 Y URLs) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
    logo_url = branding.get('logo_url', '')

    portada_val_raw = data.get('portadaUrl', '')
    fotos_raw = data.get('fotosRecorrido', [])

    fotos_limpias = []
    for f in fotos_raw:
        if isinstance(f, dict):
            if f.get('public_id') and _resolve_cloudinary_asset_url(f) != logo_url:
                fotos_limpias.append(f)
        elif isinstance(f, str) and f and f != logo_url:
            fotos_limpias.append(f)

    # Si la portada viene vacÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a o es igual al logo, usar la primera foto real de la propiedad
    if not portada_val_raw or portada_val_raw == logo_url:
        if fotos_limpias:
            portada_val_raw = fotos_limpias[0]

    portada_url = resolver_imagen(portada_val_raw)

    fotos_recorrido_urls = []
    for fv in fotos_limpias:
        url_firma = resolver_imagen(fv)
        if url_firma:
            fotos_recorrido_urls.append(url_firma)

    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Procesar escenas si las hay ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
    escenas = data.get('escenas', [])
    if isinstance(escenas, list):
        escenas_procesadas = []
        for escena in escenas:
            if isinstance(escena, dict) and escena.get('fotoUrl'):
                url_firma = resolver_imagen(escena['fotoUrl'])
                escena = {**escena, 'fotoUrl': url_firma or escena['fotoUrl']}
            escenas_procesadas.append(escena)
        data['escenas'] = escenas_procesadas

    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ DescripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n IA (si no viene en el payload) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
    descripcion = data.get('descripcion', '')
    if not descripcion:
        amenidades_str = ', '.join(amenidades) if amenidades else 'no especificadas'
        prompt_desc = f"""Genera una descripcion inmobiliaria profesional de 2 parrafos para:
{tipo_propiedad} en {operacion} en {ciudad}.
Precio: {moneda} {precio}.
Recamaras: {recamaras}. Banos: {banos}.
Superficie construida: {superficie_cubierta}m2.
Terreno: {superficie_total}m2.
Amenidades: {amenidades_str}.

Parrafo 1: Descripcion general de la propiedad y ubicacion (3-4 oraciones).
Parrafo 2: Destacar amenidades y estilo de vida que ofrece (3-4 oraciones).
Tono elegante y persuasivo. Solo los 2 parrafos, sin titulos ni bullets."""
        try:
            descripcion_ia = smart_call(
                prompt_desc,
                system_prompt="Sos un copywriter inmobiliario de lujo. Escribis en espanol, con tono sofisticado y persuasivo.",
                agente=user,
                task='pdf_description',
                listado_id=data.get('listado_id') or data.get('listadoId'),
                generation_run_id=data.get('generation_run_id') or data.get('generationRunId'),
                generation_step=data.get('generation_step') or data.get('generationStep') or 'pdf',
            )
        except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError) as exc:
            logger.warning("[PDF] Cerebras no disponible para descripcion (%s).", exc)
            raise
        if descripcion_ia:
            descripcion = descripcion_ia
            from .plan_utils import registrar_uso
            registrar_uso(user, 'ai')
        else:
            logger.warning("[PDF] Cerebras no devolvio descripcion.")
            raise APIKeyUnavailableError(
                'Cerebras no devolvio descripcion para el PDF.',
                provider='cerebras',
                scope='provider',
                quota_state='soft_rate_limited',
                retry_after_seconds=60,
            )


    # QR Code del agente
    qr_base64_ = generar_qr_url(
        telefono=agente_telefono,
        tipo_propiedad=tipo_propiedad,
        ciudad=ciudad,
        operacion=operacion,
        precio=precio,
        moneda=moneda
    )

    # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Construir contexto del template ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
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
        'agencia_logo_url':   logo_url or '',
        'portada_url_raw':    portada_url or '',
        'fotos_recorrido_raw': fotos_recorrido_urls,
        'logo_url_raw':       logo_url or '',
        'agente_nombre':      agente_nombre,
        'agente_telefono':    agente_telefono,
        'agente_email':       agente_email,
        'agente_rol':         agente_rol,
        'agente_foto_url':    agente_foto_url,
        'agencia_nombre':     agencia_nombre,
        'agente_contacto_html': _build_agent_contact_html(agente_telefono, agente_email),
        'qr_code':            qr_base64_,
        'whatsapp_url':       generar_whatsapp_url(
            telefono=agente_telefono,
            tipo_propiedad=tipo_propiedad,
            ciudad=ciudad,
            operacion=operacion,
            precio=precio,
            moneda=moneda,
        ),
    }


    return context, temp_files, listado_id_hint, tipo_propiedad, ciudad

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_pdf(request):
    # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
    # if not puede_generar(request.user, 'property'):
    #     return Response({
    #         "error": "limite_alcanzado",
    #         "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
    #         "upgrade_url": "/precios"
    #     }, status=status.HTTP_403_FORBIDDEN)

    generation_run_id = None
    generation_step_name = 'pdf'
    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        generation_run_id, generation_step_name = _mark_generation_running(data, 'pdf')
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        listado_id_val = data.get('listado_id') or data.get('listadoId')
        listado_obj_for_media = None
        if listado_id_val:
            listado_obj_for_media = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
        data = resolve_listing_media(listado_obj_for_media, data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        
        print(f"[PAYLOAD] portadaUrl tipo: {type(data.get('portadaUrl')).__name__} | valor: {str(data.get('portadaUrl', ''))[:80]}")
        print(f"[PAYLOAD] fotosRecorrido tipo: {type(data.get('fotosRecorrido')).__name__} | largo: {len(data.get('fotosRecorrido', []))}")
        if data.get('fotosRecorrido'):
            primera = data['fotosRecorrido'][0]
            print(f"[PAYLOAD] primera foto tipo: {type(primera).__name__} | valor: {str(primera)[:80]}")

        context, temp_files, listado_id_hint, tipo_propiedad, ciudad = construir_contexto_pdf(data, request.user, request)

        print(f"\n[PDF] Generando para {tipo_propiedad} en {ciudad} | portada: {bool(context.get('portada_url'))} | fotos: {len(context.get('fotos_recorrido', []))} | QR: sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­")

        from django.template.loader import render_to_string
        from django.http import HttpResponse
        from api.services.render_engine import render_html_to_pdf
        from api.services.almacenamiento import AlmacenamientoCloudinary
        from api.ai_services import generar_html_gemini

        listado_obj = None
        if listado_id_hint:
            listado_obj = Listado.objects.filter(id=listado_id_hint, agente=request.user).first()

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_hint)
        template_id = selection.get('template_id')

        context['listado_id'] = listado_id_hint
        context['template_id'] = template_id
        context['template_tokens'] = selection.get('template_tokens')
        context['template_instructions'] = selection.get('template_instructions')
        context['generation_run_id'] = generation_run_id
        context['generation_step'] = generation_step_name

        logger.info(
            "[PDF] generar_pdf listado_id=%s template_id=%s user_id=%s",
            listado_id_hint,
            template_id,
            request.user.id,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='pdf')

        try:
            html_string = generar_html_gemini(context, request.user)
        except (APIKeyUnavailableError, GeminiQuotaExhaustedError, GeminiRateLimitedError) as e:
            logger.warning("[PDF] IA no disponible en template (%s).", e)
            raise
        except Exception as e:
            logger.exception("[PDF] Error en sistema de templates IA")
            _mark_generation_failed(generation_run_id, generation_step_name, e, error_code='pdf_ia_failed')
            return Response(
                {
                    "error": "pdf_ia_failed",
                    "detalle": str(e)[:300],
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
            
        if not html_string:
            _mark_generation_failed(generation_run_id, generation_step_name, "Cerebras no devolvio HTML para el PDF.", error_code='pdf_ia_empty')
            return Response(
                {
                    "error": "pdf_ia_empty",
                    "detalle": "Cerebras no devolvio HTML para el PDF.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        html_string = _inject_agency_brand_lockup(html_string, context.get('logo_url', ''), context.get('agencia_nombre', ''))
        html_string = _repair_mojibake_text(html_string)
        validation_errors = _validate_generated_pdf_html(html_string, context)
        if validation_errors:
            try:
                repair_context = {
                    **context,
                    'pdf_repair_errors': validation_errors,
                    'pdf_repair_instruction': (
                        'Rehacer el HTML de PDF respetando template, galeria, amenidades, descripcion y contacto. '
                        'No generar una pagina web ni navegacion.'
                    ),
                }
                html_string = generar_html_gemini(repair_context, request.user)
                html_string = _inject_agency_brand_lockup(html_string, context.get('logo_url', ''), context.get('agencia_nombre', ''))
                html_string = _repair_mojibake_text(html_string)
                validation_errors = _validate_generated_pdf_html(html_string, context)
            except Exception:
                logger.exception('[PDF] Fallo retry de reparacion HTML')

        if validation_errors:
            detalle = f"Cerebras devolvio HTML incompleto para PDF: {', '.join(validation_errors)}"
            logger.error("[PDF] HTML invalido listado_id=%s errores=%s", listado_id_hint, validation_errors)
            _mark_generation_failed(generation_run_id, generation_step_name, detalle, error_code='pdf_html_invalid')
            return Response(
                {
                    "error": "pdf_html_invalid",
                    "detalle": detalle,
                    "template_id": template_id,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ ConversiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n a PDF Real con Playwright ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
        pdf_url = None
        pdf_cover_url = None
        pdf_error_detail = None
        try:
            print(f"[PDF] Iniciando conversiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n Playwright para listado {listado_id_hint}...")
            pdf_bytes = render_html_to_pdf(html_string)
            if pdf_bytes:
                print(f"[PDF] ConversiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n exitosa ({len(pdf_bytes)} bytes). Subiendo a Cloudinary...")
                pdf_url = AlmacenamientoCloudinary.guardar_pdf(
                    pdf_bytes, 
                    user_id=request.user.id, 
                    listado_id=listado_id_hint
                )
                if not pdf_url:
                    pdf_error_detail = "No se pudo subir el PDF generado a Cloudinary."
                
                # Persistir la URL en el listado para el historial
                if listado_obj and pdf_url:
                    pdf_cover_url = _render_and_store_pdf_cover(listado_obj, html_string)
                    if not listado_obj.datos_extra:
                        listado_obj.datos_extra = {}
                    if 'resultados' not in listado_obj.datos_extra:
                        listado_obj.datos_extra['resultados'] = {}

                    listado_obj.datos_extra['resultados']['pdf'] = {
                        "url": pdf_url,
                        "cover_frame_url": pdf_cover_url,
                        "cover_url": pdf_cover_url,
                        "template_id": template_id,
                        "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                        "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                    }
                    if pdf_cover_url:
                        listado_obj.datos_extra['dashboard_image_url'] = pdf_cover_url
                        listado_obj.datos_extra['cover_frame_url'] = pdf_cover_url
                    listado_obj.save(update_fields=['datos_extra'])
                    print(f"[PDF] URL guardada en DB: {pdf_url}")
            else:
                print("[PDF] Error: Playwright devolviÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ bytes vacÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­os.")
        except Exception as pdf_err:
            print(f"[PDF ERROR] FallÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ la conversiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n/subida: {pdf_err}")
            pdf_error_detail = str(pdf_err)

        # ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Limpiar archivos temporales de imÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡genes ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        if not pdf_url:
            detalle = pdf_error_detail or "No se pudo generar un PDF valido para guardar."
            logger.error("[PDF] Fallo sin URL persistida listado_id=%s detalle=%s", listado_id_hint, detalle)
            _mark_generation_failed(generation_run_id, generation_step_name, detalle, error_code='pdf_render_failed')
            return Response(
                {
                    "error": "No se pudo generar un PDF valido",
                    "detalle": detalle,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Devolvemos JSON para que el frontend maneje el preview y el link de descarga
        if request.user.is_authenticated:
            crear_notificacion(
                request.user,
                'contenido_generado',
                'Tu PDF ya está listo',
                'La ficha PDF fue generada correctamente y ya la tenés disponible para descargar.',
            )

        response_payload = {
            "html": html_string,
            "url": pdf_url,
            "cover_frame_url": pdf_cover_url,
            "cover_url": pdf_cover_url,
            "listado_id": listado_id_hint,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
        }
        _mark_generation_done(generation_run_id, generation_step_name, {
            "url": pdf_url,
            "cover_url": pdf_cover_url,
            "template_id": template_id,
        })
        return Response(response_payload, status=status.HTTP_200_OK)

    except APIKeyUnavailableError as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_pdf')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, user=request.user, source='generar_pdf')

    except Exception as exc:
        logger.exception("Error generando PDF")
        _mark_generation_failed(generation_run_id, generation_step_name, exc, error_code='pdf_failed')
        return Response({"error": "Error al generar PDF"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_imagen_post(request):
    """Genera imagen POST y la sube a Cloudinary"""
    generation_run_id = None
    generation_step_name = 'post'
    try:
        # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        generation_run_id, generation_step_name = _mark_generation_running(data, 'post')
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        
        print(f"[POST DEBUG] agenteNombre: {data.get('agenteNombre')}")
        print(f"[POST DEBUG] agenteTelefono: {data.get('agenteTelefono')}")
        print(f"[POST DEBUG] agenciaNombre: {data.get('agenciaNombre')}")
        print(f"[POST DEBUG] keys recibidas: {list(data.keys())}")

        listado_id_val = data.get('listado_id') or data.get('listadoId')
        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
        data = resolve_listing_media(listado_obj, data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response

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
            "agente_foto_url": branding.get('agente_foto_url', ''),
            "agente_contacto_html": branding.get('agente_contacto_html', ''),
            "leadbook_logo_url": _get_leadbook_logo_url(),
            "qr_url": generar_qr_url(
                telefono=branding.get('agente_telefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', '')
            ),
        }
        
        images_pool = _collect_property_images(data)
        portada_post = _resolve_primary_property_image(data) or (images_pool[0] if images_pool else '')
            
        context["portada_url"] = portada_post
        context["caracteristicas"] = [c for c in context["caracteristicas"] if c["valor"]]

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_post = TEMPLATE_POST_MAP.get(template_id, TEMPLATE_POST_MAP['dubai_night'])
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='post')

        html_content = render_to_string(template_post, context)
        html_content = _apply_template_tokens_to_html(html_content, template_id, selection.get('template_tokens'))
        html_content = _inject_agent_photo_html(html_content, branding.get('agente_foto_url', ''))
        html_content = _inject_agency_brand_lockup(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        html_content = _inject_agency_logo_fallback(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        print(f"[POST] Template elegido: {template_post}")
        image_stream = render_html_to_image(html_content, 1080, 1350)

        caption_style = _get_random_caption_style_instructions(listado_obj, formato='post')
        style_id = caption_style['id']
        style_name = caption_style['name']
        style_instructions = caption_style['instructions']
        print(f"[POST] Generando caption con estilo: {style_name}")

        prompt_text = f"""Escribi UN SOLO caption final para Instagram Feed, listo para publicar.
Propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}, {data.get('pais', '')}.
Operacion y precio: {data.get('operacion', 'venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.
Datos: habitaciones {data.get('recamaras', '')}, banos {data.get('banos', '')}, superficie {data.get('superficieCubierta') or data.get('superficieTotal') or ''}. Amenities: {', '.join(data.get('amenidades', [])) if isinstance(data.get('amenidades'), list) else ''}.
Contexto adicional: {data.get('contextoAdicional', '') or data.get('notasAdicionales', '')}.

Requisitos obligatorios:
- Enfoque de estilo requerido:
{style_instructions}
- 1100 a 1900 caracteres.
- Primera linea con gancho fuerte y personalidad, no generica.
- 2 a 4 parrafos cortos con deseo, valor comercial, inversion/estilo de vida y urgencia elegante.
- Incluir detalles concretos, no solo adjetivos.
- CTA directo a WhatsApp o mensaje privado para ficha completa, disponibilidad y visita.
- Cerrar con 25 a 30 hashtags variados, mezclando ciudad, pais, tipo de propiedad, operacion, inversion, lujo y real estate.
- No des opciones, no uses titulos como "Opcion 1", no expliques el caption, no menciones que sos IA.
Maximo 2200 caracteres. {_caption_preference_prompt(content_prefs)}"""
        prompt_text = _repair_mojibake_text(prompt_text)
        caption = smart_call(
            prompt_text,
            system_prompt="Sos un experto en marketing inmobiliario para redes sociales. Devolves solo copy final listo para publicar.",
            agente=request.user,
            task='post_caption',
            listado_id=listado_id_val,
            generation_run_id=generation_run_id,
            generation_step=generation_step_name,
        )
        caption = _finalize_caption_text(caption, data, formato='post', prefs=content_prefs, max_chars=2200)

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            img_url = AlmacenamientoCloudinary.guardar_post(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolviÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ una URL vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lida")
            public_id = img_url
        except Exception as cloud_err:
            _mark_generation_failed(generation_run_id, generation_step_name, cloud_err, error_code='post_upload_failed')
            print(f"[Cloudinary] Error crÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tico subiendo imagen: {cloud_err}")
            return Response({
                "error": "error_subida",
                "mensaje": "No se pudo subir la imagen a la nube. ReintentÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ en unos segundos."
            }, status=500)

        if listado_obj:
            caption_generation_count = _get_caption_generation_count(listado_obj, 'post') + 1
            actualizar_resultados_listado(
                listado_obj,
                'post',
                {
                    "url": img_url,
                    "caption": caption,
                    "caption_style_id": style_id,
                    "caption_style_name": style_name,
                    "caption_generation_count": caption_generation_count,
                    "template_id": template_id,
                    "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                    "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                },
            )

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')
            crear_notificacion(
                request.user,
                'contenido_generado',
                'Tu imagen POST ya está lista',
                'La pieza para feed fue generada correctamente y ya la tenés disponible en tu historial.',
            )

        response_payload = {
            "url": img_url,
            "public_id": public_id,
            "caption": caption,
            "caption_style_id": style_id,
            "caption_style_name": style_name,
            "texto": caption,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
        }
        _mark_generation_done(generation_run_id, generation_step_name, {
            "url": img_url,
            "template_id": template_id,
        })
        return Response(response_payload, status=status.HTTP_200_OK)
    except APIKeyUnavailableError as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_imagen_post')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, user=request.user, source='generar_imagen_post')
    except Exception as exc:
        logger.exception("Error generando imagen post")
        _mark_generation_failed(generation_run_id, generation_step_name, exc, error_code='post_failed')
        return Response({"error": "Error al generar imagen"}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_imagen_story(request):
    """Genera imagen Story y la sube a Cloudinary."""
    generation_run_id = None
    generation_step_name = 'story'
    try:
        # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
        # if not puede_generar(request.user, 'image'):
        #     return Response({
        #         "error": "limite_alcanzado",
        #         "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        generation_run_id, generation_step_name = _mark_generation_running(data, 'story')
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        listado_id_val = data.get('listado_id') or data.get('listadoId')

        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
        data = resolve_listing_media(listado_obj, data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_story = TEMPLATE_STORY_MAP.get(template_id, TEMPLATE_STORY_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='story')

        story_cover = _resolve_primary_property_image(data)
        images_pool = _collect_property_images(data)
        if not story_cover:
            story_cover = images_pool[0] if images_pool else ''

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
            "agente_foto_url": branding.get('agente_foto_url', ''),
            "agente_contacto_html": branding.get('agente_contacto_html', ''),
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
        html_content = _apply_template_tokens_to_html(html_content, template_id, selection.get('template_tokens'))
        html_content = _inject_agent_photo_html(html_content, branding.get('agente_foto_url', ''))
        html_content = _inject_agency_brand_lockup(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        html_content = _inject_agency_logo_fallback(html_content, branding.get('logo_url', ''), branding.get('agencia_nombre', ''))
        image_stream = render_html_to_image(html_content, 1080, 1920)

        caption = ''

        # Intentar subir a Cloudinary via Almacenamiento
        try:
            image_stream.seek(0)
            img_url = AlmacenamientoCloudinary.guardar_story(
                image_stream, user_id=request.user.id, listado_id=listado_id_val
            )
            if not img_url:
                raise Exception("Cloudinary no devolviÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ una URL vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lida")
            public_id = img_url
        except Exception as cloud_err:
            print(f"[Cloudinary] Error crÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tico subiendo story: {cloud_err}")
            _mark_generation_failed(generation_run_id, generation_step_name, cloud_err, error_code='story_upload_failed')
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
                    "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
                    "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
                },
            )

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')
            crear_notificacion(
                request.user,
                'contenido_generado',
                'Tu story ya está lista',
                'La story fue generada correctamente y ya la tenés disponible para publicar.',
            )

        response_payload = {
            "url": img_url,
            "public_id": public_id,
            "caption": caption,
            "texto": caption,
            "template_id": template_id,
            "brand_template_id": (selection.get('brand_template').id if selection.get('brand_template') else None),
            "brand_template_revision": (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None),
        }
        _mark_generation_done(generation_run_id, generation_step_name, {
            "url": img_url,
            "template_id": template_id,
        })
        return Response(response_payload, status=status.HTTP_200_OK)
    except APIKeyUnavailableError as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_imagen_story')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, user=request.user, source='generar_imagen_story')
    except Exception as exc:
        logger.exception("Error generando story")
        _mark_generation_failed(generation_run_id, generation_step_name, exc, error_code='story_failed')
        return Response({"error": "Error al generar story"}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_caption_story(request):
    """Genera caption para Story solo cuando el usuario lo solicita."""
    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        listado_id_val = data.get('listado_id') or data.get('listadoId')
        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
        data = resolve_listing_media(listado_obj, data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        caption_style = _get_random_caption_style_instructions(listado_obj, formato='story')
        style_id = caption_style['id']
        style_name = caption_style['name']
        style_instructions = caption_style['instructions']
        print(f"[STORY] Generando caption con estilo: {style_name}")

        prompt_text = f"""Escribi UN SOLO caption opcional para Instagram Story, listo para publicar.
Propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')}, {data.get('pais', '')}.
Operacion y precio: {data.get('operacion', 'venta')} por {data.get('moneda', 'USD')} {data.get('precio', '')}.
Maximo 650 caracteres.

Requisitos obligatorios:
- Enfoque de estilo requerido:
{style_instructions}
- Debe tener: gancho breve, sensacion premium, razon concreta para consultar, CTA a responder la story o escribir por WhatsApp y 8 a 12 hashtags.
- No des opciones, no uses titulos como "Opcion 1", no expliques el caption, no menciones que sos IA.
{_caption_preference_prompt(content_prefs)}"""
        prompt_text = _repair_mojibake_text(prompt_text)
        raw_caption = smart_call(
            prompt_text,
            system_prompt="Sos un experto en marketing inmobiliario para stories. Devolves solo copy final listo para publicar.",
            agente=request.user,
            task='story_caption',
            listado_id=listado_id_val,
        )
        caption = _finalize_caption_text(raw_caption, data, formato='story', prefs=content_prefs, max_chars=650)

        if listado_obj:
            caption_generation_count = _get_caption_generation_count(listado_obj, 'story') + 1
            datos = listado_obj.datos_extra if isinstance(listado_obj.datos_extra, dict) else {}
            story_result = (((datos.get('resultados') or {}).get('story')) or {})
            if not isinstance(story_result, dict):
                story_result = {}
            story_result['caption'] = caption
            story_result['texto'] = caption
            story_result['caption_style_id'] = style_id
            story_result['caption_style_name'] = style_name
            story_result['caption_generation_count'] = caption_generation_count
            actualizar_resultados_listado(listado_obj, 'story', story_result)

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'ai')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'ai')
            crear_notificacion(
                request.user,
                'contenido_generado',
                'Tu texto para story ya está listo',
                'El caption para story fue generado correctamente y ya lo podés usar.',
            )

        return Response({"caption": caption, "caption_style_id": style_id, "caption_style_name": style_name, "texto": caption}, status=status.HTTP_200_OK)
    except APIKeyUnavailableError as e:
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_caption_story')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        return _quota_error_response(e, user=request.user, source='generar_caption_story')
    except Exception:
        logger.exception("Error generando caption de story")
        return Response({"error": "Error al generar texto"}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_email(request):
    generation_run_id = None
    generation_step_name = 'email'
    try:
        # TODO: re-habilitar cuando el sistema de planes estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© estable
        # if not puede_generar(request.user, 'ai'):
        #     return Response({
        #         "error": "limite_alcanzado", 
        #         "mensaje": "Superaste el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de tu plan. ActualizÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ tu suscripciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n.",
        #         "upgrade_url": "/precios"
        #     }, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        generation_run_id, generation_step_name = _mark_generation_running(data, 'email')
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response
        listado_id_val = data.get('listado_id') or data.get('listadoId')

        listado_obj = None
        if listado_id_val:
            listado_obj = Listado.objects.filter(id=listado_id_val, agente=request.user).first()
        data = resolve_listing_media(listado_obj, data)
        blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
        if blocked_media_response:
            return blocked_media_response

        selection = _resolve_template_selection(data, request.user, listado_obj=listado_obj, listado_id_hint=listado_id_val)
        template_id = selection.get('template_id')
        template_email = TEMPLATE_EMAIL_MAP.get(template_id, TEMPLATE_EMAIL_MAP['dubai_night'])
        branding = _resolve_branding_payload(data, request.user)
        content_prefs = _attach_template_instructions_to_prefs(
            _resolve_content_preferences(request.user, selection.get('template_tokens'), data),
            selection,
        )

        if listado_obj:
            _persist_template_selection(listado_obj, selection, source='email')

        email_cover = _resolve_primary_property_image(data)
        images_pool = _collect_property_images(data)
        if not email_cover:
            email_cover = images_pool[0] if images_pool else ''
        email_gallery = [image_url for image_url in images_pool if image_url != email_cover][:6]
        template_meta = TEMPLATE_CATALOG.get(template_id, {})
        
        prompt_text = f"""
Redacta el cuerpo de un email profesional para ofrecer esta propiedad a un cliente interesado.
Tipo: {data.get('tipoPropiedad', 'Propiedad')}
Ciudad: {data.get('ciudad', '')}
Precio: {data.get('precio', '')}
OperaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: {data.get('operacion', 'venta')}
RecÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡maras: {data.get('recamaras', '')}
BaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±os: {data.get('banos', '')}
Superficie: {data.get('superficieCubierta') or data.get('superficieTotal') or ''}
Amenidades: {', '.join(data.get('amenidades', [])) if isinstance(data.get('amenidades'), list) else ''}
Agente: {branding.get('agente_nombre', '')}
Agencia: {branding.get('agencia_nombre', '')}
Preferencias de copy: {_caption_preference_prompt(content_prefs)}

Debe incluir: introducciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, galerÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a/recorrido, amenities, precio y una invitaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n general a responder el correo.
No incluyas telÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fonos, emails, WhatsApp, links, botones ni etiquetas <a>; la plantilla se encarga de los contactos reales.

Devuelve **ÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â¡NICAMENTE** y estrictamente un objeto JSON vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido (sin Markdown, sin ````json) con la siguiente estructura y nada mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s:
{{
  "asunto": "el asunto sugerido del correo",
  "html": "el cuerpo del email en una lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­nea, todo en codigo html inline, usando etiquetas como <br>, <strong> (sin los tags <html>, <head> o <body>, solo contenido directo)",
  "texto_plano": "el equivalente en texto plano bÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡sico pero atractivo"
}}
"""
        prompt_text = _repair_mojibake_text(prompt_text)
        json_str = smart_call(
            prompt_text,
            system_prompt="Sos un asistente técnico que solo responde en JSON.",
            agente=request.user,
            task='email',
            listado_id=listado_id_val,
            generation_run_id=generation_run_id,
            generation_step=generation_step_name,
        )
        
        if json_str is None:
            json_str = '{"asunto": "Propiedad destacada", "html": "<div>Tenemos una excelente oportunidad para vos. ContestÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ a este mail para mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s detalles.</div>", "texto_plano": "Tenemos una excelente oportunidad para vos. ContestÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ a este mail para mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s detalles."}'
            
        import json
        json_str = _repair_mojibake_text(json_str)
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
            crear_notificacion(
                request.user,
                'contenido_generado',
                'Tu email ya está listo',
                'El email inmobiliario fue generado correctamente y ya lo tenés disponible.',
            )

        parsed_html = _sanitize_generated_email_html(parsed.get('html', ''))
        parsed_text = _sanitize_generated_email_text(parsed.get('texto_plano', '') or parsed.get('html', ''))
        if not parsed_html:
            fallback_body = parsed_text or 'Propiedad disponible'
            parsed_html = f'<div>{html_lib.escape(fallback_body).replace("\n", "<br>")}</div>'

        parsed['asunto'] = _repair_mojibake_text(parsed.get('asunto', 'Propiedad destacada')).strip() or 'Propiedad destacada'
        parsed['html'] = parsed_html
        parsed['texto_plano'] = parsed_text or 'Propiedad disponible'

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
            "agenteFotoUrl": branding.get('agente_foto_url', ''),
            "agente_contacto_html": branding.get('agente_contacto_html', ''),
            "portada_url": email_cover,
            "galeria_urls": email_gallery,
            "logo_url": branding.get('logo_url', ''),
            "whatsapp_url": generar_whatsapp_url(
                telefono=branding.get('agente_telefono', ''),
                tipo_propiedad=data.get('tipoPropiedad', ''),
                ciudad=data.get('ciudad', ''),
                operacion=data.get('operacion', ''),
                precio=data.get('precio', ''),
                moneda=data.get('moneda', ''),
            ),
            "agenteTelefonoDisplay": _format_phone_display(branding.get('agente_telefono', '')),
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
        # We comment out the manual HTML gallery block injection because all email templates
        # natively loop over `galeria_urls` in Django's template engine. Manual injection causes duplicate galleries.
        # if email_gallery:
        #     gallery_cells = ''.join(
        #         f'<td width="50%" style="padding:6px;"><img src="{url}" alt="Galeria" width="260" style="display:block;width:100%;height:150px;object-fit:cover;border:1px solid #2a2a2a;"></td>'
        #         for url in email_gallery[:6]
        #     )
        #     rows = []
        #     for idx in range(0, len(email_gallery[:6]), 2):
        #         pair = email_gallery[idx:idx + 2]
        #         cells = ''.join(
        #             f'<td width="50%" style="padding:6px;"><img src="{url}" alt="Galeria" width="260" style="display:block;width:100%;height:150px;object-fit:cover;border:1px solid #2a2a2a;"></td>'
        #             for url in pair
        #         )
        #         if len(pair) == 1:
        #             cells += '<td width="50%" style="padding:6px;"></td>'
        #         rows.append(f'<tr>{cells}</tr>')
        #     gallery_block = (
        #         '<tr><td style="padding:10px 34px 0 34px;">'
        #         '<div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#8fb1d1;margin-bottom:8px;font-weight:700;">Galería</div>'
        #         '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        #         + ''.join(rows) +
        #         '</table></td></tr>'
        #     )
        #     premium_html = premium_html.replace('<tr>\n            <td style="padding:30px 34px 22px 34px;">', f'{gallery_block}\n<tr>\n            <td style="padding:30px 34px 22px 34px;">', 1)
        #
        premium_html = _apply_template_tokens_to_html(premium_html, template_id, selection.get('template_tokens'))
        if branding.get('agente_foto_url'):
            agent_img = (
                f'<img src="{branding.get("agente_foto_url")}" alt="Foto agente" '
                'width="58" height="58" style="display:block;width:58px;height:58px;border-radius:50%;object-fit:cover;margin-bottom:10px;border:2px solid #00e5ff;">'
            )
            premium_html = re.sub(
                r'(<div style="padding-top:20px;border-top:[^"]*;color:[^"]*;font-size:13px;line-height:1\.6;">)',
                r'\1' + agent_img,
                premium_html,
                count=1,
            )
        parsed["html"] = _repair_mojibake_text(premium_html)
        parsed["template_id"] = template_id
        parsed["brand_template_id"] = (selection.get('brand_template').id if selection.get('brand_template') else None)
        parsed["brand_template_revision"] = (selection.get('brand_template_revision').revision if selection.get('brand_template_revision') else None)
        
        # PERSISTENCIA: Guardar en el listado
        if listado_obj:
            actualizar_resultados_listado(listado_obj, 'email', parsed)

        _mark_generation_done(generation_run_id, generation_step_name, {
            "asunto": parsed.get("asunto", ""),
            "template_id": template_id,
        })
        return Response(parsed, status=status.HTTP_200_OK)
    except APIKeyUnavailableError as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, fallback_status=status.HTTP_503_SERVICE_UNAVAILABLE, user=request.user, source='generar_email')
    except (GeminiQuotaExhaustedError, GeminiRateLimitedError, ElevenLabsQuotaExhaustedError, ElevenLabsRateLimitedError) as e:
        _mark_generation_failed(generation_run_id, generation_step_name, e)
        return _quota_error_response(e, user=request.user, source='generar_email')
    except Exception as exc:
        logger.exception("Error generando email")
        _mark_generation_failed(generation_run_id, generation_step_name, exc, error_code='email_failed')
        return Response({"error": "Error al generar email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
            response['Content-Security-Policy'] = "frame-ancestors 'self' https://leadbook.com.ar https://www.leadbook.com.ar https://dash-admin-leadbook.vercel.app"
            return response
    return Response({"error": "PDF no encontrado"}, status=status.HTTP_404_NOT_FOUND)

import mercadopago
from decouple import config
from decimal import Decimal, InvalidOperation
from django.db import transaction

MP_TEST_PRICE = Decimal('100')
MP_PRODUCTION_PRICE = Decimal('100')
MP_PLAN_PRICES = {
    'starter': Decimal('100'),
    'pro': Decimal('100'),
    'scale': Decimal('100'),
    'business': Decimal('100'),
}

MP_PLAN_LABELS = {
    'starter': 'LeadBook Starter',
    'pro': 'LeadBook Pro',
    'scale': 'LeadBook Scale',
    'business': 'LeadBook Business',
}

MP_EXTRA_ITEMS = {
    'pack_completo': {'nombre': 'Pack Completo - Gemini, ElevenLabs y UploadPost'},
}

MP_EXTRA_SERVICES = {
    'extra_pack_completo': ['gemini', 'elevenlabs', 'uploadpost'],
}


def _mp_mode():
    mode = config('MP_MODE', default='production').strip().lower()
    return 'test' if mode == 'test' else 'production'


def _mp_access_token():
    return config('MP_ACCESS_TOKEN', default='').strip()


def _mp_public_key():
    return config('MP_PUBLIC_KEY', default='').strip()


def _mp_unit_price(plan=None):
    if _mp_mode() == 'test':
        return MP_TEST_PRICE
    if plan in MP_PLAN_PRICES:
        return MP_PLAN_PRICES[plan]
    return MP_TEST_PRICE if _mp_mode() == 'test' else MP_PRODUCTION_PRICE


def _mp_sdk():
    token = _mp_access_token()
    if not token:
        raise ValueError('Mercado Pago access token no configurado')
    return mercadopago.SDK(token)


def _mp_frontend_url():
    return config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app').rstrip('/')


def _mp_notification_url():
    backend_url = config('BACKEND_URL', default='http://localhost:8000').rstrip('/')
    return f'{backend_url}/api/mp/webhook/'


def _mp_decimal(value):
    try:
        return Decimal(str(value or '0'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _mp_pago_status(mp_status):
    if mp_status in {'approved', 'authorized'}:
        return 'approved'
    if mp_status in {'refunded', 'charged_back'}:
        return 'refunded'
    if mp_status in {'pending', 'in_process', 'in_mediation'}:
        return 'pending'
    return 'rejected'


def _mp_available_stock_missing(user, services):
    from .models import APIKey, Servicio

    missing = []
    for service_name in services:
        servicio = Servicio.objects.filter(nombre=service_name, activo=True).first()
        if not servicio:
            missing.append(service_name)
            continue

        available = APIKey.objects.filter(
            servicio=servicio,
            status='available',
        ).exclude(
            assignments__user=user,
            assignments__servicio=servicio,
        ).exists()
        if not available:
            missing.append(service_name)
    return missing


def _mp_create_preference(preference_data):
    preference_response = _mp_sdk().preference().create(preference_data)
    if preference_response.get('status') == 201:
        response = preference_response.get('response', {})
        init_point = response.get('init_point') or response.get('sandbox_init_point')
        amount = ((preference_data.get('items') or [{}])[0] or {}).get('unit_price')
        return {
            'init_point': init_point,
            'checkout_url': init_point,
            'preference_id': response.get('id'),
            'mode': _mp_mode(),
            'amount': str(amount if amount is not None else _mp_unit_price()),
        }
    print(f"MP Error: {preference_response}")
    return None


def _mp_webhook_event(request):
    event_type = request.data.get('type') or request.data.get('topic') or request.query_params.get('type') or request.query_params.get('topic')
    action = request.data.get('action') or request.query_params.get('action') or ''
    data = request.data.get('data') if isinstance(request.data, dict) else None
    data_id = (data.get('id') if isinstance(data, dict) else None) or request.data.get('id') or request.query_params.get('id') or request.query_params.get('data.id')
    return str(event_type or ''), str(action or ''), str(data_id or '')


def _mp_webhook_signature_valid(request, data_id):
    from django.conf import settings
    from django.utils.crypto import constant_time_compare
    import hashlib
    import hmac

    secret = str(getattr(settings, 'MP_WEBHOOK_SECRET', '') or '').strip()
    if not secret:
        return bool(getattr(settings, 'DEBUG', False))

    signature_header = request.headers.get('x-signature') or request.headers.get('X-Signature') or ''
    request_id = request.headers.get('x-request-id') or request.headers.get('X-Request-Id') or ''
    parts = {}
    for item in signature_header.split(','):
        if '=' in item:
            key, value = item.split('=', 1)
            parts[key.strip()] = value.strip()

    ts = parts.get('ts')
    v1 = parts.get('v1')
    if not data_id or not request_id or not ts or not v1:
        return False

    manifest = f'id:{data_id};request-id:{request_id};ts:{ts};'
    digest = hmac.new(secret.encode('utf-8'), manifest.encode('utf-8'), hashlib.sha256).hexdigest()
    return constant_time_compare(digest, v1)


def _mp_fetch_payment(payment_id):
    response = requests.get(
        f'https://api.mercadopago.com/v1/payments/{payment_id}',
        headers={'Authorization': f'Bearer {_mp_access_token()}'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _mp_notify(user, tipo, titulo, mensaje):
    try:
        crear_notificacion(user, tipo, titulo, mensaje)
    except Exception as exc:
        logger.warning(f'[MP] No se pudo crear notificaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: {exc}')


def _mp_assign_paid_extra(agent, tipo, pago):
    from .services.pool_service import APIPoolService

    APIPoolService.ensure_user_quotas(agent)
    return [], []

def _mp_process_payment(payment_data):
    from .models import Agent, Pago

    external_ref = str(payment_data.get('external_reference') or '')
    print(
        f"[MP] processing payment id={payment_data.get('id')} "
        f"status={payment_data.get('status')} external_reference={external_ref}",
        flush=True,
    )
    if '|' not in external_ref:
        return {'status': 'ignored', 'reason': 'external_reference_missing'}

    user_id, tipo = external_ref.split('|', 1)
    if tipo in MP_PLAN_LABELS:
        tipo = f'plan_{tipo}'

    valid_tipos = {f'plan_{plan}' for plan in MP_PLAN_LABELS} | set(MP_EXTRA_SERVICES)
    if tipo not in valid_tipos:
        return {'status': 'ignored', 'reason': 'invalid_type'}

    agent = Agent.objects.get(id=int(user_id))
    mp_payment_id = str(payment_data.get('id') or '')
    mp_status = str(payment_data.get('status') or '')
    pago_status = _mp_pago_status(mp_status)
    amount = _mp_decimal(payment_data.get('transaction_amount'))
    currency = str(payment_data.get('currency_id') or 'ARS')[:10]

    with transaction.atomic():
        pago, _ = Pago.objects.select_for_update().get_or_create(
            mp_payment_id=mp_payment_id,
            defaults={
                'user': agent,
                'tipo': tipo,
                'mp_status': pago_status,
                'monto': amount,
                'moneda': currency,
                'external_reference': external_ref,
                'datos_mp': payment_data,
            },
        )

        pago.user = pago.user or agent
        pago.tipo = tipo
        pago.mp_status = pago_status
        pago.monto = amount
        pago.moneda = currency
        pago.external_reference = external_ref
        pago.datos_mp = payment_data
        pago.procesado_en = timezone.now()
        pago.save(update_fields=[
            'user', 'tipo', 'mp_status', 'monto', 'moneda',
            'external_reference', 'datos_mp', 'procesado_en'
        ])

        if pago_status != 'approved':
            print(f"[MP] payment recorded id={mp_payment_id} status={pago_status}", flush=True)
            return {'status': 'recorded', 'mp_status': pago_status}

        if tipo.startswith('extra_'):
            assigned, missing = _mp_assign_paid_extra(agent, tipo, pago)
            print(
                f"[MP] extra payment processed id={mp_payment_id} tipo={tipo} "
                f"assigned={assigned} missing={missing}",
                flush=True,
            )
            return {'status': 'processed', 'assigned': assigned, 'missing': missing}

        plan = tipo.replace('plan_', '', 1)
        agent.plan_nombre = plan
        agent.plan_activo = True
        agent.plan_seleccionado = True
        agent.free_trial_started_at = None
        agent.free_trial_ends_at = None
        agent.save(update_fields=[
            'plan_nombre', 'plan_activo', 'plan_seleccionado',
            'free_trial_started_at', 'free_trial_ends_at'
        ])
        from .services.pool_service import assign_apis_to_agent
        assign_apis_to_agent(agent)
        _mp_notify(agent, 'pago_aprobado', 'Plan activado', f'Tu plan {plan} ya está activo.')
        print(f"[MP] plan payment processed id={mp_payment_id} user={agent.email} plan={plan}", flush=True)
        return {'status': 'processed', 'plan': plan}

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout(request):
    plan = request.data.get('plan')
    ciclo = request.data.get('ciclo', 'monthly')

    if plan not in MP_PLAN_LABELS:
        return Response({"error": "Plan invÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido"}, status=400)

    precio = _mp_unit_price(plan)
    nombre = f"{MP_PLAN_LABELS[plan]} ({'Anual' if ciclo == 'annual' else 'Mensual'})"
    frontend_url = _mp_frontend_url()

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
        "notification_url": _mp_notification_url(),
        "external_reference": f"{request.user.id}|plan_{plan}",
        "metadata": {
            "user_id": request.user.id,
            "tipo": f"plan_{plan}",
            "mp_mode": _mp_mode(),
        },
    }

    try:
        response_data = _mp_create_preference(preference_data)
    except Exception as exc:
        logger.exception(f'[MP] Error creando checkout plan: {exc}')
        response_data = None

    if response_data:
        return Response(response_data)
    return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout_api_extra(request):
    """Genera link de pago para comprar una API adicional."""
    servicio = request.data.get('servicio', 'pack_completo')

    if servicio not in MP_EXTRA_ITEMS:
        return Response({"error": "Servicio invÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido"}, status=400)

    tipo = f'extra_{servicio}'
    missing_stock = _mp_available_stock_missing(request.user, MP_EXTRA_SERVICES[tipo])
    if missing_stock:
        return Response({
            "error": "Sin stock disponible para este recurso",
            "servicios_sin_stock": missing_stock,
        }, status=409)

    item = MP_EXTRA_ITEMS[servicio]
    precio = _mp_unit_price()
    frontend_url = _mp_frontend_url()

    preference_data = {
        "items": [{
            "id": tipo,
            "title": item['nombre'],
            "description": f"Uso adicional permanente mensual de {item['nombre']}. Se suma a tu lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite actual.",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(precio)
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/dashboard?extra=exitoso&servicio={servicio}",
            "failure": f"{frontend_url}/precios?extra=fallido",
            "pending": f"{frontend_url}/dashboard?extra=pendiente"
        },
        "auto_return": "approved",
        "notification_url": _mp_notification_url(),
        "external_reference": f"{request.user.id}|{tipo}",
        "metadata": {
            "user_id": request.user.id,
            "tipo": tipo,
            "servicio": servicio,
            "mp_mode": _mp_mode(),
        },
    }

    try:
        response_data = _mp_create_preference(preference_data)
    except Exception as exc:
        logger.exception(f'[MP] Error creando checkout extra: {exc}')
        response_data = None

    if response_data:
        return Response(response_data)
    return Response({"error": "Error al crear preferencia de pago"}, status=500)



@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    from .models import WebhookLog

    topic, action, data_id = _mp_webhook_event(request)
    if not _mp_webhook_signature_valid(request, data_id):
        logger.warning('[MP] webhook rejected: invalid signature topic=%s action=%s data_id=%s', topic, action, data_id)
        return Response({'error': 'invalid_signature'}, status=status.HTTP_401_UNAUTHORIZED)

    body_payload = request.data
    if hasattr(body_payload, 'dict'):
        body_payload = body_payload.dict()
    elif isinstance(body_payload, dict):
        body_payload = dict(body_payload)
    else:
        body_payload = {}
    payload = {
        'body': body_payload,
        'query': request.query_params.dict(),
    }
    webhook_log = WebhookLog.objects.create(
        fuente='mercadopago',
        event_id=data_id or None,
        event_type=topic or action or None,
        payload=payload,
    )
    print(f"[MP] webhook received topic={topic} action={action} data_id={data_id}", flush=True)

    is_payment_event = topic == 'payment' or action.startswith('payment')
    if not data_id or not is_payment_event:
        webhook_log.status = 'ignored'
        webhook_log.procesado_en = timezone.now()
        webhook_log.save(update_fields=['status', 'procesado_en'])
        print(f"[MP] webhook ignored topic={topic} action={action} data_id={data_id}", flush=True)
        return Response({"status": "ok"})

    try:
        payment_data = _mp_fetch_payment(data_id)
        result = _mp_process_payment(payment_data)
        webhook_log.status = 'processed' if result.get('status') != 'ignored' else 'ignored'
        webhook_log.procesado_en = timezone.now()
        webhook_log.save(update_fields=['status', 'procesado_en'])
        print(f"[MP] webhook processed data_id={data_id} result={result}", flush=True)
        return Response({"status": "ok", "result": result})
    except Exception as e:
        webhook_log.status = 'error'
        webhook_log.error = str(e)
        webhook_log.procesado_en = timezone.now()
        webhook_log.save(update_fields=['status', 'error', 'procesado_en'])
        logger.exception(f"[MP] Error webhook: {e}")
        print(f"[MP] webhook error data_id={data_id} error={e}", flush=True)
        return Response({"status": "error"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def plan_status(request):
    from .plan_utils import LIMITES
    from .tracking import get_uploadpost_quota

    user = request.user
    plan = user.plan_nombre or 'starter'
    trial_status = get_free_trial_status(user)
    limites = LIMITES.get(plan, LIMITES['starter'])
    now = timezone.now()
    listados_mes = UsageLog.objects.filter(agent=user, tipo='property', fecha__year=now.year, fecha__month=now.month).count()
    videos_used = UsageLog.objects.filter(agent=user, tipo='video', fecha__year=now.year, fecha__month=now.month).count()
    uploadpost_quota = get_uploadpost_quota(user)

    return Response({
        "plan_nombre": plan,
        "plan_activo": user.plan_activo,
        "plan_seleccionado": user.plan_seleccionado,
        "requires_payment": user.plan_activo is False,
        "trial_started_at": trial_status['trial_started_at'],
        "trial_ends_at": trial_status['trial_ends_at'],
        "trial_seconds_left": trial_status['trial_seconds_left'],
        "trial_expired": trial_status['trial_expired'],
        "contact_whatsapp": "+542324581770",
        "properties_per_month": limites['properties'],
        "video_generations": limites['videos'],
        "auto_posts_per_month": limites.get('auto_posts'),
        "auto_posting_unlimited": limites.get('auto_posts') is None,
        "properties_used": listados_mes,
        "videos_used": videos_used,
        "auto_posts_used": uploadpost_quota.requests_this_month if uploadpost_quota else 0,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seleccionar_plan_free(request):
    return Response({
        "error": "access_code_required",
        "message": "La prueba Starter solo se activa con un codigo de acceso al crear la cuenta.",
    }, status=status.HTTP_403_FORBIDDEN)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_plan_info_mp(request):
    from .plan_utils import LIMITES
    from .models import UsageLog
    from .tracking import get_uploadpost_quota
    agent = request.user
    plan = agent.plan_nombre or 'starter'
    trial_status = get_free_trial_status(agent)
    limites = LIMITES.get(plan, LIMITES['starter'])
    now = timezone.now()
    uploadpost_quota = get_uploadpost_quota(agent)
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
        "plan_activo": agent.plan_activo,
        "plan_seleccionado": agent.plan_seleccionado,
        "trial_started_at": trial_status['trial_started_at'],
        "trial_ends_at": trial_status['trial_ends_at'],
        "trial_seconds_left": trial_status['trial_seconds_left'],
        "trial_expired": trial_status['trial_expired'],
        "contact_whatsapp": "+542324581770",
        "mp_public_key": _mp_public_key(),
        "mp_mode": _mp_mode(),
        "uso_actual": {
            "properties_used": listados_mes,
            "ai_used": ai_used,
            "images_used": images_used,
            "videos_used": videos_used,
            "auto_posts_used": uploadpost_quota.requests_this_month if uploadpost_quota else 0,
        },
        "limites": {
            "properties_per_month": limites['properties'],
            "ai_generations": limites['ai'],
            "image_generations": limites['images'],
            "video_generations": limites['videos'],
            "auto_posts_per_month": limites.get('auto_posts'),
            "auto_posting_unlimited": limites.get('auto_posts') is None,
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
        return Response({"error": "Demasiados intentos. EsperÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ 15 minutos."}, status=429)

    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)

    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at
    )

    # En Railway no hay garantÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a de que exista un worker Celery consumiendo cola.
    # Enviamos el OTP en el request para no reportar "enviado" cuando solo quedÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ encolado.
    import sys
    from django.conf import settings

    # Log de diagnÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³stico MUY visible en Railway
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

        sent_mode = str(send_otp_email_async(email, code))
        print(f"[EMAIL] Resultado envio OTP a {email}: {sent_mode}", flush=True)
    except Exception as exc:
        print(f"[EMAIL] ERROR al enviar OTP: {type(exc).__name__}: {str(exc)}", flush=True)
        import traceback
        traceback.print_exc()
        sent_mode = f'error:{type(exc).__name__}'

    sys.stdout.flush()
    if not str(sent_mode or '').startswith('sent:'):
        return Response({
            "error": "email_send_failed",
            "message": "No se pudo enviar el codigo por email. IntentÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ de nuevo en unos minutos.",
            "email": email,
            "_mode": sent_mode,
        }, status=502)

    return Response({"mensaje": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo enviado", "email": email, "_mode": sent_mode})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('code', '').strip()

    if not email or not code:
        return Response({"error": "Email y cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo requeridos"}, status=400)

    otp = OTPCode.objects.filter(
        email=email,
        verified=False
    ).order_by('-creado_en').first()

    if not otp:
        return Response({"error": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo invÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido o ya utilizado"}, status=400)

    if otp.is_expired():
        return Response({"error": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo expirado. PedÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ uno nuevo."}, status=400)

    if otp.attempts >= 5:
        return Response({"error": "Demasiados intentos. PedÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ un nuevo cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo."}, status=429)

    # Verificar hash ANTES de incrementar attempts para no penalizar el intento correcto
    code_hash = OTPCode.hash_code(code)
    if otp.code_hash != code_hash:
        otp.attempts += 1
        otp.save()
        intentos_restantes = 5 - otp.attempts
        return Response({"error": f"CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo incorrecto. {intentos_restantes} intentos restantes."}, status=400)

    # CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo correcto
    otp.verified = True
    otp.save()

    return Response({"verificado": True, "email": email})


@api_view(['POST'])
@permission_classes([AllowAny])
def recuperar_password(request):
    from .models import Agent
    from django.conf import settings
    from datetime import timedelta
    from django.utils import timezone
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)

    generic_response = {"mensaje": "Si el email existe, te enviamos un cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo de recuperaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n."}

    recent = OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        creado_en__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    if recent >= 3:
        return Response({"error": "Demasiados intentos. EsperÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ 15 minutos."}, status=429)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response(generic_response, status=200)
    
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

    # EnvÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ncrono: no dependemos de worker Celery para entregar el cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo.
    sent_mode = None
    try:
        from .tasks import send_otp_email_async
        sent_mode = str(send_otp_email_async(email, code))
        print(f"[OTP-RECOV] Resultado envio a {email}: {sent_mode}", flush=True)
    except Exception as exc:
        print(f"[OTP-RECOV] ERROR envio: {type(exc).__name__}: {exc}", flush=True)
        sent_mode = f'error:{type(exc).__name__}'

    if not str(sent_mode or '').startswith('sent:'):
        return Response({
            "error": "email_send_failed",
            "message": "No se pudo enviar el codigo por email. IntentÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ de nuevo en unos minutos.",
            "email": email if settings.DEBUG else None,
            "_mode": sent_mode if settings.DEBUG else None,
        }, status=502)

    return Response(generic_response, status=200)


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
        return Response({"error": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo invÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido"}, status=400)
    if otp.is_expired():
        return Response({"error": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo expirado"}, status=400)
    if not otp.is_valid(code):
        otp.attempts += 1
        otp.save(update_fields=['attempts'])
        return Response({"error": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo incorrecto"}, status=400)

    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "CÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³digo invÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido"}, status=400)

    try:
        from django.contrib.auth.password_validation import validate_password
        validate_password(nueva_password, user=user)
    except Exception as exc:
        return Response({"error": "password_insegura", "detalle": list(getattr(exc, 'messages', [str(exc)]))}, status=400)
    
    user.set_password(nueva_password)
    user.save()
    
    otp.verified = True
    otp.save()
    
    return Response({"mensaje": "ContraseÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a actualizada correctamente"}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_terminos(request):
    """Devuelve los TÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rminos y Condiciones vigentes"""
    try:
        terminos = TerminosCondiciones.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = TerminosCondicionesSerializer(terminos)
        return Response(serializer.data)
    except TerminosCondiciones.DoesNotExist:
        return Response({"error": "TÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rminos no disponibles"}, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_politica_privacidad(request):
    """Devuelve la PolÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica de Privacidad vigente"""
    try:
        politica = PoliticaPrivacidad.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = PoliticaPrivacidadSerializer(politica)
        return Response(serializer.data)
    except PoliticaPrivacidad.DoesNotExist:
        return Response({"error": "PolÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica de privacidad no disponible"}, status=404)

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


FIELD_PRESET_ALLOWED_FIELDS = {
    'tipoPropiedad', 'operacion', 'pais', 'idioma', 'ciudad', 'direccion',
    'moneda', 'precio', 'recamaras', 'banos', 'superficieConstruida',
    'superficieTerreno', 'estacionamientos', 'pisosNiveles',
    'superficieCubierta', 'superficieTotal', 'niveles',
}


def _serialize_field_preset(preset):
    return {
        'id': preset.id,
        'field': preset.field,
        'value': preset.value,
        'label': preset.label or preset.value,
        'metadata': preset.metadata or {},
        'usage_count': preset.usage_count,
        'last_used_at': preset.last_used_at.isoformat() if preset.last_used_at else None,
    }


def _upsert_field_preset(user, raw):
    from .models import UserFieldPreset

    field = str((raw or {}).get('field') or '').strip()
    value = str((raw or {}).get('value') or '').strip()
    if field not in FIELD_PRESET_ALLOWED_FIELDS or not value:
        return None

    label = str((raw or {}).get('label') or value).strip()[:255]
    metadata = (raw or {}).get('metadata') if isinstance((raw or {}).get('metadata'), dict) else {}

    preset, created = UserFieldPreset.objects.get_or_create(
        user=user,
        field=field,
        value=value[:255],
        defaults={
            'label': label,
            'metadata': metadata,
            'last_used_at': timezone.now(),
        },
    )
    if not created:
        preset.label = label or preset.label
        preset.metadata = {**(preset.metadata or {}), **metadata}
        preset.usage_count += 1
        preset.last_used_at = timezone.now()
        preset.save(update_fields=['label', 'metadata', 'usage_count', 'last_used_at', 'updated_at'])
    return preset


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def field_presets_collection(request):
    from .models import UserFieldPreset

    if request.method == 'GET':
        raw_fields = request.query_params.get('fields', '')
        fields = [f.strip() for f in raw_fields.split(',') if f.strip()]
        fields = [f for f in fields if f in FIELD_PRESET_ALLOWED_FIELDS]
        try:
            limit = min(max(int(request.query_params.get('limit', 8) or 8), 1), 30)
        except (TypeError, ValueError):
            limit = 8

        qs = UserFieldPreset.objects.filter(user=request.user)
        if fields:
            qs = qs.filter(field__in=fields)
        qs = qs.order_by('field', '-usage_count', '-last_used_at')

        grouped = {field: [] for field in fields}
        items = []
        counts = {}
        for preset in qs:
            count = counts.get(preset.field, 0)
            if count >= limit:
                continue
            serialized = _serialize_field_preset(preset)
            grouped.setdefault(preset.field, []).append(serialized)
            items.append(serialized)
            counts[preset.field] = count + 1

        return Response({'presets': grouped, 'items': items})

    payload_items = request.data.get('items') if isinstance(request.data, dict) else None
    if not isinstance(payload_items, list):
        payload_items = [request.data]

    saved = []
    for raw in payload_items:
        preset = _upsert_field_preset(request.user, raw if isinstance(raw, dict) else {})
        if preset:
            saved.append(_serialize_field_preset(preset))
    return Response({'presets': saved}, status=status.HTTP_201_CREATED if saved else status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def field_preset_detail(request, preset_id):
    from .models import UserFieldPreset

    deleted, _ = UserFieldPreset.objects.filter(id=preset_id, user=request.user).delete()
    if not deleted:
        return Response({'error': 'Preset no encontrado'}, status=404)
    return Response({'ok': True})

from django.utils import timezone
from datetime import timedelta

ADMIN_KEY = config('ADMIN_KEY', default='')

def check_admin(request):
    from admin_panel.auth import is_admin_request
    return is_admin_request(request)


def debug_endpoints_enabled():
    from django.conf import settings
    return bool(getattr(settings, 'ALLOW_DEBUG_ENDPOINTS', False))

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats(request):
    """
    Dashboard de administraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: MÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©tricas globales y estado detallado de las APIs asignadas.
    """
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
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
    for plan in ['starter','pro','scale','business']:
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
                "plan_nombre": getattr(a, 'plan_nombre', 'starter'),
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
    planes_validos = ['starter','pro','scale','business']
    
    if nuevo_plan not in planes_validos:
        return Response({"error": "Plan invÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido"}, status=400)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.plan_nombre = nuevo_plan
        agent.plan_activo = True
        agent.plan_seleccionado = True
        agent.free_trial_started_at = None
        agent.free_trial_ends_at = None
        agent.save(update_fields=[
            'plan_nombre', 'plan_activo', 'plan_seleccionado',
            'free_trial_started_at', 'free_trial_ends_at', 'updated_at'
        ])
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
    from .tracking import get_uploadpost_quota

    listados = Listado.objects.filter(agente=agent)
    property_usage = UsageLog.objects.filter(agent=agent, tipo='property')
    listados_este_mes = property_usage.filter(fecha__gte=start_of_month).count()
    total_generados = property_usage.count()
    videos_creados = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    uploadpost_quota = get_uploadpost_quota(agent)
    auto_posts_used = uploadpost_quota.requests_this_month if uploadpost_quota else 0

    listados_recientes = [
        _serialize_listing_summary(listado)
        for listado in listados.order_by('-creado_en')[:8]
    ]

    plan = agent.plan_nombre or 'starter'
    trial_status = get_free_trial_status(agent)
    limites = LIMITES.get(plan, LIMITES['starter'])

    # Uso actual del mes (via UsageLog)
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = videos_creados

    return Response({
        'nombre_inmobiliaria': getattr(agent, 'nombre_inmobiliaria', None),
        'logo_url': _safe_persisted_media_url(getattr(agent, 'logo_url', None)),
        'listados_este_mes': listados_este_mes,
        'total_generados': total_generados,
        'videos_creados': videos_creados,
        'conexiones_activas': auto_posts_used,
        'auto_posts_used': auto_posts_used,
        'listados_recientes': listados_recientes,
        'plan': plan,
        'plan_activo': agent.plan_activo,
        'trial_started_at': trial_status['trial_started_at'],
        'trial_ends_at': trial_status['trial_ends_at'],
        'trial_seconds_left': trial_status['trial_seconds_left'],
        'trial_expired': trial_status['trial_expired'],
        'contact_whatsapp': '+542324581770',
        'plan_limites': {
            'properties_per_month': limites['properties'],
            'ai_generations': limites['ai'],
            'image_generations': limites['images'],
            'video_generations': limites['videos'],
            'auto_posts_per_month': limites.get('auto_posts'),
            'auto_posting_unlimited': limites.get('auto_posts') is None,
            'branding': plan not in ('free',),
        },
        'uso_actual': {
            'properties_used': listados_este_mes,
            'ai_used': ai_used,
            'images_used': images_used,
            'videos_used': videos_used,
            'auto_posts_used': auto_posts_used,
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
    """Historial de pagos, planes y recursos extra."""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from django.db.models import Count, Sum
    from .models import Pago, WebhookLog

    pagos = Pago.objects.select_related('user').order_by('-creado_en')[:200]
    data = []
    for pago in pagos:
        data.append({
            "id": pago.id,
            "email": pago.user.email if pago.user else '',
            "nombre": pago.user.nombre if pago.user else '',
            "plan": pago.user.plan_nombre if pago.user else '',
            "plan_activo": pago.user.plan_activo if pago.user else False,
            "tipo": pago.tipo,
            "tipo_label": pago.get_tipo_display(),
            "es_extra": pago.tipo.startswith('extra_'),
            "mp_status": pago.mp_status,
            "monto": str(pago.monto),
            "moneda": pago.moneda,
            "mp_payment_id": pago.mp_payment_id,
            "external_reference": pago.external_reference or '',
            "servicios_asignados": [],
            "keys_asignadas": 0,
            "fecha_registro": pago.creado_en.strftime('%Y-%m-%d %H:%M') if pago.creado_en else '',
            "procesado_en": pago.procesado_en.strftime('%Y-%m-%d %H:%M') if pago.procesado_en else '',
        })

    resumen_tipo = dict(Pago.objects.values_list('tipo').annotate(total=Count('id')))
    total_aprobado = Pago.objects.filter(mp_status='approved').aggregate(total=Sum('monto'))['total'] or 0
    webhooks = WebhookLog.objects.filter(fuente='mercadopago').order_by('-recibido_en')[:25]

    return Response({
        "pagos": data,
        "total_pagos": Pago.objects.count(),
        "total_aprobado": str(total_aprobado),
        "resumen_tipo": resumen_tipo,
        "webhooks": [{
            "id": w.id,
            "event_id": w.event_id or '',
            "event_type": w.event_type or '',
            "status": w.status,
            "error": w.error or '',
            "recibido_en": w.recibido_en.strftime('%Y-%m-%d %H:%M') if w.recibido_en else '',
            "procesado_en": w.procesado_en.strftime('%Y-%m-%d %H:%M') if w.procesado_en else '',
        } for w in webhooks],
    })

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

        if not api_key:
            print(f"[conexiones_init] Sin key uploadpost para {user.email}. Plan={getattr(user, 'plan_nombre', 'starter')}", flush=True)
            return Response({
                "success": False,
                "error": "Tu cuenta no tiene una API de publicacion asignada. Contacta a soporte."
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
                    "error": "Alcanzaste el limite de cuentas vinculadas de tu plan actual. Para conectar mas redes sociales, mejora a un Plan Pro."
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
            "connect_title": "Conecta tus redes sociales",
            "connect_description": "Conecta tus cuentas para publicar automaticamente con LeadBook",
            "show_calendar": True
        }
        # Si viene una plataforma especÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­fica, pre-seleccionarla en el wizard de UploadPost
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
    Elimina el perfil del usuario en UploadPost (desvincula todas las redes y libera el lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite de la API).
    """
    try:
        from api.pool_manager import get_api_key
        user = request.user
        username = f"leadbook_{user.id}"
        api_key = get_api_key(user, 'uploadpost')
        
        if not api_key:
            return Response({"success": False, "error": "No se encontro API Key vinculada para este usuario"}, status=400)
            
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
            return Response({"success": True, "message": "Perfil eliminado. Podes volver a vincular tus cuentas."})
        else:
            return Response({"success": False, "error": f"Error al eliminar: {resp.text[:200]}"}, status=400)
            
    except Exception as e:
        return Response({"success": False, "error": f"Error interno: {str(e)[:100]}"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conexiones_estado(request):
    """
    Devuelve las redes sociales conectadas del usuario consultando UploadPost.
    Siempre devuelve JSON ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â nunca HTML.
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

        if not api_key:
            print(f"[conexiones_estado] Sin key uploadpost para {user.email}", flush=True)
            return Response({"success": True, "redes": [], "conectado": False})

        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }

        # ESTRATEGIA 1: Endpoint especÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­fico del usuario (mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s preciso)
        perfil = None
        resp_individual = http_requests.get(
            f"https://api.upload-post.com/api/uploadposts/users/{username}",
            headers=headers,
            timeout=10
        )
        print(f"[conexiones_estado] GET /users/{username} ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ status={resp_individual.status_code}", flush=True)

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
            print(f"[conexiones_estado] GET /users list ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ status={resp_list.status_code}", flush=True)
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
                # Si el valor estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ vacÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o (ej: ""), significa que no estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ conectado
                if not data:
                    continue
                    
                # Si es un dict, extraer la info
                if isinstance(data, dict):
                    # Ignorar si requiere reconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
                    if data.get("reauth_required") is True:
                        continue
                        
                    redes_normalizadas.append({
                        "platform": platform,
                        "username": data.get("handle") or data.get("display_name") or data.get("username") or "",
                        "status": "connected"
                    })
                elif isinstance(data, str) and data:
                    # Por si acaso devuelve un string no vacÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o
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
# DEBUG / DIAGNÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œSTICO ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â endpoints seguros (no exponen secretos)
# Uso: curl https://tuback.up.railway.app/api/v1/debug/email-check/
# ============================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_uploadpost(request, username):
    """
    Endpoint temporal para ver la estructura exacta que devuelve UploadPost
    para un usuario especÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­fico.
    """
    if not debug_endpoints_enabled():
        return Response({"error": "Not found"}, status=404)
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
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
    estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡n cargadas en Railway (o cualquier entorno).
    """
    if not debug_endpoints_enabled():
        return Response({"error": "Not found"}, status=404)
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from django.conf import settings
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''

    # Enmascarar el user (mostrar solo primeros/ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºltimos chars)
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
    Dispara un envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o SMTP REAL y SINCRÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œNICO de prueba.
    Body JSON: {"email": "destino@mail.com"}  (acepta tambiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©n "to")
    Endpoint protegido por usuario staff.
    """
    if not debug_endpoints_enabled():
        return Response({"error": "Not found"}, status=404)
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    import socket, smtplib, ssl, time
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    # Aceptar "email" o "to" (compatibilidad)
    destino = (request.data.get('email') or request.data.get('to') or '').strip().lower()
    if not destino:
        return Response({"error": "falta campo 'email' con el email destino"}, status=400)

    # Provider opcional ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â si se pasa "resend", probamos Resend sin tocar env vars
    forced_provider = (request.data.get('provider') or '').strip().lower()
    if forced_provider == 'resend':
        import os
        try:
            from .tasks import _send_via_resend
        except Exception as e_imp:
            return Response({
                "ok": False, "stage": "import-resend",
                "error_type": type(e_imp).__name__, "error": str(e_imp),
            }, status=500)
        print(f"[DEBUG-EMAIL] Forzando envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o via RESEND a {destino}", flush=True)
        subject = "LeadBook ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â prueba de email (Resend, debug)"
        text_body = "Este es un email de prueba enviado por /api/v1/debug/email-send/ (provider=resend)."
        html_body = (
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code> "
            "(<b>provider=resend</b>).</p><p>Si lo estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s leyendo, Resend funciona desde este servidor.</p>"
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
            logger.exception("Error enviando email debug via Resend")
            return Response({
                "ok": False, "stage": "resend",
                "error_type": type(e_res).__name__, "error": str(e_res),
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

    print(f"[DEBUG-EMAIL] Disparando envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o de test a {destino} ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â host={host}:{port} ssl={use_ssl} tls={use_tls}", flush=True)

    # Guardas tempranas
    if not host_user or not host_pass:
        return Response({
            "ok": False,
            "stage": "env-vars",
            "error": "GMAIL_USER o GMAIL_APP_PASSWORD no estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡n cargadas en el entorno",
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
            "hint": "Railway no puede abrir el puerto SMTP. Gmail en la nube suele fallar aquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ migrar a Resend.",
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
            "hint": "Gmail rechazÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ la autenticaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n. Si el app password es correcto y el usuario tiene 2FA, probablemente Google estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ bloqueando IPs de Railway ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)
    except Exception as e_smtp:
        logger.exception("Error en handshake SMTP debug")
        return Response({
            "ok": False,
            "stage": "smtp-handshake",
            "error_type": type(e_smtp).__name__,
            "error": str(e_smtp),
            "hint": "FallÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ el handshake SSL/TLS con Gmail. Probablemente Railway bloquea ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)

    # 3) Si llegamos acÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡, SMTP estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ OK. Enviamos el mail real.
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
            subject="LeadBook ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â prueba de email (debug)",
            body="Este es un email de prueba enviado por /api/v1/debug/email-send/.\nSi lo estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s leyendo, SMTP funciona desde este servidor.",
            from_email=from_addr,
            to=[destino],
            connection=connection,
        )
        msg.attach_alternative(
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code>.</p>"
            "<p>Si lo estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s leyendo, <b>SMTP funciona</b> desde este servidor.</p>",
            "text/html",
        )
        sent = msg.send(fail_silently=False)
        return Response({
            "ok": True,
            "stage": "sent",
            "sent_count": sent,
            "debug": smtp_debug,
            **info,
            "nota": "Si 'sent_count'=1 Gmail aceptÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ el mensaje. RevisÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ inbox y spam del destino.",
        })
    except Exception as e_send:
        logger.exception("Error enviando email debug")
        return Response({
            "ok": False,
            "stage": "send-message",
            "error_type": type(e_send).__name__,
            "error": str(e_send),
            "debug": smtp_debug,
            **info,
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def proxy_pdf_view(request, listado_id):
    """
    Sirve el PDF desde Cloudinary actuando como proxy para evitar errores 401/ACL.
    Si el PDF es local (fallback), redirige a la URL local.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id, agente=request.user)
        
        # Buscar URL en los datos del listado
        res = listado.datos_extra.get('resultados', {}) if listado.datos_extra else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data
        pdf_html = pdf_data.get('html', '') if isinstance(pdf_data, dict) else ''
        
        if not pdf_url:
            if pdf_html:
                from django.http import HttpResponse
                from api.services.render_engine import render_html_to_pdf

                pdf_bytes = render_html_to_pdf(_repair_mojibake_text(pdf_html))
                if pdf_bytes:
                    django_response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    django_response['Content-Disposition'] = f'inline; filename="ficha_leadbook_{listado_id}.pdf"'
                    return django_response
            return Response({"error": "URL de PDF no encontrada"}, status=404)

        # Si es URL local, redirigir directamente al endpoint que sirve el archivo
        if not pdf_url.startswith('http'):
            from django.shortcuts import redirect
            absolute_url = request.build_absolute_uri(pdf_url)
            if 'localhost' not in absolute_url and '127.0.0.1' not in absolute_url:
                absolute_url = absolute_url.replace('http://', 'https://')
            return redirect(absolute_url)

        if not _is_safe_remote_asset_url(pdf_url, allowed_hosts=['res.cloudinary.com']):
            return Response({"error": "URL de PDF no permitida"}, status=status.HTTP_400_BAD_REQUEST)

        # PeticiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n interna a Cloudinary
        response = requests.get(pdf_url, stream=True, timeout=30, allow_redirects=False)
        
        if response.status_code != 200:
            return Response({
                "error": f"Cloudinary respondiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³ con error {response.status_code}"
            }, status=status.HTTP_502_BAD_GATEWAY)

        django_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='application/pdf'
        )
        django_response['Content-Disposition'] = f'inline; filename="ficha_leadbook_{listado_id}.pdf"'
        return django_response

    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception:
        logger.exception("Error en proxy_pdf_view")
        return Response({"error": "Error al obtener PDF"}, status=500)

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
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else (pdf_data if isinstance(pdf_data, str) else '')
        html_content = pdf_data.get('html', '') if isinstance(pdf_data, dict) else ''
        remote_error = None

        # 1) Fuente principal: PDF ya persistido (Cloudinary)
        if isinstance(pdf_url, str) and pdf_url.startswith('http'):
            if not _is_safe_remote_asset_url(pdf_url, allowed_hosts=['res.cloudinary.com']):
                return Response({"error": "URL de PDF no permitida"}, status=status.HTTP_400_BAD_REQUEST)

            cloudinary_response = requests.get(pdf_url, stream=True, timeout=30, allow_redirects=False)
            if cloudinary_response.status_code == 200:
                response = StreamingHttpResponse(
                    cloudinary_response.iter_content(chunk_size=8192),
                    content_type=cloudinary_response.headers.get('content-type') or 'application/pdf',
                )
                response['Content-Disposition'] = f'attachment; filename="ficha_leadbook_{listado_id}.pdf"'
                return response

            remote_error = f"No se pudo descargar el PDF remoto (HTTP {cloudinary_response.status_code})"

        # 2) Fallback heredado: render desde HTML guardado
        if html_content:
            from api.services.render_engine import render_html_to_pdf
            html_content = _repair_mojibake_text(html_content)
            pdf_bytes = render_html_to_pdf(html_content)
            if not pdf_bytes:
                return Response({"error": "Error al generar PDF"}, status=500)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="ficha_leadbook_{listado_id}.pdf"'
            return response

        # 3) Sin URL ni HTML utilizable
        if remote_error:
            return Response({"error": remote_error}, status=status.HTTP_502_BAD_GATEWAY)
        if isinstance(pdf_url, str) and pdf_url and not pdf_url.startswith('http'):
            return Response({"error": "URL de PDF no válida"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"error": "No hay PDF generado todavía"}, status=404)
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        logger.error(f"Error en descargar_pdf: {e}")
        return Response({"error": "Error al descargar PDF"}, status=500)


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
@permission_classes([IsAuthenticated])
def proxy_pdf_thumbnail_view(request, listado_id):
    """
    Genera una vista previa (imagen) de la primera pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡gina del PDF vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a proxy.
    """
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id, agente=request.user)
        res = listado.datos_extra.get('resultados', {}) if listado.datos_extra else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data

        if not pdf_url or not pdf_url.startswith('http') or 'res.cloudinary.com' not in pdf_url:
            from django.shortcuts import redirect
            return redirect('https://placehold.co/400x600/111111/FFFFFF/png?text=Vista+Previa\\nNo+Disponible')

        thumb_url = pdf_url.replace('.pdf', '.jpg')
        if '/upload/' in thumb_url:
            thumb_url = thumb_url.replace('/upload/', '/upload/w_600,h_800,c_fill,pg_1/')

        if not _is_safe_remote_asset_url(thumb_url, allowed_hosts=['res.cloudinary.com']):
            return Response({"error": "URL de miniatura no permitida"}, status=400)

        response = requests.get(thumb_url, stream=True, timeout=15, allow_redirects=False)
        
        if response.status_code != 200:
            return Response({"error": "No se pudo generar miniatura"}, status=404)

        return StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='image/jpeg'
        )

    except Exception:
        logger.exception("Error en proxy_pdf_thumbnail_view")
        return Response({"error": "Error al obtener miniatura"}, status=500)

from django.shortcuts import get_object_or_404
from django.http import HttpResponse

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def generar_html(request, pk):
    from .models import Listado
    listado = get_object_or_404(Listado, pk=pk, agente=request.user)
    data = listado.datos_extra or {}
    context, temp_files, _, _, _ = construir_contexto_pdf(data, listado.agente, request)
    
    from django.template.loader import render_to_string
    try:
        html_string = render_to_string('pdf/property_brochure_html.html', context)
        html_string = _repair_mojibake_text(html_string)
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
        logger.exception("Error generando HTML para listado %s", pk)
        return HttpResponse("Error generando HTML", content_type='text/plain', status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def generar_escena(request):
    """Regenera el texto de UNA escena especÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­fica usando el mismo tono/voz del usuario."""
    data = request.data
    blocked_media_response = _reject_blocked_media_data_uri(data, 'payload')
    if blocked_media_response:
        return blocked_media_response
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
        'energetico': 'dinÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡mico y energÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©tico, usa frases cortas e impactantes',
    }
    tono_instrucciones = tono_map.get(tono, tono_map['profesional'])
    narrador = 'firme, directo, con autoridad' if voz == 'masculina' else 'cÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lido, cercano, invitador'
    tipo_video_raw = str(tipo_video or '').strip().lower()
    tipo_video_norm = {
        'tour_narrado': 'tour',
        'tour-narrado': 'tour',
        'reel_rapido': 'reel',
        'reel-rapido': 'reel',
    }.get(tipo_video_raw, tipo_video_raw if tipo_video_raw in ('tour', 'reel') else 'reel')
    reglas_palabras = {
        'tour': {'min': 24, 'max': 55},
        'reel': {'min': 6, 'max': 18},
    }[tipo_video_norm]
    contexto_extra = f"\nEnfoque adicional: {contexto_adicional}" if contexto_adicional else ''

    prompt = f"""Sos un copywriter inmobiliario experto.
GenerÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ SOLO el texto para la escena "{nombre_escena}" (escena {indice_escena + 1} de {total_escenas}) de un video inmobiliario.

PROPIEDAD: {tipo} en {operacion} | {ciudad} | {moneda} {precio}
TONO: {tono_instrucciones}
NARRADOR: {narrador}{contexto_extra}

REQUISITOS:
- Entre {reglas_palabras['min']} y {reglas_palabras['max']} palabras
- El texto es para narraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n en voz en off, debe sonar natural al hablar
- No pongas el nombre de la escena, solo el texto a narrar
- Responde SOLO el texto, sin JSON, sin comillas, sin explicaciones"""
    prompt = _repair_mojibake_text(prompt)

    try:
        result = smart_call(prompt, retries=1, agente=request.user, task='video_scene')
        if not result:
            return Response({"error": "No se pudo generar texto"}, status=503)
        return Response({"texto": _repair_mojibake_text(result).strip()})
    except Exception:
        logger.exception("Error generando texto de escena")
        return Response({"error": "Error al generar texto"}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@require_active_plan
def upload_fotos_listado(request):
    """
    Sube fotos de propiedad (portada y galerÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a) a Cloudinary a travÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s del pool del backend.
    """
    data = request.data
    mode = str(data.get('mode') or '').strip().lower()
    replace_mode = mode == 'replace'
    delete_removed = str(data.get('delete_removed') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    download_remote = str(data.get('download_remote') or data.get('downloadRemote') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    portada_input = _parse_media_ref_input(data.get('portadaUrl'))
    if hasattr(data, 'getlist'):
        fotos_input = data.getlist('fotosRecorrido') or data.get('fotosRecorrido', [])
        removed_input = data.getlist('removedMediaRefs') or data.get('removedMediaRefs', [])
    else:
        fotos_input = data.get('fotosRecorrido', [])
        removed_input = data.get('removedMediaRefs', [])
    listado_id = data.get('listado_id') or data.get('listadoId')
    portada_file = request.FILES.get('portada_file')
    fotos_files = request.FILES.getlist('fotos_files')
    allow_legacy_base64 = _allow_legacy_base64_media()
    def parse_media_list(value):
        if not isinstance(value, list):
            value = [value] if value else []
        parsed_items = []
        for item in value:
            parsed_item = _parse_media_ref_input(item)
            if isinstance(parsed_item, list):
                parsed_items.extend([sub_item for sub_item in parsed_item if sub_item])
            elif parsed_item:
                parsed_items.append(parsed_item)
        return parsed_items

    fotos_input = parse_media_list(fotos_input)
    removed_input = parse_media_list(removed_input)

    user_id = request.user.id
    response_data = {
        'portadaUrl': None,
        'fotosRecorrido': [],
        'warnings': [],
    }

    try:
        from api.services.almacenamiento import AlmacenamientoCloudinary

        def media_identity(item):
            if isinstance(item, dict):
                return item.get('public_id') or item.get('secure_url') or item.get('url')
            if isinstance(item, str) and item.startswith('data:image'):
                return item
            if isinstance(item, str) and item.startswith('http'):
                return item
            return None

        def safe_destroy_removed_refs(removed_items, accepted_items):
            if not delete_removed or not removed_items:
                return

            accepted_identities = {media_identity(item) for item in accepted_items if media_identity(item)}
            allowed_prefixes = [f'leadbook/listados/usuario_{user_id}/temp/foto_']
            if listado_id:
                allowed_prefixes.append(f'leadbook/listados/usuario_{user_id}/listado_{listado_id}/foto_')

            for removed in removed_items:
                parsed_removed = _parse_media_ref_input(removed)
                if not isinstance(parsed_removed, dict):
                    continue
                public_id = str(parsed_removed.get('public_id') or '').strip()
                if not public_id or public_id in accepted_identities:
                    continue
                if not any(public_id.startswith(prefix) for prefix in allowed_prefixes):
                    logger.warning("[UPLOAD] Ignorando eliminacion no segura de asset: %s", public_id)
                    continue

                resource_type = parsed_removed.get('resource_type') or 'image'
                cloud_name = parsed_removed.get('cloud_name') or parsed_removed.get('cloudinary_account')
                api_key_val = parsed_removed.get('api_key')
                api_secret_val = parsed_removed.get('api_secret')
                try:
                    if cloud_name and api_key_val and api_secret_val:
                        cld_cfg = cloudinary.Config(
                            cloud_name=cloud_name,
                            api_key=api_key_val,
                            api_secret=api_secret_val,
                        )
                        cloudinary.uploader.destroy(public_id, resource_type=resource_type, config=cld_cfg)
                    else:
                        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
                    logger.info("[UPLOAD] Asset removido eliminado de Cloudinary: %s", public_id)
                except Exception as cld_err:
                    logger.warning("[UPLOAD] No se pudo eliminar asset removido %s: %s", public_id, cld_err)

        def complete_media_ref(value, role, order):
            media = value.copy() if isinstance(value, dict) else {}
            resolved = AlmacenamientoCloudinary.obtener_url_foto(media) or _resolve_cloudinary_asset_url(media)
            if resolved:
                media.setdefault('url', resolved)
                media.setdefault('secure_url', resolved)
            media.setdefault('resource_type', 'image')
            media.setdefault('width', 0)
            media.setdefault('height', 0)
            media.setdefault('bytes', 0)
            media.setdefault('format', '')
            media['role'] = role
            media['order'] = order
            return media

        def upload_file(uploaded_file, role, order, indice):
            logger.info("[UPLOAD] Subiendo archivo %s order=%s listado_id=%s", role, order, listado_id)
            uploaded = AlmacenamientoCloudinary.guardar_foto_propiedad_file(
                uploaded_file,
                user_id=user_id,
                listado_id=listado_id,
                tipo_foto=role,
                indice=indice,
            )
            if not uploaded:
                return None, "No se pudo subir una foto a Cloudinary."
            return complete_media_ref(uploaded, role, order), None

        def remote_url_from_item(item):
            if isinstance(item, str) and item.startswith(('http://', 'https://')):
                return item
            if isinstance(item, dict):
                return item.get('url') or item.get('secure_url') or item.get('remote_url')
            return None

        def guess_remote_filename(url, content_type, fallback):
            from urllib.parse import urlparse
            raw_path = urlparse(str(url or '')).path.rsplit('/', 1)[-1]
            raw_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', raw_path or fallback or 'foto')
            if '.' in raw_name[-8:]:
                return raw_name[:90]
            ct = str(content_type or '').split(';', 1)[0].lower()
            ext_by_type = {
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/webp': '.webp',
                'image/avif': '.avif',
                'image/heic': '.heic',
                'image/heif': '.heif',
                'image/gif': '.gif',
                'image/bmp': '.bmp',
                'image/tiff': '.tiff',
            }
            return f"{raw_name[:80]}{ext_by_type.get(ct, '.jpg')}"

        def upload_remote_url(item, role, order):
            remote_url = remote_url_from_item(item)
            if not remote_url:
                return None, "Referencia remota incompleta."
            raw_bytes, content_type = _download_remote_asset(
                remote_url,
                timeout=18,
                max_bytes=15 * 1024 * 1024,
                allow_any_host=True,
                allowed_schemes=('https', 'http'),
                content_type_prefixes=('image/',),
                max_redirects=3,
            )
            if not raw_bytes:
                response_data['warnings'].append(f"No se pudo descargar una imagen remota: {remote_url}")
                return None, None
            from django.core.files.base import ContentFile
            filename = guess_remote_filename(remote_url, content_type, f'{role}_{order}')
            file_obj = ContentFile(raw_bytes, name=filename)
            return upload_file(file_obj, role, order, max(order - 1, 0))

        def normalize_media(item, role, order):
            if item and isinstance(item, str) and item.startswith('data:image'):
                if not allow_legacy_base64:
                    return None, "Formato base64 no permitido. Subi archivo o URL remota."
                logger.info("[UPLOAD] Subiendo foto %s order=%s listado_id=%s", role, order, listado_id)
                uploaded = AlmacenamientoCloudinary.guardar_foto_propiedad(
                    item,
                    user_id,
                    listado_id,
                    tipo_foto=role,
                    indice=max(order - 1, 0),
                )
                if not uploaded:
                    return None, "No se pudo subir una foto a Cloudinary."
                return complete_media_ref(uploaded, role, order), None
            if isinstance(item, dict):
                remote_url = remote_url_from_item(item)
                if download_remote and remote_url and not item.get('public_id'):
                    return upload_remote_url(item, role, order)
                media = complete_media_ref(item, role, order)
                if not (media.get('url') or media.get('secure_url') or media.get('public_id')):
                    return None, "Referencia de imagen incompleta."
                return media, None
            if item and isinstance(item, str) and item.startswith('http'):
                if download_remote:
                    return upload_remote_url(item, role, order)
                if not _is_safe_remote_asset_url(item):
                    return None, "URL de imagen no permitida."
                return {
                    'url': item,
                    'secure_url': item,
                    'resource_type': 'image',
                    'role': role,
                    'order': order,
                    'width': 0,
                    'height': 0,
                    'bytes': 0,
                    'format': '',
                }, None
            if item:
                return None, "Formato de imagen no soportado."
            return None, None

        raw_gallery_items = []
        portada_identity = media_identity(portada_input)
        for foto in fotos_input:
            if not foto:
                continue
            if portada_identity and media_identity(foto) == portada_identity:
                continue
            raw_gallery_items.append(foto)

        normalized = []
        if portada_file:
            media, error_msg = upload_file(portada_file, 'portada', 0, 0)
            if error_msg:
                return Response({"error": "error_subida", "mensaje": error_msg}, status=502)
            if media:
                normalized.append(media)
        elif portada_input:
            media, error_msg = normalize_media(portada_input, 'portada', 0)
            if error_msg:
                status_code = status.HTTP_400_BAD_REQUEST if 'base64' in error_msg.lower() else 502
                return Response(
                    {
                        "error": "invalid_media_payload",
                        "mensaje": error_msg,
                        "allow_legacy_base64_media": allow_legacy_base64,
                    },
                    status=status_code,
                )
            if media:
                normalized.append(media)

        for item in raw_gallery_items:
            role = 'portada' if not normalized else 'galeria'
            order = 0 if role == 'portada' else len(normalized)
            media, error_msg = normalize_media(item, role, order)
            if error_msg:
                status_code = status.HTTP_400_BAD_REQUEST if 'base64' in error_msg.lower() else 502
                return Response(
                    {
                        "error": "invalid_media_payload",
                        "mensaje": error_msg,
                        "allow_legacy_base64_media": allow_legacy_base64,
                    },
                    status=status_code,
                )
            if media:
                normalized.append(media)

        for idx, file_item in enumerate(fotos_files):
            role = 'portada' if not normalized else 'galeria'
            order = 0 if role == 'portada' else len(normalized)
            media, error_msg = upload_file(file_item, role, order, idx)
            if error_msg:
                return Response({"error": "error_subida", "mensaje": error_msg}, status=502)
            if media:
                normalized.append(media)

        if normalized:
            response_data['portadaUrl'] = normalized[0]
            response_data['fotosRecorrido'] = normalized[1:]

        safe_destroy_removed_refs(removed_input, normalized)

        if listado_id and (normalized or replace_mode):
            listado = Listado.objects.filter(id=listado_id, agente=request.user).first()
            if listado:
                datos_extra = listado.datos_extra if isinstance(listado.datos_extra, dict) else {}
                datos_extra = {
                    **datos_extra,
                    'portadaUrl': response_data['portadaUrl'],
                    'fotosRecorrido': response_data['fotosRecorrido'],
                }
                listado.datos_extra = _sanitize_listing_payload_for_storage(datos_extra)
                listado.save(update_fields=['datos_extra', 'updated_at'])
        return Response(response_data)
    except Exception:
        logger.exception("Error al subir fotos de listado")
        return Response({"error": "Error al subir fotos"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_notificaciones(request):
    from .models import Notificacion
    from .utils import repair_mojibake_text
    notifs = Notificacion.objects.filter(usuario=request.user)[:20]
    data = [{
        'id': n.id,
        'tipo': n.tipo,
        'titulo': repair_mojibake_text(n.titulo),
        'mensaje': repair_mojibake_text(n.mensaje),
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
    from .plan_utils import get_daily_listing_quota
    try:
        quota = UserAPIQuota.objects.get(user=request.user, servicio__nombre='gemini')
        quota.maybe_reset_daily()
        quota.recalcular_limite(plan=request.user.plan_nombre)
        if quota.is_blocked:
            quota.is_blocked = False
            quota.blocked_reason = None
            quota.save(update_fields=['is_blocked', 'blocked_reason', 'updated_at'])
        agotada = False
        usado = quota.requests_today
        limite = quota.user_daily_limit
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
        'porcentaje': min(100, int((ai_used / limite) * 100)) if limite > 0 else 0,
        'daily_listing_quota': get_daily_listing_quota(request.user),
    })

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def debug_quota(request):
    from .models import APIKey, UserAPIQuota
    if not debug_endpoints_enabled():
        return Response({"error": "Not found"}, status=404)
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    if request.method == 'POST':
        from .models import UserAPIQuota
        # Desbloquear todos los usuarios cuyo uso actual es menor al lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mite
        desbloqueados = 0
        for q in UserAPIQuota.objects.filter(is_blocked=True):
            if q.requests_today < q.user_daily_limit:
                q.is_blocked = False
                q.save()
                desbloqueados += 1
        # Corregir lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mites stale segÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºn plan + extras activos.
        for q in UserAPIQuota.objects.select_related('user', 'servicio'):
            q.recalcular_limite(plan=q.user.plan_nombre)
        
        return Response({'desbloqueados': desbloqueados})

    quotas = list(UserAPIQuota.objects.select_related('servicio').values(
        'user_id', 'servicio__nombre', 'user_daily_limit', 'user_monthly_limit',
        'requests_today', 'is_blocked'
    ))
    keys_info = [{
        'service': key.servicio.nombre if key.servicio_id else '',
        'key_id': key.id,
        'daily_limit': key.google_daily_limit,
        'monthly_limit': key.google_monthly_limit,
        'status': 'in_use' if key.status == 'assigned' else key.status,
        'locked_user_id': key.slot_locked_by_id,
        'locked_listado_id': key.slot_locked_listado_id,
    } for key in APIKey.objects.select_related('servicio').order_by('servicio__nombre', '-total_requests')]
    return Response({'quotas': quotas, 'keys': keys_info})
