from django.urls import path
from .views import AddStockAPIView, UpdateStockAPIView, StockListAPIView,DeleteStockAPIView, InventoryListAPIView

urlpatterns = [
    path("add/", AddStockAPIView.as_view(), name="add-stock"),
    path('update/<int:pk>/', UpdateStockAPIView.as_view(), name='update-stock'),
    path('delete/<int:pk>/', DeleteStockAPIView.as_view(), name='delete-stock'),
    path("", StockListAPIView.as_view(), name="list-stock"), 
    path('inventory/', InventoryListAPIView.as_view()),
]