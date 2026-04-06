from django.db import models
from django.utils import timezone
from products.models import Product
from accounts.models import User
from promotions.models import Coupon


class Order(models.Model):
    # Coupon & discount
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Payment status
    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
    ]

    # Order lifecycle status
    ORDER_STATUS_CHOICES = [
        ("PENDING", "Pending"),       # Order created, awaiting payment
        ("CONFIRMED", "Confirmed"),   # Payment received, ready to process
        ("SHIPPED", "Shipped"),       # Order shipped to customer
        ("DELIVERED", "Delivered"),   # Order delivered successfully
        ("CANCELLED", "Cancelled"),   # Order cancelled
    ]

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
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2) 
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"