from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework import status

from products.models import Product
from stock.models import Inventory, StockBatch
from rest_framework.generics import ListAPIView
from django.shortcuts import get_object_or_404
from ..serializers import InventorySerializer, StockBatchSerializer
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal, InvalidOperation

class AddStockAPIView(APIView):

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        if not request.user.is_staff:
            return Response(
                {"error": "Only admin can add stock"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            product = Product.objects.select_for_update().get(id=request.data.get("product"))
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        try:
            quantity = int(request.data.get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            return Response({"error": "Quantity must be positive"}, status=400)
        batch_no = request.data.get("batch_no")
        purchase_price = request.data.get("purchase_price")
        selling_price = request.data.get("selling_price")

        try:
            selling_price_value = Decimal(str(selling_price))
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"error": "Enter a valid selling price."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not selling_price_value.is_finite() or selling_price_value < 0:
            return Response({"error": "Enter a valid selling price."}, status=400)

        if selling_price_value > product.price:
            return Response(
                {
                    "error": (
                        "Selling price cannot be greater than the product price "
                        "(MRP). Please correct the price before adding stock."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update inventory
        inventory, created = Inventory.objects.select_for_update().get_or_create(
            product=product,
            defaults={'total_stock': 0}  # start at 0 if new
        )
        # Create batch
        batch = StockBatch.objects.create(
            product=product,
            batch_no=batch_no,
            quantity=quantity,
            purchase_price=purchase_price,
            selling_price=selling_price
        )

        inventory.total_stock += quantity
        inventory.save()

        return Response({
            "message": "Stock added successfully",
            "batch_id": batch.id,
            "total_stock": inventory.total_stock,
            "product_price": str(product.price),
        }, status=status.HTTP_201_CREATED)
class UpdateStockAPIView(APIView):
    """
    Update a StockBatch and automatically update related Inventory
    """
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def put(self, request, pk):
        try:
            product_id = StockBatch.objects.values_list("product_id", flat=True).get(pk=pk)
            inventory = Inventory.objects.select_for_update().get(product_id=product_id)
            batch = StockBatch.objects.select_for_update().get(pk=pk)
        except StockBatch.DoesNotExist:
            return Response({"error": "Stock batch not found"}, status=status.HTTP_404_NOT_FOUND)

        old_quantity = batch.quantity  # save old quantity for inventory adjustment

        serializer = StockBatchSerializer(batch, data=request.data, partial=True)
        if serializer.is_valid():
            if serializer.validated_data.get("product", batch.product).pk != batch.product_id:
                return Response({"error": "A stock batch cannot change products"}, status=400)
            quantity_diff = serializer.validated_data.get("quantity", old_quantity) - old_quantity
            if quantity_diff < 0 and -quantity_diff > inventory.available_stock():
                return Response({"error": "Insufficient available stock"}, status=400)
            serializer.save()
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
        stocks = StockBatch.objects.all()
        if request.query_params.get("include_empty", "").lower() != "true":
            stocks = stocks.filter(quantity__gt=0)
        stocks = stocks.order_by('-id')
        serializer = StockBatchSerializer(stocks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
class DeleteStockAPIView(APIView):
    """
    Delete a StockBatch and adjust Inventory accordingly
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk):
        # Only admin can delete stock
        if not request.user.is_staff:
            return Response(
                {"error": "Only admin can delete stock"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            product_id = StockBatch.objects.values_list("product_id", flat=True).get(pk=pk)
            inventory = Inventory.objects.select_for_update().get(product_id=product_id)
            batch = StockBatch.objects.select_for_update().get(pk=pk)
        except StockBatch.DoesNotExist:
            return Response({"error": "Stock batch not found"}, status=status.HTTP_404_NOT_FOUND)

        if batch.quantity > inventory.available_stock():
            return Response({"error": "Insufficient available stock"}, status=400)
        batch.delete()
        inventory.refresh_from_db(fields=["total_stock"])

        return Response(
            {"message": "Stock batch deleted successfully", "total_stock": inventory.total_stock},
            status=status.HTTP_200_OK
        )
class InventoryListAPIView(APIView):
    def get(self, request):
        inventories = Inventory.objects.select_related('product').all()
        serializer = InventorySerializer(inventories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
