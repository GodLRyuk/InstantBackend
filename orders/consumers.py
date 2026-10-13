import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


class DriverConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.driver_id = self.scope['url_route']['kwargs']['driver_id']
        self.group_name = f'driver_{self.driver_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f'✅ Driver {self.driver_id} connected')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

        elif data.get('type') == 'location_update':
            order_id = data.get('order_id')
            lat = data.get('lat')
            lng = data.get('lng')
            if order_id and lat and lng:
                await self.channel_layer.group_send(
                    f'order_{order_id}',
                    {'type': 'driver_location', 'lat': lat, 'lng': lng}
                )

    # Called by OrderTrackingConsumer to ask driver to send location
    async def request_location(self, event):
        await self.send(text_data=json.dumps({
            'type': 'send_location',
            'order_id': event['order_id'],
        }))

    async def new_order(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_order',
            'order': event['order'],
        }))

    async def driver_location(self, event):
        await self.send(text_data=json.dumps({
            'type': 'driver_location',
            'lat': event['lat'],
            'lng': event['lng'],
        }))


class OrderTrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.group_name = f'order_{self.order_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f'✅ Customer tracking order {self.order_id}')

        # ✅ Look up driver via DeliveryAssignment and request location
        driver_id = await self.get_driver_id()
        if driver_id:
            print(f'📍 Requesting location from driver {driver_id}')
            await self.channel_layer.group_send(
                f'driver_{driver_id}',
                {'type': 'request_location', 'order_id': self.order_id}
            )
        else:
            print(f'⚠️ No driver assigned to order {self.order_id}')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f'❌ Customer stopped tracking order {self.order_id}')

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def driver_location(self, event):
        await self.send(text_data=json.dumps({
            'type': 'driver_location',
            'lat': event['lat'],
            'lng': event['lng'],
        }))

    async def order_status_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'order_status',
            'status': event['status'],
        }))

    @database_sync_to_async
    def get_driver_id(self):
        # ✅ Uses DeliveryAssignment — the actual model linking driver to order
        from orders.models import DeliveryAssignment
        try:
            assignment = DeliveryAssignment.objects.filter(
                order_id=self.order_id
            ).order_by('-assigned_at').first()
            if assignment:
                return str(assignment.driver_id)
        except Exception as e:
            print(f'❌ get_driver_id error: {e}')
        return None


class RestaurantOwnerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        owner_id = int(self.scope['url_route']['kwargs']['owner_id'])
        query = self.scope.get('query_string', b'').decode()
        token = parse_qs(query).get('token', [None])[0]
        authenticated_owner_id = await self.get_owner_id(token) if token else None
        if authenticated_owner_id != owner_id:
            await self.close(code=4403)
            return

        self.group_name = f'restaurant_owner_{owner_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def new_order(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_order',
            'order': event['order'],
        }))

    @staticmethod
    @database_sync_to_async
    def get_owner_id(token):
        try:
            access_token = AccessToken(token)
        except TokenError:
            return None

        user_model = get_user_model()
        return user_model.objects.filter(
            pk=access_token['user_id'],
            role='RESTAURANT',
            is_active=True,
        ).values_list('pk', flat=True).first()