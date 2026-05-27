from rest_framework import serializers
from .models import ProductReview

class ProductReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = ProductReview
        fields = [
            'id',
            'product',
            'user_name',
            'rating',
            'comment',
            'created_at'
        ]