import json
from channels.generic.websocket import AsyncWebsocketConsumer
from decouple import config
from django.utils.crypto import constant_time_compare

ADMIN_KEY = config('ADMIN_KEY', default='')

class AdminDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Auth via query param: wss://...?key=ADMIN_KEY
        query_string = self.scope.get('query_string', b'').decode()
        params = dict(qc.split('=') for qc in query_string.split('&') if '=' in qc)
        provided_key = params.get('key', '')

        if not ADMIN_KEY or not provided_key or not constant_time_compare(provided_key, ADMIN_KEY):
            await self.close(code=4003)
            return

        self.group_name = "admin_dashboard"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def api_request_made(self, event):
        await self.send(text_data=json.dumps({
            'type': 'request_made',
            'data': event['data']
        }))

    async def admin_alert(self, event):
        await self.send(text_data=json.dumps({
            'type': 'alert',
            'data': event['data']
        }))

    async def receive(self, text_data=None, bytes_data=None):
        # Ping/pong keepalive
        try:
            msg = json.loads(text_data or '{}')
            if msg.get('type') == 'ping':
                await self.send(text_data=json.dumps({'type': 'pong'}))
        except Exception:
            pass
