from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import DriverAttendance
from orders.models import Order, OrderItem

from .models import PickRecord
from .serializers import AttendanceSerializer, PickOrderItemSerializer, PickOrderSerializer


class IsPickupBoy(permissions.BasePermission):
    def has_permission(self, request, view):
        return getattr(request.user, "role", None) == "PICKUP"


class ConfirmedOrderListView(generics.ListAPIView):
    serializer_class = PickOrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsPickupBoy]

    def get_queryset(self):
        return Order.objects.filter(
            order_status__in=["CONFIRMED", "PACKED"]
        ).order_by("-created_at")


class OrderItemListView(generics.ListAPIView):
    serializer_class = PickOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsPickupBoy]

    def get_queryset(self):
        return OrderItem.objects.filter(order_id=self.kwargs["order_id"])


class SubmitOrderView(APIView):
    """
    Called when the picker taps Submit on an order:
      1. Logs a PickRecord (product + picker user) for every item on the order.
      2. Moves the order to order_status = "SHIPPED".
    """
    permission_classes = [permissions.IsAuthenticated, IsPickupBoy]

    def post(self, request, order_id):
        try:
            order = Order.objects.select_related(None).get(id=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        items = OrderItem.objects.filter(order=order)
        for item in items:
            PickRecord.objects.create(
                order=order,
                order_item=item,
                product=item.product,
                picked_by=request.user,
            )

        order.order_status = "PACKED"
        order.save(update_fields=["order_status"])

        return Response(PickOrderSerializer(order).data)


class CheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPickupBoy]

    def post(self, request):
        today = timezone.localdate()
        open_session = DriverAttendance.objects.filter(
            driver=request.user, date=today, clock_out_time__isnull=True
        ).first()
        if open_session:
            return Response(AttendanceSerializer(open_session).data)

        session = DriverAttendance.objects.create(
            driver=request.user, date=today, clock_in_time=timezone.now()
        )
        return Response(AttendanceSerializer(session).data, status=status.HTTP_201_CREATED)


class CheckOutView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsPickupBoy]

    def post(self, request):
        today = timezone.localdate()
        session = DriverAttendance.objects.filter(
            driver=request.user, date=today, clock_out_time__isnull=True
        ).first()
        if not session:
            return Response({"detail": "No open attendance session."}, status=status.HTTP_400_BAD_REQUEST)

        session.clock_out_time = timezone.now()
        session.calculate_total_hours()
        return Response(AttendanceSerializer(session).data)