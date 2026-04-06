from rest_framework import serializers
from .models import Product
from stock.models import Inventory
from decimal import Decimal

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    discounted_price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "category", "category_name",
            "subcategory", "subcategory_name",
            "brand", "brand_name",
            "unit", "unit_name", "unit_size",
            "price", "discount_percent",
            "discounted_price",
            "stock",
            "image", "image_url",
            "description",
            "is_active", "created_at"
        ]
    def get_discounted_price(self, obj):
        return float(obj.discounted_price())

    def get_stock(self, obj):
        try:
            inventory = Inventory.objects.get(product=obj)
            return inventory.total_stock
        except Inventory.DoesNotExist:
            return 0

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url)
        return None
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    def get_unit_display(self, obj):
        if obj.unit and obj.unit_size:
            return f"{obj.unit_size} {obj.unit.name}"
        return None

class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    discounted_price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "subcategory",
            "subcategory_name",
            "brand",
            "brand_name",
            "unit",
            "unit_size",
            "unit_name",
            "price",
            "discount_percent",
            "discounted_price",
            "stock",
            "image",
            "description",
            "is_active",
            "created_at",
        ]

    def get_discounted_price(self, obj):
        return float(obj.discounted_price())

    def get_stock(self, obj):
        try:
            inventory = Inventory.objects.get(product=obj)
            return inventory.total_stock
        except Inventory.DoesNotExist:
            return 0

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url)
        return None
    def get_unit_display(self, obj):
        if obj.unit and obj.unit_size:
            return f"{obj.unit_size} {obj.unit.name}"
        return None