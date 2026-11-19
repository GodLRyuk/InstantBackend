from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from requests import HTTPError, Response as HTTPResponse, Timeout
from rest_framework.test import APIClient
from unittest.mock import patch

from accounts.models import User
from addresses.models import Address
from masters.models import Category, SubCategory, Unit
from orders.models import (
    CashfreeCheckoutIntent,
    DeliveryAssignment,
    Order,
    OrderItem,
)
from orders.payment_fulfillment import reconcile_due_checkouts
from orders.serializers import OrderItemSerializer
from products.models import Product
from promotions.models import DeliverySettings
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

        with (
            patch("payments.cashfree.success_payment", return_value=None),
            patch("payments.cashfree.get_order", return_value={"order_status": "ACTIVE"}),
        ):
            response = client.post(
                "/api/verify-payment/",
                {"cashfree_order_id": "cf-pending-order"},
                format="json",
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["payment_status"], "PENDING")
        self.assertFalse(Order.objects.exists())


class GroceryCheckoutFixture:
    def setUp(self):
        self.customer = User.objects.create_user(
            username="grocery-customer", phone="4444444444", role="CUSTOMER",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.customer)
        category = Category.objects.create(name="Groceries")
        subcategory = SubCategory.objects.create(name="Fruit", category=category)
        self.product = Product.objects.create(
            name="Apple", category=category, subcategory=subcategory, price="10.00",
        )
        self.inventory = self.product.inventory
        self.inventory.total_stock = 5
        self.inventory.save()
        self.batch = StockBatch.objects.create(
            product=self.product, batch_no="apple", quantity=5,
            purchase_price="5.00", selling_price="10.00",
        )
        address = Address.objects.create(
            user=self.customer, full_address="Test address", pincode="741159",
        )
        self.payload = {"address_id": address.pk, "payment_method": "COD"}

    def assert_stock(self, quantity):
        self.inventory.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.inventory.total_stock, quantity)
        self.assertEqual(self.batch.quantity, quantity)


class GroceryCheckoutTests(GroceryCheckoutFixture, TestCase):
    def test_checkout_uses_server_price_and_cancellation_restores_stock_once(self):
        self.payload.update({
            "items": [{"product": self.product.pk, "quantity": 2, "price": "0.01"}],
            "total_amount": "0.01",
        })
        with patch("orders.serializers.validate_user_location", return_value={"valid": True, "distance_km": 1}):
            response = self.client.post("/api/orders/create/", self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        self.assertEqual(order.items.get().total_price, Decimal("20.00"))
        self.assertEqual(order.total_amount, Decimal("20.00") + order.delivery_fee)
        self.assert_stock(3)

        for _ in range(2):
            response = self.client.post(f"/api/orders/{order.pk}/cancel/")
            self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "CANCELLED")
        self.assert_stock(5)

    def test_checkout_rejects_nonpositive_quantities(self):
        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                self.payload["items"] = [{"product": self.product.pk, "quantity": quantity}]
                response = self.client.post("/api/orders/create/", self.payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())
        self.assert_stock(5)

    def test_cashfree_checks_combined_quantity_before_creating_payment_session(self):
        self.payload.update({
            "payment_method": "CASHFREE",
            "items": [{"product": self.product.pk, "quantity": 3}] * 2,
        })
        with patch("payments.cashfree.create_order") as create_payment:
            response = self.client.post("/api/orders/create/", self.payload, format="json")

        self.assertEqual(response.status_code, 400)
        create_payment.assert_not_called()
        self.assert_stock(5)

    def test_expired_legacy_payment_cancels_order_and_restores_stock(self):
        order = Order.objects.create(
            user=self.customer, total_amount="10.00", cashfree_order_id="legacy-cashfree",
        )
        order.items.create(
            product=self.product, batch=self.batch, quantity=1, price="10.00", total_price="10.00",
        )
        Inventory.objects.filter(pk=self.inventory.pk).update(total_stock=4)
        StockBatch.objects.filter(pk=self.batch.pk).update(quantity=4)

        with (
            patch("payments.cashfree.success_payment", return_value=None),
            patch("payments.cashfree.get_order", return_value={"order_status": "EXPIRED"}),
            patch("payments.cashfree.get_payments", return_value=[{"payment_status": "PENDING"}]) as payments,
        ):
            for payment_status in ("PENDING", "FAILED", "FAILED"):
                payments.return_value = [{"payment_status": payment_status}]
                response = self.client.post(
                    "/api/verify-payment/", {"cashfree_order_id": order.cashfree_order_id}, format="json",
                )
                self.assertEqual(response.data["payment_status"], payment_status)
                self.assert_stock(4 if payment_status == "PENDING" else 5)
        order.refresh_from_db()
        self.assertEqual(order.order_status, "CANCELLED")
        self.assertEqual(order.payment_status, "FAILED")

    def test_customers_cannot_change_batch_prices_or_adjust_stock(self):
        response = self.client.put(
            f"/api/stock/update/{self.batch.pk}/", {"selling_price": "0.01"}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/api/stock/adjustments/", {
            "batch": self.batch.pk, "adjust_type": "OUT", "reason": "OTHER", "quantity": 1,
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assert_stock(5)

class CashfreeReservationTests(GroceryCheckoutFixture, TestCase):
    def create_checkout(self, quantity=5):
        self.payload.update({
            "payment_method": "CASHFREE",
            "items": [{"product": self.product.pk, "quantity": quantity}],
        })
        with (
            patch("orders.serializers.validate_user_location", return_value={"valid": True, "distance_km": 1}),
            patch("payments.cashfree.create_order", side_effect=lambda **kwargs: {
                "order_id": kwargs["order_id"], "payment_session_id": "cashfree-session",
            }) as create,
        ):
            response = self.client.post("/api/orders/create/", self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        intent = CashfreeCheckoutIntent.objects.get(cashfree_order_id=response.data["cashfree_order_id"])
        self.assertEqual(create.call_args.kwargs["expires_at"], intent.expires_at)
        return intent

    def verify(self, checkout):
        return self.client.post("/api/verify-payment/", {
            "cashfree_order_id": checkout.cashfree_order_id,
        }, format="json")

    def payment(self, checkout):
        return {
            "payment_status": "SUCCESS",
            "payment_currency": "INR",
            "payment_amount": str(checkout.amount),
            "cf_payment_id": "payment-1",
        }

    def run_reconciler(self, checkout):
        CashfreeCheckoutIntent.objects.filter(pk=checkout.pk).update(reconcile_at=timezone.now())
        reconcile_due_checkouts()
        checkout.refresh_from_db()

    def test_verified_payment_converts_reservation_and_creates_one_order(self):
        checkout = self.create_checkout()
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.available_stock(), 0)
        self.assert_stock(5)
        self.assertFalse(Order.objects.exists())

        with (
            patch("payments.cashfree.get_order", return_value={"order_status": "PAID"}),
            patch("payments.cashfree.get_payments", return_value=[self.payment(checkout)]),
            patch("payments.cashfree.verify_webhook", return_value=True),
        ):
            webhook = APIClient().post("/api/payments/cashfree/webhook/", {
                "data": {"order": {"order_id": checkout.cashfree_order_id}},
            }, format="json")
            self.assertEqual(webhook.status_code, 200)
            first = self.verify(checkout)
            retry = self.verify(checkout)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.data, retry.data)

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().payment_status, "PAID")
        self.assert_stock(0)
        self.assertEqual(self.inventory.reserved_stock, 0)

    def test_expired_checkout_keeps_pending_payment_then_releases_stock(self):
        checkout = self.create_checkout()
        with (
            patch("payments.cashfree.get_order", return_value={"order_status": "EXPIRED"}),
            patch("payments.cashfree.get_payments", return_value=[{"payment_status": "PENDING"}]) as payments,
        ):
            self.run_reconciler(checkout)
            self.assertEqual(checkout.status, "PENDING")
            self.inventory.refresh_from_db()
            self.assertEqual(self.inventory.reserved_stock, 5)
            payments.return_value = [{"payment_status": "USER_DROPPED"}]
            self.run_reconciler(checkout)
            self.run_reconciler(checkout)

        self.assertEqual(checkout.status, "FAILED")
        self.assertFalse(Order.objects.exists())
        self.assert_stock(5)
        self.assertEqual(self.inventory.reserved_stock, 0)

    def test_late_payment_is_refunded_using_same_id_after_timeout(self):
        checkout = self.create_checkout()
        with (
            patch("payments.cashfree.get_order", return_value={"order_status": "TERMINATED"}),
            patch("payments.cashfree.get_payments", return_value=[]),
        ):
            self.run_reconciler(checkout)

        with (
            patch("payments.cashfree.get_order", return_value={"order_status": "PAID"}),
            patch("payments.cashfree.get_payments", return_value=[self.payment(checkout)]),
        ):
            self.assertEqual(self.verify(checkout).data["payment_status"], "REFUND_PENDING")

        with (
            patch("payments.cashfree.create_refund", side_effect=[Timeout(), {"refund_status": "PENDING"}]) as create,
            patch("payments.cashfree.get_refund", return_value={"refund_status": "SUCCESS"}) as get,
        ):
            for _ in range(3):
                self.run_reconciler(checkout)
            self.assertEqual(create.call_count, 2)
            refund_id = create.call_args.kwargs["refund_id"]
            self.assertEqual(create.call_args_list[0].kwargs["refund_id"], refund_id)
            self.assertEqual(create.call_args.kwargs["amount"], checkout.amount)
            get.assert_called_once_with(checkout.cashfree_order_id, refund_id)

        self.assertEqual(checkout.status, "REFUNDED")
        self.assertFalse(Order.objects.exists())
        self.assert_stock(5)
        self.assertEqual(self.inventory.reserved_stock, 0)

    def test_unknown_session_creation_keeps_stock_until_provider_confirms_absence(self):
        self.payload.update({
            "payment_method": "CASHFREE",
            "items": [{"product": self.product.pk, "quantity": 5}],
        })
        with (
            patch("orders.serializers.validate_user_location", return_value={"valid": True, "distance_km": 1}),
            patch("payments.cashfree.create_order", side_effect=Timeout()),
        ):
            response = self.client.post("/api/orders/create/", self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        checkout = CashfreeCheckoutIntent.objects.get()
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.reserved_stock, 5)
        CashfreeCheckoutIntent.objects.filter(pk=checkout.pk).update(expires_at=timezone.now())
        missing = HTTPResponse()
        missing.status_code = 404
        with patch("payments.cashfree.get_order", side_effect=HTTPError(response=missing)):
            self.run_reconciler(checkout)
        self.assertEqual(checkout.status, "FAILED")
        self.assert_stock(5)
        self.assertEqual(self.inventory.reserved_stock, 0)


class ConcurrentGroceryCheckoutTests(GroceryCheckoutFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_ten_cod_customers_cannot_buy_more_than_five_units(self):
        self.assert_concurrent_stock_limit(["COD"] * 10)

    @skipUnlessDBFeature("has_select_for_update")
    def test_ten_cashfree_customers_can_open_only_five_sessions(self):
        self.assert_concurrent_stock_limit(["CASHFREE"] * 10)

    @skipUnlessDBFeature("has_select_for_update")
    def test_mixed_cashfree_and_cod_share_the_same_stock_limit(self):
        self.assert_concurrent_stock_limit(["CASHFREE", "COD"] * 5)

    def assert_concurrent_stock_limit(self, payment_methods):
        DeliverySettings.get()
        checkouts = []
        for index, payment_method in enumerate(payment_methods):
            customer = User.objects.create_user(
                username=f"concurrent-customer-{index}",
                phone=f"555555550{index}",
                role="CUSTOMER",
            )
            address = Address.objects.create(
                user=customer, full_address="Test address", pincode="741159",
            )
            checkouts.append((customer, address.pk, payment_method))
        barrier = Barrier(len(checkouts), timeout=15)

        def validate_location(address):
            barrier.wait()
            return {"valid": True, "distance_km": 1}

        def checkout(checkout_data):
            customer, address_id, payment_method = checkout_data
            try:
                client = APIClient()
                client.force_authenticate(user=customer)
                return client.post("/api/orders/create/", {
                    "address_id": address_id,
                    "payment_method": payment_method,
                    "items": [{"product": self.product.pk, "quantity": 1}],
                }, format="json").status_code
            finally:
                connections.close_all()

        with (
            patch("orders.serializers.validate_user_location", side_effect=validate_location),
            patch("payments.cashfree.create_order", side_effect=lambda **kwargs: {
                "order_id": kwargs["order_id"], "payment_session_id": "cashfree-session",
            }),
            ThreadPoolExecutor(max_workers=len(checkouts)) as pool,
        ):
            results = list(pool.map(checkout, checkouts))

        self.assertCountEqual(results, [201] * 5 + [400] * 5)
        cod_orders = Order.objects.count()
        payment_sessions = CashfreeCheckoutIntent.objects.count()
        self.assertEqual(cod_orders + payment_sessions, 5)
        self.assert_stock(5 - cod_orders)
        self.assertEqual(self.inventory.reserved_stock, payment_sessions)
        self.assertEqual(self.inventory.available_stock(), 0)


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

    def test_store_sales_list_returns_direct_store_sales(self):
        create_response = self.client.post(
            "/api/store/sales/create/",
            {
                "items": [{"product": self.product.id, "quantity": 1}],
                "payment_method": "UPI",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)

        response = self.client.get("/api/store/sales/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], create_response.data["id"])
        self.assertEqual(response.data[0]["items"][0]["product"], self.product.id)
        self.assertFalse(Order.objects.exists())

    def test_existing_orders_default_to_online_channel(self):
        order = Order.objects.create(user=self.seller, total_amount="1.00")

        self.assertEqual(order.order_channel, "ONLINE")
