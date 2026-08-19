from datetime import time
from django.db import models
from django.utils import timezone


class StoreSchedule(models.Model):
    """
    Singleton store operating hours. Editable anytime by admin.
    closes_at can be less than opens_at (e.g. opens 05:30, closes 00:00) —
    that's treated as closing after midnight, handled in is_open_now().
    """
    opens_at = models.TimeField(default=time(5, 30))
    closes_at = models.TimeField(default=time(23, 0))
    is_force_closed = models.BooleanField(
        default=False,
        help_text="Manual override — if on, store shows closed regardless of hours.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Store Schedule"
        verbose_name_plural = "Store Schedule"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # singleton — block delete

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def is_open_now(self):
        if self.is_force_closed:
            return False

        now = timezone.localtime().time()

        if self.closes_at > self.opens_at:
            # same-day window, e.g. 05:30 -> 23:00
            return self.opens_at <= now <= self.closes_at
        else:
            # overnight window, e.g. 05:30 -> 00:00 (next day) or 20:00 -> 02:00
            return now >= self.opens_at or now <= self.closes_at

    def __str__(self):
        return f"Store hours: {self.opens_at} - {self.closes_at}"
