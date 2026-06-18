from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
import datetime
from .models import Order

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