from django.urls import path
from .views import StoreStatusView, StoreScheduleView

urlpatterns = [
    path("status/", StoreStatusView.as_view()),
    path("schedule/", StoreScheduleView.as_view()),
]
