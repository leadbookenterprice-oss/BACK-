"""
Prueba:
1. Gmail SMTP real (manda un email de prueba a fieldultramedia@gmail.com)
2. Gemini con la key nueva
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "subzero_core.settings")

import django
django.setup()

from django.conf import settings


def banner(msg):
    print("\n" + "=" * 60)
    print(f"  {msg}")
    print("=" * 60)


banner("Config cargada")
print("EMAIL_BACKEND:", settings.EMAIL_BACKEND)
print("EMAIL_HOST_USER:", settings.EMAIL_HOST_USER)
print("GEMINI_API_KEY:", (settings.GEMINI_API_KEY[:15] + "..."))

# --- 1) Gmail SMTP ---
banner("1) Gmail SMTP — envío de email real")
try:
    from django.core.mail import get_connection, EmailMultiAlternatives

    connection = get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_ssl=settings.EMAIL_USE_SSL,
        use_tls=settings.EMAIL_USE_TLS,
        timeout=30,
    )
    msg = EmailMultiAlternatives(
        subject="[LeadBook TEST] OTP de prueba 123456",
        body="Si ves esto, Gmail SMTP está funcionando correctamente.\n\nCódigo de prueba: 123456",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.EMAIL_HOST_USER],  # nos lo mandamos a nosotros mismos
        connection=connection,
    )
    msg.attach_alternative(
        "<h2>LeadBook SMTP OK</h2><p>Código: <b>123456</b></p>",
        "text/html",
    )
    sent = msg.send(fail_silently=False)
    print(f"Enviado OK. Resultado: {sent} (1 = éxito)")
except Exception as e:
    import traceback
    print(f"ERROR SMTP: {type(e).__name__}: {e}")
    traceback.print_exc()

# --- 2) Gemini ---
banner("2) Gemini — con nueva key")
try:
    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model='gemini-2.0-flash-lite',
        contents='Respondé en 1 palabra si me estás leyendo: OK o NO.',
    )
    print("Respuesta:", (resp.text or "")[:200])
except Exception as e:
    print(f"ERROR Gemini: {type(e).__name__}: {str(e)[:300]}")

# --- 3) Test completo del flujo OTP con el task real ---
banner("3) Task send_otp_email_async — flujo real del backend")
try:
    from api.tasks import send_otp_email_async
    result = send_otp_email_async(settings.EMAIL_HOST_USER, "999888")
    print(f"Resultado task: {result}")
except Exception as e:
    import traceback
    print(f"ERROR task: {type(e).__name__}: {e}")
    traceback.print_exc()

banner("FIN")
