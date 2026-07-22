from django.urls import path

from . import views

urlpatterns = [
    path("orders/", views.ConfirmedOrderListView.as_view(), name="picker-order-list"),
    path("orders/<int:order_id>/items/", views.OrderItemListView.as_view(), name="picker-order-items"),
    path("orders/<int:order_id>/submit/", views.SubmitOrderView.as_view(), name="picker-submit-order"),
    path("attendance/check-in/", views.CheckInView.as_view(), name="picker-check-in"),
    path("attendance/check-out/", views.CheckOutView.as_view(), name="picker-check-out"),
]