import os

content_to_append = """

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def proxy_pdf_view(request, listado_id):
    \"\"\"
    Sirve el PDF desde Cloudinary actuando como proxy para evitar errores 401/ACL.
    \"\"\"
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        
        # Buscar URL en los datos del listado
        res = listado.datos.get('resultados', {}) if listado.datos else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data
        
        if not pdf_url:
            return Response({"error": "URL de PDF no encontrada"}, status=404)

        # Si es URL local, servir directamente
        if not pdf_url.startswith('http'):
             return Response({"error": "PDF local no disponible vía proxy"}, status=404)

        # Petición interna a Cloudinary (El servidor tiene acceso)
        response = requests.get(pdf_url, stream=True, timeout=30)
        
        if response.status_code != 200:
            return Response({
                "error": f"Cloudinary respondió con error {response.status_code}",
                "details": "Posible error de ACL en Cloudinary. El backend no pudo recuperar el archivo."
            }, status=status.HTTP_502_BAD_GATEWAY)

        django_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='application/pdf'
        )
        django_response['Content-Disposition'] = f'inline; filename="ficha_leadbook_{listado_id}.pdf"'
        return django_response

    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def proxy_pdf_thumbnail_view(request, listado_id):
    \"\"\"
    Genera una vista previa (imagen) de la primera página del PDF vía proxy.
    \"\"\"
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id)
        res = listado.datos.get('resultados', {}) if listado.datos else {}
        pdf_data = res.get('pdf', {})
        pdf_url = pdf_data.get('url') if isinstance(pdf_data, dict) else pdf_data

        if not pdf_url or 'res.cloudinary.com' not in pdf_url:
            from django.shortcuts import redirect
            return redirect('https://via.placeholder.com/400x600?text=Vista+Previa+No+Disponible')

        # Intentar obtener la miniatura (pg_1) transformando la URL
        thumb_url = pdf_url.replace('.pdf', '.jpg')
        if '/upload/' in thumb_url:
            thumb_url = thumb_url.replace('/upload/', '/upload/w_600,h_800,c_fill,pg_1/')

        response = requests.get(thumb_url, stream=True, timeout=15)
        
        if response.status_code != 200:
            return Response({"error": "No se pudo generar miniatura"}, status=404)

        return StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type='image/jpeg'
        )

    except Exception as e:
        return Response({"error": str(e)}, status=500)
"""

file_path = 'api/views.py'
with open(file_path, 'a', encoding='utf-8') as f:
    f.write(content_to_append)

print("Inyección completada exitosamente.")
