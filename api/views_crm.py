import html

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CRMClient
from .plan_utils import get_plan_block_payload
from .tasks import _send_via_resend


CRM_EMAIL_PLANS = {'pro', 'scale', 'business'}


def _crm_email_plan_allowed(user):
    plan = str(getattr(user, 'plan_nombre', '') or '').strip().lower()
    return plan in CRM_EMAIL_PLANS


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
    block_payload = get_plan_block_payload(request.user)
    if block_payload:
        return Response(block_payload, status=status.HTTP_402_PAYMENT_REQUIRED)

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
