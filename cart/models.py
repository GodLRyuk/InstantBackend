from django.db import models
from django.conf import settings
from products.models import Product


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)
    def remove(self):
        """Remove this item and update reserved stock"""
        inventory = self.product.inventory
        inventory.reserved_stock -= self.quantity
        if inventory.reserved_stock < 0:
            inventory.reserved_stock = 0
        inventory.save()
        self.delete()

    def __str__(self):
        return self.product.name

    @property
    def total_price(self):
        return self.product.price * self.quantity