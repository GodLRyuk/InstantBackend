from django.db import models
from django.db.models import Q

from products.models import Product


class DemandSignal(models.Model):
    class SignalType(models.TextChoices):
        SEARCH = 'SEARCH', 'Search'
        ADD_TO_CART = 'ADD_TO_CART', 'Add to cart'

    signal_type = models.CharField(max_length=20, choices=SignalType.choices)
    normalized_query = models.CharField(max_length=120, blank=True)
    result_count = models.PositiveIntegerField(null=True, blank=True)
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='demand_signals',
    )
    quantity = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['signal_type', 'created_at'],
                name='analytics_signal_type_time_idx',
            ),
            models.Index(
                fields=['product', 'created_at'],
                name='analytics_signal_prod_time_idx',
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        signal_type='SEARCH',
                        normalized_query__gt='',
                        result_count__isnull=False,
                        product__isnull=True,
                        quantity__isnull=True,
                    )
                    | Q(
                        signal_type='ADD_TO_CART',
                        normalized_query='',
                        result_count__isnull=True,
                        product__isnull=False,
                        quantity__gt=0,
                    )
                ),
                name='analytics_signal_valid_shape',
            ),
        ]

    def __str__(self):
        return f'{self.get_signal_type_display()} demand signal #{self.pk}'
