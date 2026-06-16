from django.contrib import admin
from .models import Coupon, CouponUsage, DeliveryPass, DeliverySettings


@admin.register(DeliveryPass)
class DeliveryPassAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'plan_type',
        'amount_paid',
        'purchased_at',
        'expires_at',
        'is_active',
        'free_deliveries_used',
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