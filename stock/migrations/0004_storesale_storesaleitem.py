from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("stock", "0003_stockadjustment"),
    ]

    operations = [
        migrations.CreateModel(
            name="StoreSale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("payment_method", models.CharField(choices=[("CASH", "Cash"), ("UPI", "UPI"), ("CARD", "Card")], max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_store_sales", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="store_sales", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="StoreSaleItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField()),
                ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("total_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="store_sale_items", to="stock.stockbatch")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="products.product")),
                ("sale", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="stock.storesale")),
            ],
        ),
    ]
