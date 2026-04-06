from rest_framework import viewsets
from .models import Category, SubCategory, Brand, Unit, Banner
from .serializers import *

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer


class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.all()
    serializer_class = SubCategorySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get('category_id')

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return queryset


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer


class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
class BannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.filter(is_active=True)  # only active banners
    serializer_class = BannerSerializer
class AdvBannerViewSet(viewsets.ModelViewSet):
    queryset = AdvBanner.objects.filter(is_active=True)  # only active banners
    serializer_class = ADvBannerSerializer