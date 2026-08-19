from rest_framework import serializers
from .models import Expense, ExpenseCategory


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = "__all__"


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    added_by_name = serializers.CharField(
        source="added_by.username", read_only=True, default=None
    )

    class Meta:
        model = Expense
        fields = [
            "id", "category", "category_name", "title", "amount",
            "payment_method", "reference_no", "expense_date", "remarks",
            "receipt", "added_by", "added_by_name", "created_at", "updated_at",
        ]
        read_only_fields = ["added_by", "created_at", "updated_at"]
