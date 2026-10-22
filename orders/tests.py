from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from masters.models import Category, SubCategory, Unit
from orders.models import DeliveryAssignment, Order, OrderItem
from orders.serializers import OrderItemSerializer
from products.models import Product


class OrderItemSerializerTests(TestCase):
    def test_order_item_includes_product_subcategory(self):
        user = User.objects.create_user(
            username="order-customer",
            email="order-customer@example.com",
            password="test-password",
            phone="3333333333",
            role="CUSTOMER",
        )
        category = Category.objects.create(name="Food")
        subcategory = SubCategory.objects.create(name="Dairy", category=category)
        unit = Unit.objects.create(name="Piece", short_name="pc")
        product = Product.objects.create(
            name="Butter",
            category=category,
            subcategory=subcategory,
            unit=unit,
            price="19.20",
        )
        order = Order.objects.create(user=user, total_amount="19.20")
        item = OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            price="19.20",
            total_price="19.20",
        )

        data = OrderItemSerializer(item).data

        self.assertEqual(data["subcategory"], subcategory.id)
        self.assertEqual(data["subcategory_id"], subcategory.id)
        self.assertEqual(data["subcategory_name"], "Dairy")


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
