from django.db import models
from django.conf import settings


class ExpenseCategory(models.Model):
    """
    Master list of expense categories, e.g. Salary, MIS Expenses, Net Recharge.
    Kept as its own table (like masters.Category/Brand) so new categories can be
    added from the admin/API without a code change.
    """
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Expense categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Expense(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("UPI", "UPI"),
        ("CARD", "Card"),
        ("OTHER", "Other"),
    ]

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    title = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default="CASH"
    )
    reference_no = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Transaction / cheque / UTR reference, if any (e.g. for Net Recharge).",
    )
    expense_date = models.DateField()
    remarks = models.TextField(blank=True, null=True)
    receipt = models.FileField(
        upload_to="expenses/receipts/", blank=True, null=True, max_length=500
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_added",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.category.name} - {self.amount} ({self.expense_date})"
