import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

class UserPresenceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
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
