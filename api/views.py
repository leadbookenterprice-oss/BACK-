from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Sum
from decouple import config
import cloudinary
import cloudinary.uploader

from .models import (
    Property, GeneratedAsset, Listado, OTPCode,
    TerminosCondiciones, PoliticaPrivacidad
)
from .serializers import (
    PropertySerializer, GeneratedAssetSerializer, RegisterSerializer,
    TerminosCondicionesSerializer, PoliticaPrivacidadSerializer
)
from .tasks import run_asset_generation
from .ai_services import call_groq_api, call_gemini_api, smart_call
from .plan_utils import puede_generar, incrementar_uso
from .image_generator import generate_social_image

LIMITES_PLAN = {
    'free':     {'listados_mes': 10},
    'starter':  {'listados_mes': 40},
    'pro':      {'listados_mes': 150},
    'scale':    {'listados_mes': 999999},
    'business': {'listados_mes': 999999},
}

def verificar_limite_plan(agent):
    from datetime import datetime
    plan = getattr(agent, 'plan_nombre', 'free')
    limite = LIMITES_PLAN.get(plan, LIMITES_PLAN['free'])
    
    ahora = datetime.now()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=ahora.year,
        creado_en__month=ahora.month
    ).count()
    
    if listados_mes >= limite['listados_mes']:
        return False, listados_mes, limite['listados_mes']
    return True, listados_mes, limite['listados_mes']

from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.http import HttpResponse

import base64
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import tempfile
import uuid
import os
import time

import qrcode
import base64
from io import BytesIO

def generar_qr_base64(texto):
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        from datetime import timedelta
        from django.utils import timezone
        email = request.data.get('email', '').strip().lower()
        
        # CAMBIO 1: Validar email duplicado
        from .models import Agent
        if Agent.objects.filter(email=email).exists():
            return Response({"error": "Este email ya está registrado. ¿Olvidaste tu contraseña?"}, status=400)

        otp_verificado = OTPCode.objects.filter(
            email=email,
            verified=True,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        if not otp_verificado:
            return Response({"error": "Debés verificar tu email primero"}, status=400)
            
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Asignar plan free por defecto
            user.plan_nombre = 'free'
            user.plan_activo = True
            user.plan_seleccionado = True
            user.save()
            
            # TAREA 3: Consumir el OTP para que no pueda reutilizarse
            otp_usado = OTPCode.objects.filter(
                email=email,
                verified=True,
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).order_by('-created_at').first()
            if otp_usado:
                otp_usado.verified = False
                otp_usado.code_hash = 'USED'
                otp_usado.save()

            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class PropertyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Property.objects.none()
    serializer_class = PropertySerializer

    def get_queryset(self):
        return Property.objects.filter(agent=self.request.user)

    @action(detail=True, methods=['post'])
    def generate_assets(self, request, pk=None):
        property_instance = self.get_object()
        
        # Trigger Celery Task
        run_asset_generation.delay(property_instance.id)

        return Response({
            'message': 'Asset generation triggered successfully.',
            'status': 'PROCESSING'
        }, status=status.HTTP_202_ACCEPTED)

class GeneratedAssetViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = GeneratedAsset.objects.none()
    serializer_class = GeneratedAssetSerializer

    def get_queryset(self):
        return GeneratedAsset.objects.filter(agent=self.request.user)
import os
import concurrent.futures

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_guion(request):
    if not puede_generar(request.user, 'ai'):
        return Response({
            "error": "limite_alcanzado", 
            "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
            "upgrade_url": "/precios"
        }, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    tipo_video = data.get('tipoVideo', 'reel')
    tipo = data.get('tipoPropiedad', 'Propiedad')
    ciudad = data.get('ciudad', '')
    operacion = data.get('operacion', 'Venta')
    moneda = data.get('moneda', 'USD')
    precio = data.get('precio', '')
    recamaras = str(data.get('recamaras', '') or data.get('habitaciones', ''))
    banos = str(data.get('banos', '') or data.get('bathrooms', ''))
    superficie = str(data.get('superficieCubierta', '') or data.get('metros', ''))

    # Intentar IA solo si hay keys Y con timeout estricto de 5s
    descripcion_ia = None
    GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
    GROQ_KEY = os.environ.get('GROQ_API_KEY', '')

    if GEMINI_KEY or GROQ_KEY:
        palabras_por_escena = "25-38 palabras" if tipo_video == 'reel' else "50-75 palabras"
        palabras_total = "100-150 palabras" if tipo_video == 'reel' else "200-300 palabras"
        prompt = f"""Sos un copywriter inmobiliario experto.
Generá un guión PROFESIONAL para video tipo {tipo_video}.

PROPIEDAD:
- Tipo: {tipo}
- Operación: {operacion}
- Ubicación: {ciudad}
- Precio: {moneda} {precio}
- Recámaras: {recamaras}
- Baños: {banos}

REQUISITOS:
- Genera EXACTAMENTE 4 escenas
- Cada escena: {palabras_por_escena} (texto persuasivo y descriptivo)
- Total del guión: {palabras_total}
- Tono: profesional, elegante, convincente
- Formato: JSON puro

ESTRUCTURA:
[
  {{"nombre":"Apertura","texto":"...","icono":"🏠"}},
  {{"nombre":"Detalles","texto":"...","icono":"✨"}},
  {{"nombre":"Ubicación","texto":"...","icono":"📍"}},
  {{"nombre":"CTA","texto":"...","icono":"📞"}}
]

RESPONDE SOLO JSON, SIN PREAMBLE."""
        try:
            with concurrent.futures.ThreadPoolExecutor() as ex:
                future = ex.submit(smart_call, prompt, 3, request.user)
                descripcion_ia = future.result(timeout=15)
        except Exception:
            descripcion_ia = None

    # Fallback local — siempre 4 escenas con rangos exactos de palabras
    if tipo_video == 'tour':
        # Tour narrado: 6 escenas arquitectónicas (porta el estilo de LEADBOOK UP)
        escenas_default = [
            {"nombre": "Fachada", "icono": "🏠",
             "texto": f"Bienvenidos a esta {tipo} en {operacion} en {ciudad}. Una oportunidad única en el mercado inmobiliario actual. Precio: {moneda} {precio}."},
            {"nombre": "Sala", "icono": "🛋️",
             "texto": "Amplios espacios interiores diseñados para el confort familiar. Luz natural, alturas generosas y un diseño que invita a disfrutar cada rincón."},
            {"nombre": "Cocina", "icono": "🍳",
             "texto": "Cocina funcional con terminaciones de primera calidad, espacios de guardado y distribución inteligente para el uso diario."},
            {"nombre": "Recámara", "icono": "🛏️",
             "texto": f"{'Con ' + str(recamaras) + ' recámaras y ' + str(banos) + ' baños.' if recamaras else 'Dormitorios luminosos para el descanso ideal.'} Acabados de primera línea{(', superficie cubierta de ' + superficie + ' m²') if superficie else ''}."},
            {"nombre": "Exteriores", "icono": "🌿",
             "texto": f"Espacios exteriores que complementan una vida plena en {ciudad}. Zonas de esparcimiento, acceso a servicios y conectividad inmejorable."},
            {"nombre": "Cierre", "icono": "📞",
             "texto": f"Precio: {moneda} {precio}. No dejes que alguien más tome esta decisión. Contactanos hoy mismo y agendá tu visita personalizada. ¡Te esperamos!"}
        ]
    else:  # reel rápido: 100-150 palabras totales (25-38 palabras por escena)
        escenas_default = [
            {"nombre": "Apertura", "icono": "⚡",
             "texto": f"✨ {tipo} en {operacion} en {ciudad}. Precio: {moneda} {precio}. Una oportunidad única en el mercado inmobiliario actual. No te la pierdas."},
            {"nombre": "Características", "icono": "🏠",
             "texto": f"{recamaras} recámaras · {banos} baños{(' · ' + superficie + ' m²') if superficie else ''}. Espacios amplios, luminosos y diseñados para el máximo confort. Acabados de primera categoría."},
            {"nombre": "Ubicación", "icono": "📍",
             "texto": f"Estratégicamente ubicado en {ciudad}. Acceso a los mejores servicios, comercios, transporte y zonas de esparcimiento. Todo lo que necesitás, cerca de vos."},
            {"nombre": "Contacto", "icono": "📞",
             "texto": f"¡El hogar que soñabas está en {ciudad}! Contactanos ahora mismo, agendá tu visita y hacelo tuyo antes de que sea tarde."}
        ]


    # Parsear respuesta de IA si vino bien
    escenas_finales = escenas_default
    if descripcion_ia:
        from .plan_utils import registrar_uso
        registrar_uso(request.user, 'ai')
        try:
            import json as _json
            parsed = _json.loads(descripcion_ia)
            if isinstance(parsed, list) and len(parsed) >= 4:
                escenas_finales = parsed
        except Exception:
            pass

    return Response({'escenas': escenas_finales, 'tipo_video': tipo_video})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_listado(request):
    if not puede_generar(request.user, 'ai'):
        return Response({
            "error": "limite_alcanzado", 
            "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
            "upgrade_url": "/precios"
        }, status=status.HTTP_403_FORBIDDEN)
            
    prompt_text = request.data.get("prompt", "")
    if not prompt_text:
        return Response({"error": "No prompt provided. Please pass a 'prompt' field in the JSON body."}, status=status.HTTP_400_BAD_REQUEST)
        
    system_prompt = "Sos un as copywriter de real estate. Escribí descripciones profesionales, persuasivas y completas (listados) para propiedades en venta o alquiler en español."

    try:
        result = call_groq_api(prompt_text, system_prompt=system_prompt)
    except Exception as e_groq:
        # Fallback: intentar con Gemini si Groq falla
        try:
            result = call_gemini_api(prompt_text, system_prompt=system_prompt, agente=request.user)
        except Exception as e_gem:
            return Response({
                "error": "IA no disponible",
                "detalle": f"Groq: {e_groq} | Gemini: {e_gem}"
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if request.user.is_authenticated:
        incrementar_uso(request.user, 'ai')
    return Response({"generated_text": result}, status=status.HTTP_200_OK)

class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        listados = Listado.objects.filter(agente=user)
        listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
        total_generados = listados.count()
        
        videos_creados = listados.aggregate(total_videos=Sum('videos_creados'))['total_videos'] or 0

        listados_recientes = listados.order_by('-creado_en')[:5].values(
            'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en'
        )

        susc = get_suscripcion(user)
        plan = susc.plan

        return Response({
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "listados_este_mes": listados_este_mes,
            "total_generados": total_generados,
            "videos_creados": videos_creados,
            "conexiones_activas": 0,
            "listados_recientes": list(listados_recientes),
            "plan": plan.nombre,
            "plan_limites": {
                "properties_per_month": plan.properties_per_month,
                "ai_generations": plan.ai_generations,
                "image_generations": plan.image_generations,
                "video_generations": plan.video_generations,
                "branding": plan.branding
            },
            "uso_actual": {
                "properties_used": susc.properties_used,
                "ai_used": susc.ai_used,
                "images_used": susc.images_used,
                "videos_used": susc.videos_used
            }
        })

class PerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter'),
            "is_staff": user.is_staff,
            "plan_seleccionado": user.plan_seleccionado,
            "plan_activo": user.plan_activo,
        })

    def put(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        elif 'nombreInmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombreInmobiliaria']
            
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        elif 'logoUrl' in data:
            user.logo_url = data['logoUrl']
            
        agentes_input = data.get('agentes_asociados')
        if agentes_input is None:
            agentes_input = data.get('agentesAsociados')
            
        if agentes_input is not None:
            # Si el frontend envía un string en vez de un array JSON, lo parseamos
            import json
            if isinstance(agentes_input, str):
                try:
                    agentes_input = json.loads(agentes_input)
                except json.JSONDecodeError:
                    pass
            user.agentes_asociados = agentes_input
            
        if 'meta_access_token' in data:
            user.meta_access_token = data['meta_access_token']
        if 'meta_instagram_account_id' in data:
            user.meta_instagram_account_id = data['meta_instagram_account_id']
            
        user.save()
        return Response({
            "message": "Perfil actualizado exitosamente",
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "meta_access_token": getattr(user, 'meta_access_token', None),
            "meta_instagram_account_id": getattr(user, 'meta_instagram_account_id', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

from .services.instagram_service import publicar_post, publicar_story, publicar_carrusel
from django.conf import settings

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def publicar_instagram(request):
    try:
        data = request.data
        tipo = data.get('tipo', 'post')
        imagen_url = data.get('imagen_url', '')
        imagenes_urls = data.get('imagenes_urls', [])
        caption = data.get('caption', '')
        
        user = request.user
        access_token = user.meta_access_token or getattr(settings, 'META_ACCESS_TOKEN', '')
        account_id = user.meta_instagram_account_id or getattr(settings, 'META_INSTAGRAM_ACCOUNT_ID', '')
        
        if not access_token or not account_id:
            return Response({"success": False, "error": "Credenciales de Instagram no configuradas."}, status=status.HTTP_400_BAD_REQUEST)
            
        if tipo == 'post':
            result = publicar_post(imagen_url, caption, access_token, account_id)
        elif tipo == 'story':
            result = publicar_story(imagen_url, access_token, account_id)
        elif tipo == 'carrusel':
            result = publicar_carrusel(imagenes_urls, caption, access_token, account_id)
        else:
            return Response({"success": False, "error": "Tipo invalido (post/story/carrusel)"}, status=status.HTTP_400_BAD_REQUEST)
            
        if result.get('success'):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_carrusel(request):
    """Genera 5 imágenes de carrusel y un caption con Gemini."""
    try:
        user = request.user
        if not puede_generar(user, 'image'):
             return Response({
                "error": "limite_alcanzado", 
                "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
                "upgrade_url": "/precios"
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        fotos = data.get('fotosRecorrido', [])
        if not isinstance(fotos, list): fotos = []
        
        # Aseguramos tener 5 fotos (repetimos si es necesario)
        portada = data.get('portadaUrl')
        images_to_use = []
        if portada: images_to_use.append(portada)
        images_to_use.extend([f.get('url') if isinstance(f, dict) else f for f in fotos if f])
        
        # Si no hay imágenes, generamos slides de diseño puro (sin foto de fondo)
        # Pasamos None para que generate_social_image use fondo negro/degradado
        if not images_to_use:
            images_to_use = [None] * 5
        
        while len(images_to_use) < 5:
            images_to_use.append(images_to_use[len(images_to_use) % len(images_to_use)])
            
        slides_urls = []
        titles = [
            "Descubrí esta oportunidad única",
            "Espacios amplios y luminosos",
            "Detalles de categoría y confort",
            "Ubicación privilegiada en la ciudad",
            "Tu próximo hogar te espera"
        ]

        for i in range(5):
            slide_data = data.copy()
            slide_data['portadaUrl'] = images_to_use[i]
            
            image_stream = generate_social_image(slide_data, is_story=False, headline=titles[i])
            
            # Subir a Cloudinary
            try:
                print(f"[DEBUG] Subiendo slide {i+1} a Cloudinary...")
                image_stream.seek(0)
                cloud_response = cloudinary.uploader.upload(
                    image_stream.getvalue(),
                    folder=f"leadbook/carousels/{user.id}",
                    resource_type="image",
                    public_id=f"carousel_{user.id}_{int(time.time())}_{i}"
                )
                slides_urls.append(cloud_response['secure_url'])
                print(f"[DEBUG] Slide {i+1} subida OK: {cloud_response['secure_url']}")
            except Exception as cloud_err:
                print(f"[DEBUG] ERROR Cloudinary Slide {i+1}: {str(cloud_err)}")
                raise cloud_err

        # Generar Caption con Gemini (con fallback a Groq)
        prompt_text = f"Escribí un caption para un carrusel de Instagram de una propiedad: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Enfocado en vender el estilo de vida y llamar a la acción. Usá emojis y hashtags."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario digital.", agente=user)

        if user.is_authenticated:
            incrementar_uso(user, 'image')

        return Response({
            "slides": slides_urls,
            "caption": caption
        }, status=status.HTTP_200_OK)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_upload_avatar(request):
    import cloudinary.uploader
    try:
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=400)
        result = cloudinary.uploader.upload(file, folder='leadbook/avatars')
        return Response({'url': result['secure_url']})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


class OnboardingView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return self.put(request)

    def put(self, request):
        user = request.user
        data = request.data
        
        if 'nombre_inmobiliaria' in data:
            user.nombre_inmobiliaria = data['nombre_inmobiliaria']
        if 'logo_url' in data:
            user.logo_url = data['logo_url']
        if 'nicho' in data:
            user.nicho = data['nicho']
        if 'pais' in data:
            user.pais = data['pais']
            
        user.save()
        return Response({
            "email": user.email,
            "nombre": user.nombre,
            "nombre_inmobiliaria": getattr(user, 'nombre_inmobiliaria', None),
            "logo_url": getattr(user, 'logo_url', None),
            "nicho": getattr(user, 'nicho', None),
            "pais": getattr(user, 'pais', None),
            "agentes_asociados": getattr(user, 'agentes_asociados', []),
            "plan_nombre": getattr(user, 'plan_nombre', 'starter')
        }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def video_status(request, listado_id):
    try:
        from .models import Listado
        listado = Listado.objects.get(id=listado_id, agente=request.user)
        return Response({
            "status": listado.video_status,
            "video_url": listado.video_url
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)

class ListadosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devuelve todos los listados del usuario logueado"""
        listados = Listado.objects.filter(agente=request.user)
        data = []
        for listado in listados:
            data.append({
                'id': listado.id,
                'titulo': listado.titulo,
                'tipo_propiedad': listado.tipo_propiedad,
                'ciudad': listado.ciudad,
                'precio': listado.precio,
                'creado_en': listado.creado_en,
                'videos_creados': listado.videos_creados,
                'datos': listado.datos
            })
        return Response(data)

    def post(self, request):
        from .models import Agent
        user = Agent.objects.get(id=request.user.id)
        
        # Verificar limites de plan (Nuevo sistema)
        puede, usados, maximo = verificar_limite_plan(user)
        if not puede:
            return Response({
                "error": f"Alcanzaste el límite de tu plan ({usados}/{maximo} listados este mes). Actualizá tu plan para continuar.",
                "limite_alcanzado": True,
                "usados": usados,
                "maximo": maximo
            }, status=403)
            
        data = request.data
        
        # Permitir tanto JSON plano como objeto anidado 'formData' (React)
        payload = data.get('formData') if isinstance(data, dict) and 'formData' in data else data
        if not isinstance(payload, dict):
            payload = {}
            
        if not puede_generar(user, 'property'):
            return Response({"error": "limite_alcanzado", "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción."}, status=status.HTTP_403_FORBIDDEN)
        
        titulo = payload.get('titulo') or f"Propiedad en {payload.get('ciudad', 'Desconocida')}"
        tipo_propiedad = payload.get('tipoPropiedad', payload.get('tipo_propiedad', ''))
        ciudad = payload.get('ciudad', '')
        precio = str(payload.get('precio', ''))
        
        # Guardamos en datos el payload limpio
        listado = Listado.objects.create(
            agente=user,
            titulo=titulo,
            tipo_propiedad=tipo_propiedad,
            ciudad=ciudad,
            precio=precio,
            datos=payload
        )
        
        incrementar_uso(user, 'property')
        
        return Response({
            "mensaje": "Listado guardado", 
            "id": listado.id,
            "titulo": listado.titulo
        }, status=status.HTTP_201_CREATED)

class ListadoDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            listado = Listado.objects.get(pk=pk)
        except Listado.DoesNotExist:
            return Response({"error": "Listado no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            
        if listado.agente.id != request.user.id:
            return Response({"error": "No tienes permiso para eliminar este listado"}, status=status.HTTP_403_FORBIDDEN)
            
        listado.delete()
        return Response({"mensaje": "Listado eliminado"}, status=status.HTTP_200_OK)


# ---- Celery task + endpoint para generación de video ----
from celery import shared_task
from .services.video_service import generar_video_listado

@shared_task
def generar_video_task(listado_id):
    """Genera video con Remotion para el listado"""
    try:
        success = generar_video_listado(listado_id)
        if success:
            from .models import Listado
            from .plan_utils import registrar_uso
            listado = Listado.objects.get(id=listado_id)
            registrar_uso(listado.agente, 'video')
            return {"status": "completado", "id": listado_id}
        else:
            return {"status": "fallido", "id": listado_id}
    except Exception as e:
        return {"error": str(e)}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_video(request, pk):
    """Dispara la generación de video asincronamente"""
    try:
        listado = Listado.objects.get(id=pk, agente=request.user)
        # Dispara tarea Celery
        generar_video_task.delay(pk)
        return Response({
            "status": "generando",
            "mensaje": "El video se está generando en segundo plano",
            "id": pk
        })
    except Listado.DoesNotExist:
        return Response({"error": "Listado no encontrado"}, status=404)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_pdf(request):
    if not puede_generar(request.user, 'property'):
        return Response({
            "error": "limite_alcanzado",
            "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
            "upgrade_url": "/precios"
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

        # ─── Helper: convierte base64 o URL en path local para xhtml2pdf ────
        temp_files = []

        def save_temp_image(b64_or_url):
            """
            Acepta base64 (con o sin header data:image/...) o URL http/https.
            Guarda en /tmp/ y retorna el path absoluto para xhtml2pdf.
            Retorna None si falla.
            """
            if not b64_or_url or not isinstance(b64_or_url, str):
                return None
            val = b64_or_url.strip()
            # Si es URL directa, devolverla tal cual (xhtml2pdf puede fetchearla)
            if val.startswith('http://') or val.startswith('https://'):
                return val
            # Si es base64 (con o sin header data:...)
            try:
                if ',' in val and val.startswith('data:'):
                    val = val.split(',', 1)[1]
                val += '=' * ((4 - len(val) % 4) % 4)
                img_data = base64.b64decode(val)
                # Detectar formato por magic bytes
                ext = 'jpg'
                if img_data[:8] == b'\x89PNG\r\n\x1a\n':
                    ext = 'png'
                elif img_data[:2] == b'\xff\xd8':
                    ext = 'jpg'
                elif img_data[:6] in (b'GIF87a', b'GIF89a'):
                    ext = 'gif'
                filename = os.path.join(tempfile.gettempdir(), f"lb_{uuid.uuid4().hex}.{ext}")
                with open(filename, 'wb') as f:
                    f.write(img_data)
                temp_files.append(filename)
                return filename
            except Exception as e:
                print(f"[PDF] Error decodificando imagen base64: {e}")
                return None

        def link_callback(uri, rel):
            """Permite a xhtml2pdf leer archivos locales en /tmp/ y URLs externas."""
            if os.path.isabs(uri) and os.path.exists(uri):
                return uri
            if uri.startswith('file://'):
                path = uri[7:]
                if os.path.exists(path):
                    return path
            if uri.startswith('http://') or uri.startswith('https://'):
                return uri
            return uri

        # ─── Extraer campos normalizados ──────────────────────────────────────
        tipo_propiedad   = data.get('tipoPropiedad', data.get('tipo_propiedad', 'Propiedad'))
        ciudad           = data.get('ciudad', '')
        precio           = str(data.get('precio', ''))
        moneda           = data.get('moneda', 'USD')
        operacion        = data.get('operacion', 'Venta')
        recamaras        = data.get('recamaras', '')
        banos            = data.get('banos', '')
        superficie_cubierta = data.get('superficieCubierta', data.get('superficieConstruida', ''))
        superficie_total = data.get('superficieTotal', data.get('superficieTerreno', ''))
        estacionamientos = data.get('estacionamientos', '')
        amenidades       = data.get('amenidades', [])
        if not isinstance(amenidades, list):
            amenidades = []

        # Datos de agente / agencia
        agente_nombre = data.get('agenteNombre', '') or request.user.nombre or ''
        agente_email = data.get('agenteEmail', '') or request.user.email or ''
        agencia_nombre = data.get('agenciaNombre', '') or request.user.nombre_inmobiliaria or 'LeadBook'
        agente_telefono = data.get('agenteTelefono', '') or request.user.telefono or ''

        # ─── Procesar imágenes (base64 Y URLs) ───────────────────────────────
        portada_url = save_temp_image(data.get('portadaUrl', '')) or ''
        logo_url    = save_temp_image(data.get('logoAgenciaUrl', data.get('logo_url', ''))) or ''

        fotos_raw = data.get('fotosRecorrido', [])
        fotos_recorrido = []
        for foto in fotos_raw:
            if isinstance(foto, dict):
                foto_val = foto.get('url') or foto.get('base64') or ''
            else:
                foto_val = foto or ''
            path = save_temp_image(foto_val)
            if path:
                fotos_recorrido.append(path)

        # ─── Procesar escenas si las hay ─────────────────────────────────────
        escenas = data.get('escenas', [])
        if isinstance(escenas, list):
            escenas_procesadas = []
            for escena in escenas:
                if isinstance(escena, dict) and escena.get('fotoUrl'):
                    path = save_temp_image(escena['fotoUrl'])
                    escena = {**escena, 'fotoUrl': path}
                escenas_procesadas.append(escena)
            data['escenas'] = escenas_procesadas

        # ─── Descripción IA (si no viene en el payload) ──────────────────────
        descripcion = data.get('descripcion', '')
        if not descripcion:
            amenidades_str = ', '.join(amenidades) if amenidades else 'no especificadas'
            prompt_desc = f"""Generá una descripción inmobiliaria profesional de 2 párrafos para:
{tipo_propiedad} en {operacion} en {ciudad}.
Precio: {moneda} {precio}.
Recámaras: {recamaras}. Baños: {banos}.
Superficie construida: {superficie_cubierta}m².
Terreno: {superficie_total}m².
Amenidades: {amenidades_str}.

Párrafo 1: Descripción general de la propiedad y ubicación (3-4 oraciones).
Párrafo 2: Destacar amenidades y estilo de vida que ofrece (3-4 oraciones).
Tono elegante y persuasivo. Solo los 2 párrafos, sin títulos ni bullets."""
            descripcion = smart_call(prompt_desc, system_prompt="Sos un copywriter inmobiliario de lujo. Escribís en español, con tono sofisticado y persuasivo.", agente=request.user)
            if descripcion:
                from .plan_utils import registrar_uso
                registrar_uso(request.user, 'ai')
            if not descripcion:
                descripcion = f"Esta {tipo_propiedad} en {operacion} ubicada en {ciudad} representa una oportunidad única en el mercado inmobiliario. Con una superficie de {superficie_cubierta}m² y acabados de primera calidad, ofrece el equilibrio perfecto entre confort y diseño.\n\nSu distribución inteligente permite aprovechar cada espacio al máximo, mientras que las amenidades incluidas elevan la experiencia de vida. Precio: {moneda} {precio}. No pierda la oportunidad de conocerla."


        # QR Code del agente
        qr_data    = f"Tel: {agente_telefono} | Email: {agente_email} | {agencia_nombre}"
        qr_base64_ = generar_qr_base64(qr_data)

        # ─── Construir contexto del template ─────────────────────────────────
        context = {
            'tipo_propiedad':     tipo_propiedad,
            'ciudad':             ciudad,
            'precio':             precio,
            'moneda':             moneda,
            'operacion':          operacion,
            'recamaras':          recamaras,
            'banos':              banos,
            'superficie_cubierta': superficie_cubierta,
            'superficie_total':   superficie_total,
            'estacionamientos':   estacionamientos,
            'descripcion':        descripcion,
            'amenidades':         amenidades,
            'portada_url':        portada_url,
            'fotos_recorrido':    fotos_recorrido,
            'logo_url':           logo_url,
            'agente_nombre':      agente_nombre,
            'agente_telefono':    agente_telefono,
            'agente_email':       agente_email,
            'agencia_nombre':     agencia_nombre,
            'qr_code':            qr_base64_,
        }

        print(f"\n[PDF] Generando para {tipo_propiedad} en {ciudad} | portada: {bool(portada_url)} | fotos: {len(fotos_recorrido)} | QR: sí")

        template = get_template('pdf/property_brochure.html')
        html     = template.render(context)

        result = BytesIO()
        pdf = pisa.pisaDocument(
            BytesIO(html.encode('UTF-8')),
            result,
            link_callback=link_callback
        )

        # ─── Limpiar archivos temporales de imágenes ─────────────────────────
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        if not pdf.err:
            pdf_uuid = uuid.uuid4().hex
            pdf_path = os.path.join(tempfile.gettempdir(), f"lb_pdf_{pdf_uuid}.pdf")
            with open(pdf_path, 'wb') as f:
                f.write(result.getvalue())

            from .models import Listado
            listado, created = Listado.objects.get_or_create(
                agente=request.user,
                tipo_propiedad=tipo_propiedad,
                ciudad=ciudad,
                defaults={
                    'titulo': data.get('titulo') or f"{tipo_propiedad} en {ciudad}",
                    'precio': precio,
                    'datos': data
                }
            )

            return Response({"url": f"/api/pdf/{pdf_uuid}/", "listado_id": listado.id}, status=status.HTTP_200_OK)

        return Response({"error": "Error al generar el PDF"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        import traceback
        return Response({"error": str(e), "trace": traceback.format_exc()}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_post(request):
    """Genera imagen POST y la sube a Cloudinary"""
    try:
        if not puede_generar(request.user, 'image'):
            return Response({
                "error": "limite_alcanzado", 
                "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
                "upgrade_url": "/precios"
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        image_stream = generate_social_image(data, is_story=False)

        # Generar caption con IA (con fallback)
        prompt_text = f"Escribí un caption para Instagram sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 2200 caracteres, usá hashtags y emojis."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)

        # Intentar subir a Cloudinary; si falla, devolver base64
        try:
            image_stream.seek(0)
            cloud_response = cloudinary.uploader.upload(
                image_stream,
                folder="leadbook/posts",
                resource_type="image",
                public_id=f"post_{request.user.id}_{int(time.time())}"
            )
            img_url = cloud_response['secure_url']
            public_id = cloud_response.get('public_id')
        except Exception as cloud_err:
            print(f"[Cloudinary] Error subiendo imagen: {cloud_err} — devolviendo base64")
            image_stream.seek(0)
            img_base64 = base64.b64encode(image_stream.getvalue()).decode('utf-8')
            img_url = f"data:image/png;base64,{img_base64}"
            public_id = None

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "public_id": public_id,
            "caption": caption,
            "texto": caption
        }, status=status.HTTP_200_OK)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_imagen_story(request):
    """Genera imagen Story, la sube a Cloudinary y devuelve también Base64 como respaldo"""
    try:
        if not puede_generar(request.user, 'image'):
            return Response({
                "error": "limite_alcanzado",
                "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
                "upgrade_url": "/precios"
            }, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        image_stream = generate_social_image(data, is_story=True)

        prompt_text = f"Escribí un texto para Instagram Story sobre esta propiedad en {data.get('operacion', 'venta')}: {data.get('tipoPropiedad', 'Propiedad')} en {data.get('ciudad', '')} por {data.get('precio', '')}. Máximo 500 caracteres, enfocado en llamar la atención rápido."
        caption = smart_call(prompt_text, system_prompt="Sos un experto en marketing inmobiliario para redes sociales.", agente=request.user)

        # Intentar subir a Cloudinary; si falla, devolver base64
        try:
            image_stream.seek(0)
            cloud_response = cloudinary.uploader.upload(
                image_stream,
                folder="leadbook/stories",
                resource_type="image",
                public_id=f"story_{request.user.id}_{int(time.time())}"
            )
            img_url   = cloud_response['secure_url']
            public_id = cloud_response.get('public_id')
            # También generamos base64 por si el frontend lo necesita de inmediato
            image_stream.seek(0)
            img_base64 = base64.b64encode(image_stream.getvalue()).decode('utf-8')
        except Exception as cloud_err:
            print(f"[Cloudinary] Error subiendo story: {cloud_err} — devolviendo base64")
            image_stream.seek(0)
            img_base64 = base64.b64encode(image_stream.getvalue()).decode('utf-8')
            img_url   = f"data:image/png;base64,{img_base64}"
            public_id = None

        if request.user.is_authenticated:
            incrementar_uso(request.user, 'image')
            from .plan_utils import registrar_uso
            registrar_uso(request.user, 'image')

        return Response({
            "url": img_url,
            "img_base64": img_base64,
            "public_id": public_id,
            "caption": caption,
            "texto": caption
        }, status=status.HTTP_200_OK)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": str(e), "detalle": traceback.format_exc()}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_email(request):
    try:
        if not puede_generar(request.user, 'ai'):
            return Response({
                "error": "limite_alcanzado", 
                "mensaje": "Superaste el límite de tu plan. Actualizá tu suscripción.",
                "upgrade_url": "/precios"
            }, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        prompt_text = f"""
Redacta el cuerpo de un email profesional para ofrecer esta propiedad a un cliente interesado.
Tipo: {data.get('tipoPropiedad', 'Propiedad')}
Ciudad: {data.get('ciudad', '')}
Precio: {data.get('precio', '')}
Operación: {data.get('operacion', 'venta')}
Agente: {data.get('agenteNombre', '')}
Agencia: {data.get('agenciaNombre', '')}

Devuelve **ÚNICAMENTE** y estrictamente un objeto JSON válido (sin Markdown, sin ````json) con la siguiente estructura y nada más:
{{
  "asunto": "el asunto sugerido del correo",
  "html": "el cuerpo del email en una línea, todo en codigo html inline, usando etiquetas como <br>, <strong> (sin los tags <html>, <head> o <body>, solo contenido directo)",
  "texto_plano": "el equivalente en texto plano básico pero atractivo"
}}
"""
        json_str = smart_call(prompt_text, system_prompt="Sos un asistente técnico que solo responde en JSON.", agente=request.user)
        
        if json_str is None:
            json_str = '{"asunto": "Propiedad destacada", "html": "<div>Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles.</div>", "texto_plano": "Tenemos una excelente oportunidad para vos. Contestá a este mail para más detalles."}'
            
        import json
        try:
            parsed = json.loads(json_str)
        except:
            if '```json' in json_str:
                json_str = json_str.split('```json')[1].split('```')[0].strip()
                parsed = json.loads(json_str)
            else:
                parsed = {
                    "asunto": "Propiedad destacada",
                    "html": "<div>Propiedad disponible</div>",
                    "texto_plano": "Propiedad disponible"
                }
                
        if request.user.is_authenticated:
            incrementar_uso(request.user, 'ai')
            
        return Response(parsed, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def serve_pdf_file(request, uuid_str):
    """Sirve el PDF generado. Soporta ambos prefijos (lb_pdf_ y pdf_) para compatibilidad."""
    from django.http import FileResponse
    # Buscar con nuevo prefijo primero, luego el legacy
    for prefix in ['lb_pdf_', 'pdf_']:
        pdf_path = os.path.join(tempfile.gettempdir(), f"{prefix}{uuid_str}.pdf")
        if os.path.exists(pdf_path):
            response = FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename="ficha-leadbook.pdf"'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Access-Control-Allow-Origin'] = '*'
            response['Content-Security-Policy'] = "frame-ancestors *"
            return response
    return Response({"error": "PDF no encontrado"}, status=status.HTTP_404_NOT_FOUND)

import mercadopago
from decouple import config
from datetime import datetime, timedelta

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mp_checkout(request):
    plan = request.data.get('plan')
    ciclo = request.data.get('ciclo', 'monthly')
    
    planes = {
        'starter': {'nombre': 'LeadBook Starter', 'precio_mensual': 70000, 'precio_anual': 52500},
        'pro': {'nombre': 'LeadBook Pro', 'precio_mensual': 161000, 'precio_anual': 120750},
        'scale': {'nombre': 'LeadBook Scale', 'precio_mensual': 270000, 'precio_anual': 202500},
        'business': {'nombre': 'LeadBook Business', 'precio_mensual': 542000, 'precio_anual': 406500},
    }
    
    if plan not in planes:
        return Response({"error": "Plan inválido"}, status=400)
    
    plan_data = planes[plan]
    precio = plan_data['precio_anual'] if ciclo == 'annual' else plan_data['precio_mensual']
    nombre = f"{plan_data['nombre']} ({'Anual' if ciclo == 'annual' else 'Mensual'})"
    
    sdk = mercadopago.SDK(config('MP_ACCESS_TOKEN'))
    frontend_url = config('FRONTEND_URL', default='https://front-saas-production-1e0c.up.railway.app')
    
    preference_data = {
        "items": [{
            "id": f"{plan}_{ciclo}",
            "title": nombre,
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(precio)
        }],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": f"{frontend_url}/pago-exitoso?plan={plan}",
            "failure": f"{frontend_url}/pago-fallido",
            "pending": f"{frontend_url}/pago-pendiente"
        },
        "auto_return": "approved",
        "external_reference": f"{request.user.id}|{plan}",
    }
    
    preference_response = sdk.preference().create(preference_data)
    
    if preference_response["status"] == 201:
        return Response({
            "init_point": preference_response["response"]["init_point"],
            "preference_id": preference_response["response"]["id"]
        })
    else:
        print(f"MP Error: {preference_response}")
        return Response({"error": "Error al crear preferencia de pago"}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def mp_webhook(request):
    topic = request.data.get('type')
    data_id = request.data.get('data', {}).get('id')
    
    if not data_id:
        return Response({"status": "ok"})
    
    try:
        import requests as req
        headers = {"Authorization": f"Bearer {config('MP_ACCESS_TOKEN')}"}
        
        if topic == 'payment':
            response = req.get(
                f"https://api.mercadopago.com/v1/payments/{data_id}",
                headers=headers
            )
        elif topic == 'subscription_preapproval':
            response = req.get(
                f"https://api.mercadopago.com/preapproval/{data_id}",
                headers=headers
            )
        else:
            return Response({"status": "ok"})
        
        data = response.json()
        status = data.get("status")
        external_ref = data.get("external_reference", "")
        
        if status in ["approved", "authorized"] and "|" in external_ref:
            user_id, plan = external_ref.split("|", 1)
            from .models import Agent
            try:
                agent = Agent.objects.get(id=int(user_id))
                agent.plan_nombre = plan
                agent.plan_activo = True
                agent.save()
                print(f"[MP] Plan actualizado: user {user_id} → {plan}")
            except Agent.DoesNotExist:
                print(f"[MP] Usuario no encontrado: {user_id}")
    except Exception as e:
        print(f"[MP] Error webhook: {e}")
    
    return Response({"status": "ok"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def plan_status(request):
    user = request.user
    return Response({
        "plan_nombre": user.plan_nombre,
        "plan_activo": user.plan_activo,
        "plan_seleccionado": user.plan_seleccionado,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seleccionar_plan_free(request):
    user = request.user
    user.plan_nombre = 'free'
    user.plan_activo = True
    user.plan_seleccionado = True
    user.save()
    return Response({"ok": True, "plan": "free"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_plan_info_mp(request):
    from .plan_utils import LIMITES
    from .models import UsageLog
    agent = request.user
    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])
    now = timezone.now()
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    listados_mes = Listado.objects.filter(
        agente=agent,
        creado_en__year=now.year, creado_en__month=now.month
    ).count()
    return Response({
        "plan_nombre": plan,
        "mp_public_key": settings.MP_PUBLIC_KEY,
        "uso_actual": {
            "properties_used": listados_mes,
            "ai_used": ai_used,
            "images_used": images_used,
            "videos_used": videos_used
        },
        "limites": {
            "properties_per_month": limites['properties'],
            "ai_generations": limites['ai'],
            "image_generations": limites['images'],
            "video_generations": limites['videos']
        }
    })


import secrets
import hashlib
from django.core.mail import send_mail
from datetime import timedelta


@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp(request):
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)

    recent = OTPCode.objects.filter(
        email=email,
        created_at__gte=timezone.now() - timedelta(minutes=15)
    ).count()
    if recent >= 3:
        return Response({"error": "Demasiados intentos. Esperá 15 minutos."}, status=429)

    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)

    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at
    )

    # Envío del OTP robusto: intenta Celery asíncrono; si falla o no hay broker,
    # cae a envío síncrono en el request. Así funciona en Railway sin worker.
    import sys
    from django.conf import settings

    # Log de diagnóstico MUY visible en Railway
    print(f"[EMAIL] Intentando enviar a {email}", flush=True)
    print(
        f"[EMAIL] DIAG backend={settings.EMAIL_BACKEND} "
        f"host={settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
        f"user_set={bool(settings.EMAIL_HOST_USER)} "
        f"pass_set={bool(settings.EMAIL_HOST_PASSWORD)} "
        f"eager={getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True)}",
        flush=True,
    )
    sys.stdout.flush()

    sent_mode = None
    try:
        from .tasks import send_otp_email_async

        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            # Eager: ejecutar la task sincronamente sin broker
            send_otp_email_async(email, code)
            sent_mode = 'sync-eager'
        else:
            # Intentar enviar al broker Celery (Redis)
            send_otp_email_async.delay(email, code)
            sent_mode = 'celery-queued'
        print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
    except Exception as e_celery:
        # Broker caído, sin Redis, o cualquier otro problema: fallback sync
        print(f"[EMAIL] ERROR al enviar (celery path): {type(e_celery).__name__}: {str(e_celery)}", flush=True)
        print(f"[EMAIL] Intentando fallback sync a {email}", flush=True)
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
            sent_mode = 'sync-fallback'
            print(f"[EMAIL] Enviado correctamente a {email} (mode={sent_mode})", flush=True)
        except Exception as e_sync:
            print(f"[EMAIL] ERROR al enviar: {str(e_sync)}", flush=True)
            import traceback
            traceback.print_exc()
            sent_mode = f'error:{type(e_sync).__name__}'

    sys.stdout.flush()
    return Response({"mensaje": "Código enviado", "email": email, "_mode": sent_mode})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('code', '').strip()

    if not email or not code:
        return Response({"error": "Email y código requeridos"}, status=400)

    otp = OTPCode.objects.filter(
        email=email,
        verified=False
    ).order_by('-created_at').first()

    if not otp:
        return Response({"error": "Código inválido o ya utilizado"}, status=400)

    if otp.is_expired():
        return Response({"error": "Código expirado. Pedí uno nuevo."}, status=400)

    if otp.attempts >= 5:
        return Response({"error": "Demasiados intentos. Pedí un nuevo código."}, status=429)

    # Verificar hash ANTES de incrementar attempts para no penalizar el intento correcto
    code_hash = OTPCode.hash_code(code)
    if otp.code_hash != code_hash:
        otp.attempts += 1
        otp.save()
        intentos_restantes = 5 - otp.attempts
        return Response({"error": f"Código incorrecto. {intentos_restantes} intentos restantes."}, status=400)

    # Código correcto
    otp.verified = True
    otp.save()

    return Response({"verificado": True, "email": email})


@api_view(['POST'])
@permission_classes([AllowAny])
def recuperar_password(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({"error": "Email requerido"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "No encontramos una cuenta con ese email"}, status=404)
    
    import secrets
    import hashlib
    from datetime import timedelta
    from django.utils import timezone
    
    code = str(secrets.randbelow(900000) + 100000)
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    expires_at = timezone.now() + timedelta(minutes=10)
    
    OTPCode.objects.create(
        email=email,
        code_hash=code_hash,
        expires_at=expires_at,
        tipo="recuperacion"
    )

    # Envío robusto con fallback síncrono (idéntico a send_otp)
    try:
        from django.conf import settings
        from .tasks import send_otp_email_async
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', True):
            send_otp_email_async(email, code)
        else:
            send_otp_email_async.delay(email, code)
    except Exception as e_celery:
        print(f"[OTP-RECOV] Celery falló ({e_celery}). Fallback sync.")
        try:
            from .tasks import send_otp_email_async as _send_sync
            _send_sync(email, code)
        except Exception as e_sync:
            print(f"[OTP-RECOV] ERROR envío síncrono: {e_sync}")

    return Response({"mensaje": "Código enviado", "email": email}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
def confirmar_recuperacion(request):
    from .models import Agent
    email = request.data.get('email', '').strip().lower()
    code = request.data.get('codigo', '').strip()
    nueva_password = request.data.get('nueva_password', '')
    
    if not email or not code or not nueva_password:
        return Response({"error": "Faltan datos requeridos"}, status=400)
    
    otp = OTPCode.objects.filter(
        email=email,
        tipo="recuperacion",
        verified=False
    ).order_by('-created_at').first()
    
    if not otp:
        return Response({"error": "Código inválido"}, status=400)
    if otp.is_expired():
        return Response({"error": "Código expirado"}, status=400)
    if not otp.is_valid(code):
        return Response({"error": "Código incorrecto"}, status=400)
    
    user = Agent.objects.filter(email=email).first()
    if not user:
        return Response({"error": "Usuario no encontrado"}, status=404)
    
    user.set_password(nueva_password)
    user.save()
    
    otp.verified = True
    otp.save()
    
    return Response({"mensaje": "Contraseña actualizada correctamente"}, status=200)


@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_terminos(request):
    """Devuelve los Términos y Condiciones vigentes"""
    try:
        terminos = TerminosCondiciones.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = TerminosCondicionesSerializer(terminos)
        return Response(serializer.data)
    except TerminosCondiciones.DoesNotExist:
        return Response({"error": "Términos no disponibles"}, status=404)

@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_politica_privacidad(request):
    """Devuelve la Política de Privacidad vigente"""
    try:
        politica = PoliticaPrivacidad.objects.filter(activo=True).latest('fecha_actualizacion')
        serializer = PoliticaPrivacidadSerializer(politica)
        return Response(serializer.data)
    except PoliticaPrivacidad.DoesNotExist:
        return Response({"error": "Política de privacidad no disponible"}, status=404)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def amenidades_presets(request):
    from .models import AmenidadPreset
    agente = request.user
    if request.method == 'GET':
        presets = AmenidadPreset.objects.filter(agente=agente)
        return Response({'presets': [p.nombre for p in presets]})
    
    if request.method == 'POST':
        nombre = request.data.get('nombre', '').strip()
        if not nombre:
            return Response({'error': 'Nombre requerido'}, status=400)
        preset, created = AmenidadPreset.objects.get_or_create(
            agente=agente, nombre=nombre
        )
        return Response({
            'nombre': preset.nombre, 
            'created': created
        }, status=201 if created else 200)

from django.utils import timezone
from datetime import timedelta

ADMIN_KEY = config('ADMIN_KEY', default='')

def check_admin(request):
    return request.headers.get('X-Admin-Key') == ADMIN_KEY

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_stats(request):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    ahora = timezone.now()
    hoy = ahora - timedelta(hours=24)
    semana = ahora - timedelta(days=7)
    
    from .models import Agent, Listado
    
    total = Agent.objects.count()
    activos_hoy = Agent.objects.filter(
        last_login__gte=hoy).count()
    activos_semana = Agent.objects.filter(
        last_login__gte=semana).count()
    nuevos_hoy = Agent.objects.filter(
        fecha_registro__gte=hoy).count()
    nuevos_semana = Agent.objects.filter(
        fecha_registro__gte=semana).count()
    
    distribucion = {}
    for plan in ['free','starter','pro','scale','business']:
        distribucion[plan] = Agent.objects.filter(
            plan_nombre=plan).count()
    
    try:
        total_listados = Listado.objects.count()
    except:
        total_listados = 0
    
    return Response({
        "total_usuarios": total,
        "activos_hoy": activos_hoy,
        "activos_semana": activos_semana,
        "nuevos_hoy": nuevos_hoy,
        "nuevos_semana": nuevos_semana,
        "distribucion_planes": distribucion,
        "total_listados": total_listados
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuarios(request):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    try:
        from .models import Agent, Listado
        incluir_eliminados = request.query_params.get('incluir_eliminados') in ('1', 'true', 'True')
        agentes_qs = Agent.objects.all().order_by('-fecha_registro')
        if not incluir_eliminados:
            try:
                agentes_qs = agentes_qs.filter(eliminado_en__isnull=True)
            except Exception as e:
                import sys
                print(f"[admin_usuarios] WARN filter eliminado_en fallo: {e}", file=sys.stderr, flush=True)
        
        resultado = []
        for a in agentes_qs:
            try:
                listados = Listado.objects.filter(agente=a).count()
            except:
                listados = 0
            
            resultado.append({
                "id": a.id,
                "email": a.email,
                "nombre": getattr(a, 'nombre', ''),
                "agencia": getattr(a, 'agencia', '') or getattr(a, 'nombre_inmobiliaria', ''),
                "plan_nombre": getattr(a, 'plan_nombre', 'free'),
                "plan_activo": getattr(a, 'plan_activo', True),
                "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
                "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
                "listados_count": listados,
                "pais": getattr(a, 'pais', ''),
                "nicho": getattr(a, 'nicho', ''),
            })
        return Response({"usuarios": resultado})
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return Response({"error": "internal", "detail": str(e)[:300]}, status=500)

@api_view(['DELETE'])
@permission_classes([AllowAny])
def admin_eliminar_usuario(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.delete()
        return Response({"mensaje": "Usuario eliminado"})
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['POST'])
@permission_classes([AllowAny])
def admin_cambiar_plan(request, user_id):
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    
    nuevo_plan = request.data.get('plan')
    planes_validos = ['free','starter','pro','scale','business']
    
    if nuevo_plan not in planes_validos:
        return Response({"error": "Plan inválido"}, status=400)
    
    from .models import Agent
    try:
        agent = Agent.objects.get(id=user_id)
        agent.plan_nombre = nuevo_plan
        agent.save()
        return Response({
            "mensaje": f"Plan actualizado a {nuevo_plan}",
            "plan": nuevo_plan
        })
    except Agent.DoesNotExist:
        return Response({"error": "No encontrado"}, status=404)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    agent = request.user
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from .models import Listado, UsageLog
    from .plan_utils import LIMITES

    listados = Listado.objects.filter(agente=agent)
    listados_este_mes = listados.filter(creado_en__gte=start_of_month).count()
    total_generados = listados.count()
    videos_creados = listados.aggregate(total=Sum('videos_creados'))['total'] or 0

    listados_recientes = list(listados.order_by('-creado_en')[:5].values(
        'id', 'titulo', 'tipo_propiedad', 'ciudad', 'precio', 'creado_en'
    ))

    plan = agent.plan_nombre or 'free'
    limites = LIMITES.get(plan, LIMITES['free'])

    # Uso actual del mes (via UsageLog)
    ai_used = UsageLog.objects.filter(
        agent=agent, tipo='ai',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    images_used = UsageLog.objects.filter(
        agent=agent, tipo='image',
        fecha__year=now.year, fecha__month=now.month
    ).count()
    videos_used = UsageLog.objects.filter(
        agent=agent, tipo='video',
        fecha__year=now.year, fecha__month=now.month
    ).count()

    return Response({
        'nombre_inmobiliaria': getattr(agent, 'nombre_inmobiliaria', None),
        'logo_url': getattr(agent, 'logo_url', None),
        'listados_este_mes': listados_este_mes,
        'total_generados': total_generados,
        'videos_creados': videos_creados,
        'conexiones_activas': 0,
        'listados_recientes': listados_recientes,
        'plan': plan,
        'plan_limites': {
            'properties_per_month': limites['properties'],
            'ai_generations': limites['ai'],
            'image_generations': limites['images'],
            'video_generations': limites['videos'],
            'branding': plan not in ('free',),
        },
        'uso_actual': {
            'properties_used': listados_este_mes,
            'ai_used': ai_used,
            'images_used': images_used,
            'videos_used': videos_used,
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_listados(request):
    """Todos los listados del sistema"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Listado
    listados = Listado.objects.select_related('agente').order_by('-creado_en')[:100]
    data = [{
        "id": l.id,
        "titulo": l.titulo,
        "tipo": l.tipo_propiedad,
        "ciudad": l.ciudad,
        "precio": str(l.precio) if l.precio else None,
        "agente_email": l.agente.email,
        "agente_nombre": l.agente.nombre,
        "video_status": l.video_status,
        "creado_en": l.creado_en.strftime('%Y-%m-%d %H:%M') if l.creado_en else ''
    } for l in listados]
    return Response({"listados": data, "total": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_assets(request):
    """Stats de assets generados"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import GeneratedAsset
    total = GeneratedAsset.objects.count()
    por_tipo = {}
    for tipo in ['PDF', 'VIDEO', 'EMAIL', 'SOCIAL']:
        por_tipo[tipo] = GeneratedAsset.objects.filter(asset_type=tipo).count()
    por_status = {}
    for status in ['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED']:
        por_status[status] = GeneratedAsset.objects.filter(status=status).count()
    return Response({
        "total": total,
        "por_tipo": por_tipo,
        "por_status": por_status
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_pagos(request):
    """Historial de pagos/planes"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent
    agentes_pagos = Agent.objects.exclude(
        plan_nombre='free'
    ).order_by('-fecha_registro')
    data = [{
        "email": a.email,
        "nombre": a.nombre,
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "mp_customer_id": a.mp_customer_id or '',
        "mp_subscription_id": a.mp_subscription_id or '',
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d') if a.fecha_registro else ''
    } for a in agentes_pagos]
    return Response({"pagos": data, "total_pagos": len(data)})

@api_view(['GET'])
@permission_classes([AllowAny])
def admin_usuario_detalle(request, user_id):
    """Detalle completo de un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    from .models import Agent, Listado
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    listados = Listado.objects.filter(agente=a).order_by('-creado_en')
    return Response({
        "id": a.id,
        "email": a.email,
        "nombre": a.nombre,
        "agencia": a.agencia or '',
        "telefono": a.telefono or '',
        "pais": a.pais or '',
        "nicho": a.nicho or '',
        "plan": a.plan_nombre,
        "plan_activo": a.plan_activo,
        "is_active": a.is_active,
        "fecha_registro": a.fecha_registro.strftime('%Y-%m-%d %H:%M') if a.fecha_registro else '',
        "last_login": a.last_login.strftime('%Y-%m-%d %H:%M') if a.last_login else 'Nunca',
        "total_listados": listados.count(),
        "listados_recientes": [{
            "titulo": l.titulo,
            "tipo": l.tipo_propiedad,
            "ciudad": l.ciudad,
            "creado_en": l.creado_en.strftime('%Y-%m-%d') if l.creado_en else ''
        } for l in listados[:10]]
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def admin_suspender_usuario(request, user_id):
    """Suspender o reactivar un usuario"""
    if not check_admin(request):
        return Response({"error": "Forbidden"}, status=403)
    if request.method != 'POST':
        return Response({"error": "Method not allowed"}, status=405)
    from .models import Agent
    try:
        a = Agent.objects.get(id=user_id)
    except Agent.DoesNotExist:
        return Response({"error": "Usuario no encontrado"}, status=404)
    a.is_active = not a.is_active
    a.save()
    estado = "suspendido" if not a.is_active else "reactivado"
    return Response({"ok": True, "estado": estado, "is_active": a.is_active})

import requests as http_requests

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def conexiones_init(request):
    """
    Crea perfil en UploadPost para el usuario y devuelve 
    la URL segura para conectar sus redes sociales.
    """
    import traceback, sys
    try:
        from django.conf import settings
        from api.pool_manager import get_api_key
        
        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_init] user={user.email} username={username}", flush=True)
        
        api_key = get_api_key(user, 'uploadpost')
        
        if not api_key:
            print(f"[conexiones_init] No hay API key de uploadpost para {user.email}. Plan={getattr(user, 'plan_nombre', 'free')}", flush=True)
            return Response({
                "success": False,
                "error": "No hay cuentas disponibles en el pool"
            }, status=400)
        
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        # PASO 1: Crear perfil (si no existe)
        create_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            json={"username": username},
            timeout=10
        )
        print(f"[conexiones_init] create_profile status={create_resp.status_code}", flush=True)
        # 200 o 409 (ya existe) son aceptables
        if create_resp.status_code not in [200, 201, 409]:
            return Response({
                "success": False,
                "error": f"Error creando perfil: {create_resp.text[:200]}"
            }, status=500)
        
        # PASO 2: Generar JWT URL
        jwt_resp = http_requests.post(
            "https://api.upload-post.com/api/uploadposts/users/generate-jwt",
            headers=headers,
            json={
                "username": username,
                "redirect_url": f"{settings.FRONTEND_URL}/conexiones",
                "logo_image": "https://res.cloudinary.com/dpqgbgilw/image/upload/leadbook_logo",
                "connect_title": "Conectá tus redes sociales",
                "connect_description": "Conectá tus cuentas para publicar automáticamente con LeadBook",
                "show_calendar": True
            },
            timeout=10
        )
        print(f"[conexiones_init] generate_jwt status={jwt_resp.status_code}", flush=True)
        if jwt_resp.status_code != 200:
            return Response({
                "success": False,
                "error": f"Error generando URL: {jwt_resp.text[:200]}"
            }, status=500)
        
        data = jwt_resp.json()
        return Response({
            "success": True,
            "access_url": data.get("access_url"),
            "username": username
        })
    except Exception as e:
        print(f"[conexiones_init] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "error": f"Error interno del servidor: {str(e)[:200]}"
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conexiones_estado(request):
    """
    Devuelve las redes sociales conectadas del usuario.
    Siempre devuelve JSON — nunca HTML.
    """
    import traceback, sys
    try:
        from api.pool_manager import get_api_key
        
        user = request.user
        username = f"leadbook_{user.id}"
        print(f"[conexiones_estado] user={user.email} username={username}", flush=True)
        
        api_key = get_api_key(user, 'uploadpost')
        
        if not api_key:
            print(f"[conexiones_estado] No uploadpost key para {user.email}, devolviendo vacío", flush=True)
            return Response({"success": True, "redes": [], "conectado": False})
        
        headers = {
            "Authorization": f"Apikey {api_key}",
            "Content-Type": "application/json"
        }
        
        resp = http_requests.get(
            "https://api.upload-post.com/api/uploadposts/users",
            headers=headers,
            timeout=10
        )
        print(f"[conexiones_estado] uploadpost status={resp.status_code}", flush=True)
        
        if resp.status_code != 200:
            return Response({"success": True, "redes": [], "conectado": False})
        
        usuarios = resp.json()
        
        # Asegurar que usuarios sea una lista
        if not isinstance(usuarios, list):
            usuarios = usuarios.get('users', usuarios.get('data', []))
            if not isinstance(usuarios, list):
                usuarios = []
        
        perfil = next(
            (u for u in usuarios if u.get("username") == username), 
            None
        )
        
        if not perfil:
            return Response({"success": True, "redes": [], "conectado": False})
        
        redes = perfil.get("accounts", [])
        return Response({
            "success": True,
            "conectado": len(redes) > 0,
            "redes": redes,
            "username": username
        })
    except Exception as e:
        print(f"[conexiones_estado] EXCEPTION: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return Response({
            "success": False,
            "redes": [],
            "conectado": False,
            "error": f"Error interno: {str(e)[:200]}"
        }, status=500)


# ============================================================
# DEBUG / DIAGNÓSTICO — endpoints seguros (no exponen secretos)
# Uso: curl https://tuback.up.railway.app/api/v1/debug/email-check/
# ============================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_email_check(request):
    """
    Devuelve metadata de la config de email sin exponer la password.
    Sirve para verificar si las env vars GMAIL_USER y GMAIL_APP_PASSWORD
    están cargadas en Railway (o cualquier entorno).
    """
    from django.conf import settings
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''

    # Enmascarar el user (mostrar solo primeros/últimos chars)
    def mask(s, head=3, tail=3):
        if not s:
            return None
        if len(s) <= head + tail:
            return "*" * len(s)
        return f"{s[:head]}***{s[-tail:]}"

    import os
    provider    = (os.environ.get("EMAIL_PROVIDER") or getattr(settings, "EMAIL_PROVIDER", "") or "gmail").strip().lower()
    resend_key  = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "") or ""
    resend_from = os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or ""

    # Verdict operativo unificado
    if provider == "resend":
        if resend_key:
            verdict = "RESEND-OK-listo-para-enviar"
        else:
            verdict = "RESEND-seleccionado-pero-falta-RESEND_API_KEY"
    else:
        if bool(host_user) and bool(host_pass):
            verdict = "SMTP-OK-listo-para-enviar"
        else:
            verdict = "CONSOLE-BACKEND-emails-NO-saldran-cargar-GMAIL_APP_PASSWORD"

    return Response({
        "EMAIL_PROVIDER": provider,
        "EMAIL_BACKEND": getattr(settings, 'EMAIL_BACKEND', None),
        "EMAIL_HOST": getattr(settings, 'EMAIL_HOST', None),
        "EMAIL_PORT": getattr(settings, 'EMAIL_PORT', None),
        "EMAIL_USE_SSL": getattr(settings, 'EMAIL_USE_SSL', None),
        "EMAIL_USE_TLS": getattr(settings, 'EMAIL_USE_TLS', None),
        "DEFAULT_FROM_EMAIL": getattr(settings, 'DEFAULT_FROM_EMAIL', None),
        "GMAIL_USER_set": bool(host_user),
        "GMAIL_USER_masked": mask(host_user),
        "GMAIL_APP_PASSWORD_set": bool(host_pass),
        "GMAIL_APP_PASSWORD_len": len(host_pass),
        "RESEND_API_KEY_set": bool(resend_key),
        "RESEND_API_KEY_len": len(resend_key),
        "RESEND_FROM": resend_from or None,
        "CELERY_TASK_ALWAYS_EAGER": getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', None),
        "DEBUG": getattr(settings, 'DEBUG', None),
        "verdict": verdict,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def debug_email_send(request):
    """
    Dispara un envío SMTP REAL y SINCRÓNICO de prueba.
    Body JSON: {"email": "destino@mail.com"}  (acepta también "to")
    Devuelve exactamente lo que pasó, incluyendo error SMTP completo si falla.

    IMPORTANTE: En producción deberías proteger este endpoint con
    X-Admin-Key antes de dejarlo abierto. Aquí queda AllowAny para debug rápido.
    """
    import traceback, socket, smtplib, ssl, time
    from django.conf import settings
    from django.core.mail import get_connection, EmailMultiAlternatives

    # Aceptar "email" o "to" (compatibilidad)
    destino = (request.data.get('email') or request.data.get('to') or '').strip().lower()
    if not destino:
        return Response({"error": "falta campo 'email' con el email destino"}, status=400)

    # Provider opcional — si se pasa "resend", probamos Resend sin tocar env vars
    forced_provider = (request.data.get('provider') or '').strip().lower()
    if forced_provider == 'resend':
        import os, traceback
        try:
            from .tasks import _send_via_resend
        except Exception as e_imp:
            return Response({
                "ok": False, "stage": "import-resend",
                "error_type": type(e_imp).__name__, "error": str(e_imp),
            }, status=500)
        print(f"[DEBUG-EMAIL] Forzando envío via RESEND a {destino}", flush=True)
        subject = "LeadBook — prueba de email (Resend, debug)"
        text_body = "Este es un email de prueba enviado por /api/v1/debug/email-send/ (provider=resend)."
        html_body = (
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code> "
            "(<b>provider=resend</b>).</p><p>Si lo estás leyendo, Resend funciona desde este servidor.</p>"
        )
        try:
            ok, detalle = _send_via_resend(destino, subject, text_body, html_body)
            return Response({
                "ok": ok,
                "stage": "resend",
                "result": detalle,
                "destino": destino,
                "provider": "resend",
                "RESEND_API_KEY_set": bool(os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")),
                "RESEND_FROM": os.environ.get("RESEND_FROM") or getattr(settings, "RESEND_FROM", "") or None,
            }, status=200 if ok else 500)
        except Exception as e_res:
            return Response({
                "ok": False, "stage": "resend",
                "error_type": type(e_res).__name__, "error": str(e_res),
                "traceback": traceback.format_exc()[-1500:],
            }, status=500)

    host      = getattr(settings, 'EMAIL_HOST', '')
    port      = getattr(settings, 'EMAIL_PORT', 0)
    use_ssl   = getattr(settings, 'EMAIL_USE_SSL', False)
    use_tls   = getattr(settings, 'EMAIL_USE_TLS', False)
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    from_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', host_user)

    info = {
        "destino": destino,
        "backend": settings.EMAIL_BACKEND,
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
        "user_set": bool(host_user),
        "user_masked": (host_user[:3] + "***" + host_user[-3:]) if host_user else None,
        "pass_set": bool(host_pass),
        "pass_len": len(host_pass),
        "from": from_addr,
    }

    print(f"[DEBUG-EMAIL] Disparando envío de test a {destino} — host={host}:{port} ssl={use_ssl} tls={use_tls}", flush=True)

    # Guardas tempranas
    if not host_user or not host_pass:
        return Response({
            "ok": False,
            "stage": "env-vars",
            "error": "GMAIL_USER o GMAIL_APP_PASSWORD no están cargadas en el entorno",
            **info,
        }, status=500)

    # 1) Prueba de conectividad TCP pura
    t0 = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=15)
        sock.close()
        tcp_ok = True
        tcp_ms = int((time.time() - t0) * 1000)
    except Exception as e_tcp:
        return Response({
            "ok": False,
            "stage": "tcp-connect",
            "error_type": type(e_tcp).__name__,
            "error": str(e_tcp),
            "hint": "Railway no puede abrir el puerto SMTP. Gmail en la nube suele fallar aquí → migrar a Resend.",
            **info,
        }, status=500)

    # 2) Handshake SMTP + login con smtplib directo para capturar respuesta exacta del server
    smtp_debug = {"tcp_ok": tcp_ok, "tcp_ms": tcp_ms}
    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            if use_tls:
                smtp.starttls(context=ctx)
        ehlo_code, ehlo_msg = smtp.ehlo()
        smtp_debug["ehlo_code"] = ehlo_code
        smtp_debug["ehlo_msg"] = (ehlo_msg or b"").decode(errors="ignore")[:200]

        smtp.login(host_user, host_pass)
        smtp_debug["login"] = "ok"
        smtp.quit()
    except smtplib.SMTPAuthenticationError as e_auth:
        return Response({
            "ok": False,
            "stage": "smtp-auth",
            "error_type": "SMTPAuthenticationError",
            "smtp_code": e_auth.smtp_code,
            "smtp_error": (e_auth.smtp_error or b"").decode(errors="ignore"),
            "hint": "Gmail rechazó la autenticación. Si el app password es correcto y el usuario tiene 2FA, probablemente Google está bloqueando IPs de Railway → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)
    except Exception as e_smtp:
        return Response({
            "ok": False,
            "stage": "smtp-handshake",
            "error_type": type(e_smtp).__name__,
            "error": str(e_smtp),
            "traceback": traceback.format_exc()[-1500:],
            "hint": "Falló el handshake SSL/TLS con Gmail. Probablemente Railway bloquea → migrar a Resend.",
            "debug": smtp_debug,
            **info,
        }, status=500)

    # 3) Si llegamos acá, SMTP está OK. Enviamos el mail real.
    try:
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=host, port=port,
            username=host_user, password=host_pass,
            use_ssl=use_ssl, use_tls=use_tls,
            fail_silently=False,
            timeout=30,
        )
        msg = EmailMultiAlternatives(
            subject="LeadBook — prueba de email (debug)",
            body="Este es un email de prueba enviado por /api/v1/debug/email-send/.\nSi lo estás leyendo, SMTP funciona desde este servidor.",
            from_email=from_addr,
            to=[destino],
            connection=connection,
        )
        msg.attach_alternative(
            "<p>Este es un email de prueba enviado por <code>/api/v1/debug/email-send/</code>.</p>"
            "<p>Si lo estás leyendo, <b>SMTP funciona</b> desde este servidor.</p>",
            "text/html",
        )
        sent = msg.send(fail_silently=False)
        return Response({
            "ok": True,
            "stage": "sent",
            "sent_count": sent,
            "debug": smtp_debug,
            **info,
            "nota": "Si 'sent_count'=1 Gmail aceptó el mensaje. Revisá inbox y spam del destino.",
        })
    except Exception as e_send:
        return Response({
            "ok": False,
            "stage": "send-message",
            "error_type": type(e_send).__name__,
            "error": str(e_send),
            "traceback": traceback.format_exc()[-1500:],
            "debug": smtp_debug,
            **info,
        }, status=500)
