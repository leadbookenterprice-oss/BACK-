import html
import hmac
import hashlib

from decouple import config
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import CRMClient, FollowUpTask, Lead, PipelineStage
from .plan_utils import get_plan_block_payload, get_pro_feature_block_payload, has_pro_feature_access
from .serializers import FollowUpTaskSerializer, LeadSerializer, PipelineStageSerializer
from .services.crm_service import (
    CRMExternalProviderError,
    CRMSoftRateLimited,
    create_lead_event,
    create_or_get_lead,
    crm_metrics,
    ensure_default_pipeline_stages,
    get_stage,
    ingest_meta_webhook,
    mark_lead_contacted,
    move_lead_stage,
)
from .tasks import _send_via_resend


CRM_EMAIL_PLANS = {'pro', 'scale', 'business'}


def _verify_meta_signature(request):
    app_secret = config('META_APP_SECRET', default=getattr(settings, 'META_APP_SECRET', '')).strip()
    if not app_secret:
        return True
    supplied = request.headers.get('X-Hub-Signature-256', '')
    if not supplied.startswith('sha256='):
        return False
    digest = hmac.new(app_secret.encode('utf-8'), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, f'sha256={digest}')


def _crm_error(code, message, http_status=status.HTTP_400_BAD_REQUEST, **extra):
    return Response({'error': code, 'message': message, **extra}, status=http_status)


def _crm_email_plan_allowed(user):
    return has_pro_feature_access(user)


def _require_crm_access(user):
    block_payload = get_plan_block_payload(user)
    if block_payload:
        return Response(block_payload, status=status.HTTP_402_PAYMENT_REQUIRED)
    pro_payload = get_pro_feature_block_payload(user, feature='crm')
    if pro_payload:
        return Response(pro_payload, status=status.HTTP_403_FORBIDDEN)
    return None


def _render_crm_email_html(sender, client, message):
    agency = getattr(sender, 'nombre_inmobiliaria', '') or 'LeadBook'
    sender_name = getattr(sender, 'nombre', '') or agency
    safe_message = html.escape(message).replace('\n', '<br>')
    safe_client_name = html.escape(client.nombre or '')
    safe_sender_name = html.escape(sender_name)
    safe_agency = html.escape(agency)

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:28px;background:#f7f8fb;color:#111827;">
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:28px;">
        <p style="margin:0 0 18px;color:#6b7280;font-size:13px;">Hola {safe_client_name},</p>
        <div style="font-size:15px;line-height:1.7;color:#111827;">{safe_message}</div>
        <div style="margin-top:28px;padding-top:18px;border-top:1px solid #e5e7eb;">
          <p style="margin:0;color:#111827;font-weight:700;">{safe_sender_name}</p>
          <p style="margin:4px 0 0;color:#6b7280;font-size:13px;">{safe_agency}</p>
        </div>
      </div>
      <p style="text-align:center;color:#9ca3af;font-size:11px;margin:18px 0 0;">Enviado desde LeadBook CRM</p>
    </div>
    """


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crm_client_send_email(request, client_id):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response

    if not _crm_email_plan_allowed(request.user):
        return Response({
            'error': 'pro_required',
            'message': 'Los envíos de email desde CRM están disponibles para usuarios Pro.',
            'required_plan': 'pro',
        }, status=status.HTTP_403_FORBIDDEN)

    client = get_object_or_404(CRMClient, id=client_id, owner=request.user)
    if not client.email:
        return Response({'error': 'client_email_required', 'message': 'Este cliente no tiene email cargado.'}, status=status.HTTP_400_BAD_REQUEST)

    subject = str(request.data.get('subject') or '').strip()
    message = str(request.data.get('message') or '').strip()
    if not subject or not message:
        return Response({'error': 'subject_message_required', 'message': 'Asunto y mensaje son requeridos.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(subject) > 160:
        return Response({'error': 'subject_too_long', 'message': 'El asunto no puede superar 160 caracteres.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(message) > 5000:
        return Response({'error': 'message_too_long', 'message': 'El mensaje no puede superar 5000 caracteres.'}, status=status.HTTP_400_BAD_REQUEST)

    html_body = _render_crm_email_html(request.user, client, message)
    text_body = f"Hola {client.nombre},\n\n{message}\n\n{request.user.nombre or 'LeadBook'}"
    ok, detail = _send_via_resend(client.email, subject, text_body, html_body)
    if not ok:
        return Response({
            'error': 'email_send_failed',
            'message': 'No se pudo enviar el email. Revisá la configuración de Resend.',
            'detail': detail,
        }, status=status.HTTP_502_BAD_GATEWAY)

    if client.estado == 'nuevo':
        client.estado = 'contactado'
        client.save(update_fields=['estado', 'updated_at'])

    return Response({
        'sent': True,
        'client_id': client.id,
        'email': client.email,
        'detail': detail,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def crm_pipeline_stages(request):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    stages = ensure_default_pipeline_stages(request.user)
    return Response({'items': PipelineStageSerializer(stages, many=True).data}, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def crm_leads_collection(request):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    if request.method == 'GET':
        ensure_default_pipeline_stages(request.user)
        leads = Lead.objects.filter(owner=request.user).select_related('pipeline_stage', 'assigned_to', 'listing').prefetch_related('follow_up_tasks')
        stage = request.query_params.get('stage')
        origin = request.query_params.get('origin')
        assigned_to = request.query_params.get('assigned_to')
        date_from = request.query_params.get('from')
        date_to = request.query_params.get('to')

        if stage:
            leads = leads.filter(pipeline_stage__slug=stage)
        if origin:
            leads = leads.filter(origin=origin)
        if assigned_to:
            leads = leads.filter(assigned_to_id=assigned_to)
        if date_from:
            leads = leads.filter(created_at__date__gte=date_from)
        if date_to:
            leads = leads.filter(created_at__date__lte=date_to)

        serializer = LeadSerializer(leads.order_by('-updated_at'), many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    payload = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data or {})
    payload.setdefault('owner_id', request.user.id)
    lead, created, dedupe_reason = create_or_get_lead(
        request.user,
        payload,
        origin=payload.get('origin') or payload.get('origen') or 'manual',
        created_by=request.user,
    )
    return Response({
        'item': LeadSerializer(lead).data,
        'created': created,
        'dedupe_reason': dedupe_reason,
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def crm_lead_detail(request, lead_id):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    lead = get_object_or_404(
        Lead.objects.select_related('pipeline_stage', 'assigned_to', 'listing').prefetch_related('events', 'follow_up_tasks'),
        id=lead_id,
        owner=request.user,
    )
    if request.method == 'GET':
        return Response(LeadSerializer(lead).data, status=status.HTTP_200_OK)

    data = request.data or {}
    old_stage_id = lead.pipeline_stage_id
    allowed_fields = ['full_name', 'email', 'phone', 'message', 'origin', 'status']
    for field in allowed_fields:
        if field in data:
            setattr(lead, field, data.get(field))
    if data.get('pipeline_stage_id'):
        stage = get_stage(request.user, stage_id=data.get('pipeline_stage_id'))
        if not stage:
            return _crm_error('stage_not_found', 'La etapa indicada no existe.', status.HTTP_404_NOT_FOUND)
        lead.pipeline_stage = stage
    lead.save()
    if old_stage_id != lead.pipeline_stage_id:
        create_lead_event(lead, 'stage_changed', 'Lead movido de etapa', created_by=request.user, metadata={'to': lead.pipeline_stage.slug})
    return Response(LeadSerializer(lead).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crm_lead_move_stage(request, lead_id):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    lead = get_object_or_404(Lead, id=lead_id, owner=request.user)
    stage = get_stage(request.user, stage_id=request.data.get('stage_id'), slug=request.data.get('stage'))
    if not stage:
        return _crm_error('stage_not_found', 'La etapa indicada no existe.', status.HTTP_404_NOT_FOUND)
    move_lead_stage(lead, stage, user=request.user)
    lead.refresh_from_db()
    return Response(LeadSerializer(lead).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crm_lead_mark_contacted(request, lead_id):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    lead = get_object_or_404(Lead, id=lead_id, owner=request.user)
    mark_lead_contacted(lead, user=request.user, message=str(request.data.get('message') or 'Contacto registrado'))
    contact_stage = get_stage(request.user, slug='contactado')
    if contact_stage and lead.pipeline_stage.slug == 'nuevo':
        move_lead_stage(lead, contact_stage, user=request.user)
    lead.refresh_from_db()
    return Response(LeadSerializer(lead).data, status=status.HTTP_200_OK)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def crm_followup_task_detail(request, task_id):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    task = get_object_or_404(FollowUpTask.objects.select_related('lead'), id=task_id, owner=request.user)
    if request.method == 'GET':
        return Response(FollowUpTaskSerializer(task).data, status=status.HTTP_200_OK)

    if request.data.get('status') == 'done' and task.status != 'done':
        task.status = 'done'
        task.completed_at = timezone.now()
    elif request.data.get('status') in {'pending', 'cancelled'}:
        task.status = request.data.get('status')
        if task.status != 'done':
            task.completed_at = None
    task.save(update_fields=['status', 'completed_at', 'updated_at'])
    return Response(FollowUpTaskSerializer(task).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def crm_metrics_view(request):
    access_response = _require_crm_access(request.user)
    if access_response:
        return access_response
    ensure_default_pipeline_stages(request.user)
    return Response(crm_metrics(request.user), status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def meta_leads_webhook(request):
    if request.method == 'GET':
        verify_token = config('CRM_META_VERIFY_TOKEN', default=config('META_LEADS_VERIFY_TOKEN', default='')).strip()
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge', '')
        if mode == 'subscribe' and verify_token and token == verify_token:
            return HttpResponse(challenge, status=200, content_type='text/plain')
        return _crm_error('invalid_verify_token', 'Token de verificacion invalido.', status.HTTP_403_FORBIDDEN)

    if not _verify_meta_signature(request):
        return _crm_error('invalid_signature', 'Firma Meta invalida.', status.HTTP_403_FORBIDDEN)

    try:
        results = ingest_meta_webhook(request.data or {}, request=request)
    except CRMSoftRateLimited:
        return _crm_error(
            'soft_rate_limited',
            'Meta rate limit transitorio. Reintentar este webhook.',
            status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
        )
    except CRMExternalProviderError as exc:
        return _crm_error('provider_error', 'No se pudo consultar Meta.', status.HTTP_502_BAD_GATEWAY, detail=str(exc)[:300])

    return Response({'ok': True, 'results': results}, status=status.HTTP_200_OK)
