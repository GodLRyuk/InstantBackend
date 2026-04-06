from django.contrib import admin
from .models import Coupon

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