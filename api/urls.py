from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .views import (
    PropertyViewSet, GeneratedAssetViewSet, generar_guion, generar_listado, 
    RegisterView, LogoutView, DashboardView, ListadosView, generar_pdf, 
    PerfilView, ListadoDetalleView, generar_imagen_post, generar_imagen_story, 
    generar_email, serve_pdf_file, mp_checkout, mp_webhook, get_plan_info_mp,
    OnboardingView, video_status, publicar_instagram, send_otp, verify_otp,
    generar_video, obtener_terminos, obtener_politica_privacidad,
    plan_status, seleccionar_plan_free, test_upload_avatar, generar_carrusel,
    amenidades_presets, recuperar_password, confirmar_recuperacion
)
from .views_admin import (
    admin_metricas, admin_usuarios_list, admin_usuario_cambiar_plan, admin_usuario_eliminar,
    admin_usuario_detalle, admin_usuarios_eliminados, admin_usuario_restaurar,
    admin_usuario_suspender, admin_apikeys_resumen, admin_apikeys_pool,
    admin_apikeys_pool_crear, admin_apikeys_pool_detail, admin_apikeys_global,
    admin_pool_estado, admin_alerts_read, admin_health_check, admin_enviar_email
)

router = DefaultRouter()
router.register(r'properties', PropertyViewSet)
router.register(r'assets', GeneratedAssetViewSet)

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh_alt'),
    path('auth/logout/', LogoutView.as_view(), name='auth_logout'),
    path('auth/perfil/', PerfilView.as_view(), name='auth_perfil'),
    path('auth/onboarding/', OnboardingView.as_view(), name='auth_onboarding'),
    path('auth/send-otp/', send_otp, name='auth_send_otp'),
    path('auth/verify-otp/', verify_otp, name='auth_verify_otp'),
    path('auth/plan-status/', plan_status, name='plan_status'),
    path('auth/seleccionar-plan-free/', seleccionar_plan_free, name='seleccionar_plan_free'),
    path('recuperar-password/', recuperar_password, name='recuperar_password'),
    path('confirmar-recuperacion/', confirmar_recuperacion, name='confirmar_recuperacion'),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    path('listados/', ListadosView.as_view(), name='listados'),
    path('listados/<int:pk>/', ListadoDetalleView.as_view(), name='listado_detalle'),
    path('listados/<int:pk>/generar-video/', generar_video, name='generar_video'),

    path('', include(router.urls)),
    path('generar-guion/', generar_guion, name='generar_guion'),
    path('generar-listado/', generar_listado, name='generar_listado'),
    path('generar-pdf/', generar_pdf, name='generar_pdf'),
    path('generar-imagen-post/', generar_imagen_post, name='generar_imagen_post'),
    path('generar-imagen-story/', generar_imagen_story, name='generar_imagen_story'),
    path('generar-email/', generar_email, name='generar_email'),
    path('publicar-instagram/', publicar_instagram, name='publicar_instagram'),
    path('pdf/<str:uuid_str>/', serve_pdf_file, name='serve_pdf'),
    path('video-status/<int:listado_id>/', video_status, name='video_status'),
    
    path('mp/checkout/', mp_checkout,  name='mp_checkout'),
    path('mp/webhook/',  mp_webhook,   name='mp_webhook'),
    path('mp/plan/',     get_plan_info_mp,       name='mp_plan_info'),

    # Legal
    path('terminos-y-condiciones/', obtener_terminos, name='obtener_terminos'),
    path('politica-privacidad/', obtener_politica_privacidad, name='obtener_politica_privacidad'),

    # Test endpoints
    path('test-upload/', test_upload_avatar, name='test_upload_avatar'),
    path('generar-carrusel/', generar_carrusel, name='generar_carrusel'),
    path('amenidades-presets/', amenidades_presets, name='amenidades_presets'),

    # Admin Dash
    path('admin/stats/', admin_metricas),
    path('admin/usuarios/', admin_usuarios_list),
    path('admin/usuarios-eliminados/', admin_usuarios_eliminados),
    path('admin/usuarios/<int:user_id>/', admin_usuario_eliminar),
    path('admin/usuarios/<int:user_id>/restaurar/', admin_usuario_restaurar),
    path('admin/usuarios/<int:user_id>/detalle/', admin_usuario_detalle),
    path('admin/usuarios/<int:user_id>/cambiar-plan/', admin_usuario_cambiar_plan),
    path('admin/usuarios/<int:user_id>/suspender/', admin_usuario_suspender),
    path('admin/usuarios/<int:user_id>/email/', admin_enviar_email),
    path('admin/listados/', views.admin_listados),
    path('admin/assets/', views.admin_assets),
    path('admin/pagos/', views.admin_pagos),
    
    # API Keys & Pool
    path('admin/apikeys/resumen/', admin_apikeys_resumen),
    path('admin/apikeys/pool/', admin_apikeys_pool),
    path('admin/apikeys/pool/crear/', admin_apikeys_pool_crear),
    path('admin/apikeys/pool/<int:key_id>/', admin_apikeys_pool_detail),
    path('admin/apikeys/global/', admin_apikeys_global),
    path('admin/pool/estado/', admin_pool_estado),
    path('admin/pool/listar/', admin_apikeys_pool), # Alias
    path('admin/alerts/<int:alert_id>/read/', admin_alerts_read),
    path('admin/health-check/', admin_health_check),

    # Conexiones Redes (UploadPost)
    path('conexiones/init/', views.conexiones_init),
    path('conexiones/estado/', views.conexiones_estado),

    # Debug / Diagnóstico
    path('debug/email-check/', views.debug_email_check, name='debug_email_check'),
    path('debug/email-send/',  views.debug_email_send,  name='debug_email_send'),
]