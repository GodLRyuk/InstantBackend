from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Coupon, DeliveryPass


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
                "pass_members_only": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        coupon = Coupon.objects.get(pk=response.data["id"])
        self.assertEqual(coupon.code, "WELCOME10")
        self.assertEqual(coupon.coupon_type, "PERCENTAGE")
        self.assertEqual(coupon.value, 10)
        self.assertTrue(coupon.pass_members_only)

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

    def test_regular_coupon_can_be_used_without_a_delivery_pass(self):
        customer = get_user_model().objects.create_user(
            username="regular-coupon-customer",
            phone="1000000002",
            role="CUSTOMER",
        )
        Coupon.objects.create(
            code="WELCOME10",
            coupon_type="PERCENTAGE",
            value="10.00",
        )
        self.client.force_authenticate(customer)

        response = self.client.post(
            "/api/promotions/validate-coupon/",
            {"code": "WELCOME10", "order_total": "400.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["discount"], 40.0)

    def test_pass_only_coupon_is_rejected_without_active_pass(self):
        customer = get_user_model().objects.create_user(
            username="pass-only-coupon-customer",
            phone="1000000003",
            role="CUSTOMER",
        )
        Coupon.objects.create(
            code="PASS10",
            coupon_type="PERCENTAGE",
            value="10.00",
            pass_members_only=True,
        )
        self.client.force_authenticate(customer)

        response = self.client.post(
            "/api/promotions/validate-coupon/",
            {"code": "PASS10", "order_total": "400.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_pass_only_coupon_can_be_used_with_active_pass(self):
        customer = get_user_model().objects.create_user(
            username="active-pass-customer",
            phone="1000000004",
            role="CUSTOMER",
        )
        DeliveryPass.objects.create(
            user=customer,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Coupon.objects.create(
            code="PASS10",
            coupon_type="PERCENTAGE",
            value="10.00",
            pass_members_only=True,
        )
        self.client.force_authenticate(customer)

        response = self.client.post(
            "/api/promotions/validate-coupon/",
            {"code": "PASS10", "order_total": "400.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_coupon_discount_uses_model_fields(self):
        percentage_coupon = Coupon.objects.create(
            code="TENPERCENT",
            coupon_type="PERCENTAGE",
            value="10.00",
        )
        fixed_coupon = Coupon.objects.create(
            code="TENRUPEES",
            coupon_type="FIXED",
            value="10.00",
        )

        self.assertEqual(
            percentage_coupon.calculate_discount("125.00"), Decimal("12.50")
        )
        self.assertEqual(fixed_coupon.calculate_discount("125.00"), Decimal("10.00"))
