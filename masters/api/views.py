from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from masters.models import Brand, Category, SubCategory


class CreateBrandAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):

        name = request.data.get("name")

        if not name:
            return Response(
                {"error": "Brand name is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if Brand.objects.filter(name=name).exists():
            return Response(
                {"error": "Brand already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        brand = Brand.objects.create(name=name)

        return Response({
            "message": "Brand created successfully",
            "brand_id": brand.id,
            "name": brand.name
        }, status=status.HTTP_201_CREATED)
class BrandUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def put(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin allowed"}, status=403)

        try:
            brand = Brand.objects.get(id=pk)
        except Brand.DoesNotExist:
            return Response({"error": "Brand not found"}, status=404)

        name = request.data.get("name")

        if name:
            brand.name = name
            brand.save()

        return Response({
            "message": "Brand updated",
            "id": brand.id,
            "name": brand.name
        })
class BrandDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin allowed"}, status=403)

        try:
            brand = Brand.objects.get(id=pk)
        except Brand.DoesNotExist:
            return Response({"error": "Brand not found"}, status=404)

        brand.delete()

        return Response({
            "message": "Brand deleted successfully"
        })
class BrandListAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        brands = Brand.objects.all().values("id", "name")

        return Response({
            "brands": list(brands)
        })

class CategoryCreateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):

        if not request.user.is_staff:
            return Response({"error": "Only admin can create category"}, status=403)

        name = request.data.get("name")

        if not name:
            return Response({"error": "Name is required"}, status=400)

        category = Category.objects.create(name=name)

        return Response({
            "message": "Category created successfully",
            "id": category.id,
            "name": category.name
        })
class CategoryListAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        categories = Category.objects.all()

        data = []
        for cat in categories:
            data.append({
                "id": cat.id,
                "name": cat.name
            })

        return Response(data)
class CategoryListAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        categories = Category.objects.all()

        data = []
        for cat in categories:
            data.append({
                "id": cat.id,
                "name": cat.name
            })

        return Response(data)
class CategoryUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def put(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can update category"}, status=403)

        try:
            category = Category.objects.get(id=pk)
        except Category.DoesNotExist:
            return Response({"error": "Category not found"}, status=404)

        category.name = request.data.get("name", category.name)
        category.save()

        return Response({"message": "Category updated"})
class CategoryDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can delete category"}, status=403)

        try:
            category = Category.objects.get(id=pk)
        except Category.DoesNotExist:
            return Response({"error": "Category not found"}, status=404)

        category.delete()

        return Response({"message": "Category deleted"})
from masters.models import Unit

class UnitCreateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):

        if not request.user.is_staff:
            return Response({"error": "Only admin can create unit"}, status=403)

        name = request.data.get("name")

        unit = Unit.objects.create(name=name)

        return Response({
            "message": "Unit created",
            "id": unit.id
        })

from masters.models import SubCategory

class SubCategoryCreateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):

        if not request.user.is_staff:
            return Response({"error": "Only admin can create subcategory"}, status=403)

        name = request.data.get("name")
        category_id = request.data.get("category")

        category = Category.objects.get(id=category_id)

        subcategory = SubCategory.objects.create(
            name=name,
            category=category
        )

        return Response({
            "message": "SubCategory created",
            "id": subcategory.id
        })
class SubCategoryListAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        subcategories = SubCategory.objects.all()

        data = []
        for sub in subcategories:
            data.append({
                "id": sub.id,
                "name": sub.name,
                "category": sub.category.name
            })

        return Response(data)
class SubCategoryUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def put(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can update subcategory"}, status=403)

        try:
            subcategory = SubCategory.objects.get(id=pk)
        except SubCategory.DoesNotExist:
            return Response({"error": "SubCategory not found"}, status=404)

        name = request.data.get("name")
        category_id = request.data.get("category")

        if name:
            subcategory.name = name

        if category_id:
            category = Category.objects.get(id=category_id)
            subcategory.category = category

        subcategory.save()

        return Response({"message": "SubCategory updated successfully"})
class SubCategoryUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def put(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can update subcategory"}, status=403)

        try:
            subcategory = SubCategory.objects.get(id=pk)
        except SubCategory.DoesNotExist:
            return Response({"error": "SubCategory not found"}, status=404)

        name = request.data.get("name")
        category_id = request.data.get("category")

        if name:
            subcategory.name = name

        if category_id:
            category = Category.objects.get(id=category_id)
            subcategory.category = category

        subcategory.save()

        return Response({"message": "SubCategory updated successfully"})

class SubCategoryDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can delete subcategory"}, status=403)

        try:
            subcategory = SubCategory.objects.get(id=pk)
        except SubCategory.DoesNotExist:
            return Response({"error": "SubCategory not found"}, status=404)

        subcategory.delete()

        return Response({"message": "SubCategory deleted"})

class UnitListAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):

        units = Unit.objects.all()

        data = []
        for unit in units:
            data.append({
                "id": unit.id,
                "name": unit.name
            })

        return Response(data)
class UnitUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def put(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can update unit"}, status=403)

        try:
            unit = Unit.objects.get(id=pk)
        except Unit.DoesNotExist:
            return Response({"error": "Unit not found"}, status=404)

        unit.name = request.data.get("name", unit.name)
        unit.save()

        return Response({"message": "Unit updated successfully"})

class UnitDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, pk):

        if not request.user.is_staff:
            return Response({"error": "Only admin can delete unit"}, status=403)

        try:
            unit = Unit.objects.get(id=pk)
        except Unit.DoesNotExist:
            return Response({"error": "Unit not found"}, status=404)

        unit.delete()

        return Response({"message": "Unit deleted"})