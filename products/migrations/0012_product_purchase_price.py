from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0011_product_barcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="purchase_price",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True
            ),
        ),
    ]
