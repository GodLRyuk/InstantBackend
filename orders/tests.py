from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from accounts.models import User
from masters.models import Category, SubCategory, Unit
from orders.models import (
    CashfreeCheckoutIntent,
    DeliveryAssignment,
    Order,
    OrderItem,
)
from orders.serializers import OrderItemSerializer
from products.models import Product
from stock.models import Inventory, StockBatch
from stock.models import StoreSale


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


class CashfreeCheckoutIntentTests(TestCase):
    def test_unverified_payment_does_not_create_an_order(self):
        customer = User.objects.create_user(
            username="cashfree-customer",
            email="cashfree-customer@example.com",
            password="test-password-123",
            phone="5555555555",
            role="CUSTOMER",
        )
        CashfreeCheckoutIntent.objects.create(
            user=customer,
            cashfree_order_id="cf-pending-order",
            payment_session_id="pending-session",
            amount="80.10",
            checkout_data={},
        )
        client = APIClient()
        client.force_authenticate(user=customer)

        with patch("payments.cashfree.success_payment", return_value=None):
            response = client.post(
                "/api/verify-payment/",
                {"cashfree_order_id": "cf-pending-order"},
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["payment_status"], "PENDING")
        self.assertFalse(Order.objects.exists())


class StoreSaleApiTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username="store-seller",
            email="seller@example.com",
            password="test-password",
            phone="6666666666",
            role="CUSTOMER",
        )
        category = Category.objects.create(name="Store Sale Food")
        subcategory = SubCategory.objects.create(
            name="Store Sale Dairy",
            category=category,
        )
        self.product = Product.objects.create(
            name="Store Sale Milk",
            category=category,
            subcategory=subcategory,
            price="15.00",
        )
        self.inventory = self.product.inventory
        self.inventory.total_stock = 5
        self.inventory.save(update_fields=["total_stock"])
        self.batch = StockBatch.objects.create(
            product=self.product,
            batch_no="STORE-SALE-1",
            quantity=5,
            purchase_price="8.00",
            selling_price="12.50",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.seller)

    def test_store_sale_creates_walk_in_bill_and_deducts_stock(self):
        response = self.client.post(
            "/api/orders/store/create/",
            {
                "items": [{"product": self.product.id, "quantity": 2}],
                "payment_method": "CASH",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        sale = StoreSale.objects.get(pk=response.data["id"])
        self.assertIsNone(sale.customer)
        self.assertEqual(sale.created_by, self.seller)
        self.assertEqual(sale.payment_method, "CASH")
        self.assertEqual(str(sale.total_amount), "25.00")
        self.assertFalse(Order.objects.exists())

        self.inventory.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.inventory.total_stock, 3)
        self.assertEqual(self.batch.quantity, 3)

    def test_store_sale_with_insufficient_stock_does_not_create_bill(self):
        response = self.client.post(
            "/api/orders/store/create/",
            {
                "items": [{"product": self.product.id, "quantity": 6}],
                "payment_method": "UPI",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StoreSale.objects.exists())
        self.assertFalse(Order.objects.exists())
        self.inventory.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.inventory.total_stock, 5)
        self.assertEqual(self.batch.quantity, 5)

    def test_existing_orders_default_to_online_channel(self):
        order = Order.objects.create(user=self.seller, total_amount="1.00")

        self.assertEqual(order.order_channel, "ONLINE")
