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
            'product_name',
            'batch_no',
            'quantity',
            'purchase_price',
            'selling_price',
            'created_at'
        ] 