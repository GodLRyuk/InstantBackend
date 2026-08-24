from django.db import models
from products.models import Product


class Inventory(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        related_name='inventory'
    )
    total_stock = models.IntegerField(default=0)
    reserved_stock = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=5)
    updated_at = models.DateTimeField(auto_now=True)

    def available_stock(self):
        return self.total_stock - self.reserved_stock

    def is_low_stock(self):
        return self.available_stock() <= self.low_stock_threshold

    def __str__(self):
        return f"{self.product.name} Inventory"


class StockBatch(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="batches"
    )

    batch_no = models.CharField(max_length=50)

    quantity = models.IntegerField()

    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)

    selling_price = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - Batch {self.batch_no}"

class StockAdjustment(models.Model):
    ADJUST_TYPE = (("IN", "Stock In"), ("OUT", "Stock Out"))
    REASON_CHOICES = (
        ("DAMAGE", "Damaged"),
        ("RETURN_TO_DEALER", "Return to Dealer"),
        ("EXPIRED", "Expired"),
        ("LOST", "Lost/Theft"),
        ("CORRECTION", "Manual Correction"),
        ("OTHER", "Other"),
    )

    batch = models.ForeignKey(StockBatch, on_delete=models.CASCADE, related_name="adjustments")
    adjust_type = models.CharField(max_length=3, choices=ADJUST_TYPE)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    quantity = models.PositiveIntegerField()
    notes = models.TextField(blank=True, null=True)
    adjusted_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.adjust_type} {self.quantity} - {self.batch.batch_no} ({self.reason})"