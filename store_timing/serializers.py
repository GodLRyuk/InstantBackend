from rest_framework import serializers
from .models import StoreSchedule


class StoreScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSchedule
        fields = ["opens_at", "closes_at", "is_force_closed", "updated_at"]
        read_only_fields = ["updated_at"]


class StoreStatusSerializer(serializers.Serializer):
    is_open = serializers.BooleanField()
    opens_at = serializers.TimeField()
    closes_at = serializers.TimeField()
    server_time = serializers.DateTimeField()
