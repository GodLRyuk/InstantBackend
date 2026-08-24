from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import StockAdjustment, StockBatch
from .serializers import StockAdjustmentSerializer, StockBatchSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListCreateAPIView



class StockListAPIView(APIView):

    def get(self, request):
        stocks = StockBatch.objects.select_related('product').order_by('-id')  # ✅ Fixed
        serializer = StockBatchSerializer(stocks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class StockAdjustmentAPIView(ListCreateAPIView):
    serializer_class = StockAdjustmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = StockAdjustment.objects.select_related('batch__product','adjusted_by').order_by('-created_at')
        batch_id = self.request.query_params.get('batch')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        adj = serializer.save(adjusted_by=self.request.user)
        batch = adj.batch
        inv = batch.product.inventory

        if adj.adjust_type == "OUT":
            batch.quantity -= adj.quantity
            inv.total_stock -= adj.quantity
        else:  # IN
            batch.quantity += adj.quantity
            inv.total_stock += adj.quantity

        batch.save()
        inv.save()