from celery import shared_task
from django.utils import timezone
from django.db.models import F, Q
from datetime import timedelta
from .models import APIKey, Agent, Notificacion, UserAPIAssignment, UserAPIQuota
from .services.pool_service import APIPoolService
import requests
import logging

logger = logging.getLogger(__name__)


FREE_POOL_SERVICES = ['gemini', 'elevenlabs']


def _notify_free_pool_reset(user, now):
    cutoff = now - timedelta(hours=11, minutes=30)
    if Notificacion.objects.filter(
        usuario=user,
        tipo='reset_creditos',
        creada_en__gte=cutoff,
    ).exists():
        return

    Notificacion.objects.create(
        usuario=user,
        tipo='reset_creditos',
        titulo='Ya podés generar contenido de nuevo',
        mensaje='Las APIs compartidas fueron reintentadas/resetadas. Si el proveedor ya renovó la cuota, podés generar contenido otra vez.',
    )


# ============================================================
# EMAIL PROVIDER — Resend HTTP API (fallback a Gmail SMTP)
# ============================================================
def _send_via_resend(email, subject, text_body, html_body):
    """
    Envía email usando la API HTTP de Resend.
    Requiere env vars: RESEND_API_KEY y RESEND_FROM (o usa DEFAULT_FROM_EMAIL).
    Retorna (ok: bool, detalle: str).
    """
    import os, sys
    from django.conf import settings
    try:
        import resend
    except ImportError as e:
        print(f"[EMAIL] ERROR al enviar (resend): paquete 'resend' no instalado: {e}", flush=True)
        return False, f"ImportError:{e}"

    api_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")
    if not api_key:
        print("[EMAIL] ERROR al enviar (resend): falta RESEND_API_KEY", flush=True)
        return False, "missing:RESEND_API_KEY"

    resend.api_key = api_key
    from_addr = (
        os.environ.get("RESEND_FROM")
        or getattr(settings, "RESEND_FROM", "")
        or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        or "onboarding@resend.dev"
    )

    print(f"[EMAIL] Intentando enviar via Resend a {email} (from={from_addr})", flush=True)
    try:
        params = {
            "from": from_addr,
            "to": [email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
        result = resend.Emails.send(params)
        rid = (result or {}).get("id") if isinstance(result, dict) else str(result)
        print(f"[EMAIL] Enviado correctamente a {email} via Resend (id={rid})", flush=True)
        sys.stdout.flush()
        return True, f"sent:resend:{rid}"
    except Exception as e:
        print(f"[EMAIL] ERROR al enviar (resend): {type(e).__name__}: {str(e)}", flush=True)
        sys.stdout.flush()
        return False, f"error:resend:{type(e).__name__}:{str(e)[:200]}"

@shared_task
def run_asset_generation(listado_id):
    """Stub — se mantiene por compatibilidad con imports. No hace nada."""
    return f"run_asset_generation: listado {listado_id} — usar generar_video_task"


@shared_task(name='api.tasks.generar_video_task')
def generar_video_task(listado_id):
    """Genera video del listado en worker Celery."""
    from django.conf import settings
    from decouple import config
    from .models import Listado
    from .plan_utils import registrar_uso

    logger.info("[VIDEO_TASK] Inicio listado_id=%s", listado_id)
    try:
        default_provider = 'hyperframes' if settings.DEBUG else 'veo3'
        provider = config('VIDEO_PROVIDER', default=default_provider).strip().lower()
        if provider in {'veo3', 'veo', 'gemini_veo', 'gemini'}:
            from .services.gemini_video_service import generar_video_listado_veo3
            success = generar_video_listado_veo3(listado_id)
        else:
            from .services.video_service import generar_video_listado
            success = generar_video_listado(listado_id)

        logger.info("[VIDEO_TASK] Resultado listado_id=%s provider=%s success=%s", listado_id, provider, success)
        if success:
            listado = Listado.objects.get(id=listado_id)
            registrar_uso(listado.agente, 'video')
            return {"status": "completado", "id": listado_id}
        return {"status": "fallido", "id": listado_id}
    except Exception as e:
        logger.exception("[VIDEO_TASK] Error listado_id=%s", listado_id)
        return {"error": str(e), "id": listado_id}


@shared_task
def send_otp_email_async(email, code):
    """
    Envía el OTP vía Gmail SMTP. Si no hay credenciales configuradas,
    cae a console backend (imprime el código en la consola del server)
    para que el desarrollo/testing no se bloquee.
    """
    import traceback
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    subject = "Tu código de verificación - LeadBook"
    text_body = (
        f"Tu código de verificación es: {code}\n\n"
        "Expira en 10 minutos.\n\n"
        "Si no solicitaste este código, ignorá este email."
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;
                padding:24px;border:1px solid #eee;border-radius:12px;">
      <h2 style="color:#111;margin:0 0 16px;">Verificá tu email</h2>
      <p style="color:#444;font-size:14px;">
        Usá este código para completar tu registro en <b>LeadBook</b>:
      </p>
      <div style="font-size:32px;font-weight:700;letter-spacing:6px;
                  text-align:center;background:#f5f5f5;padding:16px;
                  border-radius:8px;margin:16px 0;">{code}</div>
      <p style="color:#888;font-size:12px;">
        Expira en 10 minutos. Si no lo solicitaste, ignorá este email.
      </p>
    </div>
    """

    import sys, os
    host_user = getattr(settings, "EMAIL_HOST_USER", "") or ""
    host_pass = getattr(settings, "EMAIL_HOST_PASSWORD", "") or ""
    backend   = getattr(settings, "EMAIL_BACKEND", "")
    resend_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")
    provider = (
        os.environ.get("EMAIL_PROVIDER")
        or getattr(settings, "EMAIL_PROVIDER", "")
        or ("resend" if resend_key else "gmail")
    ).strip().lower()

    print(f"[EMAIL] Intentando enviar a {email} (provider={provider})", flush=True)
    print(
        f"[EMAIL] DIAG task backend={backend} "
        f"host={getattr(settings,'EMAIL_HOST','?')}:{getattr(settings,'EMAIL_PORT','?')} "
        f"ssl={getattr(settings,'EMAIL_USE_SSL',None)} "
        f"tls={getattr(settings,'EMAIL_USE_TLS',None)} "
        f"user_set={bool(host_user)} pass_set={bool(host_pass)} pass_len={len(host_pass)} "
        f"provider={provider}",
        flush=True,
    )

    # --- Path Resend (HTTP API) ---
    if provider == "resend":
        ok, detalle = _send_via_resend(email, subject, text_body, html_body)
        if ok:
            return detalle
        # si Resend falla, dejamos caer el código en logs y no seguimos a Gmail
        print(f"[EMAIL-FALLBACK] OTP para {email}: {code} (solo visible en logs)", flush=True)
        return detalle

    # --- Path Gmail SMTP (default) ---
    # Si faltan credenciales: fallback a consola. IMPORTANTE: en Railway esto
    # significa que el email NO LLEGA al usuario, solo se imprime en logs.
    if not host_user or not host_pass:
        print("=" * 60, flush=True)
        print(f"[EMAIL] ERROR al enviar: faltan GMAIL_USER o GMAIL_APP_PASSWORD en env vars", flush=True)
        print(f"[EMAIL-FALLBACK] OTP para {email}: {code} (solo visible en logs)", flush=True)
        print("=" * 60, flush=True)
        sys.stdout.flush()
        return f"console:{email}"

    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=host_user,
            password=host_pass,
            use_ssl=getattr(settings, "EMAIL_USE_SSL", True),
            use_tls=getattr(settings, "EMAIL_USE_TLS", False),
            timeout=20,
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", host_user) or host_user
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[email],
            connection=connection,
        )
        msg.attach_alternative(html_body, "text/html")
        result = msg.send(fail_silently=False)
        print(f"[EMAIL] Enviado correctamente a {email} (send_result={result})", flush=True)
        sys.stdout.flush()
        return f"sent:{email}"
    except Exception as e:
        print(f"[EMAIL] ERROR al enviar: {type(e).__name__}: {str(e)}", flush=True)
        traceback.print_exc()
        # Mostrar el código para no bloquear diagnóstico
        print(f"[EMAIL-FALLBACK] OTP para {email}: {code}", flush=True)
        sys.stdout.flush()
        return f"error:{type(e).__name__}:{str(e)[:120]}"

@shared_task
def health_check_all_keys():
    """Ejecuta un health check para cada API Key en el sistema"""
    keys = APIKey.objects.exclude(status__in=['disabled', 'dead'])
    for key in keys:
        try:
            res = None
            servicio_nombre = key.servicio.nombre if hasattr(key.servicio, 'nombre') else str(key.servicio)
            if servicio_nombre == 'gemini':
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={key.api_key}"
                res = requests.post(url, json={"contents":[{"parts":[{"text":"hello"}]}]}, timeout=5)
                is_healthy = res.status_code == 200
            elif servicio_nombre == 'elevenlabs':
                url = "https://api.elevenlabs.io/v1/voices"
                res = requests.get(url, headers={"xi-api-key": key.api_key}, timeout=5)
                is_healthy = res.status_code == 200
            elif servicio_nombre == 'uploadpost':
                url = "https://api.upload-post.com/api/uploadposts/users"
                res = requests.get(url, headers={"Authorization": f"Apikey {key.api_key}"}, timeout=5)
                is_healthy = res.status_code == 200
            else:
                is_healthy = True  # Desconocido, asume sano

            if res is not None and res.status_code == 429:
                key.status = 'exhausted'
                key.last_health_status = True
                key.error_count = 0
                key.save(update_fields=['status', 'last_health_status', 'last_health_check', 'error_count', 'updated_at'])
                continue
                
            key.last_health_status = is_healthy
            key.last_health_check = timezone.now()
            
            if not is_healthy:
                key.error_count += 1
                if key.error_count >= 5:
                    APIPoolService.mark_key_dead(key)
            else:
                key.error_count = 0 # reset error count si está sana
            key.save()
            
        except Exception as e:
            key.last_health_status = False
            key.last_health_check = timezone.now()
            key.error_count += 1
            if key.error_count >= 5:
                APIPoolService.mark_key_dead(key)
            key.save()

@shared_task
def reset_free_pool_counters():
    """Reinicia contadores compartidos cada 12 horas y notifica a usuarios afectados."""
    now = timezone.now()

    affected_user_ids = set(
        UserAPIQuota.objects.filter(servicio__nombre__in=FREE_POOL_SERVICES)
        .filter(Q(is_blocked=True) | Q(requests_today__gte=F('user_daily_limit')))
        .values_list('user_id', flat=True)
    )
    affected_user_ids.update(
        UserAPIAssignment.objects.filter(
            activo=True,
            servicio__nombre__in=FREE_POOL_SERVICES,
            apikey__status='exhausted',
        ).values_list('user_id', flat=True)
    )

    UserAPIQuota.objects.filter(servicio__nombre__in=FREE_POOL_SERVICES).update(
        requests_today=0,
        is_blocked=False,
        blocked_reason=None,
        last_reset_daily=now,
    )
    APIKey.objects.filter(servicio__nombre__in=FREE_POOL_SERVICES).update(requests_today=0)

    exhausted_keys = APIKey.objects.filter(servicio__nombre__in=FREE_POOL_SERVICES, status='exhausted')
    for key in exhausted_keys:
        has_assignment = UserAPIAssignment.objects.filter(apikey=key, activo=True).exists()
        key.status = 'assigned' if has_assignment else 'available'
        key.save(update_fields=['status', 'updated_at'])

    for user in Agent.objects.filter(id__in=affected_user_ids):
        _notify_free_pool_reset(user, now)

    return {'notified_users': len(affected_user_ids)}


@shared_task
def reset_daily_counters():
    """Se ejecuta cada noche a las 00:00 UTC para reiniciar cuotas"""
    reset_free_pool_counters()
    now = timezone.now()
    APIKey.objects.exclude(servicio__nombre__in=FREE_POOL_SERVICES).update(requests_today=0)

    non_free_quotas = UserAPIQuota.objects.exclude(servicio__nombre__in=FREE_POOL_SERVICES)
    monthly_blocked_ids = list(
        non_free_quotas.filter(blocked_reason__icontains='mensual').values_list('id', flat=True)
    )
    non_free_quotas.filter(id__in=monthly_blocked_ids).update(
        requests_today=0,
        last_reset_daily=now,
    )
    non_free_quotas.exclude(id__in=monthly_blocked_ids).update(
        requests_today=0,
        is_blocked=False,
        blocked_reason=None,
        last_reset_daily=now,
    )

@shared_task
def reset_monthly_counters():
    """Se ejecuta cada 1 de mes para reiniciar cuotas"""
    now = timezone.now()
    APIKey.objects.update(requests_this_month=0)
    UserAPIQuota.objects.update(requests_this_month=0, last_reset_monthly=now)
    UserAPIQuota.objects.filter(blocked_reason__icontains='mensual').update(
        is_blocked=False,
        blocked_reason=None,
        last_reset_monthly=now,
    )
    exhausted_uploadpost = APIKey.objects.filter(servicio__nombre='uploadpost', status='exhausted')
    for key in exhausted_uploadpost:
        has_assignment = UserAPIAssignment.objects.filter(apikey=key, activo=True).exists()
        key.status = 'assigned' if has_assignment else 'available'
        key.save(update_fields=['status', 'updated_at'])
