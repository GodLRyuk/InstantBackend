from django.contrib import admin
from .models import Coupon, CouponUsage, DeliverySettings

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
        'pass_price_monthly',  # ✅ updated
        'pass_price_yearly',   # ✅ added
        'free_delivery_cap'
    ]
    list_filter = ['plan_type', 'is_active']
    search_fields = ['user__email', 'user__phone']
    readonly_fields = ['purchased_at', 'free_deliveries_used']
    ordering = ['-purchased_at']

@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ['user', 'coupon', 'used_at']
    search_fields = ['user__email', 'coupon__code']
    ordering = ['-used_at']