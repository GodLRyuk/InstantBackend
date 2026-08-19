from django.db.models import Sum
from django.utils.dateparse import parse_date
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Expense, ExpenseCategory
from .serializers import ExpenseSerializer, ExpenseCategorySerializer


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    """
    /api/expenses/categories/  - list/create
    /api/expenses/categories/<id>/  - retrieve/update/delete
    """
    queryset = ExpenseCategory.objects.filter(is_active=True)
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]


class ExpenseViewSet(viewsets.ModelViewSet):
    """
    /api/expenses/records/  - list (with filters) / create
    /api/expenses/records/<id>/  - retrieve/update/delete
    /api/expenses/records/summary/  - totals for a dashboard / MIS report

    Filters (all optional, via query params on the list endpoint):
      - category_id
      - payment_method
      - start_date, end_date  (expense_date range, YYYY-MM-DD)
    """
    queryset = Expense.objects.select_related("category", "added_by").all()
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        category_id = params.get("category_id")
        if category_id:
            qs = qs.filter(category_id=category_id)

        payment_method = params.get("payment_method")
        if payment_method:
            qs = qs.filter(payment_method=payment_method)

        start_date = parse_date(params.get("start_date", "") or "")
        if start_date:
            qs = qs.filter(expense_date__gte=start_date)

        end_date = parse_date(params.get("end_date", "") or "")
        if end_date:
            qs = qs.filter(expense_date__lte=end_date)

        return qs

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        GET /api/expenses/records/summary/?start_date=&end_date=
        Returns total spend and a breakdown by category - handy for an
        MIS-style dashboard. Respects the same date filters as the list view.
        """
        qs = self.get_queryset()

        total = qs.aggregate(total=Sum("amount"))["total"] or 0

        by_category = (
            qs.values("category__id", "category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )

        return Response({
            "total_expenses": float(total),
            "count": qs.count(),
            "by_category": [
                {
                    "category_id": row["category__id"],
                    "category_name": row["category__name"],
                    "total": float(row["total"] or 0),
                }
                for row in by_category
            ],
        })
