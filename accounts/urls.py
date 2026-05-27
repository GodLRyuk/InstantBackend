# accounts/api/urls.py
from django.urls import path
from .views import AdminLoginAPIView, CustomerLoginAPIView, UserProfileAPIView

urlpatterns = [
    path('admin-login/', AdminLoginAPIView.as_view(), name='admin-login'),
    path('register/', RegisterAPIView.as_view()),
    path("customer-login/", CustomerLoginAPIView.as_view()),
    path("profile/", UserProfileAPIView.as_view(), name="user-profile"),
]