from rest_framework import viewsets
from accounts.permissions import PublicCatalogPermission
from .models import Category, SubCategory, Brand, Unit, Banner
from .serializers import *

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [PublicCatalogPermission]


class SubCategoryViewSet(viewsets.ModelViewSet):
    queryset = SubCategory.objects.all()
    serializer_class = SubCategorySerializer
    permission_classes = [PublicCatalogPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get('category_id')

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        return queryset


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    permission_classes = [PublicCatalogPermission]


class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    permission_classes = [PublicCatalogPermission]


class BannerViewSet(viewsets.ModelViewSet):
    queryset = Banner.objects.filter(is_active=True)  # only active banners
    serializer_class = BannerSerializer
    permission_classes = [PublicCatalogPermission]


class AdvBannerViewSet(viewsets.ModelViewSet):
    queryset = AdvBanner.objects.filter(is_active=True)  # only active banners
    serializer_class = ADvBannerSerializer
    permission_classes = [PublicCatalogPermission]