from django.urls import path
from . import views

urlpatterns = [
    path("validate-coupon/", views.validate_coupon, name="validate_coupon"),
]

# In your root urls.py, include this with:
#   path("api/promotions/", include("promotions.urls")),
# So the full URL becomes: POST /api/promotions/validate-coupon/