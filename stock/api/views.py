from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from products.models import Product
from stock.models import Inventory, StockBatch
from rest_framework.generics import ListAPIView
from django.shortcuts import get_object_or_404
from ..serializers import InventorySerializer, StockBatchSerializer
from django.db.models import Sum

class AddStockAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        if not request.user.is_staff:
            return Response(
                {"error": "Only admin can add stock"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            product = Product.objects.get(id=request.data.get("product_id"))
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        quantity = int(request.data.get("quantity", 0))
        batch_no = request.data.get("batch_no")
        purchase_price = request.data.get("purchase_price")
        selling_price = request.data.get("selling_price")

        # Create batch
        batch = StockBatch.objects.create(
            product=product,
            batch_no=batch_no,
            quantity=quantity,
            purchase_price=purchase_price,
            selling_price=selling_price
        )

        # Update inventory
        inventory, created = Inventory.objects.get_or_create(
            product=product,
            defaults={'total_stock': 0}  # start at 0 if new
        )
        inventory.total_stock += quantity
        inventory.save()

        # Optional: Update product selling price
        if selling_price:
            product.price = selling_price
            product.save()

        return Response({
            "message": "Stock added successfully",
            "batch_id": batch.id,
            "total_stock": inventory.total_stock
        }, status=status.HTTP_201_CREATED)
class UpdateStockAPIView(APIView):
    """
    Update a StockBatch and automatically update related Inventory
    """
    def put(self, request, pk):
        try:
            batch = StockBatch.objects.get(pk=pk)
        except StockBatch.DoesNotExist:
            return Response({"error": "Stock batch not found"}, status=status.HTTP_404_NOT_FOUND)

        old_quantity = batch.quantity  # save old quantity for inventory adjustment

        serializer = StockBatchSerializer(batch, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Update Inventory
            inventory = batch.product.inventory
            quantity_diff = batch.quantity - old_quantity
            inventory.total_stock += quantity_diff
            inventory.save()

            return Response({
                "message": "Stock batch updated successfully",
                "batch": serializer.data,
                "inventory": {
                    "total_stock": inventory.total_stock
                }
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class StockListAPIView(APIView):
    def get(self, request):
        stocks = StockBatch.objects.all().order_by('-id')  
        serializer = StockBatchSerializer(stocks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
class DeleteStockAPIView(APIView):
    """
    Delete a StockBatch and adjust Inventory accordingly
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        # Only admin can delete stock
        if not request.user.is_staff:
            return Response(
                {"error": "Only admin can delete stock"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            batch = StockBatch.objects.get(pk=pk)
        except StockBatch.DoesNotExist:
            return Response({"error": "Stock batch not found"}, status=status.HTTP_404_NOT_FOUND)

        # Adjust inventory
        inventory = batch.product.inventory
        inventory.total_stock -= batch.quantity
        if inventory.total_stock < 0:
            inventory.total_stock = 0  # just in case
        inventory.save()

        # Delete the batch
        batch.delete()

        return Response(
            {"message": "Stock batch deleted successfully", "total_stock": inventory.total_stock},
            status=status.HTTP_200_OK
        )
class InventoryListAPIView(APIView):
    def get(self, request):
        inventories = Inventory.objects.select_related('product').all()
        serializer = InventorySerializer(inventories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)