from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Coupon


class CouponAdminAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/promotions/admin/coupons/"
        self.admin = get_user_model().objects.create_user(
            username="coupon-admin",
            phone="1000000000",
            role="ADMIN",
            is_staff=True,
        )

    def test_staff_can_create_coupon_for_management_form(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            self.url,
            {
                "code": "  welcome10 ",
                "coupon_type": "PERCENTAGE",
                "value": "10.00",
                "min_order_amount": "100.00",
                "active": True,
                "one_time_per_user": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        coupon = Coupon.objects.get(pk=response.data["id"])
        self.assertEqual(coupon.code, "WELCOME10")
        self.assertEqual(coupon.coupon_type, "PERCENTAGE")
        self.assertEqual(coupon.value, 10)

    def test_non_staff_cannot_manage_coupons(self):
        customer = get_user_model().objects.create_user(
            username="coupon-customer",
            phone="1000000001",
            role="CUSTOMER",
        )
        self.client.force_authenticate(customer)

        response = self.client.post(
            self.url,
            {
                "code": "WELCOME10",
                "coupon_type": "PERCENTAGE",
                "value": "10.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Coupon.objects.filter(code="WELCOME10").exists())
