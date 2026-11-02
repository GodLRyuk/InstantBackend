from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import DemandSignal


class AnalyticsDateRangeSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        today = timezone.localdate()
        end_date = attrs.get('end_date', today)
        start_date = attrs.get('start_date', end_date - timedelta(days=29))

        if start_date > end_date:
            raise serializers.ValidationError(
                {'start_date': 'Must be on or before end_date.'}
            )
        if end_date > today:
            raise serializers.ValidationError(
                {'end_date': 'Future dates are not allowed.'}
            )
        if (end_date - start_date).days + 1 > 366:
            raise serializers.ValidationError(
                {'start_date': 'Date ranges cannot exceed 366 days.'}
            )

        attrs['start_date'] = start_date
        attrs['end_date'] = end_date
        return attrs


class SalesSummaryFilterSerializer(AnalyticsDateRangeSerializer):
    group_by = serializers.ChoiceField(
        choices=['day', 'week', 'month'],
        required=False,
        default='day',
    )


class TopProductsFilterSerializer(AnalyticsDateRangeSerializer):
    limit = serializers.IntegerField(
        required=False,
        default=10,
        min_value=1,
        max_value=100,
    )
    sort_by = serializers.ChoiceField(
        choices=['revenue', 'quantity'],
        required=False,
        default='revenue',
    )


class InventoryPaginationSerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )
    offset = serializers.IntegerField(
        required=False,
        min_value=0,
    )


class DemandForecastFilterSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(required=False, min_value=1)
    horizon_days = serializers.IntegerField(
        required=False,
        default=7,
        min_value=1,
        max_value=30,
    )
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )
    offset = serializers.IntegerField(
        required=False,
        min_value=0,
    )


class DemandSignalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemandSignal
        fields = [
            'id',
            'signal_type',
            'normalized_query',
            'result_count',
            'product',
            'quantity',
            'created_at',
        ]
