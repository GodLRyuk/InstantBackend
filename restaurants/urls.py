from django.urls import path
from rest_framework.routers import SimpleRouter

from . import payment_admin, views

router = SimpleRouter()
router.register(r'partner/categories', views.PartnerCategoryViewSet, basename='partner-category')
router.register(r'partner/items', views.PartnerItemViewSet, basename='partner-item')
router.register(
    r'partner/items/(?P<item_pk>\d+)/addon-groups',
    views.PartnerAddOnGroupViewSet,
    basename='partner-addon-group',
)
router.register(
    r'partner/items/(?P<item_pk>\d+)/addon-groups/(?P<group_pk>\d+)/options',
    views.PartnerAddOnOptionViewSet,
    basename='partner-addon-option',
)
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
    path('delivery-charge/', views.DeliveryChargeView.as_view(), name='restaurant-delivery-charge'),
    path('partner/onboard/', views.PartnerOnboardView.as_view(), name='partner-onboard'),
    path('partner/menu-workbook/', views.PartnerMenuWorkbookView.as_view(), name='partner-menu-workbook'),
    path('admin/commissions/', payment_admin.CommissionsView.as_view(), name='admin-commissions'),
    path('admin/payment-splits/', payment_admin.SplitsView.as_view(), name='admin-payment-splits'),
    path('admin/refunds/', payment_admin.RefundsView.as_view(), name='admin-restaurant-refunds'),
    path('admin/vendors/', views.AdminRestaurantVendorView.as_view(), name='admin-restaurant-vendors'),
    path('admin/payment-splits/process/', views.ProcessPaymentSplitsView.as_view(), name='process-restaurant-payment-splits'),
    path('admin/payment-splits/sync/', views.SyncPaymentSplitsView.as_view(), name='sync-restaurant-payment-splits'),
    path('admin/refunds/process/', views.ProcessRestaurantRefundsView.as_view(), name='process-restaurant-refunds'),
    path('driver/orders/', views.RestaurantDriverOrdersView.as_view(), name='restaurant-driver-orders'),
    path(
        'driver/orders/<int:order_id>/',
        views.RestaurantDriverOrderDetailView.as_view(),
        name='restaurant-driver-order-detail',
    ),
    path(
        'driver/orders/<int:order_id>/status/',
        views.RestaurantDriverOrderDetailView.as_view(),
        name='restaurant-driver-order-status',
    ),
] + router.urls
