from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import APIException
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
    AnalyticsAssistantSerializer,
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
from .services.ai_assistant import (
    AssistantInputTooLarge,
    AssistantProviderError,
    AssistantProviderTimeout,
    OllamaProvider,
    build_approved_analytics_data,
    build_calculation_records,
    classify_analytics_intent,
)


class OllamaCalculationTooLarge(APIException):
    status_code = 413
    default_detail = 'The report is too large for a single Ollama calculation.'
    default_code = 'ollama_calculation_too_large'


class OllamaCalculationTimeout(APIException):
    status_code = 504
    default_detail = 'The local AI model timed out. Please try again.'
    default_code = 'ollama_calculation_timeout'


class OllamaCalculationUnavailable(APIException):
    status_code = 502
    default_detail = 'The local AI model is unavailable or returned an invalid calculation.'
    default_code = 'ollama_calculation_unavailable'


def _ollama_calculation(
    intent,
    start_date,
    end_date,
    backend_calculation,
    *,
    group_by='day',
    sort_by='revenue',
    limit=10,
):
    try:
        records = build_calculation_records(
            intent,
            start_date,
            end_date,
            group_by=group_by,
            sort_by=sort_by,
            limit=limit,
        )
        return OllamaProvider().calculate_report(
            intent,
            records,
            backend_calculation=backend_calculation,
            limit=limit,
        )
    except AssistantInputTooLarge as exc:
        raise OllamaCalculationTooLarge(str(exc)) from exc
    except AssistantProviderTimeout as exc:
        raise OllamaCalculationTimeout from exc
    except AssistantProviderError as exc:
        raise OllamaCalculationUnavailable from exc


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
        inventory = get_inventory_overview()
        response_data = {
            'start_date': date_range['start_date'].isoformat(),
            'end_date': date_range['end_date'].isoformat(),
            'sales_definitions': SALES_DEFINITIONS,
            'sales': sales['totals'],
            'inventory': inventory,
        }
        response = Response(response_data)
        if settings.AI_REPORTS_ENABLED:
            response.data['ollama_calculation'] = _ollama_calculation(
                'overview',
                date_range['start_date'],
                date_range['end_date'],
                {'sales': sales['totals'], 'inventory': inventory},
            )
        return response


class SalesSummaryAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filters = SalesSummaryFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        data = get_sales_summary(**filters.validated_data)
        response = Response(data)
        if settings.AI_REPORTS_ENABLED:
            response.data['ollama_calculation'] = _ollama_calculation(
                'sales',
                filters.validated_data['start_date'],
                filters.validated_data['end_date'],
                {'totals': data['totals']},
                group_by=filters.validated_data['group_by'],
            )
        return response


class TopProductsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        filters = TopProductsFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        results = get_top_products(
            data['start_date'],
            data['end_date'],
            limit=data['limit'],
            sort_by=data['sort_by'],
        )
        response = Response({
            'start_date': data['start_date'].isoformat(),
            'end_date': data['end_date'].isoformat(),
            'sort_by': data['sort_by'],
            'sales_definitions': SALES_DEFINITIONS,
            'results': results,
        })
        if settings.AI_REPORTS_ENABLED:
            response.data['ollama_calculation'] = _ollama_calculation(
                'top_products',
                data['start_date'],
                data['end_date'],
                {'results': results},
                sort_by=data['sort_by'],
                limit=data['limit'],
            )
        return response


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


class AnalyticsAssistantAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        if not settings.AI_ASSISTANT_ENABLED:
            return Response(
                {'error': 'The analytics assistant is disabled.'},
                status=503,
            )

        serializer = AnalyticsAssistantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        intent = classify_analytics_intent(data['question'])
        analytics_data = build_approved_analytics_data(
            intent,
            data['start_date'],
            data['end_date'],
        )

        try:
            answer = OllamaProvider().generate_explanation(intent, analytics_data)
        except AssistantProviderTimeout:
            return Response(
                {'error': 'The local AI model timed out. Please try again.'},
                status=504,
            )
        except AssistantProviderError:
            return Response(
                {'error': 'The local AI model is unavailable or returned an invalid response.'},
                status=502,
            )

        response_data = {
            'answer': answer,
            'intent': intent,
            'start_date': data['start_date'].isoformat(),
            'end_date': data['end_date'].isoformat(),
            'model': settings.OLLAMA_MODEL,
            'data': analytics_data,
        }
        if intent == 'overview':
            backend_calculation = {
                'sales': analytics_data['sales'],
                'inventory': analytics_data['inventory'],
            }
        elif intent == 'sales':
            backend_calculation = {'totals': analytics_data['totals']}
        elif intent == 'top_products':
            backend_calculation = {'results': analytics_data['top_products']}
        else:
            backend_calculation = {'inventory': analytics_data['inventory']}
        response_data['ollama_calculation'] = _ollama_calculation(
            intent,
            data['start_date'],
            data['end_date'],
            backend_calculation,
            limit=5 if intent == 'top_products' else 10,
        )
        return Response(response_data)


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

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if settings.AI_REPORTS_ENABLED:
            today = timezone.localdate()
            response.data['ollama_calculation'] = _ollama_calculation(
                'inventory',
                today,
                today,
                {'inventory': get_inventory_overview()},
            )
        return response
