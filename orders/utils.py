# orders/utils.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def notify_driver(driver_id, order_data):
    """Call this anywhere in your views to push to driver"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'driver_{driver_id}',
        {
            'type': 'new_order',  # maps to new_order() in consumer
            'order': order_data
        }
    )
    print(f'📤 Notified driver {driver_id} about order {order_data["order_id"]}')