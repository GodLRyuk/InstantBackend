from itertools import product

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Cart, CartItem
from products.models import Product


class AddToCartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))

        product = Product.objects.get(id=product_id)
        inventory = product.inventory

        cart, _ = Cart.objects.get_or_create(user=user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product
        )

        if created:
            cart_item.quantity = quantity
        else:
            cart_item.quantity = cart_item.quantity + quantity

        cart_item.save()

        return Response({"message": "Product added to cart"})
class ViewCartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = Cart.objects.get(user=request.user)
        items = cart.items.all().order_by('product_id')

        data = []
        total = 0

        for item in items:
            product = item.product 
            inventory = product.inventory
            price = product.discounted_price()
            item_total = price * item.quantity

            data.append({
                "product_id": item.product_id,
                "product": product.name,
                "quantity": item.quantity,
                "price": price,
                "total": item_total,
                "available_stock": inventory.available_stock(),
                "image": request.build_absolute_uri(product.image.url) if product.image else None
            })

            total += item_total

        return Response({
            "items": data,
            "cart_total": total
        })
class RemoveFromCartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        product_id = request.data.get("product_id")

        if not product_id:
            return Response({"error": "Product ID required"}, status=400)

        try:
            cart_item = CartItem.objects.get(
                cart__user=user,
                product_id=product_id
            )
        except CartItem.DoesNotExist:
            return Response({"error": "Item not in cart"}, status=404)

        cart_item.delete()

        return Response({
            "success": True,
            "message": "Item removed from cart",
        })
class UpdateCartQuantityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))

        if quantity < 1:
            return Response({"error": "Quantity must be at least 1"}, status=400)

        try:
            cart_item = CartItem.objects.get(
                cart__user=user,
                product_id=product_id
            )
        except CartItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=404)

        cart_item.quantity = quantity
        cart_item.save()

        return Response({
            "success": True,
            "message": "Cart updated"
        })
    
class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cart = Cart.objects.get(user=request.user)
        items = cart.items.select_related('product__inventory').all()

        # ✅ Validate all items before doing anything
        errors = []
        for item in items:
            available = item.product.inventory.total_stock
            if item.quantity > available:
                errors.append({
                    "product": item.product.name,
                    "requested": item.quantity,
                    "available": available,
                })

        if errors:
            return Response({
                "error": "Some items are out of stock",
                "items": errors
            }, status=400)

        # ✅ All good — deduct stock and place order
        for item in items:
            inventory = item.product.inventory
            inventory.total_stock -= item.quantity
            inventory.save()

        # ... create order, payment etc.