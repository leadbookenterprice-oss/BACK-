import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from urllib.parse import parse_qs


@database_sync_to_async
def _user_id_from_token(token):
    if not token:
        return None
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        validated = AccessToken(token)
        return str(validated.get('user_id') or '')
    except Exception:
        return None

class UserPresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        user = self.scope.get('user')
        authenticated_id = str(getattr(user, 'id', '') or '') if getattr(user, 'is_authenticated', False) else ''
        if authenticated_id != str(self.user_id):
            query = parse_qs(self.scope.get('query_string', b'').decode())
            authenticated_id = await _user_id_from_token((query.get('token') or [''])[0])
        if authenticated_id != str(self.user_id):
            await self.close(code=4003)
            return

        self.group_name = f"presence_{self.user_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.update_last_seen()

    async def disconnect(self, close_code):
        await self.update_last_seen()
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            msg = json.loads(text_data or '{}')
            if msg.get('type') == 'ping':
                await self.update_last_seen()
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except Exception:
            pass

    async def account_revoked(self, event):
        await self.send(text_data=json.dumps({
            'type': 'account_revoked',
            'reason': event.get('reason') or 'access_code_revoked',
            'access_code': event.get('access_code') or '',
            'message': event.get('message') or 'Tu cuenta fue cerrada.',
        }))
        await self.close(code=4001)

    @database_sync_to_async
    def update_last_seen(self):
        from api.models import Agent
        try:
            Agent.objects.filter(pk=self.user_id).update(last_seen=timezone.now())
        except Exception:
            pass
