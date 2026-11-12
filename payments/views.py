import logging

from django.db import transaction
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import cashfree
from orders.models import CashfreeCheckoutIntent, Order
from orders.payment_fulfillment import (
    activate_paid_order,
    finalize_cashfree_checkout,
)
from restaurants.models import RestaurantOrder

logger = logging.getLogger(__name__)


class CashfreeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = []

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get('x-webhook-signature', '')
        timestamp = request.headers.get('x-webhook-timestamp', '')
        if not cashfree.verify_webhook(raw_body, timestamp, signature):
            return HttpResponse(status=400)
        try:
            payload = cashfree.parse_webhook(raw_body)
            provider_order_id = payload['data']['order']['order_id']
        except (ValueError, KeyError, TypeError):
            return HttpResponse(status=400)

        # Query Cashfree directly before marking an order paid. A webhook alone
        # is an authenticated notification, but the API confirms state and amount.
        try:
            payment = cashfree.success_payment(provider_order_id)
        except Exception:
            return HttpResponse(status=503)
        if not payment:
            return HttpResponse(status=200)

        intent = CashfreeCheckoutIntent.objects.filter(
            cashfree_order_id=provider_order_id
        ).first()
        if intent:
            if not cashfree.payment_matches(payment, amount=intent.amount):
                return HttpResponse(status=400)
            try:
                order = finalize_cashfree_checkout(intent.pk, payment)
                if order:
                    activate_paid_order(order)
            except Exception:
                logger.exception(
                    'Could not finalize paid Cashfree checkout %s',
                    provider_order_id,
                )
                return HttpResponse(status=503)
            return HttpResponse(status=200)

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                cashfree_order_id=provider_order_id
            ).first()
            if order:
                if not cashfree.payment_matches(payment, amount=order.total_amount):
                    return HttpResponse(status=400)
                if order.payment_status != 'PAID':
                    order.cashfree_payment_id = str(payment.get('cf_payment_id', ''))
                    order.mark_paid()
                return HttpResponse(status=200)

            restaurant_order = RestaurantOrder.objects.select_for_update().filter(
                cashfree_order_id=provider_order_id
            ).first()
            if restaurant_order:
                if not cashfree.payment_matches(
                    payment,
                    amount=restaurant_order.total_amount,
                ):
                    return HttpResponse(status=400)
                if restaurant_order.payment_status != RestaurantOrder.PaymentStatus.PAID:
                    restaurant_order.cashfree_payment_id = str(payment.get('cf_payment_id', ''))
                    restaurant_order.payment_status = RestaurantOrder.PaymentStatus.PAID
                    if restaurant_order.status == RestaurantOrder.Status.AWAITING_PAYMENT:
                        restaurant_order.status = RestaurantOrder.Status.PLACED
                        from restaurants.services import notify_restaurant_owner_order_placed
                        notify_restaurant_owner_order_placed(restaurant_order)
                    restaurant_order.save()
                return HttpResponse(status=200)
        # Unknown IDs are acknowledged to avoid pointless webhook retries.
        return HttpResponse(status=200)
