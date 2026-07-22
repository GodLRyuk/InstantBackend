import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store_picker", "0002_remove_storepickerprofile_store_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0011_order_driver_lat_order_driver_lng"),
        ("products", "0011_product_barcode"),
    ]

    operations = [
        migrations.DeleteModel(name="BatchStockItem"),
        migrations.DeleteModel(name="Batch"),
        migrations.DeleteModel(name="Store"),
        migrations.CreateModel(
            name="PickRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("picked_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pick_records", to="orders.order")),
                ("order_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="orders.orderitem")),
                ("picked_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pick_records", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="products.product")),
            ],
        ),
    ]