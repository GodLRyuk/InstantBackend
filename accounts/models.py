from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):

    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('CUSTOMER', 'Customer'),
        ('DELIVERY', 'Delivery Boy'),
        ('PICKUP', 'Pickup Boy'),
        ('RESTAURANT', 'Restaurant Owner'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=15, unique=True)
    address = models.TextField(blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)
    profile_image = models.ImageField(blank=True, null=True, upload_to='profile_images/', max_length=500)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    otp_attempts = models.IntegerField(default=0)
    is_online = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    fcm_token = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.username


class DriverAttendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('half_day', 'Half Day'),
        ('absent', 'Absent'),
    ]

    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    date = models.DateField(default=timezone.now)
    clock_in_time = models.DateTimeField(null=True, blank=True)
    clock_out_time = models.DateTimeField(null=True, blank=True)
    total_hours = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='present'
    )

    class Meta:
        # ✅ REMOVED unique_together — multiple records per day allowed
        ordering = ['-clock_in_time']

    def __str__(self):
        return f"{self.driver.username} - {self.date} - {self.clock_in_time}"

    def calculate_total_hours(self):
        if self.clock_in_time and self.clock_out_time:
            diff = self.clock_out_time - self.clock_in_time
            self.total_hours = round(diff.total_seconds() / 3600, 2)
            self.save()