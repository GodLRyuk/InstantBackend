from django.db import models
from masters.models import Category, SubCategory, Brand, Unit
from decimal import Decimal


class Product(models.Model):

    name = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    subcategory = models.ForeignKey(SubCategory, on_delete=models.CASCADE)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True)
    unit_size = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='products/media/', blank=True, null=True, max_length=500)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def current_batch(self):
        return self.batches.filter(quantity__gt=0).order_by('created_at').first()

    def current_selling_price(self):
        batch = self.current_batch()
        if batch:
            return batch.selling_price
        return self.price  
    def discounted_price(self):
        price = self.current_selling_price()
        if self.discount_percent and self.discount_percent > 0:
            discount_amount = (price * self.discount_percent) / Decimal("100")
            return round(price - discount_amount, 2)
        return price

    def __str__(self):
        return self.name
    
class FlashSale(models.Model):
    title = models.CharField(max_length=255, default="Flash Sale")
    products = models.ManyToManyField('Product', blank=True) 
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_live(self):
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and self.start_time <= now <= self.end_time

    def __str__(self):
        return f"{self.title} ({self.start_time} → {self.end_time})"
    
class Bundle(models.Model):
    name = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='bundles/', blank=True, null=True)
    products = models.ManyToManyField(Product, blank=True)
    bundle_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def original_price(self):
        return sum(p.discounted_price() for p in self.products.all())

    def discount_percent(self):
        original = self.original_price()
        if original > 0:
            return round((1 - self.bundle_price / original) * 100, 1)
        return 0

    def __str__(self):
        return self.name

        