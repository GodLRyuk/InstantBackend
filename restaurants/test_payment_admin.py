from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import PaymentSplit, Restaurant, RestaurantOrder, RestaurantRefund, RestaurantVendor, VendorCommission


class PaymentAdminTests(TestCase):
    base = '/api/restaurants/admin/'

    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.staff = users.create_user(username='payment-staff', phone='9876543211', is_staff=True)
        cls.customer = users.create_user(username='payment-customer', phone='9876543212')
        cls.restaurant = Restaurant.objects.create(owner=cls.customer, name='Payment test restaurant')
        cls.vendor = RestaurantVendor.objects.create(
            restaurant=cls.restaurant, cashfree_vendor_id='vendor-test',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def order(self, number, **changes):
        fields = {
            'order_number': number, 'cashfree_order_id': f'cf-{number}',
            'customer': self.customer, 'restaurant': self.restaurant,
            'payment_method': RestaurantOrder.PaymentMethod.ONLINE,
            'payment_status': RestaurantOrder.PaymentStatus.PAID,
            'item_total': Decimal('100'), 'total_amount': Decimal('100'),
        }
        return RestaurantOrder.objects.create(**{**fields, **changes})

    def test_endpoints_require_staff(self):
        self.client.force_authenticate(self.customer)
        for path in ['commissions/', 'payment-splits/', 'refunds/']:
            self.assertEqual(self.client.get(self.base + path).status_code, 403)
            self.assertEqual(self.client.post(self.base + path, {}, format='json').status_code, 403)

    def test_commission_validation_and_safe_resubmission(self):
        endpoint = self.base + 'commissions/'
        data = {
            'restaurant': self.restaurant.pk,
            'commission_percentage': '12.50',
            'effective_from': timezone.now().isoformat(),
        }
        self.assertEqual(self.client.post(endpoint, {**data, 'commission_percentage': '101'}).status_code, 400)
        response = self.client.post(endpoint, data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.post(endpoint, data).data['id'], response.data['id'])
        self.assertEqual(self.client.get(endpoint).data[0]['commission_percentage'], '12.50')
        self.assertEqual(VendorCommission.objects.count(), 1)

    @patch('restaurants.services.cashfree.get_order_split_details')
    @patch('restaurants.services.cashfree.submit_order_split')
    def test_split_uses_effective_commission_and_only_submits_selected_order(self, submit, details):
        submit.return_value = {}
        details.return_value = {'vendors': [
            {'vendor_id': self.vendor.cashfree_vendor_id, 'status': 'SETTLED', 'settlement_id': 'settlement-1'},
        ]}
        VendorCommission.objects.create(
            restaurant=self.restaurant, commission_percentage='12.50',
            effective_from=timezone.now() - timedelta(days=1),
        )
        selected = self.order('RO000001')
        other = self.order('RO000002')
        endpoint = self.base + 'payment-splits/'

        for order in [selected, other]:
            response = self.client.post(endpoint, {'order_number': order.order_number})
            self.assertEqual(response.data['status'], 'pending')
            self.assertEqual(response.data['vendor_amount'], '87.50')
        submit.assert_not_called()

        PaymentSplit.objects.update(paid_at=timezone.now() - timedelta(minutes=3))
        response = self.client.post(endpoint, {'order_number': selected.order_number})
        self.assertEqual(response.data['status'], 'submitted')
        submit.assert_called_once_with(
            selected.cashfree_order_id, vendor_id=self.vendor.cashfree_vendor_id, vendor_percentage=Decimal('87.50'),
        )
        self.assertEqual(PaymentSplit.objects.get(order=other).cashfree_split_status, PaymentSplit.Status.PENDING)

        response = self.client.post(endpoint, {'order_number': selected.order_number})
        self.assertEqual(response.data['status'], 'settled')
        self.assertEqual(response.data['provider_reference'], 'settlement-1')
        self.assertEqual(submit.call_count, 1)

    @patch('restaurants.services.cashfree.create_refund')
    def test_refund_uses_full_order_amount_and_stays_idempotent(self, create_refund):
        create_refund.return_value = {'refund_status': 'SUCCESS', 'cf_refund_id': 'cf-123'}
        endpoint = self.base + 'refunds/'
        order = self.order('RO000001')
        self.assertEqual(self.client.post(endpoint, {'order_number': order.order_number}).status_code, 400)
        create_refund.assert_not_called()

        order.status = RestaurantOrder.Status.CANCELLED
        order.payment_status = RestaurantOrder.PaymentStatus.REFUND_PENDING
        order.save()
        for _ in range(2):
            response = self.client.post(endpoint, {'order_number': order.order_number, 'amount': '1'})
            self.assertEqual(response.data['status'], 'success')
            self.assertEqual(response.data['provider_reference'], 'cf-123')
        create_refund.assert_called_once()
        self.assertEqual(create_refund.call_args.kwargs['amount'], Decimal('100'))
        self.assertEqual(RestaurantRefund.objects.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, RestaurantOrder.PaymentStatus.REFUNDED)
