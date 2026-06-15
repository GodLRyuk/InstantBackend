from django.db import models
from django.conf import settings

class Wishlist(models.Model):
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE)  # adjust app name
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')  # no duplicates

    def __str__(self):
        return f"{self.user} → {self.product}"