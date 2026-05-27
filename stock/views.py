from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import StockBatch
from .serializers import StockBatchSerializer

class StockListAPIView(APIView):

    def get(self, request):
        stocks = Inventory.objects.all().order_by('-id')
        serializer = StockBatchSerializer(stocks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)