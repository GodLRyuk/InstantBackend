from datetime import timedelta

from django.db.models import F
from django.utils import timezone
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from stock.models import Inventory
from products.models import Product

from .models import DemandSignal
from .serializers import (
    AnalyticsDateRangeSerializer,
    DemandSignalSerializer,
    DemandForecastFilterSerializer,
    InventoryPaginationSerializer,
    SalesSummaryFilterSerializer,
    TopProductsFilterSerializer,
)
from .services.sales_analytics import (
    SALES_DEFINITIONS,
    get_inventory_overview,
    get_sales_summary,
    get_top_products,
)
from .services.demand_forecasting import (
    HISTORY_DAYS,
    MIN_SALES_DAYS,
    MODEL_NAME,
    MODEL_VERSION,
    build_demand_forecasts,
)


class DemandSignalListAPIView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = DemandSignalSerializer
    pagination_class = None
    queryset = (
        DemandSignal.objects
        .select_related('product')
        .order_by('-created_at', '-id')[:100]
    )


class OverviewAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filters = AnalyticsDateRangeSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        date_range = filters.validated_data
        sales = get_sales_summary(
            date_range['start_date'],
            date_range['end_date'],
        )
        return Response({
            'start_date': date_range['start_date'].isoformat(),
            'end_date': date_range['end_date'].isoformat(),
            'sales_definitions': SALES_DEFINITIONS,
            'sales': sales['totals'],
            'inventory': get_inventory_overview(),
        })


class SalesSummaryAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filters = SalesSummaryFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        return Response(get_sales_summary(**filters.validated_data))


class TopProductsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filters = TopProductsFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        return Response({
            'start_date': data['start_date'].isoformat(),
            'end_date': data['end_date'].isoformat(),
            'sort_by': data['sort_by'],
            'sales_definitions': SALES_DEFINITIONS,
            'results': get_top_products(
                data['start_date'],
                data['end_date'],
                limit=data['limit'],
                sort_by=data['sort_by'],
            ),
        })


class DemandForecastPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 100


class DemandForecastAPIView(APIView):
    permission_classes = [IsAdminUser]
    pagination_class = DemandForecastPagination

    def get(self, request):
        filters = DemandForecastFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data

        products = Product.objects.filter(is_active=True).order_by('name', 'id')
        if 'product_id' in data:
            products = products.filter(id=data['product_id'])

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(products, request, view=self)
        forecast_rows = build_demand_forecasts(page, data['horizon_days'])
        response = paginator.get_paginated_response(forecast_rows)
        today = timezone.localdate()
        response.data.update({
            'generated_at': timezone.now().isoformat(),
            'model': {'name': MODEL_NAME, 'version': MODEL_VERSION},
            'horizon_days': data['horizon_days'],
            'history': {
                'start_date': (today - timedelta(days=HISTORY_DAYS)).isoformat(),
                'end_date': (today - timedelta(days=1)).isoformat(),
                'minimum_sales_days': MIN_SALES_DAYS,
            },
            'sales_definitions': SALES_DEFINITIONS,
            'evaluation': {
                'method': 'time_holdout_21_days_train_7_days_test',
                'metrics': ['MAE', 'WAPE'],
            },
            'caveats': [
                'This is a transparent baseline estimate, not a validated production prediction.',
                'Historical stock availability is not recorded; zero-sales days may be stockouts.',
                'No prediction intervals are available.',
            ],
        })
        return response


class InventoryInsightsPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 100

    def paginate_queryset(self, queryset, request, view=None):
        filters = InventoryPaginationSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        self.low_stock_count = queryset.filter(
            available_stock__lte=F('low_stock_threshold')
        ).count()
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data['low_stock_count'] = self.low_stock_count
        return response


class InventoryInsightSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    available_stock = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = [
            'product_id',
            'product_name',
            'total_stock',
            'reserved_stock',
            'available_stock',
            'low_stock_threshold',
            'is_low_stock',
        ]

    def get_is_low_stock(self, obj):
        return obj.available_stock <= obj.low_stock_threshold


class InventoryInsightsAPIView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = InventoryInsightSerializer
    pagination_class = InventoryInsightsPagination

    def get_queryset(self):
        return (
            Inventory.objects
            .select_related('product')
            .annotate(available_stock=F('total_stock') - F('reserved_stock'))
            .order_by('available_stock', 'product__name', 'id')
        )
