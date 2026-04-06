from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price',  'total_price')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "total_amount", "discount_amount", "coupon", "payment_status", "order_status", "created_at")
    list_filter = ("order_status", "payment_status", "created_at")
    inlines = [OrderItemInline] 