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

            if new_quantity > inventory.available_stock():
                return Response(
                    {"error": "Stock limit exceeded"},
                    status=400
                )

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
        items = cart.items.all()

        data = []
        total = 0

        for item in items:
            price = item.product.discounted_price()
            item_total = price * item.quantity

            data.append({
                "product": item.product.name,
                "quantity": item.quantity,
                "price": price,
                "total": item_total
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

        try:
            cart_item = CartItem.objects.get(cart__user=user, product_id=product_id)
        except CartItem.DoesNotExist:
            return Response({"error": "Item not in cart"}, status=400)

        # Remove and update inventory
        cart_item.remove()

        return Response({"message": "Item removed from cart"})