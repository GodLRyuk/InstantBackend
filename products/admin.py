from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'subcategory',
        'brand',
        'unit',
        'price',
        'available_stock',  # <- method defined below
        'is_active',
        'created_at'
    )

    def available_stock(self, obj):
        """Return stock from related Inventory"""
        if hasattr(obj, 'inventory'):
            return obj.inventory.available_stock()
        return 0  # default if no inventory

    available_stock.short_description = "Stock"