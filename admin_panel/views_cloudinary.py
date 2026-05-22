import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from api.models import APIKey, Servicio, UserAPIAssignment
from api.services.pool_service import APIPoolService
from decouple import config
from django.conf import settings
from django.utils.crypto import constant_time_compare

ADMIN_KEY = config('ADMIN_KEY', default='')

def _check_admin(request):
    supplied_key = request.headers.get('X-Admin-Key', '')
    if getattr(settings, 'ALLOW_ADMIN_KEY_AUTH', False) and ADMIN_KEY and supplied_key and constant_time_compare(supplied_key, ADMIN_KEY):
        return True
    return request.user and request.user.is_authenticated and request.user.is_staff

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_cloudinary_stats(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    servicio = Servicio.objects.filter(nombre='cloudinary').first()
    if not servicio:
        return Response({'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0})
    keys = APIKey.objects.filter(servicio=servicio, status='available')
    return Response({'total_cuentas': keys.count(), 'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_cloudinary_keys(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    servicio = Servicio.objects.filter(nombre='cloudinary').first()
    if not servicio:
        return Response({'keys': []})
    keys = APIKey.objects.filter(servicio=servicio)
    data = [{'id': k.id, 'cloud_name': k.label or 'Sin nombre',
             'api_key_masked': k.api_key[:6] + '...' if k.api_key else '',
             'total_bytes': 0, 'used_bytes': 0, 'activa': k.status == 'available'} for k in keys]
    return Response({'keys': data})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_cloudinary_keys_add(request):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    cn = request.data.get('cloud_name')
    ak = request.data.get('api_key')
    asec = request.data.get('api_secret')
    if not (cn and ak and asec):
        return Response({'error': 'Faltan credenciales'}, status=400)
    servicio = Servicio.objects.filter(nombre='cloudinary').first()
    if not servicio:
        return Response({'error': 'Servicio cloudinary no existe en DB'}, status=400)
    url = f"cloudinary://{ak}:{asec}@{cn}"
    APIKey.objects.create(servicio=servicio, api_key=url, label=cn, status='available')
    return Response({'success': True}, status=201)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_cloudinary_keys_delete(request, pk):
    if not _check_admin(request): return Response({'error': 'Forbidden'}, status=403)
    servicio = Servicio.objects.filter(nombre='cloudinary').first()
    if servicio:
        APIKey.objects.filter(pk=pk, servicio=servicio).delete()
    return Response({'success': True})
