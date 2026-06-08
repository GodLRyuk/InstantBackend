from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True, max_length=500)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Unit(models.Model):
    name = models.CharField(max_length=50)  # Kg, Gram, Litre, Piece
    short_name = models.CharField(max_length=10)  # kg, g, L, pc

    def __str__(self):
        return self.name
class Banner(models.Model):
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='banners/', max_length=500)  # images will go to media/banners/
    link = models.URLField(blank=True, null=True)   # optional link when banner is clicked
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)  # timestamp for creation
    updated_at = models.DateTimeField(auto_now=True)      # timestamp for updates

    def __str__(self):
        return self.title
class AdvBanner(models.Model):
    image = models.ImageField(upload_to='advbanners/', max_length=500)  # images will go to media/banners/
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)  # timestamp for creation
    updated_at = models.DateTimeField(auto_now=True)      # timestamp for updatesjdjhj
