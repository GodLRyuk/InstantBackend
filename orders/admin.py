from django.contrib import admin
from .models import CashRemittanceItem, Order, OrderItem, DeliveryAssignment

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price', 'total_price')

class DeliveryAssignmentInline(admin.TabularInline):
    model = DeliveryAssignment
    extra = 0
    readonly_fields = ('driver', 'status', 'assigned_at')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "total_amount", "discount_amount", "coupon", "payment_status", "order_status", "created_at")
    list_filter = ("order_status", "payment_status", "created_at")
    inlines = [OrderItemInline, DeliveryAssignmentInline]  # ✅ shows assignment inside order

@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "driver", "status", "assigned_at")  # ✅ own table in admin
    list_filter = ("status", "assigned_at")
    search_fields = ("order__id", "driver__username")
    readonly_fields = ("assigned_at",)
@admin.register(CashRemittanceItem)
class CashRemittanceItemAdmin(admin.ModelAdmin):
    list_display = ("id", "remittance", "order")
    search_fields = ("order__id", "remittance__id")