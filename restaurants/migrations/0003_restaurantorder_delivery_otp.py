import restaurants.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0002_restaurantdeliveryassignment'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurantorder',
            name='delivery_otp',
            field=models.CharField(
                default=restaurants.models.generate_delivery_otp,
                max_length=6,
            ),
        ),
        migrations.AddField(
            model_name='restaurantorder',
            name='delivery_otp_verified',
            field=models.BooleanField(default=False),
        ),
    ]
