from django.contrib import admin
from .models import Coupon, DeliverySettings

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        'code', 
        'coupon_type',   # matches your model field
        'value',         # matches your model field
        'min_order_amount',
        'active',
        'expires_at'
    )
    list_filter = ('active', 'coupon_type')
    search_fields = ('code',)

@admin.register(DeliverySettings)
class DeliverySettingsAdmin(admin.ModelAdmin):
    list_display = [
        'delivery_fee', 
        'free_delivery_min', 
        'coupon_unlock_min', 
        'pass_price',
        'free_delivery_cap'
    ]

    # Prevent adding/deleting — only edit the one row
    def has_add_permission(self, request):
        return not DeliverySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False