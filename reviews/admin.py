from django.contrib import admin
from .models import ProductReview

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user__name', 'comment')
    ordering = ('-created_at',)