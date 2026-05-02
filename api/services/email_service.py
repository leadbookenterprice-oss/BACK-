from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from api.models import GeneratedAsset

def send_property_notification_email(property_instance, recipient_email="test@example.com"):
    subject = f"Nueva Propiedad: {property_instance.title}"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@subzero.com')
    
    # Render with pure inline CSS template
    html_content = render_to_string('email/notification.html', {'property': property_instance})
    
    msg = EmailMultiAlternatives(subject, "Nueva propiedad registrada en el sistema.", from_email, [recipient_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()

    GeneratedAsset.objects.create(
        property=property_instance,
        asset_type='EMAIL',
        status='COMPLETED'
    )
