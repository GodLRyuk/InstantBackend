from django.contrib import admin
from django.utils import timezone
from .models import Coupon, CouponUsage, DeliveryPass, DeliverySettings


# ── COUPON ────────────────────────────────────────────────────
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = [
        'code',
        'coupon_type',
        'value',
        'min_order_amount',
        'active',
        'expires_at',
        'one_time_per_user',
        'total_usage_count',
    ]
    list_filter   = ['coupon_type', 'active', 'one_time_per_user']
    search_fields = ['code']
    ordering      = ['-id']

    def total_usage_count(self, obj):
        return obj.usages.count()
    total_usage_count.short_description = "Times Used"


# ── COUPON USAGE ──────────────────────────────────────────────
@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display    = ['user', 'coupon', 'used_at']
    list_filter     = ['coupon']
    search_fields   = ['user__email', 'user__phone', 'coupon__code']
    ordering        = ['-used_at']
    readonly_fields = ['user', 'coupon', 'used_at']


# ── DELIVERY PASS ─────────────────────────────────────────────
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
        'days_remaining',
    ]
    list_filter     = ['plan_type', 'is_active']
    search_fields   = ['user__email', 'user__phone']
    readonly_fields = [
        'purchased_at',
        'free_deliveries_used',
        'last_reset_month',
        'last_reset_year',
    ]
    ordering = ['-purchased_at']

    def days_remaining(self, obj):
        if not obj.is_valid():
            return "Expired"
        delta = obj.expires_at - timezone.now()
        return f"{delta.days} days"
    days_remaining.short_description = "Days Left"


# ── DELIVERY SETTINGS ─────────────────────────────────────────
@admin.register(DeliverySettings)
class DeliverySettingsAdmin(admin.ModelAdmin):
    list_display = [
        'delivery_fee',
        'free_delivery_min',
        'coupon_unlock_min',
        'pass_price_monthly',
        'free_delivery_cap_monthly',   # ← new
        'pass_price_yearly',
        'free_delivery_cap_yearly',    # ← new
    ]


    def has_add_permission(self, request):
        return not DeliverySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False