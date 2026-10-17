from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from orders.models import DeliveryAssignment, Order


class DeliveryOtpTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="password",
            phone="1111111111",
            role="CUSTOMER",
        )
        self.driver = User.objects.create_user(
            username="driver",
            email="driver@example.com",
            password="password",
            phone="2222222222",
            role="DELIVERY",
        )
        self.order = Order.objects.create(user=self.customer, total_amount="10.00")
        DeliveryAssignment.objects.create(order=self.order, driver=self.driver)

    def test_customer_order_detail_includes_delivery_otp(self):
        client = APIClient()
        client.force_authenticate(user=self.customer)

        response = client.get(f"/api/orders/{self.order.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["delivery_otp"], self.order.delivery_otp)
        self.assertRegex(response.data["delivery_otp"], r"^\d{6}$")

    def test_assigned_driver_can_verify_delivery_otp(self):
        client = APIClient()
        client.force_authenticate(user=self.driver)

        response = client.post(
            f"/api/orders/{self.order.id}/otp/verify/",
            {"otp": self.order.delivery_otp},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.delivery_otp_verified)

    def test_assigned_driver_cannot_verify_invalid_otp(self):
        client = APIClient()
        client.force_authenticate(user=self.driver)

        response = client.post(
            f"/api/orders/{self.order.id}/otp/verify/",
            {"otp": "000000" if self.order.delivery_otp != "000000" else "111111"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.delivery_otp_verified)
