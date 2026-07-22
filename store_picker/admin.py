from django.contrib import admin

from .models import PickRecord


@admin.register(PickRecord)
class PickRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product", "picked_by", "picked_at")
    list_filter = ("picked_by",)
    search_fields = ("order__id", "product__name")