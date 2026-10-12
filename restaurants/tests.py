from datetime import time
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import Restaurant
from .services import calculate_bill
from .utils import fmt_time, haversine_km, whole_rupees


def item(price, packaging=0):
    return SimpleNamespace(price=Decimal(price), packaging_charge=Decimal(packaging))


def restaurant(**kw):
    base = dict(
        offer_percent=30, offer_max_discount=75, offer_min_order=0, delivery_fee=Decimal('25'),
    )
    base.update(kw)
    return SimpleNamespace(**base)


class BillTests(SimpleTestCase):
    def test_matches_the_app_design(self):
        # 1 biryani (249, packaging 10) + 2 naan (40) -> total 302
        bill = calculate_bill(restaurant(), [(item('249', '10'), 1), (item('40'), 2)])
        self.assertEqual(bill.item_total, Decimal('329'))
        self.assertEqual(bill.discount, Decimal('75'))  # 30% = 99, capped at 75
        self.assertEqual(bill.packaging, Decimal('10'))
        self.assertEqual(bill.gst, Decimal('13'))
        self.assertEqual(bill.total, Decimal('302'))

    def test_no_offer(self):
        bill = calculate_bill(restaurant(offer_percent=None), [(item('100'), 2)])
        self.assertEqual(bill.discount, Decimal('0'))
        self.assertEqual(bill.gst, Decimal('10'))
        self.assertEqual(bill.total, Decimal('235'))

    def test_offer_needs_minimum_order(self):
        bill = calculate_bill(restaurant(offer_min_order=500), [(item('100'), 2)])
        self.assertEqual(bill.discount, Decimal('0'))

    def test_offer_without_cap(self):
        bill = calculate_bill(restaurant(offer_max_discount=0), [(item('1000'), 1)])
        self.assertEqual(bill.discount, Decimal('300'))


class UtilTests(SimpleTestCase):
    def test_rounding_goes_up_on_half(self):
        self.assertEqual(whole_rupees(Decimal('12.5')), Decimal('13'))
        self.assertEqual(whole_rupees(Decimal('12.4')), Decimal('12'))

    def test_time_format(self):
        self.assertEqual(fmt_time(time(23, 0)), '11:00 pm')
        self.assertEqual(fmt_time(time(9, 30)), '9:30 am')

    def test_distance(self):
        # Asansol to Durgapur is roughly 35 km
        km = haversine_km(23.6850, 86.9740, 23.5204, 87.3119)
        self.assertTrue(30 < km < 45)


class AdminCatalogAPITests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username='catalog-admin',
            password='StrongPass123',
            phone='9876543211',
            role='ADMIN',
            is_staff=True,
        )
        self.owner = user_model.objects.create_user(
            username='restaurant-owner',
            password='StrongPass123',
            phone='9876543212',
            role='CUSTOMER',
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner,
            name='Test Restaurant',
            phone='9876543213',
            address_line='1 Main Road',
            city='Bengaluru',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_admin_can_create_and_list_cuisines(self):
        create_response = self.client.post(
            '/api/restaurants/admin/cuisines/',
            {'name': 'South Indian'},
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data, {'id': create_response.data['id'], 'name': 'South Indian'})

        list_response = self.client.get('/api/restaurants/admin/cuisines/')

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]['name'], 'South Indian')

    def test_admin_can_create_and_filter_menu_categories(self):
        create_response = self.client.post(
            '/api/restaurants/admin/menu-categories/',
            {
                'restaurant': self.restaurant.id,
                'name': 'Beverages',
                'sort_order': 2,
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data['restaurant'], self.restaurant.id)
        self.assertEqual(create_response.data['restaurant_name'], 'Test Restaurant')
        self.assertEqual(create_response.data['name'], 'Beverages')

        list_response = self.client.get(
            f'/api/restaurants/admin/menu-categories/?restaurant={self.restaurant.id}'
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]['name'], 'Beverages')

    def test_non_staff_cannot_create_cuisine(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            '/api/restaurants/admin/cuisines/',
            {'name': 'South Indian'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)


class RestaurantMenuAPITests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='menu-owner',
            password='StrongPass123',
            phone='9876543217',
            role='RESTAURANT',
        )
        self.other_owner = user_model.objects.create_user(
            username='other-menu-owner',
            password='StrongPass123',
            phone='9876543218',
            role='RESTAURANT',
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner,
            name='Owner Restaurant',
            phone='9876543219',
            address_line='1 Main Road',
            city='Bengaluru',
        )
        self.other_restaurant = Restaurant.objects.create(
            owner=self.other_owner,
            name='Other Restaurant',
            phone='9876543220',
            address_line='2 Main Road',
            city='Bengaluru',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_restaurant_owner_can_add_edit_and_delete_own_menu_item(self):
        create_response = self.client.post(
            '/api/restaurants/partner/items/',
            {
                'name': 'Paneer Biryani',
                'description': 'Served with raita',
                'is_veg': True,
                'price': '220.00',
                'mrp': '250.00',
                'is_available': True,
                'packaging_charge': '10.00',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        item_id = create_response.data['id']
        self.assertTrue(
            self.restaurant.items.filter(pk=item_id, name='Paneer Biryani').exists()
        )

        update_response = self.client.patch(
            f'/api/restaurants/partner/items/{item_id}/',
            {'price': '240.00'},
            format='json',
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data['price'], '240.00')
        self.assertEqual(
            self.restaurant.items.get(pk=item_id).price,
            Decimal('240.00'),
        )

        delete_response = self.client.delete(f'/api/restaurants/partner/items/{item_id}/')

        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(self.restaurant.items.filter(pk=item_id).exists())

    def test_restaurant_owner_uploads_and_stores_menu_item_image(self):
        image_data = BytesIO()
        Image.new('RGB', (1, 1), color='white').save(image_data, format='PNG')
        uploaded_image = SimpleUploadedFile(
            'clear-soup.png',
            image_data.getvalue(),
            content_type='image/png',
        )

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                '/api/restaurants/partner/items/',
                {
                    'name': 'Clear Soup',
                    'description': '',
                    'category': '',
                    'is_veg': 'true',
                    'price': '100.00',
                    'image': uploaded_image,
                },
                format='multipart',
            )

            self.assertEqual(response.status_code, 201, response.data)
            menu_item = self.restaurant.items.get(pk=response.data['id'])
            self.assertEqual(menu_item.image.name, f'restaurants/items/{uploaded_image.name}')
            self.assertTrue(Path(menu_item.image.path).is_file())

    def test_restaurant_owner_cannot_access_another_restaurants_menu_item(self):
        other_item = self.other_restaurant.items.create(
            name='Other Dish',
            price='100.00',
        )

        response = self.client.patch(
            f'/api/restaurants/partner/items/{other_item.id}/',
            {'price': '1.00'},
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        other_item.refresh_from_db()
        self.assertEqual(other_item.price, Decimal('100.00'))

    def test_restaurant_owner_cannot_access_staff_admin_catalog(self):
        response = self.client.post(
            '/api/restaurants/admin/menu-categories/',
            {
                'restaurant': self.restaurant.id,
                'name': 'Beverages',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)
