"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/masters/', include('masters.urls')),
    path('api/products/', include('products.urls')),
    path('api/cart/', include('cart.urls')),
    path('api/', include('orders.urls')),
    path('api/accounts/', include('accounts.api.urls')),
    path('api/stock/', include('stock.api.urls')),
    path('api/token/refresh/', TokenRefreshView.as_view()),
    path('api/addresses/', include('addresses.urls')),
    path('api/', include('reviews.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/promotions/', include('promotions.urls')), 
    path('api/wishlist/', include('wishlist.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
