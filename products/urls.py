from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, new_arrivals, recommended_products,products_by_category

router = DefaultRouter()
router.register('', ProductViewSet, basename='products')

urlpatterns = [
    path('new-arrivals/', new_arrivals),
    path('recommended/', recommended_products), 
    path('category/<int:category_id>/products/', products_by_category),

]

urlpatterns += router.urls   