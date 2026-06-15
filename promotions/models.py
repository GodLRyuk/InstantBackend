from django.db import models
from django.utils import timezone
from django.conf import settings


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
    one_time_per_user = models.BooleanField(default=False)

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
class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('coupon', 'user')  # prevents duplicate entries

class DeliveryPass(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='delivery_pass'
    )
    amount_paid    = models.DecimalField(max_digits=10, decimal_places=2, default=1499)
    purchased_at   = models.DateTimeField(auto_now_add=True)
    expires_at     = models.DateTimeField()
    is_active      = models.BooleanField(default=True)
    free_deliveries_used = models.PositiveIntegerField(default=0)  # resets monthly
    last_reset_month     = models.PositiveIntegerField(null=True, blank=True)
    last_reset_year      = models.PositiveIntegerField(null=True, blank=True)

    FREE_DELIVERY_CAP    = 20
    MIN_ORDER_DELIVERY   = 149   # min subtotal for free delivery
    MIN_ORDER_COUPON     = 299   # min subtotal to unlock coupon

    def is_valid(self):
        return self.is_active and timezone.now() < self.expires_at

    def reset_monthly_count_if_needed(self):
        now = timezone.now()
        if (self.last_reset_month != now.month or 
            self.last_reset_year != now.year):
            self.free_deliveries_used = 0
            self.last_reset_month = now.month
            self.last_reset_year = now.year
            self.save()

    def can_use_free_delivery(self):
        self.reset_monthly_count_if_needed()
        return (
            self.is_valid() and 
            self.free_deliveries_used < self.FREE_DELIVERY_CAP
        )

    def use_free_delivery(self):
        self.free_deliveries_used += 1
        self.save()

    def can_use_coupon(self, order_subtotal):
        return self.is_valid() and order_subtotal >= self.MIN_ORDER_COUPON

    def __str__(self):
        return f"Pass({self.user.email}) expires {self.expires_at.date()}"
    
class DeliverySettings(models.Model):
    delivery_fee        = models.DecimalField(max_digits=6, decimal_places=2, default=40)
    free_delivery_min   = models.DecimalField(max_digits=6, decimal_places=2, default=149)
    coupon_unlock_min   = models.DecimalField(max_digits=6, decimal_places=2, default=299)
    pass_price          = models.DecimalField(max_digits=6, decimal_places=2, default=1499)
    free_delivery_cap   = models.PositiveIntegerField(default=20)  # per month

    class Meta:
        verbose_name = "Delivery Settings"

    def save(self, *args, **kwargs):
        # Always keep only one row
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Delivery Settings"