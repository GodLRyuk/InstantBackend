from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import datetime
from .models import Order
from .utils import send_order_notification

@receiver(post_save, sender=Order)
def schedule_driver_assignment(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.delivery_type != 'SCHEDULED':
        return
    if not instance.scheduled_date or not instance.scheduled_slot_start:
        return

    from .tasks import assign_driver_for_scheduled_order

    # Combine date + time into a timezone-aware datetime
    slot_dt = timezone.make_aware(
        datetime.datetime.combine(instance.scheduled_date, instance.scheduled_slot_start)
    )
    eta = slot_dt - datetime.timedelta(minutes=30)

    # Don't schedule in the past
    if eta <= timezone.now():
        eta = timezone.now() + datetime.timedelta(seconds=10)

    assign_driver_for_scheduled_order.apply_async(
        args=[instance.id],
        eta=eta
    )
    print(f"📅 Scheduled driver assignment for order #{instance.id} at {eta}")
@receiver(post_save, sender=Order)
def order_status_notification(sender, instance, created, **kwargs):
    if created:
        send_order_notification(
            user=instance.user,          
            title="Order Placed! 🎉",
            body="Your order has been confirmed and is being prepared.",
            data={"type": "order_placed", "order_id": str(instance.id)}
        )
    else:
        status = instance.order_status   

        if status == 'CONFIRMED':
            send_order_notification(
                user=instance.user,
                title="Your order is confirmed! 🕒",
                body="Your order has been confirmed and is being prepared.",
                data={"type": "order_confirmed", "order_id": str(instance.id)}
            )
        elif status == 'SHIPPED':
            send_order_notification(
                user=instance.user,
                title="Order Shipped! 🚚",
                body="Your order has been shipped and is on its way!",
                data={"type": "order_shipped", "order_id": str(instance.id)}
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
                body="Your order has been cancelled. Please contact support for more info.",
                data={"type": "order_cancelled", "order_id": str(instance.id)}
            )