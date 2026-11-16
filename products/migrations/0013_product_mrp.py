from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0012_product_purchase_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="mrp",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True
            ),
        ),
    ]
