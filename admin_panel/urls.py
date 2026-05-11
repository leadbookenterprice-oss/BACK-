from django.urls import path
from . import views
from . import views_cloudinary

urlpatterns = [
    # Stats
    path('stats/', views.admin_stats_v2),

    # API Keys Pool
    path('apikeys/pool/', views.admin_api_keys_list),
    path('apikeys/pool/crear/', views.admin_api_keys_create),
    path('apikeys/pool/bulk/', views.admin_api_keys_bulk_create),
    path('apikeys/pool/auto-repair/', views.admin_apikeys_auto_repair),
    path('apikeys/pool/<int:pk>/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/liberar/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/reactivar/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/reset/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/actualizar/', views.admin_pool_key_actualizar),
    path('apikeys/pool/<int:pk>/eliminar/', views.admin_pool_key_eliminar),
    path('apikeys/resumen/', views.admin_api_keys_list),

    # Global Keys
    path('apikeys/global/', views.admin_global_keys_list),
    path('apikeys/global/upsert/', views.admin_global_keys_upsert),
    path('apikeys/global/<int:key_id>/toggle/', views.admin_global_key_toggle),
    path('apikeys/global/<int:key_id>/eliminar/', views.admin_global_key_eliminar),
    path('apikeys/global/<int:key_id>/reset/', views.admin_global_key_reset),

    # Pool estado/listar
    path('pool/estado/', views.admin_api_keys_list),
    path('pool/listar/', views.admin_api_keys_list),
    path('pool/keys/<int:pk>/toggle/', views.admin_pool_key_toggle),

    # Cloudinary
    path('cloudinary/stats/', views_cloudinary.admin_cloudinary_stats),
    path('cloudinary/keys/', views_cloudinary.admin_cloudinary_keys),
    path('cloudinary/keys/add/', views_cloudinary.admin_cloudinary_keys_add),
    path('cloudinary/keys/<int:pk>/eliminar/', views_cloudinary.admin_cloudinary_keys_delete),

    # Bundles (deprecated)
    path('bundles/', views.admin_bundles_list),
    path('bundles/crear/', views.admin_bundles_crear),
    path('bundles/stats/', views.admin_bundles_stats),
    path('bundles/<int:bundle_id>/', views.admin_bundles_detail),
    path('bundles/<int:bundle_id>/asignar/', views.admin_bundles_asignar),
    path('bundles/<int:bundle_id>/liberar/', views.admin_bundles_liberar),

    # Usuarios
    path('usuarios/', views.admin_users_list),
    path('usuarios-eliminados/', views.admin_usuarios_eliminados),
    path('usuarios/<int:pk>/', views.admin_usuario_eliminar),
    path('usuarios/<int:pk>/detalle/', views.admin_users_detail),
    path('usuarios/<int:pk>/restaurar/', views.admin_usuario_restaurar),
    path('usuarios/<int:pk>/cambiar-plan/', views.admin_usuario_cambiar_plan),
    path('usuarios/<int:pk>/suspender/', views.admin_users_ban),
    path('usuarios/<int:pk>/unban/', views.admin_users_unban),
    path('usuarios/<int:pk>/email/', views.admin_enviar_email),

    # Contenido
    path('listados/', views.admin_listados),
    path('assets/', views.admin_assets),
    path('pagos/', views.admin_pagos),
    path('requests/', views.admin_requests_list),

    # Alertas
    path('alerts/', views.admin_alerts_list),
    path('alerts/<int:alert_id>/read/', views.admin_alert_read),

    # Analytics
    path('analytics/timeseries/', views.admin_analytics_timeseries),
    path('analytics/top/', views.admin_analytics_top),

    # Health
    path('health/', views.admin_health_status),
    path('health-check/', views.admin_health_check_trigger),
]