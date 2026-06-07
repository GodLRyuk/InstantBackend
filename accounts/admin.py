from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, DriverAttendance


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'phone', 'is_online']
    list_filter = ['role', 'is_online']


@admin.register(DriverAttendance)
class DriverAttendanceAdmin(admin.ModelAdmin):
    list_display = ['driver', 'date', 'clock_in_time', 'clock_out_time', 'total_hours', 'status']
    list_filter = ['status', 'date']
    search_fields = ['driver__username', 'driver__phone']
    ordering = ['-date']
    readonly_fields = ['total_hours']  # calculated automatically, not editable