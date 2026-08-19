from django.contrib import admin
from .models import StoreSchedule


@admin.register(StoreSchedule)
class StoreScheduleAdmin(admin.ModelAdmin):
    list_display = ["opens_at", "closes_at", "is_force_closed", "updated_at"]

    def has_add_permission(self, request):
        # singleton — block creating extra rows via admin "+Add"
        return not StoreSchedule.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
