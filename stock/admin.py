from django.contrib import admin
from .models import Inventory, StockBatch


class StockStatusFilter(admin.SimpleListFilter):
    title = 'stock status'
    parameter_name = 'stock_status'

    def lookups(self, request, model_admin):
        return (
            ('available', 'Available'),
            ('empty', 'Empty'),
            ('all', 'All'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'empty':
            return queryset.filter(quantity=0)
        if self.value() == 'all':
            return queryset
        return queryset.filter(quantity__gt=0)


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


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ('product', 'batch_no', 'quantity', 'purchase_price', 'selling_price', 'created_at')
    list_filter = ('product', StockStatusFilter)
    search_fields = ('product__name', 'batch_no')
