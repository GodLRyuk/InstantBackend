from django.contrib import admin

from .models import (
    Cuisine,
    MenuCategory,
    MenuItem,
    Restaurant,
    RestaurantOrder,
    RestaurantOrderItem,
    RestaurantVendor,
    VendorCommission,
    PaymentSplit,
    RestaurantRefund,
)


@admin.register(Cuisine)
class CuisineAdmin(admin.ModelAdmin):
    search_fields = ['name']


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    fields = ['name', 'category', 'is_veg', 'price', 'mrp', 'is_available']


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'city', 'status', 'is_accepting_orders', 'rating', 'created_at']
    list_filter = ['status', 'city', 'is_accepting_orders']
    search_fields = ['name', 'phone', 'fssai_number', 'owner__username']
    filter_horizontal = ['cuisines']
    inlines = [MenuItemInline]
    actions = ['approve', 'suspend']

    @admin.action(description='Approve selected restaurants')
    def approve(self, request, queryset):
        queryset.update(status=Restaurant.Status.APPROVED, rejection_reason='')

    @admin.action(description='Suspend selected restaurants')
    def suspend(self, request, queryset):
        queryset.update(status=Restaurant.Status.SUSPENDED)


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'restaurant', 'sort_order']
    list_filter = ['restaurant']


class OrderItemInline(admin.TabularInline):
    model = RestaurantOrderItem
    extra = 0
    can_delete = False
    readonly_fields = ['menu_item', 'name', 'is_veg', 'unit_price', 'quantity', 'line_total']


@admin.register(RestaurantOrder)
class RestaurantOrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 'restaurant', 'customer', 'status', 'payment_method',
        'payment_status', 'total_amount', 'created_at',
    ]
    list_filter = ['status', 'payment_method', 'payment_status', 'restaurant']
    search_fields = ['order_number', 'customer_phone', 'customer_name']
    inlines = [OrderItemInline]
    readonly_fields = ['order_number', 'created_at', 'updated_at']


@admin.register(RestaurantVendor)
class RestaurantVendorAdmin(admin.ModelAdmin):
    list_display = ['restaurant', 'cashfree_vendor_id', 'verification_status', 'settlement_status', 'updated_at']
    search_fields = ['restaurant__name', 'cashfree_vendor_id']
    readonly_fields = ['cashfree_vendor_id', 'verification_status', 'settlement_status', 'last_cashfree_response']
    fields = ['restaurant', 'cashfree_vendor_id', 'bank_account_number', 'ifsc_code',
              'account_holder_name', 'verification_status', 'settlement_status', 'last_cashfree_response']


@admin.register(VendorCommission)
class VendorCommissionAdmin(admin.ModelAdmin):
    list_display = ['restaurant', 'commission_percentage', 'effective_from']
    list_filter = ['restaurant']


@admin.register(PaymentSplit)
class PaymentSplitAdmin(admin.ModelAdmin):
    list_display = ['order', 'vendor', 'gross_amount', 'platform_commission', 'vendor_amount',
                    'cashfree_split_status', 'settlement_id', 'paid_at']
    list_filter = ['cashfree_split_status']
    readonly_fields = [field.name for field in PaymentSplit._meta.fields]


@admin.register(RestaurantRefund)
class RestaurantRefundAdmin(admin.ModelAdmin):
    list_display = ['order', 'refund_id', 'amount', 'status', 'cashfree_refund_id', 'updated_at']
    list_filter = ['status']
    readonly_fields = [field.name for field in RestaurantRefund._meta.fields]
