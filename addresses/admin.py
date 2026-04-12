from django.contrib import admin
from .models import Address

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'user',
        'full_address',
        'city',
        'state',
        'pincode',
        'address_type',
        'is_default',
        'created_at'
    )

    list_filter = (
        'address_type',
        'is_default',
        'city',
        'state',
        'created_at'
    )

    search_fields = (
        'user__username',
        'user__email',
        'full_address',
        'pincode'
    )

    ordering = ('-created_at',)