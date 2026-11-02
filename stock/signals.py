from django.db.models import Case, F, IntegerField, Value, When
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone
from products.models import Product
from .models import Inventory, StockBatch


@receiver(post_save, sender=Product)
def create_inventory(sender, instance, created, **kwargs):
    if created:
        Inventory.objects.create(product=instance)


@receiver(post_delete, sender=StockBatch)
def update_inventory_on_stock_batch_delete(sender, instance, **kwargs):
    Inventory.objects.filter(product_id=instance.product_id).update(
        total_stock=Case(
            When(
                total_stock__gte=instance.quantity,
                then=F('total_stock') - instance.quantity,
            ),
            default=Value(0),
            output_field=IntegerField(),
        ),
        updated_at=timezone.now(),
    )