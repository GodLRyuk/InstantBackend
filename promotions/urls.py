from django.urls import path
from . import views

urlpatterns = [
    path("validate-coupon/", views.validate_coupon, name="validate_coupon"),
    path("pass/purchase/", views.purchase_pass, name="purchase_pass"),
    path("pass/status/", views.pass_status, name="pass_status"),
]