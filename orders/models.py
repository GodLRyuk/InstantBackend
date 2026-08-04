from django.db import models
from django.utils import timezone
from products.models import Product
from accounts.models import User
from promotions.models import Coupon
from addresses.models import Address
from stock.models import StockBatch


class Order(models.Model):
    # Coupon & discount
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_signature = models.TextField(null=True, blank=True)
    payment_method = models.CharField(max_length=20, default="RAZORPAY")
    driver_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    driver_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    cash_remitted = models.BooleanField(default=False)

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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
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
    # ---------------------- PAYMENT STATUS METHODS ----------------------

    def mark_paid(self):
        self.payment_status = "PAID"
        if self.order_status == "PENDING":
            self.order_status = "CONFIRMED"
        self.save()

    def mark_failed(self):
        self.payment_status = "FAILED"
        self.save()

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

    def mark_cancelled(self):
        """Cancel order and restore inventory for all items"""
        self.order_status = "CANCELLED"
        for item in self.items.all():
            inventory = item.product.inventory
            inventory.total_stock += item.quantity
            inventory.save()
        self.save()

    # ---------------------- COUPON / DISCOUNT ----------------------

    def apply_coupon(self):
        """Calculate discount from coupon and store it"""
        if self.coupon and self.coupon.is_valid():
            self.discount_amount = self.coupon.calculate_discount(self.total_amount)
            self.total_amount -= self.discount_amount
            self.save()

    def __str__(self):
        return f"Order #{self.id} - {self.user.email}"


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
