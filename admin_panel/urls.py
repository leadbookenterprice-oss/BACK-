from django.urls import path
from . import views

urlpatterns = [
    # ── Stats ─────────────────────────────────────────────────────────────────
    path('stats/', views.admin_stats_v2, name='admin_stats_v2'),

    # ── API Keys ──────────────────────────────────────────────────────────────
    path('api-keys/', views.admin_api_keys_list, name='admin_api_keys_list'),
    path('api-keys/create/', views.admin_api_keys_create, name='admin_api_keys_create'),
    path('api-keys/<int:pk>/', views.admin_api_keys_detail, name='admin_api_keys_detail'),
    path('api-keys/<int:pk>/test/', views.admin_api_keys_test, name='admin_api_keys_test'),
    path('api-keys/<int:pk>/reassign/', views.admin_api_keys_reassign, name='admin_api_keys_reassign'),

    # ── Pool (aliases used by the old frontend) ───────────────────────────────
    path('apikeys/pool/bulk/', views.admin_api_keys_bulk_create, name='admin_apikeys_pool_bulk'),
    path('apikeys/pool/', views.admin_api_keys_list, name='admin_apikeys_pool'),
    path('apikeys/pool/crear/', views.admin_api_keys_create, name='admin_apikeys_pool_crear'),
    path('apikeys/pool/<int:pk>/', views.admin_api_keys_detail, name='admin_apikeys_pool_detail'),
    path('apikeys/pool/<int:pk>/liberar/', views.admin_api_keys_detail, name='admin_apikeys_pool_liberar'),
    path('apikeys/pool/<int:pk>/reactivar/', views.admin_api_keys_detail, name='admin_apikeys_pool_reactivar'),
    path('apikeys/pool/<int:pk>/reset/', views.admin_api_keys_detail, name='admin_apikeys_pool_reset'),
    path('apikeys/resumen/', views.admin_api_keys_list, name='admin_apikeys_resumen'),
    path('apikeys/global/', views.admin_api_keys_list, name='admin_apikeys_global'),
    path('pool/estado/', views.admin_api_keys_list, name='admin_pool_estado'),
    path('pool/listar/', views.admin_api_keys_list, name='admin_pool_listar'),
    path('pool/keys/<int:pk>/toggle/', views.admin_api_keys_detail, name='admin_pool_keys_toggle'),

    # ── Bundles ───────────────────────────────────────────────────────────────
    path('bundles/', views.admin_bundles_list, name='admin_bundles_list'),
    path('bundles/crear/', views.admin_bundles_crear, name='admin_bundles_crear'),
    path('bundles/stats/', views.admin_bundles_stats, name='admin_bundles_stats'),
    path('bundles/<int:bundle_id>/', views.admin_bundles_detail, name='admin_bundles_detail'),
    path('bundles/<int:bundle_id>/asignar/', views.admin_bundles_asignar, name='admin_bundles_asignar'),
    path('bundles/<int:bundle_id>/liberar/', views.admin_bundles_liberar, name='admin_bundles_liberar'),

    # ── Users ─────────────────────────────────────────────────────────────────
    path('users/', views.admin_users_list, name='admin_users_list'),
    path('usuarios/', views.admin_users_list, name='admin_usuarios_list'),
    path('users/<int:pk>/', views.admin_users_detail, name='admin_users_detail'),
    path('usuarios/<int:pk>/detalle/', views.admin_users_detail, name='admin_usuarios_detail'),
    path('usuarios/<int:pk>/', views.admin_usuario_eliminar, name='admin_usuarios_eliminar'),
    path('users/<int:pk>/info-general/', views.admin_user_info_general, name='admin_user_info_general'),
    path('users/<int:pk>/api-asignada/', views.admin_user_api_pool, name='admin_user_api_pool'),
    path('users/<int:pk>/delete/', views.admin_users_hard_delete, name='admin_users_hard_delete'),
    path('users/<int:pk>/ban/', views.admin_users_ban, name='admin_users_ban'),
    path('usuarios/<int:pk>/suspender/', views.admin_users_ban, name='admin_usuarios_ban'),
    path('users/<int:pk>/unban/', views.admin_users_unban, name='admin_users_unban'),
    path('usuarios/<int:pk>/unban/', views.admin_users_unban, name='admin_usuarios_unban'),
    path('usuarios-eliminados/', views.admin_usuarios_eliminados, name='admin_usuarios_eliminados'),
    path('usuarios/<int:pk>/restaurar/', views.admin_usuario_restaurar, name='admin_usuario_restaurar'),
    path('usuarios/<int:pk>/cambiar-plan/', views.admin_usuario_cambiar_plan, name='admin_usuario_cambiar_plan'),
    path('usuarios/<int:pk>/email/', views.admin_enviar_email, name='admin_enviar_email'),

    # ── Requests / Logs ────────────────────────────────────────────────────────
    path('requests/', views.admin_requests_list, name='admin_requests_list'),

    # ── Alerts ────────────────────────────────────────────────────────────────
    path('alerts/', views.admin_alerts_list, name='admin_alerts_list'),
    path('alerts/<int:alert_id>/read/', views.admin_alert_read, name='admin_alert_read'),

    # ── Analytics ─────────────────────────────────────────────────────────────
    path('analytics/timeseries/', views.admin_analytics_timeseries, name='admin_analytics_timeseries'),
    path('analytics/top/', views.admin_analytics_top, name='admin_analytics_top'),

    # ── Listados / Assets / Pagos ─────────────────────────────────────────────
    path('listados/', views.admin_listados, name='admin_listados'),
    path('assets/', views.admin_assets, name='admin_assets'),
    path('pagos/', views.admin_pagos, name='admin_pagos'),

    # ── Health ────────────────────────────────────────────────────────────────
    path('health/', views.admin_health_status, name='admin_health_status'),
    path('health-check/', views.admin_health_check_trigger, name='admin_health_check_trigger'),
]
