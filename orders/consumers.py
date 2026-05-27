# orders/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class DriverConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.driver_id = self.scope['url_route']['kwargs']['driver_id']
        self.group_name = f'driver_{self.driver_id}'

        # Join driver's personal group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        print(f'✅ Driver {self.driver_id} connected via WebSocket')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        print(f'❌ Driver {self.driver_id} disconnected')

    # Receive ping from Flutter
    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'ping':
            print(f'💓 Ping from driver {self.driver_id}')
            await self.send(text_data=json.dumps({'type': 'pong'}))

    # Called when group_send fires — sends to Flutter
    async def new_order(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_order',
            'order': event['order']
        }))