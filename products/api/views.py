from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from products.models import Product
from masters.models import Category, SubCategory, Brand, Unit
from stock.models import Inventory
from django.db.models import Q


class ProductCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        if not request.user.is_staff:
            return Response(
                {"error": "Only admin can create product"},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            category = Category.objects.get(id=request.data.get("category"))
            subcategory = SubCategory.objects.get(id=request.data.get("subcategory"))
            unit = Unit.objects.get(id=request.data.get("unit"))
        except:
            return Response({"error": "Invalid category/subcategory/unit"}, status=400)

        brand_id = request.data.get("brand")
        brand = None
        if brand_id:
            brand = Brand.objects.filter(id=brand_id).first()

        product = Product.objects.create(
            name=request.data.get("name"),
            category=category,
            subcategory=subcategory,
            brand=brand,
            unit=unit,
            unit_size=request.data.get("unit_size"),
            price=request.data.get("price"),
            discount_percent=request.data.get("discount_percent", 0),
            description=request.data.get("description"),
            image=request.FILES.get("image"),
            is_active=True
        )

        # ADD STOCK HERE
        stock = request.data.get("stock", 0)

        inventory, created = Inventory.objects.get_or_create(product=product)
        inventory.total_stock = stock
        inventory.save()

        return Response({
            "message": "Product created successfully",
            "product_id": product.id,
            "stock_added": stock
        }, status=201)

class ProductListAPIView(APIView):

    permission_classes = [AllowAny]

    def get(self, request):

        products = Product.objects.all()

        data = []

        for product in products:
            data.append({
            "id": product.id,
            "name": product.name,
            "category": product.category.name,
            "subcategory": product.subcategory.name,
            "brand": product.brand.name if product.brand else None,
            "unit_id": product.unit.id if product.unit else None,
            "unit_name": product.unit.name if product.unit else None,
            "unit_size": product.unit_size,
            "price": str(product.price),
            "discount_percent": str(product.discount_percent),
            "final_price": str(product.discounted_price()),
            "description": product.description,   # ✅ comma added
            "stock": product.stock,               # ✅ comma added
            "image": product.image.url if product.image else None,
            "is_active": product.is_active
        })

        return Response(data)
class ProductUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def put(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can update product"}, status=403)

        try:
            product = Product.objects.get(id=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        product.name = request.data.get("name", product.name)
        product.price = request.data.get("price", product.price)
        product.discount_percent = request.data.get("discount_percent", product.discount_percent)
        product.description = request.data.get("description", product.description)
        product.is_active = request.data.get("is_active", product.is_active)

        if request.FILES.get("image"):
            product.image = request.FILES.get("image")

        product.save()

        return Response({"message": "Product updated successfully"})

class ProductDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can delete product"}, status=403)

        try:
            product = Product.objects.get(id=pk)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        product.delete()

        return Response({"message": "Product deleted successfully"})
class ProductSearchAPIView(APIView):

    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("search", "").strip()

        if not query:
            return Response({"error": "Search query is required"}, status=400)

        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(brand__name__icontains=query) |
            Q(category__name__icontains=query) |
            Q(subcategory__name__icontains=query) |
            Q(description__icontains=query)
        ).distinct()

        data = [{
            "id": p.id,
            "name": p.name,
            "category": p.category.name,
            "subcategory": p.subcategory.name,
            "brand": p.brand.name if p.brand else None,
            "unit_name": p.unit.name if p.unit else None,
            "price": str(p.price),
            "final_price": str(p.discounted_price()),
            "image": p.image.url if p.image else None,
            "description": p.description,
            "is_active": p.is_active,
        } for p in products]

        return Response({
            "count": products.count(),
            "results": data
        })