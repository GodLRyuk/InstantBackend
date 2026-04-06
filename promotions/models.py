from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    COUPON_TYPE_CHOICES = [
        ("PERCENTAGE", "Percentage"),
        ("FIXED", "Fixed Amount")
    ]

    code = models.CharField(max_length=50, unique=True)
    coupon_type = models.CharField(max_length=20, choices=COUPON_TYPE_CHOICES)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self):
        """Check if coupon is active and not expired"""
        if not self.active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def calculate_discount(self, order_total):
        """Return the discount amount for a given order_total"""
        if not self.is_valid() or order_total < self.min_order_amount:
            return 0
        if self.coupon_type == "PERCENTAGE":
            return order_total * (self.value / 100)
        return self.value

    def __str__(self):
        return self.code