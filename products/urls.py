from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, new_arrivals, recommended_products,products_by_category, flash_sale_products, bundle_offers

router = DefaultRouter()
router.register('', ProductViewSet, basename='products')

urlpatterns = [
    path('new-arrivals/', new_arrivals),
    path('recommended/', recommended_products), 
    path('category/<int:category_id>/products/', products_by_category),
    path('flash-sale/', flash_sale_products, name='flash-sale-products'),
    path('bundles/', bundle_offers, name='bundle-offers'),

]

urlpatterns += router.urls   