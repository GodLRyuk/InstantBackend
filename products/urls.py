from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    GenerateBarcodeAPIView,
    FlashSaleAdminDetailAPIView,
    FlashSaleAdminListAPIView,
    ProductViewSet,
    bundle_offers,
    flash_sale_products,
    new_arrivals,
    products_by_category,
    recommended_products,
)

router = DefaultRouter()
router.register('', ProductViewSet, basename='products')

urlpatterns = [
    path(
        'admin/flash-sales/',
        FlashSaleAdminListAPIView.as_view(),
        name='admin-flash-sales',
    ),
    path(
        'admin/flash-sales/<int:pk>/',
        FlashSaleAdminDetailAPIView.as_view(),
        name='admin-flash-sale-detail',
    ),
    path(
        'generate-barcode/',
        GenerateBarcodeAPIView.as_view(),
        name='generate-barcode',
    ),
    path('new-arrivals/', new_arrivals),
    path('recommended/', recommended_products), 
    path('category/<int:category_id>/products/', products_by_category),
    path('flash-sale/', flash_sale_products, name='flash-sale-products'),
    path('bundles/', bundle_offers, name='bundle-offers'),

]

urlpatterns += router.urls   