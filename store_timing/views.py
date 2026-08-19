from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import StoreSchedule
from .serializers import StoreScheduleSerializer, StoreStatusSerializer


class StoreStatusView(APIView):
    """
    GET /api/store/status/
    Public — anyone (including logged-out app screens) can check if the
    store is currently open, and what the hours are.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        schedule = StoreSchedule.get()
        data = {
            "is_open": schedule.is_open_now(),
            "opens_at": schedule.opens_at,
            "closes_at": schedule.closes_at,
            "server_time": timezone.localtime(),
        }
        return Response(StoreStatusSerializer(data).data)


class StoreScheduleView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT/PATCH /api/store/schedule/
    Admin-only. Update opens_at / closes_at / is_force_closed.
    """
    serializer_class = StoreScheduleSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_object(self):
        return StoreSchedule.get()
