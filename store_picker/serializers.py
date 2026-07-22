from rest_framework import serializers

from accounts.models import DriverAttendance
from orders.serializers import OrderSerializer as BaseOrderSerializer
from orders.serializers import OrderItemSerializer as BaseOrderItemSerializer


class PickOrderItemSerializer(BaseOrderItemSerializer):
    product_barcode = serializers.CharField(
        source="product.barcode", read_only=True, allow_null=True
    )

    class Meta(BaseOrderItemSerializer.Meta):
        fields = BaseOrderItemSerializer.Meta.fields + ["product_barcode"]


class PickOrderSerializer(BaseOrderSerializer):
    items = PickOrderItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta(BaseOrderSerializer.Meta):
        fields = BaseOrderSerializer.Meta.fields + ["items_count"]

    def get_items_count(self, obj):
        return obj.items.count()


class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverAttendance
        fields = ["id", "date", "clock_in_time", "clock_out_time", "total_hours", "status"]
        read_only_fields = ["date", "clock_in_time", "total_hours"]