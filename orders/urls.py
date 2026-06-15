from django.urls import path
from .views import (
    OrderListView,
    OrderDetailView,
    CancelOrderView,
    UpdateOrderStatusView,
    CreateOrderView,
    ValidateOrderView,
    VerifyPaymentView,
    AutoAssignDriverAPIView,
    DriverAssignedOrdersAPIView,
    ConfirmPaymentView,
    SendDeliveryOtpAPIView,
    VerifyDeliveryOtpAPIView,
)

urlpatterns = [
    path('orders/', OrderListView.as_view()),
    path('orders/<int:pk>/', OrderDetailView.as_view()),
    path('orders/<int:pk>/cancel/', CancelOrderView.as_view()),
    path('orders/<int:pk>/status/', UpdateOrderStatusView.as_view()),
    path('orders/validate/', ValidateOrderView.as_view()),
    path('orders/create/', CreateOrderView.as_view()),
    path("verify-payment/", VerifyPaymentView.as_view()),
    path('admin/orders/', OrderListView.as_view()),
    path("orders/auto-assign-driver/", AutoAssignDriverAPIView.as_view()),
    path("driver/orders/", DriverAssignedOrdersAPIView.as_view()),
    path("<int:pk>/payment/confirm/", ConfirmPaymentView.as_view()),  
    path("<int:pk>/otp/send/",   SendDeliveryOtpAPIView.as_view()), 
    path("<int:pk>/otp/verify/", VerifyDeliveryOtpAPIView.as_view()), 
]