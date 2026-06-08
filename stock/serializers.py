from rest_framework import serializers
from .models import Inventory, StockBatch  # or Stock model name

class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    available_stock = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = [
            'id',
            'product',
            'product_name',
            'total_stock',
            'reserved_stock',
            'available_stock',
            'low_stock_threshold',
            'is_low_stock',
            'updated_at'
        ]

    def get_available_stock(self, obj):
        return obj.total_stock - obj.reserved_stock

    def get_is_low_stock(self, obj):
        return obj.total_stock <= obj.low_stock_threshold

class StockBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = StockBatch
        fields = [
            'id',
            'product',
            'product_name',
            'batch_no',
            'quantity',
            'purchase_price',
            'selling_price',
        ]