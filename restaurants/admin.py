from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from rest_framework.exceptions import ValidationError

from . import menu_workbook

from .models import (
    Cuisine,
    MenuCategory,
    MenuItem,
    MenuItemAddOnGroup,
    MenuItemAddOnOption,
    Restaurant,
    RestaurantOrder,
    RestaurantOrderItem,
    VendorCommission,
    PaymentSplit,
    RestaurantRefund,
)


def workbook_error_messages(detail, path=()):
    if isinstance(detail, dict):
        for field, value in detail.items():
            yield from workbook_error_messages(value, (*path, field))
    elif isinstance(detail, list):
        for value in detail:
            yield from workbook_error_messages(value, path)
    else:
        yield ' · '.join((*path, str(detail)))


@admin.register(Cuisine)
class CuisineAdmin(admin.ModelAdmin):
    search_fields = ['name']


class MenuItemInline(admin.TabularInline):
    model = MenuItem
    extra = 0
    show_change_link = True
    fields = ['name', 'category', 'is_veg', 'price', 'mrp', 'is_available']


class MenuItemAddOnGroupInline(admin.TabularInline):
    model = MenuItemAddOnGroup
    extra = 0
    show_change_link = True


class MenuItemAddOnOptionInline(admin.TabularInline):
    model = MenuItemAddOnOption
    extra = 0


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'restaurant', 'category', 'price', 'is_available']
    list_filter = ['restaurant', 'is_available']
    inlines = [MenuItemAddOnGroupInline]

    readonly_fields = ['restaurant']

    def has_add_permission(self, request):
        return False  # Dishes are created on the restaurant's change page.

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj and 'category' in form.base_fields:
            form.base_fields['category'].queryset = obj.restaurant.categories.all()
        return form


@admin.register(MenuItemAddOnGroup)
class MenuItemAddOnGroupAdmin(admin.ModelAdmin):
    inlines = [MenuItemAddOnOptionInline]

    def get_readonly_fields(self, request, obj=None):
        return ('menu_item',) if obj else ()


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    change_form_template = 'admin/restaurants/restaurant/change_form.html'
    list_display = ['name', 'owner', 'city', 'status', 'is_accepting_orders', 'rating', 'created_at']
    list_filter = ['status', 'city', 'is_accepting_orders']
    search_fields = ['name', 'phone', 'fssai_number', 'owner__username']
    filter_horizontal = ['cuisines']
    inlines = [MenuItemInline]
    actions = ['approve', 'suspend']

    def get_urls(self):
        return [
            path(
                '<int:object_id>/menu-workbook/',
                self.admin_site.admin_view(self.menu_workbook_view),
                name='restaurants_restaurant_menu_workbook',
            ),
        ] + super().get_urls()

    def menu_workbook_view(self, request, object_id):
        restaurant = self.get_object(request, object_id)
        if restaurant is None:
            raise Http404
        if not self.has_view_or_change_permission(request, restaurant):
            raise PermissionDenied
        user = request.user
        can_export = all(
            user.has_perm(f'restaurants.view_{model}') or user.has_perm(f'restaurants.change_{model}')
            for model in ('menucategory', 'menuitem')
        )
        can_import = self.has_change_permission(request, restaurant) and user.has_perms([
            f'restaurants.{action}_{model}'
            for model in ('menucategory', 'menuitem')
            for action in ('add', 'change')
        ])
        if not (can_export or can_import):
            raise PermissionDenied

        errors = None
        if request.method == 'POST':
            if not can_import:
                raise PermissionDenied
            try:
                result = menu_workbook.import_menu(restaurant, request.FILES.get('file'))
            except ValidationError as exc:
                errors = list(workbook_error_messages(exc.detail))
            else:
                for sheet, counts in result.items():
                    self.message_user(
                        request,
                        f'{sheet.capitalize()}: {counts["created"]} created, {counts["updated"]} updated.',
                        messages.SUCCESS,
                    )
                return redirect(reverse('admin:restaurants_restaurant_menu_workbook', args=[object_id]))
        elif request.method != 'GET':
            return HttpResponseNotAllowed(['GET', 'POST'])
        elif request.GET.get('download') == 'template':
            return menu_workbook.export_menu(restaurant, template=True)
        elif request.GET.get('download') == 'menu':
            if not can_export:
                raise PermissionDenied
            return menu_workbook.export_menu(restaurant)

        return TemplateResponse(request, 'admin/restaurants/restaurant/menu_workbook.html', {
            **self.admin_site.each_context(request),
            'title': 'Menu Excel import and export',
            'restaurant': restaurant,
            'can_export': can_export,
            'can_import': can_import,
            'errors': errors,
        }, status=400 if errors else 200)

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
    readonly_fields = ['menu_item', 'name', 'is_veg', 'unit_price', 'quantity', 'selected_addons', 'line_total']

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('addons')

    @admin.display(description='Add-ons per dish')
    def selected_addons(self, item):
        if not item.pk:
            return ''
        return ', '.join(
            f'{addon.group_name}: {addon.name} (+{addon.unit_price:.2f})'
            for addon in item.addons.all()
        )


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
