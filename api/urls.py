from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import views_usage
from .views import (
    PropertyViewSet, GeneratedAssetViewSet, generar_guion, generar_listado, 
    RegisterView, LogoutView, DashboardView, ListadosView, generar_pdf, 
    PerfilView, ListadoDetalleView, generar_imagen_post, generar_imagen_story, 
    generar_email, serve_pdf_file, mp_checkout, mp_webhook, get_plan_info_mp,
    OnboardingView, video_status, publicar_instagram, send_otp, verify_otp,
    generar_video, obtener_terminos, obtener_politica_privacidad,
    plan_status, seleccionar_plan_free, test_upload_avatar, generar_carrusel,
    amenidades_presets, recuperar_password, confirmar_recuperacion,
    publicar_redes_sociales, proxy_pdf_view, proxy_pdf_thumbnail_view,
    generar_html, generar_escena, CustomTokenObtainPairView,
    upload_fotos_listado
)
from .views_admin import (
    admin_metricas, admin_usuarios_list, admin_usuario_cambiar_plan, admin_usuario_eliminar,
    admin_usuario_detalle, admin_usuarios_eliminados, admin_usuario_restaurar,
    admin_usuario_suspender, admin_apikeys_resumen, admin_apikeys_pool,
    admin_apikeys_pool_crear, admin_apikeys_pool_bulk, admin_apikeys_pool_detail, admin_apikeys_global,
    admin_pool_estado, admin_alerts_read, admin_health_check, admin_enviar_email,
    admin_bundles_list, admin_bundles_crear, admin_bundles_detail,
    admin_bundles_asignar, admin_bundles_liberar, admin_bundles_stats,
    admin_audio_music, admin_audio_music_detail, admin_audio_sfx, admin_audio_sfx_detail,
    admin_apikeys_auto_repair, admin_branding_watermark,
)

router = DefaultRouter()
router.register(r'properties', PropertyViewSet)
router.register(r'assets', GeneratedAssetViewSet)

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
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
    path('listados/upload-fotos/', upload_fotos_listado, name='upload_fotos_listado'),
    path('listados/<int:pk>/html/', generar_html, name='generar_html'),
    path('listados/<int:pk>/generar-video/', generar_video, name='generar_video'),
    path('listados/<int:listado_id>/pdf-proxy/', proxy_pdf_view, name='pdf_proxy'),
    path('listados/<int:listado_id>/pdf-thumbnail/', proxy_pdf_thumbnail_view, name='pdf_thumbnail'),
    path('descargar-pdf/<int:listado_id>/', views.descargar_pdf, name='descargar_pdf'),

    path('', include(router.urls)),
    path('generar-guion/', generar_guion, name='generar_guion'),
    path('generar-escena/', generar_escena, name='generar_escena'),
    path('generar-listado/', generar_listado, name='generar_listado'),
    path('generar-pdf/', generar_pdf, name='generar_pdf'),
    path('generar-imagen-post/', generar_imagen_post, name='generar_imagen_post'),
    path('generar-imagen-story/', generar_imagen_story, name='generar_imagen_story'),
    path('generar-email/', generar_email, name='generar_email'),
    path('publicar-instagram/', publicar_instagram, name='publicar_instagram'),
    path('publicar-redes/', publicar_redes_sociales, name='publicar_redes_sociales'),
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
    path('admin/apikeys/pool/bulk/', admin_apikeys_pool_bulk),
    path('admin/apikeys/pool/<int:key_id>/', admin_apikeys_pool_detail),
    path('admin/apikeys/pool/<int:key_id>/detalle/', admin_apikeys_pool_detail),
    path('admin/apikeys/global/', admin_apikeys_global),
    path('admin/apikeys/pool/auto-repair/', admin_apikeys_auto_repair),
    path('admin/pool/estado/', admin_pool_estado),
    path('admin/pool/listar/', admin_apikeys_pool), # Alias
    path('admin/alerts/<int:alert_id>/read/', admin_alerts_read),
    path('admin/health-check/', admin_health_check),

    # Conexiones Redes (UploadPost)
    path('conexiones/init/', views.conexiones_init),
    path('conexiones/estado/', views.conexiones_estado),
    path('conexiones/eliminar/', views.conexiones_eliminar),

    # Debug / Diagnóstico
    path('debug/email-check/', views.debug_email_check, name='debug_email_check'),
    path('debug/email-send/',  views.debug_email_send,  name='debug_email_send'),
    path('debug/uploadpost/<str:username>/', views.debug_uploadpost, name='debug_uploadpost'),

    # Uso de APIs
    path('auth/mi-uso/', views_usage.mi_uso_apis, name='mi_uso_apis'),
    path('admin/uso-global/', views_usage.admin_uso_global, name='admin_uso_global'),

    # API Bundles
    path('admin/bundles/', admin_bundles_list),
    path('admin/bundles/crear/', admin_bundles_crear),
    path('admin/bundles/stats/', admin_bundles_stats),
    path('admin/bundles/<int:bundle_id>/', admin_bundles_detail),
    path('admin/bundles/<int:bundle_id>/asignar/', admin_bundles_asignar),
    path('admin/bundles/<int:bundle_id>/liberar/', admin_bundles_liberar),

    # Librería de Audio
    path('admin/audio/music/', admin_audio_music),
    path('admin/audio/music/<int:pk>/', admin_audio_music_detail),
    path('admin/audio/sfx/', admin_audio_sfx),
    path('admin/audio/sfx/<int:pk>/', admin_audio_sfx_detail),
    path('admin/branding/watermark/', admin_branding_watermark),

    # Notificaciones
    path('notificaciones/', views.listar_notificaciones),
    path('notificaciones/<int:notif_id>/leer/', views.marcar_notificacion_leida),
    path('notificaciones/leer-todas/', views.marcar_todas_leidas),
]