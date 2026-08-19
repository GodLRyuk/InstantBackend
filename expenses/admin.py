from django.contrib import admin
from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    search_fields = ["name"]
    list_filter = ["is_active"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        "id", "category", "title", "amount", "payment_method",
        "expense_date", "added_by", "created_at",
    ]
    list_filter = ["category", "payment_method", "expense_date"]
    search_fields = ["title", "reference_no", "remarks"]
    date_hierarchy = "expense_date"
    autocomplete_fields = []
