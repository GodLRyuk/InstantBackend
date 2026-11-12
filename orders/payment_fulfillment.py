import logging
from decimal import Decimal

from django.db import transaction

from orders.models import (
    CashfreeCheckoutIntent,
    DeliveryAssignment,
    Order,
    OrderItem,
)
from orders.services.driver_assignment import assign_driver
from orders.utils import notify_driver
from promotions.models import CouponUsage, DeliveryPass
from products.models import Product
from stock.models import Inventory, StockBatch

logger = logging.getLogger(__name__)


@transaction.atomic
def finalize_cashfree_checkout(intent_id, payment):
    intent = CashfreeCheckoutIntent.objects.select_for_update().get(pk=intent_id)
    if intent.order_id:
        return intent.order
    if intent.status != CashfreeCheckoutIntent.Status.PENDING:
        return None

    data = intent.checkout_data
    order = Order.objects.create(
        user=intent.user,
        total_amount=intent.amount,
        coupon_id=data["coupon_id"],
        discount_amount=Decimal(data["discount_amount"]),
        delivery_fee=Decimal(data["delivery_fee"]),
        cashfree_order_id=intent.cashfree_order_id,
        cashfree_payment_id=str(payment.get("cf_payment_id", "")),
        payment_method="CASHFREE",
        payment_status="PENDING",
        address_snapshot=data["address_snapshot"],
        delivery_type=data["delivery_type"],
        scheduled_date=data["scheduled_date"],
        scheduled_slot_start=data["scheduled_slot_start"],
        scheduled_slot_end=data["scheduled_slot_end"],
    )

    for item in data["items"]:
        product = Product.objects.select_for_update().get(pk=item["product_id"])
        inventory = Inventory.objects.select_for_update().get(product=product)
        quantity = item["quantity"]
        if inventory.available_stock() < quantity:
            raise ValueError(f"Insufficient stock for {product.name}")

        batch = (
            StockBatch.objects.select_for_update()
            .filter(product=product, quantity__gte=quantity)
            .order_by("created_at")
            .first()
        )
        if batch:
            batch.quantity -= quantity
            batch.save(update_fields=["quantity"])

        inventory.total_stock -= quantity
        inventory.save(update_fields=["total_stock", "updated_at"])
        price = Decimal(item["price"])
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            price=price,
            total_price=price * quantity,
            batch=batch,
        )

    if data["pass_used"]:
        try:
            delivery_pass = DeliveryPass.objects.select_for_update().get(user=intent.user)
        except DeliveryPass.DoesNotExist:
            raise ValueError("The delivery pass used for this checkout is no longer available")
        delivery_pass.use_free_delivery()

    if order.coupon_id and order.coupon.one_time_per_user:
        CouponUsage.objects.get_or_create(coupon=order.coupon, user=intent.user)

    order.mark_paid()
    intent.order = order
    intent.status = CashfreeCheckoutIntent.Status.PAID
    intent.save(update_fields=["order", "status", "updated_at"])
    return order


def activate_paid_order(order):
    if order.delivery_type == "ASAP":
        try:
            if DeliveryAssignment.objects.filter(order=order).exists():
                return
            driver = assign_driver(order)
            if not driver:
                logger.warning("No driver available for paid order %s", order.pk)
                return
            assignment, created = DeliveryAssignment.objects.get_or_create(
                order=order,
                defaults={"driver": driver, "status": "ASSIGNED"},
            )
            if created:
                notify_driver(assignment.driver_id, {
                    "order_id": order.id,
                    "order_status": order.order_status,
                    "payment_status": order.payment_status,
                    "total_amount": float(order.total_amount),
                    "customer_name": (
                        f"{order.user.first_name} {order.user.middle_name} "
                        f"{order.user.last_name}"
                    ).strip(),
                    "customer_phone": order.user.phone,
                    "address": order.address_snapshot,
                    "assigned_at": str(assignment.assigned_at),
                    "status": assignment.status,
                })
        except Exception:
            logger.exception("Could not activate paid order %s", order.pk)
