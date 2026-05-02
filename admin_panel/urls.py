from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.admin_stats_v2, name='admin_stats_v2'),
    
    path('api-keys/', views.admin_api_keys_list, name='admin_api_keys_list'),
    path('api-keys/create/', views.admin_api_keys_create, name='admin_api_keys_create'),
    path('api-keys/<int:pk>/', views.admin_api_keys_detail, name='admin_api_keys_detail'),
    path('api-keys/<int:pk>/test/', views.admin_api_keys_test, name='admin_api_keys_test'),
    path('api-keys/<int:pk>/reassign/', views.admin_api_keys_reassign, name='admin_api_keys_reassign'),
    
    path('users/', views.admin_users_list, name='admin_users_list'),
    path('usuarios/', views.admin_users_list, name='admin_usuarios_list'),
    path('users/<int:pk>/', views.admin_users_detail, name='admin_users_detail'),
    path('usuarios/<int:pk>/detalle/', views.admin_users_detail, name='admin_usuarios_detail'),
    path('users/<int:pk>/info-general/', views.admin_user_info_general, name='admin_user_info_general'),
    path('users/<int:pk>/api-asignada/', views.admin_user_api_pool, name='admin_user_api_pool'),
    path('users/<int:pk>/delete/', views.admin_users_hard_delete, name='admin_users_hard_delete'),
    path('users/<int:pk>/ban/', views.admin_users_ban, name='admin_users_ban'),
    path('usuarios/<int:pk>/suspender/', views.admin_users_ban, name='admin_usuarios_ban'),
    path('users/<int:pk>/unban/', views.admin_users_unban, name='admin_users_unban'),
    path('usuarios/<int:pk>/unban/', views.admin_users_unban, name='admin_usuarios_unban'),
    
    path('requests/', views.admin_requests_list, name='admin_requests_list'),
    
    path('alerts/', views.admin_alerts_list, name='admin_alerts_list'),
    
    path('analytics/timeseries/', views.admin_analytics_timeseries, name='admin_analytics_timeseries'),
    path('analytics/top/', views.admin_analytics_top, name='admin_analytics_top'),
    
    path('health/', views.admin_health_status, name='admin_health_status'),
]
