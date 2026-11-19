from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Order
from .utils import send_order_notification
from asgiref.sync import async_to_sync


@receiver(post_save, sender=Order)
def order_status_notification(sender, instance, created, **kwargs):
    transaction.on_commit(lambda: notify_order_status(instance, created), robust=True)


def notify_order_status(instance, created):
    channel_layer = get_channel_layer()

    if created:
        if instance.user_id and instance.order_channel == "ONLINE":
            send_order_notification(
                user=instance.user,
                title="Order Placed! 🎉",
                body="Your order has been confirmed!",
                data={"type": "order_placed", "order_id": str(instance.id)}
            )
        return

    status = instance.order_status

    # ✅ Push status update via WebSocket to customer tracking screen
    async_to_sync(channel_layer.group_send)(
        f'order_{instance.id}',
        {
            'type': 'order_status_update',
            'status': status,
        }
    )

    if instance.order_channel != "ONLINE" or not instance.user_id:
        return

    if status == 'OUT_FOR_DELIVERY':
        send_order_notification(
            user=instance.user,
            title="Your order is on the way 🚚",
            body="Your order is out for delivery!",
            data={"type": "order_on_the_way", "order_id": str(instance.id)}
        )
    elif status == 'DELIVERED':
        send_order_notification(
            user=instance.user,
            title="Order Delivered! ✅",
            body="Enjoy! Please rate your experience.",
            data={"type": "order_delivered", "order_id": str(instance.id)}
        )
    elif status == 'CANCELLED':
        send_order_notification(
            user=instance.user,
            title="Order Cancelled ❌",
            body="Your order has been cancelled.",
            data={"type": "order_cancelled", "order_id": str(instance.id)}
        )