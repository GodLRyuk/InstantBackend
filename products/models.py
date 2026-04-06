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

    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='products/media/', blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def discounted_price(self):
        if self.discount_percent and self.discount_percent > 0:
            discount_amount = (self.price * self.discount_percent) / Decimal("100")
            return round(self.price - discount_amount, 2)
        return self.price

    def __str__(self):
        return self.name

        