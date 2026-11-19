from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Inventory, StockAdjustment, StockBatch
from .serializers import StockAdjustmentSerializer, StockBatchSerializer
from rest_framework.permissions import IsAdminUser
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView



class StockListAPIView(APIView):

    def get(self, request):
        stocks = StockBatch.objects.select_related('product')
        if request.query_params.get("include_empty", "").lower() != "true":
            stocks = stocks.filter(quantity__gt=0)
        stocks = stocks.order_by('-id')
        serializer = StockBatchSerializer(stocks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class StockAdjustmentAPIView(ListCreateAPIView):
    serializer_class = StockAdjustmentSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = StockAdjustment.objects.select_related('batch__product','adjusted_by').order_by('-created_at')
        batch_id = self.request.query_params.get('batch')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        inventory = Inventory.objects.select_for_update().get(product_id=data["batch"].product_id)
        batch = StockBatch.objects.select_for_update().filter(pk=data["batch"].pk).first()
        if batch is None:
            raise ValidationError({"batch": "Stock batch no longer exists"})

        quantity = data["quantity"]
        if data["adjust_type"] == "OUT":
            if quantity > min(batch.quantity, inventory.available_stock()):
                raise ValidationError({"quantity": "Insufficient available stock"})
            quantity = -quantity

        serializer.save(adjusted_by=self.request.user, batch=batch)
        batch.quantity += quantity
        batch.save(update_fields=["quantity"])
        inventory.total_stock += quantity
        inventory.save(update_fields=["total_stock", "updated_at"])
