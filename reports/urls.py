from django.urls import path
from .views import (
    SalesReportExcelAPIView, SalesTrendAPIView, TopProductsAPIView,
    OrderStatusBreakdownAPIView, InventorySummaryAPIView
)

urlpatterns = [
    path('sales-trend/', SalesTrendAPIView.as_view()),
    path('top-products/', TopProductsAPIView.as_view()),
    path('order-status/', OrderStatusBreakdownAPIView.as_view()),
    path('inventory-summary/', InventorySummaryAPIView.as_view()),
    path('sales-export/', SalesReportExcelAPIView.as_view()), 
]