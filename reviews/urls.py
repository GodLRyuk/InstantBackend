from django.urls import path
from .views import product_reviews

urlpatterns = [
    path('products/<int:product_id>/reviews/', product_reviews),
]