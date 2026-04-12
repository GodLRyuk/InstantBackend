from django.urls import path
from .views import AddToCartView, ViewCartView, RemoveFromCartView, UpdateCartQuantityView

urlpatterns = [
    path('add/', AddToCartView.as_view()),
    path('view/', ViewCartView.as_view()),
    path("remove/", RemoveFromCartView.as_view(), name="remove-from-cart"),
    path('update-cart-quantity/', UpdateCartQuantityView.as_view()),
]