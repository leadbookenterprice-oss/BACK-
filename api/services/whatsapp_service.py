import logging
from decouple import config

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='')
TWILIO_WHATSAPP_FROM = config('TWILIO_WHATSAPP_FROM', default='whatsapp:+14155238886')
WHATSAPP_ENABLED = config('WHATSAPP_ENABLED', default=False, cast=bool)


def send_whatsapp_message(to_phone, message):
    if not WHATSAPP_ENABLED or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        reason = (
            "Twilio no configurado: revisá WHATSAPP_ENABLED, "
            "TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN"
        )
        logger.warning(
            "[WHATSAPP] %s | to=%s",
            reason,
            to_phone,
        )
        return False, reason, None
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        if not to_phone.startswith('+'):
            to_phone = '+54' + to_phone.lstrip('0')

        msg = client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_FROM,
            to=f'whatsapp:{to_phone}',
        )
        logger.info("[WHATSAPP] Enviado a %s — SID: %s", to_phone, msg.sid)
        return True, None, msg.sid
    except Exception as e:
        reason = str(e)
        logger.error("[WHATSAPP] Error enviando a %s: %s", to_phone, reason)
        return False, reason, None


def send_trial_token(phone, token):
    message = (
        f"¡Hola! Tu código de acceso para activar la prueba "
        f"Starter de 30 días en LeadBook es:\n\n"
        f"{token}\n\n"
        f"Ingresalo en la app para continuar."
    )
    return send_whatsapp_message(phone, message)
