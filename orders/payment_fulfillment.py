import logging
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from requests import HTTPError

from orders.models import (
    CashfreeCheckoutIntent,
    CheckoutStockReservation,
    DeliveryAssignment,
    Order,
    OrderItem,
)
from orders.services.driver_assignment import assign_driver
from orders.utils import notify_driver
from promotions.models import Coupon, CouponUsage, DeliveryPass
from products.models import Product
from payments import cashfree
from stock.models import Inventory, StockBatch

logger = logging.getLogger(__name__)


class CheckoutUnavailable(ValueError):
    pass


class CheckoutInitializationError(ValueError):
    pass


Status = CashfreeCheckoutIntent.Status
CHECKOUT_TTL = timedelta(minutes=20)
RECONCILE_DELAY = timedelta(minutes=1)
LATE_PAYMENT_WINDOW = timedelta(hours=24)


@transaction.atomic
def reserve_cashfree_stock(user, amount, checkout_data):
    expires_at = (timezone.now() + CHECKOUT_TTL).replace(microsecond=0)
    checkout = CashfreeCheckoutIntent.objects.create(
        user=user, cashfree_order_id=f"cf_{uuid4().hex}", amount=amount,
        checkout_data=checkout_data, expires_at=expires_at,
        reconcile_at=timezone.now() + RECONCILE_DELAY,
    )
    for item in sorted(checkout_data["items"], key=lambda item: item["product_id"]):
        product = Product.objects.select_for_update().filter(pk=item["product_id"], is_active=True).first()
        inventory = Inventory.objects.select_for_update().filter(product=product).first()
        quantity = item["quantity"]
        if inventory is None or inventory.available_stock() < quantity:
            name = product.name if product else "this product"
            raise CheckoutUnavailable(f"Insufficient stock for {name}")
        inventory.reserved_stock += quantity
        inventory.save(update_fields=["reserved_stock", "updated_at"])
        CheckoutStockReservation.objects.create(checkout=checkout, inventory=inventory, quantity=quantity)
    return checkout


def open_cashfree_checkout(user, amount, checkout_data):
    checkout = reserve_cashfree_stock(user, amount, checkout_data)
    try:
        response = cashfree.create_order(
            order_id=checkout.cashfree_order_id, expires_at=checkout.expires_at,
            amount=amount, currency="INR", customer_id=user.pk,
            customer_phone=user.phone, customer_email=user.email,
            order_note="Grocery checkout", return_url=settings.CASHFREE_RETURN_URL,
            notify_url=settings.CASHFREE_NOTIFY_URL,
        )
        if response.get("order_id") != checkout.cashfree_order_id or not response.get("payment_session_id"):
            raise ValueError("Cashfree returned an invalid checkout session")
    except Exception as exc:
        # A timed-out request may still have created the provider order.
        if isinstance(exc, HTTPError) and exc.response is not None and exc.response.status_code in {400, 401, 403, 422}:
            try:
                cashfree.get_order(checkout.cashfree_order_id)
            except HTTPError as lookup_error:
                if lookup_error.response is not None and lookup_error.response.status_code == 404:
                    close_unpaid_checkout(checkout.pk)
            except Exception:
                logger.exception("Could not confirm rejection of Cashfree checkout %s", checkout.cashfree_order_id)
        logger.exception("Could not open Cashfree checkout %s", checkout.cashfree_order_id)
        raise CheckoutInitializationError("Unable to initialize Cashfree checkout.") from exc

    checkout.payment_session_id = response["payment_session_id"]
    if not CashfreeCheckoutIntent.objects.filter(pk=checkout.pk, status=Status.PENDING).update(
        payment_session_id=checkout.payment_session_id,
    ):
        raise CheckoutInitializationError("Cashfree checkout is already closed.")
    return checkout


def release_checkout_stock(checkout):
    for reservation in checkout.reservations.order_by("inventory__product_id"):
        inventory = Inventory.objects.select_for_update().get(pk=reservation.inventory_id)
        if inventory.reserved_stock < reservation.quantity:
            raise RuntimeError(f"Inventory reservation mismatch for checkout {checkout.pk}")
        inventory.reserved_stock -= reservation.quantity
        inventory.save(update_fields=["reserved_stock", "updated_at"])
        reservation.delete()


@transaction.atomic
def close_unpaid_checkout(checkout_id):
    checkout = CashfreeCheckoutIntent.objects.select_for_update().get(pk=checkout_id)
    if checkout.status == Status.PENDING:
        release_checkout_stock(checkout)
        checkout.status = Status.FAILED
        checkout.reconcile_at = timezone.now() + RECONCILE_DELAY if checkout.expires_at else None
        checkout.save(update_fields=["status", "reconcile_at", "updated_at"])
    return checkout.status == Status.FAILED


def reconcile_unpaid_cashfree_order(provider_order_id, *, provider_order=None):
    if provider_order is None:
        provider_order = cashfree.get_order(provider_order_id)
    if provider_order.get("order_status") not in {"EXPIRED", "TERMINATED"}:
        return False

    payments = cashfree.get_payments(provider_order_id)
    if isinstance(payments, dict):
        payments = payments.get("payments", [])
    final_unpaid_statuses = {"FAILED", "USER_DROPPED", "CANCELLED", "VOID", "NOT_ATTEMPTED"}
    if any(payment.get("payment_status") not in final_unpaid_statuses for payment in payments):
        return False

    with transaction.atomic():
        intent = CashfreeCheckoutIntent.objects.select_for_update().filter(
            cashfree_order_id=provider_order_id,
        ).first()
        if intent:
            return close_unpaid_checkout(intent.pk)

        order = Order.objects.select_for_update().filter(
            cashfree_order_id=provider_order_id,
        ).first()
        if not order or order.payment_status == "PAID":
            return False
        if order.order_status == "CANCELLED":
            return True
        return order.mark_failed()


@transaction.atomic
def finalize_cashfree_checkout(intent_id, payment):
    intent = CashfreeCheckoutIntent.objects.select_for_update().get(pk=intent_id)
    if intent.order_id:
        return intent.order
    if intent.status not in {Status.PENDING, Status.FAILED}:
        return None

    try:
        if intent.status == Status.FAILED or not intent.user_id:
            raise CheckoutUnavailable("The checkout has closed")
        if not cashfree.payment_matches(payment, amount=intent.amount):
            raise CheckoutUnavailable("The payment amount or currency does not match the checkout")
        with transaction.atomic():
            return create_paid_order(intent, payment)
    except (CheckoutUnavailable, Product.DoesNotExist, Inventory.DoesNotExist) as exc:
        logger.warning("Cashfree checkout %s requires a refund: %s", intent.cashfree_order_id, exc)
        release_checkout_stock(intent)
        intent.refund_amount = Decimal(str(payment["payment_amount"]))
        intent.status = Status.REFUND_PENDING
        intent.reconcile_at = timezone.now()
        intent.save(update_fields=["refund_amount", "status", "reconcile_at", "updated_at"])
        return None


def create_paid_order(intent, payment):
    reservations = {reservation.inventory_id: reservation for reservation in intent.reservations.all()}
    data = intent.checkout_data
    if data["pass_used"]:
        try:
            delivery_pass = DeliveryPass.objects.select_for_update().get(user=intent.user)
        except DeliveryPass.DoesNotExist:
            raise CheckoutUnavailable("The delivery pass used for this checkout is no longer available")
        delivery_pass.use_free_delivery()

    order = Order.objects.create(
        user=intent.user,
        total_amount=intent.amount,
        coupon_id=Coupon.objects.filter(pk=data["coupon_id"]).values_list("pk", flat=True).first(),
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

    for item in sorted(data["items"], key=lambda item: item["product_id"]):
        product = Product.objects.select_for_update().get(pk=item["product_id"])
        inventory = Inventory.objects.select_for_update().get(product=product)
        quantity = item["quantity"]
        reservation = reservations.get(inventory.pk)
        if intent.expires_at and (
            reservation is None or reservation.quantity != quantity or inventory.reserved_stock < quantity
        ):
            raise CheckoutUnavailable(f"Missing stock reservation for {product.name}")
        if inventory.available_stock() + (reservation.quantity if reservation else 0) < quantity:
            raise CheckoutUnavailable(f"Insufficient stock for {product.name}")

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
        if reservation:
            inventory.reserved_stock -= quantity
            reservation.delete()
        inventory.save(update_fields=["total_stock", "reserved_stock", "updated_at"])
        price = Decimal(item["price"])
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            price=price,
            total_price=price * quantity,
            batch=batch,
        )

    if order.coupon_id and order.coupon.one_time_per_user:
        CouponUsage.objects.get_or_create(coupon=order.coupon, user=intent.user)

    order.mark_paid()
    intent.order = order
    intent.status = CashfreeCheckoutIntent.Status.PAID
    intent.reconcile_at = None
    intent.save(update_fields=["order", "status", "reconcile_at", "updated_at"])
    return order


def sync_cashfree_checkout(checkout):
    if checkout.status in {Status.PENDING, Status.FAILED}:
        try:
            provider_order = cashfree.get_order(checkout.cashfree_order_id)
        except HTTPError as exc:
            if not (
                exc.response is not None and exc.response.status_code == 404
                and not checkout.payment_session_id and checkout.expires_at
                and checkout.expires_at <= timezone.now()
            ):
                raise
            close_unpaid_checkout(checkout.pk)
        else:
            payment = cashfree.success_payment(checkout.cashfree_order_id, order=provider_order)
            if payment:
                order = finalize_cashfree_checkout(checkout.pk, payment)
                if order:
                    activate_paid_order(order)
            else:
                reconcile_unpaid_cashfree_order(checkout.cashfree_order_id, provider_order=provider_order)
        checkout.refresh_from_db()
    return checkout


def process_checkout_refund(checkout):
    refund_id = f"grocery_{checkout.pk}_{checkout.refund_attempt}"
    if checkout.refund_started:
        result = cashfree.get_refund(checkout.cashfree_order_id, refund_id)
    else:
        try:
            result = cashfree.create_refund(
                checkout.cashfree_order_id, refund_id=refund_id,
                amount=checkout.refund_amount, note="Grocery checkout could not be fulfilled",
            )
        except HTTPError as exc:
            if exc.response is None or exc.response.status_code != 409:
                raise
            result = cashfree.get_refund(checkout.cashfree_order_id, refund_id)

    if isinstance(result, list):
        result = next((refund for refund in result if refund.get("refund_id") == refund_id), {})
    status = str(result.get("refund_status", "")).upper()
    if not status:
        raise ValueError(f"Invalid Cashfree refund response for {refund_id}")
    updates = {"refund_started": True}
    if status == "SUCCESS":
        updates.update(status=Status.REFUNDED, reconcile_at=None)
    elif status in {"FAILED", "CANCELLED", "REJECTED"}:
        if checkout.refund_attempt < 3:
            updates.update(refund_attempt=checkout.refund_attempt + 1, refund_started=False)
        else:
            logger.error("Cashfree refund requires review for %s", checkout.cashfree_order_id)
            updates.update(status=Status.REFUND_FAILED, reconcile_at=None)

    CashfreeCheckoutIntent.objects.filter(
        pk=checkout.pk, status=Status.REFUND_PENDING, refund_attempt=checkout.refund_attempt,
    ).update(**updates, updated_at=timezone.now())


def reconcile_due_checkouts():
    now = timezone.now()
    due = CashfreeCheckoutIntent.objects.filter(reconcile_at__lte=now).order_by("reconcile_at", "pk")
    for checkout in list(due[:50]):
        delay = RECONCILE_DELAY
        if checkout.status == Status.FAILED:
            delay = timedelta(minutes=5)
        if not due.filter(pk=checkout.pk, reconcile_at=checkout.reconcile_at).update(reconcile_at=now + delay):
            continue
        try:
            if checkout.status == Status.REFUND_PENDING:
                process_checkout_refund(checkout)
            else:
                sync_cashfree_checkout(checkout)
                if checkout.status == Status.FAILED and (
                    not checkout.expires_at or checkout.expires_at + LATE_PAYMENT_WINDOW <= now
                ):
                    CashfreeCheckoutIntent.objects.filter(pk=checkout.pk, status=Status.FAILED).update(
                        reconcile_at=None,
                    )
        except Exception:
            logger.exception("Could not reconcile Cashfree checkout %s", checkout.cashfree_order_id)


def activate_paid_order(order):
    if order.delivery_type == "ASAP":
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order.pk)
                if not order.can_fulfill() or DeliveryAssignment.objects.filter(order=order).exists():
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
