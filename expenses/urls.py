from rest_framework.routers import DefaultRouter
from .views import ExpenseViewSet, ExpenseCategoryViewSet

router = DefaultRouter()
router.register("categories", ExpenseCategoryViewSet)
router.register("records", ExpenseViewSet)

urlpatterns = router.urls
