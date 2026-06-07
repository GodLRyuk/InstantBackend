from django.urls import path
from .views import AddStockAPIView, UpdateStockAPIView, StockListAPIView,DeleteStockAPIView, InventoryListAPIView

urlpatterns = [
    path("add/", AddStockAPIView.as_view(), name="add-stock"),
    path('update/<int:pk>/', UpdateStockAPIView.as_view(), name='update-stock'),
    path('delete/<int:pk>/', DeleteStockAPIView.as_view(), name='delete-stock'),
    path('inventory/', StockListAPIView.as_view(), name="list-stock"),   # ✅ StockBatch data
    path('', InventoryListAPIView.as_view(), name="inventory-list"),     # ✅ Inventory data
]