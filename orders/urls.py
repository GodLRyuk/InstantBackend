from django.urls import path
from .views import (
    OrderListView,
    OrderDetailView,
    CancelOrderView,
    UpdateOrderStatusView,
    CreateOrderView
)

urlpatterns = [
    path('orders/', OrderListView.as_view()),
    path('orders/<int:pk>/', OrderDetailView.as_view()),
    path('orders/<int:pk>/cancel/', CancelOrderView.as_view()),
    path('orders/<int:pk>/status/', UpdateOrderStatusView.as_view()),
    path('orders/create/', CreateOrderView.as_view()),
]