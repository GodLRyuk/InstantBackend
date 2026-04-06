from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register('categories', CategoryViewSet)
router.register('subcategories', SubCategoryViewSet)
router.register('brands', BrandViewSet)
router.register('units', UnitViewSet)
router.register('banners', BannerViewSet) 
router.register('advbanners', AdvBannerViewSet) 

urlpatterns = router.urls