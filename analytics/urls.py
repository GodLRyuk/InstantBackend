from django.urls import path

from .views import (
    DemandSignalListAPIView,
    DemandForecastAPIView,
    InventoryInsightsAPIView,
    OverviewAPIView,
    SalesSummaryAPIView,
    TopProductsAPIView,
)


urlpatterns = [
    path('overview/', OverviewAPIView.as_view(), name='overview'),
    path('sales-summary/', SalesSummaryAPIView.as_view(), name='sales-summary'),
    path('top-products/', TopProductsAPIView.as_view(), name='top-products'),
    path('demand-forecast/', DemandForecastAPIView.as_view(), name='demand-forecast'),
    path('inventory-insights/', InventoryInsightsAPIView.as_view(), name='inventory-insights'),
    path('demand-signals/', DemandSignalListAPIView.as_view(), name='demand-signals'),
]
