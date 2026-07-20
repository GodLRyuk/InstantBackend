from rest_framework import serializers
from .models import Inventory, StockBatch  # or Stock model name

class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    available_stock = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()
    current_selling_price = serializers.SerializerMethodField()
    current_batch_no = serializers.SerializerMethodField()

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
            'updated_at',
            'current_selling_price',
            'current_batch_no',
        ]

    def get_available_stock(self, obj):
        return obj.total_stock - obj.reserved_stock

    def get_is_low_stock(self, obj):
        return obj.total_stock <= obj.low_stock_threshold
    
    def get_current_selling_price(self, obj):
        return obj.product.current_selling_price()
    
    def get_current_batch_no(self, obj): 
        batch = obj.product.current_batch()
        return batch.batch_no if batch else None

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