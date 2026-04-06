# accounts/api/urls.py
from django.urls import path
from .views import AdminLoginAPIView, RegisterAPIView, CustomerLoginAPIView

urlpatterns = [
    path('admin-login/', AdminLoginAPIView.as_view(), name='admin-login'),
    path('register/', RegisterAPIView.as_view(), name='register'),
    path("customer-login/", CustomerLoginAPIView.as_view()),
]