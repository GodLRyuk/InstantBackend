from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register('categories', CategoryViewSet)
router.register('subcategories', SubCategoryViewSet)
router.register('brands', BrandViewSet)
router.register('units', UnitViewSet)
router.register(r'banners', BannerViewSet)

urlpatterns = [
    # ✅ include router urls
    path('', include(router.urls)),

    # ✅ your manual APIs
    path('brand/create/', CreateBrandAPIView.as_view()),
    path("brand/list/", BrandListAPIView.as_view()),
    path("brand/update/<int:pk>/", BrandUpdateAPIView.as_view()),
    path("brand/delete/<int:pk>/", BrandDeleteAPIView.as_view()),

    path('category/create/', CategoryCreateAPIView.as_view()),
    path('category/list/', CategoryListAPIView.as_view()),
    path('category/update/<int:pk>/', CategoryUpdateAPIView.as_view()),
    path('category/delete/<int:pk>/', CategoryDeleteAPIView.as_view()),

    path('subcategory/create/', SubCategoryCreateAPIView.as_view()),
    path('subcategory/list/', SubCategoryListAPIView.as_view()),
    path('subcategory/update/<int:pk>/', SubCategoryUpdateAPIView.as_view()),
    path('subcategory/delete/<int:pk>/', SubCategoryDeleteAPIView.as_view()),

    path('unit/create/', UnitCreateAPIView.as_view()),
    path('unit/list/', UnitListAPIView.as_view()),
    path('unit/update/<int:pk>/', UnitUpdateAPIView.as_view()),
    path('unit/delete/<int:pk>/', UnitDeleteAPIView.as_view()),

    
]