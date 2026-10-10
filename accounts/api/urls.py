# accounts/api/urls.py
from django.urls import path

from .views import (
    AdminLoginAPIView,
    RegisterAPIView,
    CustomerLoginAPIView,
    UserProfileAPIView,
    UserListAPIView,
    VerifyOTPAPIView,
    ResendOTPAPIView,
    UpdateProfileAPIView,
    ChangePasswordAPIView,
    RequestEmailOtpAPIView,
    VerifyEmailChangeOTPAPIView,
    DriverLoginAPIView,
    DriverOrderDetailAPIView,
    save_device_token,              # ✅ add this
)
from accounts.api.driver_views import DriverStatusAPIView, DriverAttendanceAPIView


urlpatterns = [
    path('admin-login/', AdminLoginAPIView.as_view(), name='admin-login'),
    path('register/', RegisterAPIView.as_view(), name='register'),
    path("customer-login/", CustomerLoginAPIView.as_view()),
    path("profile/", UserProfileAPIView.as_view(), name="user-profile"),
    path("users/", UserListAPIView.as_view(), name="user-list"),
    path('update-profile/', UpdateProfileAPIView.as_view(), name='update-profile'),
    path('change-password/', ChangePasswordAPIView.as_view(), name='change-password'),
    path("verify-otp/", VerifyOTPAPIView.as_view()),
    path("resend-otp/", ResendOTPAPIView.as_view()),
    path("request-email-otp/", RequestEmailOtpAPIView.as_view()),
    path("verify-email-change-otp/", VerifyEmailChangeOTPAPIView.as_view()),
    path('driver/login/', DriverLoginAPIView.as_view(), name='driver-login'),
    path('driver/status/', DriverStatusAPIView.as_view()),
    path("driver/order/<int:order_id>/", DriverOrderDetailAPIView.as_view()),
    path('driver/attendance/', DriverAttendanceAPIView.as_view()),
    path('save-device-token/', save_device_token, name='save-device-token'),  # ✅
]