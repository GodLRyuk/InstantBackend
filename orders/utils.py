# orders/utils.py
import json
import os

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django_extensions import settings
import firebase_admin
import firebase_admin.credentials as fb_credentials
import firebase_admin.messaging as fb_messaging

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

def get_firebase_app():
    if not firebase_admin._apps:
        json_str = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        if json_str:
            # Production: read from environment variable
            service_account_info = json.loads(json_str)
            cred = fb_credentials.Certificate(service_account_info)
        else:
            # Local: read from file
            from django.conf import settings
            cred = fb_credentials.Certificate(str(settings.FIREBASE_SERVICE_ACCOUNT_PATH))
        
        firebase_admin.initialize_app(cred)

def send_order_notification(user, title: str, body: str, data: dict = {}):
    try:
        token = getattr(user, 'fcm_token', None)
        if not token:
            print(f"No FCM token for user {user.id}")
            return

        get_firebase_app()  # ✅ initialize here, not at import time

        str_data = {k: str(v) for k, v in data.items()}

        message = fb_messaging.Message(
            notification=fb_messaging.Notification(
                title=title,
                body=body,
            ),
            data=str_data,
            token=token,
            android=fb_messaging.AndroidConfig(priority='high'),
            apns=fb_messaging.APNSConfig(
                payload=fb_messaging.APNSPayload(
                    aps=fb_messaging.Aps(sound='default')
                )
            )
        )

        response = fb_messaging.send(message)
        print(f"Notification sent to user {user.id}: {response}")

    except Exception as e:
        print(f"Failed to send notification to user {user.id}: {e}")