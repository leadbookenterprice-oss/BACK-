from django.urls import path
from . import views
from . import views_cloudinary
from api import views_admin as api_admin_views

urlpatterns = [
    # Stats
    path('stats/', views.admin_stats_v2),

    # API Keys Pool
    path('apikeys/export/', views.admin_api_keys_export),
    path('apikeys/pool/', api_admin_views.admin_apikeys_pool),
    path('apikeys/pool/crear/', api_admin_views.admin_apikeys_pool_crear),
    path('apikeys/pool/bulk/', api_admin_views.admin_apikeys_pool_bulk),
    path('apikeys/pool/auto-repair/', views.admin_apikeys_auto_repair),
    path('apikeys/pool/<int:pk>/test/', api_admin_views.admin_apikeys_pool_test),
    path('apikeys/pool/<int:pk>/', api_admin_views.admin_apikeys_pool_detail),
    path('apikeys/pool/<int:pk>/liberar/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/reactivar/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/reset/', views.admin_api_keys_detail),
    path('apikeys/pool/<int:pk>/actualizar/', views.admin_pool_key_actualizar),
    path('apikeys/pool/<int:pk>/eliminar/', api_admin_views.admin_apikeys_pool_detail),
    path('apikeys/resumen/', api_admin_views.admin_apikeys_pool),
    path('api-usage/summary/', api_admin_views.admin_api_usage_summary),
    path('api-usage/logs/', api_admin_views.admin_api_usage_logs),
    path('api-usage/keys/<int:key_id>/', api_admin_views.admin_api_usage_key_detail),

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
    path('cloudinary/logs/', views_cloudinary.admin_cloudinary_logs),
    path('cloudinary/keys/add/', views_cloudinary.admin_cloudinary_keys_add),
    path('cloudinary/keys/test-all/', views_cloudinary.admin_cloudinary_keys_test_all),
    path('cloudinary/keys/<int:pk>/test/', views_cloudinary.admin_cloudinary_keys_test),
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
    path('usuarios/<int:pk>/add-extra/', views.admin_add_extra_api),

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
