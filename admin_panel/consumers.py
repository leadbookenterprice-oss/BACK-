import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from urllib.parse import parse_qs
from django.utils import timezone


@database_sync_to_async
def _staff_user_from_token(token):
    if not token:
        return None
    try:
        from admin_panel.auth import admin_session_user, validate_admin_session_token

        payload = validate_admin_session_token(token)
        if payload:
            return admin_session_user(payload.get('email'))
    except Exception:
        pass
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from api.models import Agent
        validated = AccessToken(token)
        user = Agent.objects.filter(id=validated.get('user_id'), is_active=True, is_staff=True).first()
        return user
    except Exception:
        return None

class AdminDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_staff', False):
            query = parse_qs(self.scope.get('query_string', b'').decode())
            token = (query.get('token') or [''])[0]
            user = await _staff_user_from_token(token)

        if not user:
            await self.close(code=4003)
            return

        self.user = user
        self.group_name = "admin_dashboard"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def api_request_made(self, event):
        await self._send_payload('request', event)

    async def admin_alert(self, event):
        await self._send_payload('alert', event)

    async def stats_update(self, event):
        await self._send_payload('stats_update', event)

    async def trial_token_request(self, event):
        await self._send_payload('trial_token_request', event)

    async def _send_payload(self, event_type, event):
        payload = event.get('data') or {}
        if not isinstance(payload, dict):
            payload = {'value': payload}

        outgoing = {
            'type': event_type,
            'data': payload,
        }
        outgoing.update(payload)
        outgoing.setdefault('message', event_type.replace('_', ' ').strip().capitalize())
        outgoing.setdefault('timestamp', timezone.now().isoformat())

        await self.send(text_data=json.dumps(outgoing, default=str))

    async def receive(self, text_data=None, bytes_data=None):
        # Ping/pong keepalive
        try:
            msg = json.loads(text_data or '{}')
            if msg.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except Exception:
            pass
