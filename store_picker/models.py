from django.conf import settings
from django.db import models


class PickRecord(models.Model):
    """One row per product picked on an order — who picked it, when."""
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="pick_records")
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE)  # adjust app label if different
    picked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pick_records")
    picked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product} picked by {self.picked_by} for order {self.order_id}"