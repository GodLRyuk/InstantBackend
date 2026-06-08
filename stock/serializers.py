from rest_framework import serializers
from .models import Inventory, StockBatch  # or Stock model name

class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = ['id', 'product', 'quantity', 'batch_no', 'expiry_date']
        read_only_fields = ['id']  # prevent ID from being updated

class StockBatchSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = StockBatch
        fields = [
            'id',
            'product',
            'batch_no',
            'product_name',
            'total_stock',
            'reserved_stock',
            'available_stock',
            'low_stock_threshold',
            'is_low_stock',
            'updated_at'
        ] 