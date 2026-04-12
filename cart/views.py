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

        # ✅ Check available stock
        if quantity > inventory.available_stock():
            return Response(
                {"error": "Not enough stock available"},
                status=400
            )

        cart, created = Cart.objects.get_or_create(user=user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product
        )

        # ✅ If item already in cart
        if not created:
            new_quantity = cart_item.quantity + quantity

            old_quantity = cart_item.quantity if not created else 0

            available_stock = inventory.available_stock() + old_quantity

            if new_quantity > available_stock:
                return Response({"error": "Stock limit exceeded"}, status=400)

            cart_item.quantity = new_quantity
        else:
            cart_item.quantity = quantity

        cart_item.save()

        # ✅ Reserve stock AFTER successful cart update
        inventory.reserved_stock += quantity
        inventory.save()

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

        product = cart_item.product

        # ✅ SAFE inventory access
        try:
            inventory = product.inventory
        except:
            return Response({
                "error": "Inventory not found for this product"
            }, status=500)

        # ✅ update reserved stock
        inventory.reserved_stock -= cart_item.quantity

        # safety check
        if inventory.reserved_stock < 0:
            inventory.reserved_stock = 0

        inventory.save()

        # ✅ delete cart item
        cart_item.delete()

        return Response({
            "success": True,
            "message": "Item removed from cart",
            "available_stock": inventory.available_stock()
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

        product = cart_item.product
        inventory = product.inventory

        old_qty = cart_item.quantity
        available_stock = inventory.available_stock() + old_qty

        if quantity > available_stock:
            return Response({"error": "Stock limit exceeded"}, status=400)

        # ✅ adjust reserved stock
        inventory.reserved_stock = inventory.reserved_stock - old_qty + quantity
        inventory.save()

        cart_item.quantity = quantity
        cart_item.save()

        return Response({
            "success": True,
            "message": "Cart updated"
        })