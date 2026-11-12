from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0003_restaurantorder_delivery_otp'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurantorder', name='cashfree_order_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='restaurantorder', name='cashfree_payment_session_id',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='restaurantorder', name='cashfree_payment_id',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
