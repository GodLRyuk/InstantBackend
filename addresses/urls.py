from django.urls import path
from .views import AddAddressAPIView, ListAddressAPIView, DeleteAddressAPIView

urlpatterns = [
    path('add/', AddAddressAPIView.as_view()),
    path('list/', ListAddressAPIView.as_view()),
    path('delete/<int:id>/', DeleteAddressAPIView.as_view()),
]