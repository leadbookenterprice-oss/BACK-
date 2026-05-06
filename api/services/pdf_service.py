import os
from django.template.loader import render_to_string
# from weasyprint import HTML
from django.core.files.base import ContentFile
from api.models import GeneratedAsset


def generate_pdf_for_property(property_instance, request=None):
    """
    Genera un PDF de brochure para la propiedad dada usando WeasyPrint.
    Retorna el objeto GeneratedAsset si tiene éxito, None si falla.
    """
    context = {'property': property_instance}
    html_string = render_to_string('pdf/property_brochure.html', context)

    base_url = request.build_absolute_uri('/') if request else 'http://localhost/'

    try:
        pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()
    except Exception as e:
        print(f"[pdf_service] Error generando PDF con WeasyPrint: {e}")
        return None

    asset = GeneratedAsset.objects.create(
        property=property_instance,
        asset_type='PDF',
        status='COMPLETED'
    )
    file_name = f'brochure_{property_instance.id}.pdf'
    asset.file.save(file_name, ContentFile(pdf_bytes))
    return asset
