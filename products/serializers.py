from rest_framework import serializers
from .models import Bundle, Product
from stock.models import Inventory
from decimal import Decimal
from reviews.serializers import ProductReviewSerializer


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    discounted_price = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    reviews = ProductReviewSerializer(many=True, read_only=True)

    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

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
            "is_active", "created_at","reviews","average_rating","review_count"
        ]
    def get_discounted_price(self, obj):
        return float(obj.discounted_price())

    def get_stock(self, obj):
        try:
            return obj.inventory.total_stock
        except Exception:
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
    def get_average_rating(self, obj):
        reviews = obj.reviews.all()
        if reviews.exists():
            return round(sum(r.rating for r in reviews) / reviews.count(), 1)
        return 0

    def get_review_count(self, obj):
        return obj.reviews.count()

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
            return obj.inventory.total_stock
        except Exception:
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
    
class BundleProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None
    def get_price(self, obj):   # ✅ NEW
        return float(obj.discounted_price())


class BundleSerializer(serializers.ModelSerializer):
    products = BundleProductSerializer(many=True, read_only=True)
    original_price = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Bundle
        fields = [
            'id', 'name', 'description',
            'image_url', 'bundle_price',
            'original_price', 'discount_percent',
            'products'
        ]

    def get_original_price(self, obj):
        return float(obj.original_price())

    def get_discount_percent(self, obj):
        return float(obj.discount_percent())

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None