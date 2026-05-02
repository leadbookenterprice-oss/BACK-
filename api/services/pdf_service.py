import os
from io import BytesIO
from django.conf import settings
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.core.files.base import ContentFile
from api.models import GeneratedAsset

def generate_pdf_for_property(property_instance):
    template_path = 'pdf/property_brochure.html'
    template = get_template(template_path)
    
    # Simple context with the property
    context = {'property': property_instance}
    html = template.render(context)
    
    result = BytesIO()
    
    # Generate the PDF
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        asset = GeneratedAsset.objects.create(
            property=property_instance,
            asset_type='PDF',
            status='COMPLETED'
        )
        file_name = f'brochure_{property_instance.id}.pdf'
        asset.file.save(file_name, ContentFile(result.getvalue()))
        return asset

    return None
