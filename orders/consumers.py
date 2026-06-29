# orders/consumers.py
import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

class DriverConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.driver_id = self.scope['url_route']['kwargs']['driver_id']
        self.group_name = f'driver_{self.driver_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f'✅ Driver {self.driver_id} connected via WebSocket')

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f'❌ Driver {self.driver_id} disconnected')

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

        # ✅ Driver sends their live location
        elif data.get('type') == 'location_update':
            order_id = data.get('order_id')
            lat = data.get('lat')
            lng = data.get('lng')

            if order_id and lat and lng:
                # Save to DB
                await self.save_driver_location(order_id, lat, lng)

                # Broadcast to customer tracking this order
                await self.channel_layer.group_send(
                    f'order_{order_id}',
                    {
                        'type': 'driver_location',
                        'lat': lat,
                        'lng': lng,
                        'driver_id': self.driver_id,
                    }
                )

    async def new_order(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_order',
            'order': event['order']
        }))

    async def driver_location(self, event):
        await self.send(text_data=json.dumps({
            'type': 'driver_location',
            'lat': event['lat'],
            'lng': event['lng'],
        }))

    @database_sync_to_async
    def save_driver_location(self, order_id, lat, lng):
        from orders.models import Order
        try:
            order = Order.objects.get(id=order_id)
            order.driver_lat = lat
            order.driver_lng = lng
            order.save(update_fields=['driver_lat', 'driver_lng'])
        except Order.DoesNotExist:
            pass


# ✅ NEW — Customer tracks their order in real-time
class OrderTrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.group_name = f'order_{self.order_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        print(f'✅ Customer tracking order {self.order_id}')

        # Send current driver location immediately on connect
        location = await self.get_current_location()
        if location:
            await self.send(text_data=json.dumps({
                'type': 'driver_location',
                'lat': location['lat'],
                'lng': location['lng'],
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        print(f'❌ Customer stopped tracking order {self.order_id}')

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    # Called when driver sends location update
    async def driver_location(self, event):
        await self.send(text_data=json.dumps({
            'type': 'driver_location',
            'lat': event['lat'],
            'lng': event['lng'],
        }))

    # Called when order status changes
    async def order_status_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'order_status',
            'status': event['status'],
        }))

    @database_sync_to_async
    def get_current_location(self):
        from orders.models import Order
        try:
            order = Order.objects.get(id=self.order_id)
            if order.driver_lat and order.driver_lng:
                return {'lat': float(order.driver_lat), 'lng': float(order.driver_lng)}
        except Order.DoesNotExist:
            pass
        return None