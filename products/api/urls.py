from django.urls import path
from .views import (
    ProductCreateAPIView,
    ProductListAPIView,
    ProductUpdateAPIView,
    ProductDeleteAPIView,
    new_arrivals,
    recommended_products,
    products_by_category,
    ProductSearchAPIView
)

urlpatterns = [
    path('product/create/', ProductCreateAPIView.as_view()),
    path('product/list/', ProductListAPIView.as_view()),
    path('product/update/<int:pk>/', ProductUpdateAPIView.as_view()),
    path('product/delete/<int:pk>/', ProductDeleteAPIView.as_view()),
    path("search/", ProductSearchAPIView.as_view()),
    path('new-arrivals/', new_arrivals),
    path('recommended/', recommended_products),
]