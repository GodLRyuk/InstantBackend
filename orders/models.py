from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
import secrets
from products.models import Product
from accounts.models import User
from promotions.models import Coupon
from addresses.models import Address
from stock.models import Inventory, StockBatch


def generate_delivery_otp():
    return str(secrets.randbelow(900000) + 100000)


class Order(models.Model):
    ORDER_CHANNEL_CHOICES = [
        ("ONLINE", "Online"),
        ("STORE", "Store"),
    ]

    # Coupon & discount
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_signature = models.TextField(null=True, blank=True)
    cashfree_order_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    cashfree_payment_id = models.CharField(max_length=255, null=True, blank=True)
    payment_method = models.CharField(max_length=20, default="CASHFREE")
    driver_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    driver_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    cash_remitted = models.BooleanField(default=False)
    delivery_otp = models.CharField(max_length=6, default=generate_delivery_otp)
    delivery_otp_verified = models.BooleanField(default=False)

    # Payment status
    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
    ]

    # Order lifecycle status
    ORDER_STATUS_CHOICES = [
        ("PENDING", "Pending"),       # Order created, awaiting payment
        ("CONFIRMED", "Confirmed"),
        ("PACKED", "Packed"),   # Payment received, ready to process
        ("SHIPPED", "Shipped"),       # Order shipped to customer
        ("DELIVERED", "Delivered"),   # Order delivered successfully
        ("CANCELLED", "Cancelled"),   # Order cancelled
    ]
    # ---------------------- DELIVERY SCHEDULING ----------------------
    DELIVERY_TYPE_CHOICES = [
        ("ASAP", "As Soon As Possible"),
        ("SCHEDULED", "Scheduled"),
    ]

    delivery_type = models.CharField(
        max_length=10,
        choices=DELIVERY_TYPE_CHOICES,
        default="ASAP"
    )
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_slot_start = models.TimeField(null=True, blank=True)
    scheduled_slot_end = models.TimeField(null=True, blank=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
    )
    order_channel = models.CharField(
        max_length=10,
        choices=ORDER_CHANNEL_CHOICES,
        default="ONLINE",
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="PENDING"
    )

    order_status = models.CharField(
        max_length=20,
        choices=ORDER_STATUS_CHOICES,
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    address_snapshot = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=['order_status', 'payment_status', 'created_at'],
                name='orders_sales_status_date_idx',
            ),
        ]

    # ---------------------- PAYMENT STATUS METHODS ----------------------

    def mark_paid(self):
        self.payment_status = "PAID"
        if self.order_status == "PENDING":
            self.order_status = "CONFIRMED"
        self.save()

    def mark_failed(self):
        return self.mark_cancelled(payment_failed=True)

    def mark_pending(self):
        self.payment_status = "PENDING"
        self.save()

    # ---------------------- ORDER LIFECYCLE METHODS ----------------------

    def mark_shipped(self):
        self.order_status = "SHIPPED"
        self.save()

    def mark_delivered(self):
        self.order_status = "DELIVERED"
        self.save()

    @transaction.atomic
    def mark_cancelled(self, *, payment_failed=False):
        order = Order.objects.select_for_update().get(pk=self.pk)
        if order.order_status in {"CANCELLED", "SHIPPED", "DELIVERED"} or order.payment_status == "PAID":
            return False

        for item in order.items.order_by("product_id", "pk"):
            Inventory.objects.filter(product_id=item.product_id).update(
                total_stock=F("total_stock") + item.quantity,
                updated_at=timezone.now(),
            )
            if item.batch_id:
                StockBatch.objects.filter(pk=item.batch_id).update(
                    quantity=F("quantity") + item.quantity,
                )

        order.order_status = "CANCELLED"
        if payment_failed:
            order.payment_status = "FAILED"
        order.save(update_fields=["order_status", "payment_status", "updated_at"])
        self.order_status = order.order_status
        self.payment_status = order.payment_status
        return True

    def can_fulfill(self):
        return (
            self.order_status != "CANCELLED"
            and self.payment_status != "FAILED"
            and (self.payment_method in {"COD", "UPI"} or self.payment_status == "PAID")
        )

    # ---------------------- COUPON / DISCOUNT ----------------------

    def apply_coupon(self):
        """Calculate discount from coupon and store it"""
        if self.coupon and self.coupon.is_valid():
            self.discount_amount = self.coupon.calculate_discount(self.total_amount)
            self.total_amount -= self.discount_amount
            self.save()

    def __str__(self):
        customer = self.user.email if self.user else "Walk-in"
        return f"Order #{self.id} - {customer}"


class CashfreeCheckoutIntent(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        REFUND_PENDING = "REFUND_PENDING", "Refund pending"
        REFUNDED = "REFUNDED", "Refunded"
        REFUND_FAILED = "REFUND_FAILED", "Refund failed"

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cashfree_checkout_intents",
    )
    cashfree_order_id = models.CharField(max_length=255, unique=True)
    payment_session_id = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reconcile_at = models.DateTimeField(null=True, blank=True, db_index=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refund_attempt = models.PositiveIntegerField(default=1)
    refund_started = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    checkout_data = models.JSONField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    order = models.OneToOneField(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cashfree_checkout_intent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cashfree checkout {self.cashfree_order_id} ({self.status})"


class CheckoutStockReservation(models.Model):
    checkout = models.ForeignKey(
        CashfreeCheckoutIntent, on_delete=models.PROTECT, related_name="reservations",
    )
    inventory = models.ForeignKey(Inventory, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["checkout", "inventory"], name="unique_checkout_inventory_reservation",
            ),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    
    # ✅ NEW — which batch this item was pulled from
    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items'
    )

class DeliveryAssignment(models.Model):
    order = models.ForeignKey("Order", on_delete=models.CASCADE)
    driver = models.ForeignKey(User, on_delete=models.CASCADE)

    STATUS_CHOICES = (
        ("ASSIGNED", "Assigned"),
        ("PICKED_UP", "Picked Up"),
        ("OUT_FOR_DELIVERY", "Out for Delivery"),
        ("DELIVERED", "Delivered"),
    )

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="ASSIGNED")

    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order_id} -> {self.driver_id}"
class CashRemittance(models.Model):
    STATUS_CHOICES = (
        ("CONFIRMED", "Confirmed"),
        ("DISCREPANCY", "Discrepancy"),
    )
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="remittances")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)     # sum of selected orders
    amount_received = models.DecimalField(max_digits=10, decimal_places=2)  # what admin actually counted
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="recorded_remittances")
    recorded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Remittance #{self.id} - {self.driver.username} - ₹{self.amount_received}"


class CashRemittanceItem(models.Model):
    remittance = models.ForeignKey(CashRemittance, on_delete=models.CASCADE, related_name="items")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="remittance_items")

    class Meta:
        unique_together = ("remittance", "order")
