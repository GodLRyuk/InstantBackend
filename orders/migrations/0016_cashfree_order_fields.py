from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0015_order_orders_sales_status_date_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='order', name='cashfree_order_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='order', name='cashfree_payment_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='order', name='payment_method',
            field=models.CharField(default='CASHFREE', max_length=20),
        ),
    ]
