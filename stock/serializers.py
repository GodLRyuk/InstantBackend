from rest_framework import serializers
from .models import Inventory, StockAdjustment, StockBatch  
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

class StockAdjustmentSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='batch.product.name', read_only=True)
    batch_no = serializers.CharField(source='batch.batch_no', read_only=True)
    adjusted_by_name = serializers.CharField(source='adjusted_by.username', read_only=True)

    class Meta:
        model = StockAdjustment
        fields = ['id','batch','batch_no','product_name','adjust_type','reason',
                  'quantity','notes','adjusted_by','adjusted_by_name','created_at']
        read_only_fields = ['adjusted_by','created_at']

    def validate(self, data):
        batch = data['batch']
        if data['adjust_type'] == 'OUT' and data['quantity'] > batch.quantity:
            raise serializers.ValidationError(
                f"Only {batch.quantity} left in batch {batch.batch_no}."
            )
        return data