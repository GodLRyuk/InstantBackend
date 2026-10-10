from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .utils import haversine_km


class Cuisine(models.Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Restaurant(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        SUSPENDED = 'suspended', 'Suspended'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='restaurants'
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    cuisines = models.ManyToManyField(Cuisine, blank=True, related_name='restaurants')

    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=80)
    pincode = models.CharField(max_length=10, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    fssai_number = models.CharField(max_length=20, blank=True)

    logo = models.ImageField(upload_to='restaurants/logos/', null=True, blank=True)
    cover_image = models.ImageField(upload_to='restaurants/covers/', null=True, blank=True)

    opens_at = models.TimeField(default=time(10, 0))
    closes_at = models.TimeField(default=time(22, 0))
    is_accepting_orders = models.BooleanField(default=True)  # owner "pause" switch
    avg_prep_minutes = models.PositiveSmallIntegerField(default=30)

    # Set by Instant (admin), not by the restaurant
    delivery_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('25'))
    delivery_radius_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('8'))
    min_order_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))

    # Restaurant-wide offer, e.g. 30% off up to Rs 75
    offer_percent = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(90)]
    )
    offer_max_discount = models.PositiveIntegerField(default=0)  # 0 = no cap
    offer_min_order = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    offer_code = models.CharField(max_length=30, blank=True)

    rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal('0'))
    rating_count = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_open_now(self):
        if self.status != self.Status.APPROVED or not self.is_accepting_orders:
            return False
        now = timezone.localtime().time()
        o, c = self.opens_at, self.closes_at
        if o == c:
            return True  # treated as open 24 hours
        if o < c:
            return o <= now <= c
        return now >= o or now <= c  # overnight, e.g. 6 pm to 2 am

    def distance_from(self, lat, lng):
        if None in (lat, lng, self.latitude, self.longitude):
            return None
        return haversine_km(lat, lng, self.latitude, self.longitude)

    def eta_range(self, distance_km=None):
        extra = int(round(distance_km * 3)) if distance_km else 0
        low = self.avg_prep_minutes + extra
        return low, low + 5


class MenuCategory(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'menu categories'
        constraints = [
            models.UniqueConstraint(fields=['restaurant', 'name'], name='uniq_category_per_restaurant')
        ]

    def __str__(self):
        return f'{self.restaurant.name} - {self.name}'


class MenuItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='items')
    category = models.ForeignKey(
        MenuCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='items'
    )
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=300, blank=True)
    is_veg = models.BooleanField(default=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    mrp = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to='restaurants/items/', null=True, blank=True)
    is_available = models.BooleanField(default=True)
    packaging_charge = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.mrp is not None and self.price is not None and self.mrp < self.price:
            raise ValidationError({'mrp': 'MRP cannot be lower than the selling price.'})

    @property
    def discount_percent(self):
        if self.mrp and self.mrp > self.price:
            return int(round((self.mrp - self.price) / self.mrp * 100))
        return None


class RestaurantOrder(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = 'awaiting_payment', 'Awaiting payment'
        PLACED = 'placed', 'Placed'
        ACCEPTED = 'accepted', 'Accepted'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready for pickup'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for delivery'
        DELIVERED = 'delivered', 'Delivered'
        REJECTED = 'rejected', 'Rejected by restaurant'
        CANCELLED = 'cancelled', 'Cancelled'

    class PaymentMethod(models.TextChoices):
        ONLINE = 'online', 'Online (UPI / Card)'
        COD = 'cod', 'Cash on delivery'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUND_PENDING = 'refund_pending', 'Refund pending'
        REFUNDED = 'refunded', 'Refunded'

    order_number = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='restaurant_orders'
    )
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name='orders')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    razorpay_order_id = models.CharField(max_length=60, blank=True)
    razorpay_payment_id = models.CharField(max_length=60, blank=True)

    item_total = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    packaging_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    gst = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    offer_code = models.CharField(max_length=30, blank=True)

    customer_name = models.CharField(max_length=150, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    delivery_address = models.JSONField(default=dict, blank=True)  # snapshot at order time
    delivery_lat = models.FloatField(null=True, blank=True)
    delivery_lng = models.FloatField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['restaurant', 'status']),
        ]

    def __str__(self):
        return self.order_number or f'RestaurantOrder {self.pk}'


class RestaurantOrderItem(models.Model):
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, null=True, on_delete=models.SET_NULL, related_name='+')
    name = models.CharField(max_length=150)  # snapshot, the menu may change later
    is_veg = models.BooleanField(default=True)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    packaging_charge = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))

    def __str__(self):
        return f'{self.quantity} x {self.name}'
