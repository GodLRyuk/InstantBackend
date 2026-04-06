# orders/views.py

from rest_framework.generics import ListAPIView, RetrieveAPIView, CreateAPIView
from rest_framework.permissions import IsAuthenticated
from .models import Order
from .serializers import OrderSerializer, CreateOrderSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class OrderListView(ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects
            .filter(user=self.request.user)
            .prefetch_related('items__product')
            .order_by('-id')
        )
class OrderDetailView(RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects
            .filter(user=self.request.user)
            .prefetch_related('items__product')
        )
class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Order.objects.get(id=pk, user=request.user)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.order_status == "DELIVERED":
            return Response({"error": "Delivered order cannot be cancelled"}, status=400)

        if order.order_status == "CANCELLED":
            return Response({"error": "Order already cancelled"}, status=400)

        order.mark_cancelled()

        return Response({"message": "Order cancelled successfully"})
class UpdateOrderStatusView(APIView):
    permission_classes = [IsAuthenticated]  # later change to Admin only

    def post(self, request, pk):
        status_value = request.data.get("status")

        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if status_value == "SHIPPED":
            order.mark_shipped()
        elif status_value == "DELIVERED":
            order.mark_delivered()
        elif status_value == "CONFIRMED":
            order.order_status = "CONFIRMED"
            order.save()
        else:
            return Response({"error": "Invalid status"}, status=400)

        return Response({"message": "Order status updated"})
class CreateOrderView(CreateAPIView):
    serializer_class = CreateOrderSerializer
    permission_classes = [IsAuthenticated]