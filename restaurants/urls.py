from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register(r'partner/categories', views.PartnerCategoryViewSet, basename='partner-category')
router.register(r'partner/items', views.PartnerItemViewSet, basename='partner-item')
router.register(r'partner/orders', views.PartnerOrderViewSet, basename='partner-order')
router.register(r'admin/cuisines', views.AdminCuisineViewSet, basename='admin-cuisine')
router.register(
    r'admin/menu-categories', views.AdminMenuCategoryViewSet, basename='admin-menu-category'
)
router.register(r'admin/restaurants', views.AdminRestaurantViewSet, basename='admin-restaurant')
router.register(r'admin/orders', views.AdminOrderViewSet, basename='admin-restaurant-order')
router.register(r'orders', views.CustomerOrderViewSet, basename='restaurant-order')
router.register(r'', views.RestaurantViewSet, basename='restaurant')  # keep last

urlpatterns = [
    path('cuisines/', views.CuisineListView.as_view(), name='restaurant-cuisines'),
    path('partner/onboard/', views.PartnerOnboardView.as_view(), name='partner-onboard'),
    path('partner/restaurant/', views.PartnerRestaurantView.as_view(), name='partner-restaurant'),
] + router.urls
