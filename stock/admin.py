from django.contrib import admin
from .models import Inventory, StockBatch

class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        'product',
        'total_stock',
        'reserved_stock',
        'available_stock',
        'low_stock_threshold',
        'is_low_stock',
        'updated_at'
    )
    list_filter = ('product',)
    search_fields = ('product__name',)
    readonly_fields = ('available_stock', 'is_low_stock', 'updated_at')

    def is_low_stock(self, obj):
        return obj.is_low_stock()
    is_low_stock.boolean = True  # shows as a green/red icon in admin
    is_low_stock.short_description = 'Low Stock?'

admin.site.register(Inventory, InventoryAdmin)
admin.site.register(StockBatch)
