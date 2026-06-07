from rest_framework import viewsets
from .models import Bundle, FlashSale, Product
from .serializers import BundleSerializer, ProductSerializer
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import ProductListSerializer
from orders.models import OrderItem
from cart.models import CartItem
import random
from decimal import Decimal
from django.db.models import Q
from django.utils import timezone

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(brand__name__icontains=search) |
                Q(category__name__icontains=search) |
                Q(subcategory__name__icontains=search) |
                Q(description__icontains=search)
            ).distinct()

        return queryset

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

    purchased_products = OrderItem.objects.filter(
        order__user=user
    ).values_list('product', flat=True)

    cart_products = CartItem.objects.filter(
        cart__user=user
    ).values_list('product', flat=True)

    all_products = list(purchased_products) + list(cart_products)

    recommended = Product.objects.none()

    if all_products:
        categories = Product.objects.filter(
            id__in=all_products
        ).values_list('category', flat=True)

        if categories:
            recommended = Product.objects.filter(
                category__in=categories,
                is_active=True
            ).exclude(
                id__in=all_products
            ).distinct()[:10]

    # ✅ Fallback if empty
    if not recommended.exists():
        recommended = Product.objects.filter(
            is_active=True
        ).exclude(
            id__in=all_products
        ).order_by('?')[:10]

    serializer = ProductListSerializer(
        recommended,
        many=True,
        context={'request': request}
    )

    return Response(serializer.data)
@api_view(['GET'])
def products_by_category(request, category_id):
    """
    Get products filtered by category ID
    """
    products = Product.objects.filter(category_id=category_id, is_active=True)
    serializer = ProductListSerializer(products, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['GET'])
def flash_sale_products(request):
    flash_sale = FlashSale.objects.filter(
        is_active=True,
        start_time__lte=timezone.now(),
        end_time__gte=timezone.now()
    ).first()

    if not flash_sale:
        return Response({'flash_sale': None, 'products': []})

    products = flash_sale.products.filter(  # ← products linked to this sale
        is_active=True,
        discount_percent__gt=0
    ).select_related(
        'category', 'subcategory', 'brand', 'unit'
    ).prefetch_related(
        'inventory'
    ).order_by('-discount_percent')[:10]

    serializer = ProductListSerializer(products, many=True, context={'request': request})

    return Response({
        'flash_sale': {
            'title': flash_sale.title,
            'end_time': flash_sale.end_time,
        },
        'products': serializer.data
    })
@api_view(['GET'])
def bundle_offers(request):
    bundles = Bundle.objects.filter(is_active=True)
    serializer = BundleSerializer(bundles, many=True, context={'request': request})
    return Response(serializer.data)