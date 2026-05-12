from django.urls import re_path
from admin_panel import consumers as admin_consumers
from api import consumers as user_consumers

websocket_urlpatterns = [
    re_path(r'ws/admin/live/$', admin_consumers.AdminDashboardConsumer.as_asgi()),
    re_path(r'ws/presence/(?P<user_id>\d+)/$', user_consumers.UserPresenceConsumer.as_asgi()),
]
