from unittest.mock import patch

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

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

    def test_create_generates_unique_in_store_ean13_when_requested(self):
        serializer = ProductSerializer(
            data={
                "name": "Pear",
                "category": self.category.id,
                "subcategory": self.subcategory.id,
                "price": "2.00",
                "generate_barcode": True,
            },
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        product = serializer.save()

        self.assertRegex(product.barcode, r"^2\d{12}$")
        checksum_total = sum(
            int(digit) * (3 if index % 2 else 1)
            for index, digit in enumerate(product.barcode[:12])
        ) + int(product.barcode[-1])
        self.assertEqual(checksum_total % 10, 0)
        self.assertEqual(Product.objects.filter(barcode=product.barcode).count(), 1)

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
