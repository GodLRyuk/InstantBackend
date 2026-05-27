from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):

    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('CUSTOMER', 'Customer'),
        ('DELIVERY', 'Delivery Boy'),
        ('VENDOR', 'Vendor'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=15, unique=True)
    address = models.TextField(blank=True, null=True)
    zip_code = models.CharField(max_length=10, blank=True, null=True)
    profile_image = models.ImageField(
        upload_to='profile_images/',
        blank=True,
        null=True
    )
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    otp_attempts = models.IntegerField(default=0)

    is_online = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)


    def __str__(self):
        return self.username