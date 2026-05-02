from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from decouple import config

ADMIN_KEY = config('ADMIN_KEY', default='')
from .models import Agent, Listado, Plan, APIKey, AdminAlert
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Count, Sum, Q

def _is_staff_check(request):
    if request.headers.get('X-Admin-Key') == ADMIN_KEY and ADMIN_KEY != '':
        return True
    return request.user and request.user.is_authenticated and request.user.is_staff

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_metricas(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    hoy = now().date()
    inicio_mes = hoy.replace(day=1)

    total_usuarios = Agent.objects.count()
    # Usuarios activos mes: usuarios que se loguearon este mes
    usuarios_activos_mes = Agent.objects.filter(last_login__date__gte=inicio_mes).count()
    total_listados = Listado.objects.count()
    listados_hoy = Listado.objects.filter(creado_en__date=hoy).count()

    # Ingresos mes estimado (MRR simplificado basándose en planes activos)
    ingresos = 0
    planes = Plan.objects.all()
    for p in planes:
        count = Agent.objects.filter(plan_nombre=p.nombre, plan_activo=True).count()
        ingresos += (count * float(p.precio_usd))

    usuarios_por_plan = {"free": 0, "starter": 0, "pro": 0, "scale": 0, "business": 0}
    stats_planes = Agent.objects.values('plan_nombre').annotate(total=Count('id'))
    for s in stats_planes:
        nombre = s['plan_nombre']
        if nombre in usuarios_por_plan:
            usuarios_por_plan[nombre] = s['total']

    return Response({
        "total_usuarios": total_usuarios,
        "usuarios_activos_mes": usuarios_activos_mes,
        "total_listados": total_listados,
        "listados_hoy": listados_hoy,
        "ingresos_mes": round(ingresos, 2),
        "usuarios_por_plan": usuarios_por_plan,
        # Compatibilidad con dashboard viejo
        "activos_hoy": Agent.objects.filter(last_login__gte=now()-timedelta(hours=24)).count(),
        "nuevos_hoy": Agent.objects.filter(fecha_registro__gte=now()-timedelta(hours=24)).count(),
        "distribucion_planes": usuarios_por_plan
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_list(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from django.core.paginator import Paginator
    page_num = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))
    search = request.query_params.get('search', '')

    agentes = Agent.objects.filter(eliminado_en__isnull=True).order_by('-fecha_registro')
    
    if search:
        agentes = agentes.filter(
            Q(email__icontains=search) | Q(nombre__icontains=search)
        )

    paginator = Paginator(agentes, page_size)
    page = paginator.get_page(page_num)

    data = []
    for agente in page:
        data.append({
            'id': agente.id,
            'email': agente.email,
            'nombre': agente.nombre,
            'plan_nombre': agente.plan_nombre or 'free',
            'fecha_registro': agente.fecha_registro.isoformat() if agente.fecha_registro else None,
            'total_listados': Listado.objects.filter(agente=agente).count(),
            'ultimo_acceso': agente.last_login.isoformat() if agente.last_login else None,
            'is_active': agente.is_active
        })

    return Response({
        'total': paginator.count,
        'usuarios': data
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios_eliminados(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    agentes = Agent.objects.filter(eliminado_en__isnull=False).order_by('-eliminado_en')
    data = []
    for a in agentes:
        data.append({
            'id': a.id,
            'email': a.email,
            'nombre': a.nombre,
            'eliminado_en': a.eliminado_en.isoformat() if a.eliminado_en else None,
            'is_active': a.is_active
        })
    return Response({'usuarios': data})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_restaurar(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        agente = Agent.objects.get(id=user_id)
        agente.eliminado_en = None
        agente.is_active = True
        agente.save()
        return Response({'success': True, 'message': 'Usuario restaurado correctamente'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_usuario_suspender(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        agente = Agent.objects.get(id=user_id)
        agente.is_active = not agente.is_active
        agente.save()
        estado = "suspendido" if not agente.is_active else "reactivado"
        return Response({'success': True, 'is_active': agente.is_active, 'estado': estado})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['PUT'])
@permission_classes([AllowAny])
def admin_usuario_cambiar_plan(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    nuevo_plan = request.data.get('plan')
    valid_plans = ['free', 'starter', 'pro', 'scale', 'business']
    if nuevo_plan not in valid_plans:
        return Response({'error': f'Plan inválido. Debe ser uno de: {", ".join(valid_plans)}'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        agente = Agent.objects.get(id=user_id)
        agente.plan_nombre = nuevo_plan
        agente.plan_activo = True # Se asume que si el admin lo cambia, queda activo
        agente.save()
        return Response({'success': True, 'id': agente.id, 'plan': nuevo_plan})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_usuario_eliminar(request, user_id):
    """Soft delete: marca eliminado_en y desactiva"""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        agente = Agent.objects.get(id=user_id)
        email = agente.email
        agente.is_active = False
        agente.eliminado_en = now()
        agente.save()
        return Response({'success': True, 'eliminado': email, 'message': 'Usuario marcado como eliminado (soft delete)'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        agente = Agent.objects.get(id=user_id)
        listados = Listado.objects.filter(agente=agente).order_by('-creado_en')
        
        listados_data = []
        for l in listados:
            listados_data.append({
                "id": l.id,
                "titulo": l.titulo,
                "tipo": l.tipo_propiedad,
                "fecha": l.creado_en.isoformat() if l.creado_en else None,
                "video": l.video_status != 'none'
            })
            
        return Response({
            "usuario": {
                "id": agente.id,
                "email": agente.email,
                "nombre": agente.nombre,
                "plan": agente.plan_nombre,
                "fecha_registro": agente.fecha_registro.isoformat() if agente.fecha_registro else None,
                "is_active": agente.is_active,
                "eliminado_en": agente.eliminado_en.isoformat() if agente.eliminado_en else None
            },
            "actividad": {
                "total_listados": listados.count(),
                "listados": listados_data
            }
        })
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_enviar_email(request, user_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        agente = Agent.objects.get(id=user_id)
        asunto = request.data.get('asunto', 'Mensaje de LeadBook')
        mensaje = request.data.get('mensaje', '')
        if not mensaje:
            return Response({'error': 'Mensaje requerido'}, status=400)
        
        from django.core.mail import send_mail
        from django.conf import settings
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[agente.email],
            fail_silently=False
        )
        return Response({'success': True, 'message': f'Email enviado a {agente.email}'})
    except Agent.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# --- API Keys & Pool ---

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_apikeys_resumen(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    umbral = request.query_params.get('umbral_libres')
    
    total = APIKey.objects.count()
    por_servicio = APIKey.objects.values('servicio').annotate(
        total=Count('id'),
        disponibles=Count('id', filter=Q(status='available')),
        agotadas=Count('id', filter=Q(status='exhausted'))
    )
    
    if umbral is not None:
        return Response(list(por_servicio))
        
    estado_pool = APIKey.objects.values('status').annotate(total=Count('id'))
    
    return Response({
        "total": total,
        "por_servicio": list(por_servicio),
        "estados": list(estado_pool)
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_apikeys_pool(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    servicio = request.query_params.get('servicio')
    keys = APIKey.objects.all().order_by('servicio', '-created_at')
    if servicio:
        keys = keys.filter(servicio=servicio)
        
    data = []
    for k in keys:
        data.append({
            "id": k.id,
            "servicio": k.servicio,
            "status": k.status,
            "key_masked": k.api_key[:10] + "..." if k.api_key else "",
            "requests_today": k.requests_today,
            "total_requests": k.total_requests,
            "error_count": k.error_count,
            "last_used": k.last_used_at.isoformat() if k.last_used_at else None,
            "health": k.last_health_status,
            "assigned_to_email": k.assigned_to.email if k.assigned_to else None,
            "assigned_to_id": k.assigned_to.id if k.assigned_to else None,
            "assigned_to_nombre": k.assigned_to.nombre if k.assigned_to else None,
        })
    return Response(data)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_pool_crear(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    servicio = request.data.get('servicio')
    api_key = request.data.get('api_key')
    daily_limit = request.data.get('daily_limit', 1500)
    if not servicio or not api_key:
        return Response({'error': 'Servicio y API Key son requeridos'}, status=400)
        
    k = APIKey.objects.create(
        servicio=servicio,
        api_key=api_key,
        status='available',
        daily_limit=daily_limit,
    )
    return Response({"success": True, "id": k.id})

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_apikeys_pool_detail(request, key_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        k = APIKey.objects.get(id=key_id)
        if request.method == 'GET':
            return Response({
                "id": k.id,
                "servicio": k.servicio,
                "status": k.status,
                "api_key": k.api_key,
                "requests_today": k.requests_today,
                "error_count": k.error_count,
                "notes": k.notes
            })
        elif request.method == 'PUT':
            for attr, value in request.data.items():
                if hasattr(k, attr):
                    setattr(k, attr, value)
            k.save()
            return Response({"success": True})
        elif request.method == 'DELETE':
            k.delete()
            return Response({"success": True})
    except APIKey.DoesNotExist:
        return Response({'error': 'Key no encontrada'}, status=404)

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_apikeys_global(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    # Placeholder para configuraciones globales
    return Response({"message": "Settings globales no implementados"})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pool_estado(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        
    servicios = APIKey.objects.values('servicio').annotate(
        total=Count('id'),
        disponibles=Count('id', filter=Q(status='available')),
        agotadas=Count('id', filter=Q(status='exhausted')),
        muertas=Count('id', filter=Q(status='dead'))
    )
    
    alertas_criticas = AdminAlert.objects.filter(is_read=False, severity='critical').count()
    
    if "pool/estado" in request.path:
        return Response(list(servicios))

    return Response({
        "servicios": servicios,
        "alertas_criticas": alertas_criticas,
        "estado_general": "OK" if alertas_criticas == 0 else "WARNING"
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_alerts_read(request, alert_id):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    try:
        alerta = AdminAlert.objects.get(id=alert_id)
        alerta.is_read = True
        alerta.save()
        return Response({"success": True})
    except AdminAlert.DoesNotExist:
        return Response({'error': 'Alerta no encontrada'}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_health_check(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    # Aquí iría el disparador de la tarea de health check
    # Por ahora devolvemos éxito simulado
    return Response({"success": True, "message": "Health check iniciado"})
