from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from decouple import config

ADMIN_KEY = config('ADMIN_KEY', default='')
from .models import Agent, Listado, Plan, APIKey, APIBundle, APIBundleAssignment, AdminAlert
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
        
        # Liberar APIs atadas a esta cuenta
        from api.services.pool_service import APIPoolService
        APIPoolService.release_keys_from_user(agente)

        # Trazabilidad
        AdminAlert.objects.create(
            type='system',
            severity='info',
            title='Usuario Desactivado y APIs Liberadas',
            message=f"El usuario {email} fue marcado como eliminado (soft-delete). Sus llaves API han sido regresadas al pool."
        )
        
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
    keys = APIKey.objects.all().select_related('assigned_to').order_by('servicio', '-created_at')
    if servicio:
        keys = keys.filter(servicio__icontains=servicio)
        
    # Límite por defecto para el cálculo de porcentaje
    DEFAULT_LIMITS = {
        'gemini': 1500,
        'elevenlabs': 10000,
        'uploadpost': 10
    }
    
    data = []
    for k in keys:
        limite = k.monthly_limit or DEFAULT_LIMITS.get(k.servicio, 100)
        consumo = k.requests_this_month
        porcentaje = min(100, int((consumo / limite) * 100)) if limite else 0

        # Si tiene usuario asignado, cruzar con UserAPIQuota para datos reales
        user_daily_used = k.requests_today
        user_daily_limit = k.daily_limit or 1500
        user_is_blocked = False
        
        if k.assigned_to:
            from .models import UserAPIQuota
            q = UserAPIQuota.objects.filter(user=k.assigned_to, service=k.servicio).first()
            if q:
                user_daily_used = q.requests_today
                user_daily_limit = q.daily_limit or 1500
                user_is_blocked = q.is_blocked
                if user_is_blocked:
                    user_daily_used = user_daily_limit
                    porcentaje = 100

        data.append({
            "id": k.id,
            "servicio": k.servicio,
            "status": k.status,
            "key_masked": k.api_key[:10] + "..." if k.api_key else "",
            "requests_today": user_daily_used,
            "daily_limit": user_daily_limit,
            "requests_this_month": consumo,
            "monthly_limit": limite,
            "porcentaje_uso": porcentaje,
            "total_requests": k.total_requests,
            "error_count": k.error_count,
            "last_used": k.last_used_at.isoformat() if k.last_used_at else None,
            "health": k.last_health_status,
            "assigned_to_email": k.assigned_to.email if k.assigned_to else None,
            "assigned_to_id": k.assigned_to.id if k.assigned_to else None,
            "assigned_to_nombre": k.assigned_to.nombre if k.assigned_to else None,
            "is_blocked": user_is_blocked,
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
        servicio=servicio.lower() if isinstance(servicio, str) else servicio,
        api_key=api_key,
        status='available',
        daily_limit=daily_limit,
    )
    return Response({"success": True, "id": k.id})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_pool_bulk(request):
    """
    Carga masiva de keys desde el dashboard.
    Mapea 'service' -> 'servicio' y 'key' -> 'api_key' para compatibilidad con el frontend.
    """
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    
    keys_data = request.data.get('keys', [])
    creadas = 0
    for k in keys_data:
        # Usamos los nombres de campos que envía el frontend en ApiPoolPage.jsx
        service_val = k.get('service') or k.get('servicio', 'gemini')
        key_val = k.get('key') or k.get('api_key')
        
        if not key_val:
            continue

        APIKey.objects.create(
            api_key=key_val,
            servicio=service_val.lower().strip() if isinstance(service_val, str) else service_val,
            label=k.get('label', '-'),
            status='available',
            daily_limit=k.get('daily_limit', 1500),
            monthly_limit=k.get('monthly_limit', None),
        )
        creadas += 1
        
    return Response({
        'success': True, 
        'creadas': creadas, 
        'mensaje': f'{creadas} keys creadas exitosamente'
    })

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


# ── Bundle endpoints ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_list(request):
    """Lista todos los bundles con su estado y usuario asignado."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    bundles = APIBundle.objects.prefetch_related('assignments__usuario').select_related(
        'key_gemini', 'key_elevenlabs', 'key_uploadpost'
    ).all().order_by('-created_at')

    data = []
    for b in bundles:
        asig_activa = b.assignments.filter(activo=True).select_related('usuario').first()
        data.append({
            'id': b.id,
            'nombre': b.nombre,
            'status': b.status,
            'is_complete': b.is_complete(),
            'notas': b.notas,
            'key_gemini': b.key_gemini.label if b.key_gemini else None,
            'key_elevenlabs': b.key_elevenlabs.label if b.key_elevenlabs else None,
            'key_uploadpost': b.key_uploadpost.label if b.key_uploadpost else None,
            'usuario_asignado': {
                'id': asig_activa.usuario.id,
                'email': asig_activa.usuario.email,
                'nombre': asig_activa.usuario.nombre,
                'asignado_en': asig_activa.asignado_en.isoformat(),
            } if asig_activa else None,
            'created_at': b.created_at.isoformat(),
        })
    return Response({'bundles': data})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_crear(request):
    """Crea un nuevo bundle y opcionalmente lo asigna a un usuario."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    nombre = request.data.get('nombre')
    if not nombre:
        return Response({'error': 'El campo nombre es requerido'}, status=400)

    key_gemini_id = request.data.get('key_gemini_id')
    key_elevenlabs_id = request.data.get('key_elevenlabs_id')
    key_uploadpost_id = request.data.get('key_uploadpost_id')
    notas = request.data.get('notas', '')

    bundle = APIBundle(nombre=nombre, notas=notas)
    if key_gemini_id:
        bundle.key_gemini_id = key_gemini_id
    if key_elevenlabs_id:
        bundle.key_elevenlabs_id = key_elevenlabs_id
    if key_uploadpost_id:
        bundle.key_uploadpost_id = key_uploadpost_id
    bundle.save()

    return Response({'success': True, 'id': bundle.id, 'nombre': bundle.nombre})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([AllowAny])
def admin_bundles_detail(request, bundle_id):
    """Detalle, edición y eliminación de un bundle."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        b = APIBundle.objects.get(id=bundle_id)
    except APIBundle.DoesNotExist:
        return Response({'error': 'Bundle no encontrado'}, status=404)

    if request.method == 'GET':
        asig_activa = b.assignments.filter(activo=True).select_related('usuario').first()
        return Response({
            'id': b.id,
            'nombre': b.nombre,
            'status': b.status,
            'notas': b.notas,
            'is_complete': b.is_complete(),
            'key_gemini_id': b.key_gemini_id,
            'key_elevenlabs_id': b.key_elevenlabs_id,
            'key_uploadpost_id': b.key_uploadpost_id,
            'usuario_asignado': {
                'id': asig_activa.usuario.id,
                'email': asig_activa.usuario.email,
            } if asig_activa else None,
        })

    elif request.method == 'PUT':
        for field in ['nombre', 'status', 'notas', 'key_gemini_id', 'key_elevenlabs_id', 'key_uploadpost_id']:
            if field in request.data:
                setattr(b, field, request.data[field])
        b.save()
        return Response({'success': True})

    elif request.method == 'DELETE':
        if b.assignments.filter(activo=True).exists():
            return Response({'error': 'No se puede eliminar un bundle con usuarios activos'}, status=400)
        b.delete()
        return Response({'success': True})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_asignar(request, bundle_id):
    """Asigna manualmente un bundle a un usuario específico."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    usuario_id = request.data.get('usuario_id')
    if not usuario_id:
        return Response({'error': 'usuario_id es requerido'}, status=400)

    try:
        bundle = APIBundle.objects.get(id=bundle_id)
        usuario = Agent.objects.get(id=usuario_id)
    except (APIBundle.DoesNotExist, Agent.DoesNotExist) as e:
        return Response({'error': str(e)}, status=404)

    # Liberar bundle anterior si tiene
    APIBundleAssignment.objects.filter(usuario=usuario, activo=True).update(
        activo=False
    )

    bundle.status = 'assigned'
    bundle.save(update_fields=['status'])

    asig, _ = APIBundleAssignment.objects.get_or_create(
        bundle=bundle,
        usuario=usuario,
        defaults={'activo': True}
    )
    asig.activo = True
    asig.save()

    return Response({'success': True, 'bundle': bundle.nombre, 'usuario': usuario.email})


@api_view(['POST'])
@permission_classes([AllowAny])
def admin_bundles_liberar(request, bundle_id):
    """Libera un bundle de su usuario actual."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from django.utils import timezone as tz
    try:
        bundle = APIBundle.objects.get(id=bundle_id)
    except APIBundle.DoesNotExist:
        return Response({'error': 'Bundle no encontrado'}, status=404)

    asig = bundle.assignments.filter(activo=True).first()
    if asig:
        asig.activo = False
        asig.liberado_en = tz.now()
        asig.save()

    bundle.status = 'available'
    bundle.save(update_fields=['status'])
    return Response({'success': True, 'message': 'Bundle liberado correctamente'})


@api_view(['GET'])
@permission_classes([AllowAny])
def admin_bundles_stats(request):
    """Estadísticas rápidas del pool de bundles."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from .services.pool_service import APIPoolService
    return Response(APIPoolService.get_pool_stats())


# ─── Librería de Audio (VideoMusic + VideoSFX) ───────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_audio_music(request):
    """Lista o sube música de fondo para los videos."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)

    from .models import VideoMusic
    if request.method == 'GET':
        tracks = VideoMusic.objects.all().order_by('-creado_en')
        data = [{
            'id': t.id,
            'nombre': t.nombre,
            'duracion_segundos': t.duracion_segundos,
            'activo': t.activo,
            'url': request.build_absolute_uri(t.archivo.url) if t.archivo else None,
            'creado_en': t.creado_en,
        } for t in tracks]
        return Response(data)

    # POST: subir nueva pista
    archivo = request.FILES.get('archivo')
    nombre = request.data.get('nombre', archivo.name if archivo else 'Sin nombre')
    duracion = request.data.get('duracion_segundos', 0)
    if not archivo:
        return Response({'error': 'No se envió archivo'}, status=400)
    track = VideoMusic.objects.create(nombre=nombre, archivo=archivo, duracion_segundos=duracion)
    return Response({'success': True, 'id': track.id, 'nombre': track.nombre}, status=201)


@api_view(['DELETE', 'PATCH'])
@permission_classes([AllowAny])
def admin_audio_music_detail(request, pk):
    """Elimina o activa/desactiva una pista de música."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    from .models import VideoMusic
    try:
        track = VideoMusic.objects.get(pk=pk)
    except VideoMusic.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)

    if request.method == 'DELETE':
        track.archivo.delete(save=False)
        track.delete()
        return Response({'success': True})

    # PATCH: toggle activo
    track.activo = not track.activo
    track.save(update_fields=['activo'])
    return Response({'success': True, 'activo': track.activo})


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_audio_sfx(request):
    """Lista o sube efectos de sonido (SFX)."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)

    from .models import VideoSFX
    if request.method == 'GET':
        sfx_list = VideoSFX.objects.all().order_by('-creado_en')
        data = [{
            'id': s.id,
            'nombre': s.nombre,
            'tipo': s.tipo,
            'activo': s.activo,
            'url': request.build_absolute_uri(s.archivo.url) if s.archivo else None,
            'creado_en': s.creado_en,
        } for s in sfx_list]
        return Response(data)

    # POST: subir nuevo SFX
    archivo = request.FILES.get('archivo')
    nombre = request.data.get('nombre', archivo.name if archivo else 'Sin nombre')
    tipo = request.data.get('tipo', 'other')
    if not archivo:
        return Response({'error': 'No se envió archivo'}, status=400)
    sfx = VideoSFX.objects.create(nombre=nombre, tipo=tipo, archivo=archivo)
    return Response({'success': True, 'id': sfx.id, 'nombre': sfx.nombre}, status=201)


@api_view(['DELETE', 'PATCH'])
@permission_classes([AllowAny])
def admin_audio_sfx_detail(request, pk):
    """Elimina o activa/desactiva un SFX."""
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
    from .models import VideoSFX
    try:
        sfx = VideoSFX.objects.get(pk=pk)
    except VideoSFX.DoesNotExist:
        return Response({'error': 'No encontrado'}, status=404)

    if request.method == 'DELETE':
        sfx.archivo.delete(save=False)
        sfx.delete()
        return Response({'success': True})

    sfx.activo = not sfx.activo
    sfx.save(update_fields=['activo'])
    return Response({'success': True, 'activo': sfx.activo})

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_apikeys_auto_repair(request):
    """
    Busca usuarios activos que tengan servicios faltantes o caídos 
    y les intenta asignar las faltantes del pool usando APIPoolService.
    """
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=403)
        
    from api.models import Agent
    from api.services.pool_service import APIPoolService
    
    # Podemos filtrar por IDs si se pasan en el request (para reparación selectiva)
    user_ids = request.data.get('user_ids', [])
    
    if user_ids:
        users = Agent.objects.filter(id__in=user_ids, is_active=True)
    else:
        # Por defecto repara a todos los activos
        users = Agent.objects.filter(is_active=True)
        
    fixed = 0
    details = []
    
    for user in users:
        repaired = APIPoolService.repair_user_apis(user)
        if repaired:
            fixed += 1
            details.append({"email": user.email, "repaired": repaired})
            
    return Response({"status": "success", "fixed_count": fixed, "details": details})
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_branding_watermark(request):
    if not _is_staff_check(request):
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from .models import ConfiguracionSistema
    import base64
    from io import BytesIO
    import cloudinary.uploader
    from api.services.almacenamiento import AlmacenamientoCloudinary

    if request.method == 'GET':
        config, created = ConfiguracionSistema.objects.get_or_create(clave='watermark')
        url = config.datos.get('url') if config.datos else None
        return Response({
            'url': url,
            'actualizado_en': config.actualizado_en
        })

    if request.method == 'POST':
        image_base64 = request.data.get('image')
        if not image_base64:
            return Response({'error': 'Imagen requerida'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Limpiar el prefijo data:image/png;base64, si existe
            if 'base64,' in image_base64:
                image_base64 = image_base64.split('base64,')[1]
            
            image_data = base64.b64decode(image_base64)
            image_stream = BytesIO(image_data)
            
            # Usar la mejor cuenta disponible del pool
            creds, key_id = AlmacenamientoCloudinary.get_mejor_cuenta()
            extra_creds = creds if creds else {}

            resultado = cloudinary.uploader.upload(
                image_stream,
                folder="leadbook/sistema",
                public_id="watermark",
                overwrite=True,
                invalidate=True,
                **extra_creds
            )

            url = resultado.get('secure_url')

            if not url:
                return Response({'error': 'Error al subir a Cloudinary'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Guardar en la configuración
            config, created = ConfiguracionSistema.objects.get_or_create(clave='watermark')
            config.datos = {
                'url': url,
                'public_id': resultado.get('public_id'),
                'cloud_name': extra_creds.get('cloud_name')
            }
            config.save()

            return Response({
                'message': 'Marca de agua actualizada exitosamente',
                'url': url
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
