from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import cashfree
from orders.models import Order
from restaurants.models import RestaurantOrder


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

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                cashfree_order_id=provider_order_id
            ).first()
            if order:
                if Decimal(str(payment.get('payment_amount', 0))) != order.total_amount:
                    return HttpResponse(status=400)
                if order.payment_status != 'PAID':
                    order.cashfree_payment_id = str(payment.get('cf_payment_id', ''))
                    order.mark_paid()
                return HttpResponse(status=200)

            restaurant_order = RestaurantOrder.objects.select_for_update().filter(
                cashfree_order_id=provider_order_id
            ).first()
            if restaurant_order:
                if Decimal(str(payment.get('payment_amount', 0))) != restaurant_order.total_amount:
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
