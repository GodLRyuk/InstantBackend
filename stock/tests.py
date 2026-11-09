from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from masters.models import Category, SubCategory, Unit
from products.models import Product
from stock.models import Inventory, StockBatch


class StockBatchDeletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="stock-admin",
            email="stock-admin@example.com",
            password="test-password",
            phone="5555555555",
            role="ADMIN",
            is_staff=True,
        )
        category = Category.objects.create(name="Stock category")
        subcategory = SubCategory.objects.create(name="Stock subcategory", category=category)
        unit = Unit.objects.create(name="Piece", short_name="pc")
        product = Product.objects.create(
            name="Stock product",
            category=category,
            subcategory=subcategory,
            unit=unit,
            price="10.00",
        )
        self.inventory = product.inventory
        self.inventory.total_stock = 10
        self.inventory.save()
        self.batch = StockBatch.objects.create(
            product=product,
            batch_no="batch-1",
            quantity=4,
            purchase_price="5.00",
            selling_price="10.00",
        )
        self.empty_batch = StockBatch.objects.create(
            product=product,
            batch_no="batch-empty",
            quantity=0,
            purchase_price="5.00",
            selling_price="10.00",
        )

    def test_batch_list_hides_empty_batches_by_default(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        response = client.get("/api/stock/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([batch["id"] for batch in response.data], [self.batch.id])

    def test_batch_list_can_include_empty_batches(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        response = client.get("/api/stock/?include_empty=true")

        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            [batch["id"] for batch in response.data],
            [self.batch.id, self.empty_batch.id],
        )

    def test_api_delete_updates_inventory(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)

        response = client.delete(f"/api/stock/delete/{self.batch.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_stock"], 6)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.total_stock, 6)

    def test_direct_batch_delete_updates_inventory(self):
        self.batch.delete()

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.total_stock, 6)
