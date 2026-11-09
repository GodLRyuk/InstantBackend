from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("promotions", "0005_deliverysettings_base_delivery_fee_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="coupon",
            name="pass_members_only",
            field=models.BooleanField(default=False),
        ),
    ]
