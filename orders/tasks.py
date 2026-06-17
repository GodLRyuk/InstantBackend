# orders/tasks.py

from config.celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def assign_driver_for_scheduled_order(self, order_id):
    """
    Runs 30 minutes before the scheduled delivery slot.
    Finds an available driver and assigns them.
    """
    from orders.models import Order, DeliveryAssignment
    from orders.services.driver_assignment import assign_driver
    from orders.utils import notify_driver

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        print(f"⚠️ Order #{order_id} not found for scheduled assignment")
        return

    # Skip if already cancelled or assigned
    if order.order_status == "CANCELLED":
        print(f"⏭️ Order #{order_id} was cancelled — skipping driver assignment")
        return

    existing = DeliveryAssignment.objects.filter(order=order).first()
    if existing:
        print(f"⏭️ Order #{order_id} already has a driver assigned")
        return

    driver = assign_driver(order)

    if not driver:
        # No driver available — retry after 5 mins
        print(f"⚠️ No driver available for order #{order_id}, retrying...")
        raise self.retry(countdown=300)

    assignment = DeliveryAssignment.objects.create(
        order=order,
        driver=driver,
        status="ASSIGNED"
    )

    notify_driver(driver.id, {
        "order_id": order.id,
        "order_status": order.order_status,
        "payment_status": order.payment_status,
        "total_amount": float(order.total_amount),
        "customer_name": (
            order.user.first_name + " " +
            order.user.middle_name + " " +
            order.user.last_name
        ),
        "customer_phone": order.user.phone,
        "address": order.address_snapshot,
        "assigned_at": str(assignment.assigned_at),
        "status": assignment.status,
        "scheduled_date": str(order.scheduled_date),
        "scheduled_slot": f"{order.scheduled_slot_start}–{order.scheduled_slot_end}",
    })

    print(f"✅ Driver #{driver.id} assigned to scheduled order #{order_id}")