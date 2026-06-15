from rest_framework import serializers
from .models import Wishlist
from products.serializers import ProductSerializer  # adjust import

class WishlistSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Wishlist
        fields = ['id', 'product', 'product_id', 'added_at']

    def create(self, validated_data):
        user = self.context['request'].user
        return Wishlist.objects.get_or_create(
            user=user,
            product_id=validated_data['product_id']
        )[0]