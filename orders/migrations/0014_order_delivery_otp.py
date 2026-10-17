import secrets

import orders.models
from django.db import migrations, models


def populate_existing_delivery_otps(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    orders = Order.objects.filter(delivery_otp__isnull=True)
    batch = []

    for order in orders.iterator(chunk_size=1000):
        order.delivery_otp = str(secrets.randbelow(900000) + 100000)
        batch.append(order)
        if len(batch) == 1000:
            Order.objects.bulk_update(batch, ["delivery_otp"], batch_size=1000)
            batch.clear()

    if batch:
        Order.objects.bulk_update(batch, ["delivery_otp"], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0013_rename_submitted_at_cashremittance_recorded_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="delivery_otp",
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_otp_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            populate_existing_delivery_otps,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_otp",
            field=models.CharField(
                default=orders.models.generate_delivery_otp,
                max_length=6,
            ),
        ),
    ]
