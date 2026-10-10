from django.contrib import admin

from .models import (
    Cuisine,
    MenuCategory,
    MenuItem,
    Restaurant,
    RestaurantOrder,
    RestaurantOrderItem,
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
