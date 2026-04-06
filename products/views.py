from rest_framework import viewsets
from .models import Product
from .serializers import ProductSerializer
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import ProductListSerializer
from orders.models import OrderItem
from cart.models import CartItem
import random
from decimal import Decimal

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer

@api_view(['GET'])
def new_arrivals(request):
    # Get all active products, ordered by created_at descending
    products = Product.objects.filter(is_active=True).order_by('-created_at')

    # Use the same serializer as ProductViewSet
    # serializer = ProductSerializer(products, many=True, context={'request': request})
    serializer = ProductListSerializer(products, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
def recommended_products(request):
    user = request.user
    recommended = Product.objects.none()

    purchased_products = OrderItem.objects.filter(order__user=user).values_list('product', flat=True)

    if purchased_products.exists():
        categories = Product.objects.filter(id__in=purchased_products).values_list('category', flat=True)
        recommended = Product.objects.filter(category__in=categories, is_active=True).exclude(id__in=purchased_products).distinct()[:10]

    elif CartItem.objects.filter(cart__user=user).exists():
        cart_products = CartItem.objects.filter(cart__user=user).values_list('product', flat=True)
        categories = Product.objects.filter(id__in=cart_products).values_list('category', flat=True)
        recommended = Product.objects.filter(category__in=categories, is_active=True).exclude(id__in=cart_products).distinct()[:10]

    else:
        all_active = Product.objects.filter(is_active=True)
        recommended = random.sample(list(all_active), min(10, all_active.count()))

    serializer = ProductListSerializer(recommended, many=True, context={'request': request})
    return Response(serializer.data)
@api_view(['GET'])
def products_by_category(request, category_id):
    """
    Get products filtered by category ID
    """
    products = Product.objects.filter(category_id=category_id, is_active=True)
    serializer = ProductListSerializer(products, many=True, context={'request': request})
    return Response(serializer.data)