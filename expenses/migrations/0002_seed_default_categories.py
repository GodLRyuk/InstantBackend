from django.db import migrations

DEFAULT_CATEGORIES = ["Salary", "MIS Expenses", "Net Recharge"]


def seed_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model("expenses", "ExpenseCategory")
    for name in DEFAULT_CATEGORIES:
        ExpenseCategory.objects.get_or_create(name=name)


def remove_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model("expenses", "ExpenseCategory")
    ExpenseCategory.objects.filter(name__in=DEFAULT_CATEGORIES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories, remove_categories),
    ]
