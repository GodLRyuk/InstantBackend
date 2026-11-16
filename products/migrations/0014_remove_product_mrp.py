from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0013_product_mrp"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="mrp",
        ),
    ]
