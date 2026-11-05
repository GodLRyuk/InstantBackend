from unittest.mock import patch

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from masters.models import Category, SubCategory
from products.barcodes import generate_unique_in_store_ean13
from products.models import Product
from products.serializers import MAX_PRODUCT_IMAGE_SIZE, ProductSerializer


class ProductSerializerTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Food")
        self.subcategory = SubCategory.objects.create(
            name="Fruit",
            category=self.category,
        )
        self.other_subcategory = SubCategory.objects.create(
            name="Vegetables",
            category=self.category,
        )
        self.product = Product.objects.create(
            name="Apple",
            category=self.category,
            subcategory=self.subcategory,
            price="1.00",
        )

    def test_product_response_includes_category_and_subcategory_ids(self):
        data = ProductSerializer(self.product).data

        self.assertEqual(data["category_id"], self.category.id)
        self.assertEqual(data["subcategory_id"], self.subcategory.id)

    def test_product_subcategory_can_be_updated(self):
        serializer = ProductSerializer(
            self.product,
            data={"subcategory": self.other_subcategory.id},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        updated_product = serializer.save()

        self.assertEqual(updated_product.subcategory, self.other_subcategory)

    def test_image_larger_than_10_mb_is_rejected(self):
        oversized_image = SimpleUploadedFile(
            "oversized.jpg",
            b"x" * (MAX_PRODUCT_IMAGE_SIZE + 1),
            content_type="image/jpeg",
        )
        serializer = ProductSerializer(
            self.product,
            data={"image": oversized_image},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("10 MB or smaller", str(serializer.errors["image"]))

    def test_barcode_generator_skips_codes_already_in_use(self):
        existing_barcode = "2000000000008"
        self.product.barcode = existing_barcode
        self.product.save()

        with patch(
            "products.barcodes.secrets.randbelow",
            side_effect=[0, 1],
        ):
            barcode = generate_unique_in_store_ean13()

        self.assertNotEqual(barcode, existing_barcode)
        self.assertEqual(barcode, "2000000000015")


class GenerateBarcodeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/products/generate-barcode/"
        self.admin = get_user_model().objects.create_user(
            username="admin",
            phone="1000000000",
            role="ADMIN",
            is_staff=True,
        )

    def test_admin_can_generate_barcode_without_creating_product(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        barcode = response.data["barcode"]
        self.assertRegex(barcode, r"^2\d{12}$")
        self.assertEqual(Product.objects.count(), 0)

    def test_barcode_generation_requires_admin(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)

        customer = get_user_model().objects.create_user(
            username="customer",
            phone="1000000001",
            role="CUSTOMER",
        )
        self.client.force_authenticate(customer)
        self.assertEqual(self.client.post(self.url).status_code, 403)
