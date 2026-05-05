import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from api.models import APIKey
from api.services.cloudinary_pool_service import CloudinaryPoolService

@csrf_exempt
def admin_cloudinary_stats(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method'}, status=405)
        
    keys = APIKey.objects.filter(servicio='cloudinary', status='available')
    total_limit = 0
    total_used = 0
    
    for k in keys:
        st = CloudinaryPoolService.get_stats_for_key(k)
        total_limit += st.get('total_bytes', 0)
        total_used += st.get('used_bytes', 0)
        
    return JsonResponse({
        'total_bytes': total_limit, 
        'used_bytes': total_used, 
        'free_bytes': total_limit - total_used
    })

@csrf_exempt
def admin_cloudinary_keys(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method'}, status=405)
        
    keys = APIKey.objects.filter(servicio='cloudinary')
    data = []
    for k in keys:
        creds = CloudinaryPoolService.parse_cloudinary_url(k.api_key)
        st = CloudinaryPoolService.get_stats_for_key(k)
        if creds:
            ak = creds['api_key']
            masked = ak[:4] + '****' if ak else ''
            cn = creds['cloud_name']
        else:
            masked = ''
            cn = 'Unknown'
            
        data.append({
            'id': k.id,
            'cloud_name': cn,
            'api_key_masked': masked,
            'total_bytes': st.get('total_bytes', 0),
            'used_bytes': st.get('used_bytes', 0),
            'activa': k.status == 'available'
        })
    return JsonResponse({'keys': data})

@csrf_exempt
def admin_cloudinary_keys_add(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            cn = body.get('cloud_name')
            ak = body.get('api_key')
            asec = body.get('api_secret')
            if not (cn and ak and asec):
                return JsonResponse({'error': 'Faltan credenciales'}, status=400)
                
            url = f"cloudinary://{ak}:{asec}@{cn}"
            APIKey.objects.create(
                servicio='cloudinary', 
                api_key=url, 
                label=cn,
                status='available'
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)

@csrf_exempt
def admin_cloudinary_keys_delete(request, pk):
    if request.method == 'DELETE':
        try:
            APIKey.objects.filter(pk=pk, servicio='cloudinary').delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)
