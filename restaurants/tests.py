from datetime import time
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from openpyxl import Workbook, load_workbook
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from addresses.models import Address
from orders.routing import websocket_urlpatterns
from .models import MenuItem, Restaurant, RestaurantDeliveryAssignment, RestaurantOrder
from . import services
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

    def test_delivery_fee_stays_base_within_one_kilometre(self):
        bill = calculate_bill(restaurant(delivery_fee=Decimal('30')), [(item('100'), 1)], distance_km=1)
        self.assertEqual(bill.delivery_fee, Decimal('30'))

    def test_delivery_fee_adds_eight_above_one_kilometre(self):
        bill = calculate_bill(restaurant(delivery_fee=Decimal('30')), [(item('100'), 1)], distance_km=1.01)
        self.assertEqual(bill.delivery_fee, Decimal('38.08'))

    def test_delivery_fee_adds_eight_for_each_kilometre(self):
        bill = calculate_bill(restaurant(delivery_fee=Decimal('30')), [(item('100'), 1)], distance_km=4)
        self.assertEqual(bill.delivery_fee, Decimal('62.00'))


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

    def upload_menu(self, workbook, url='/api/restaurants/partner/menu-workbook/'):
        output = BytesIO()
        workbook.save(output)
        return self.client.post(
            url,
            {'file': SimpleUploadedFile('menu.xlsx', output.getvalue())},
            format='multipart',
        )

    def test_separate_bulk_endpoints_have_single_sheet_templates_and_imports(self):
        categories_url = '/api/restaurants/partner/categories/bulk/'
        items_url = '/api/restaurants/partner/items/bulk/'
        categories = load_workbook(BytesIO(self.client.get(categories_url, {'template': '1'}).content))
        self.assertEqual(categories.sheetnames, ['Categories'])
        self.assertEqual(list(categories.active.values), [('name', 'sort_order')])
        categories.active.append(['Starters', 1])
        categories.active.append(['Main Course', 2])

        wrong_endpoint = self.upload_menu(categories, items_url)
        self.assertEqual(wrong_endpoint.status_code, 400)
        self.assertFalse(self.restaurant.categories.exists())
        response = self.upload_menu(categories, categories_url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'created': 2, 'updated': 0})
        self.assertEqual(
            list(self.restaurant.categories.values_list('name', 'sort_order')),
            [('Starters', 1), ('Main Course', 2)],
        )

        items = load_workbook(BytesIO(self.client.get(items_url, {'template': '1'}).content))
        self.assertEqual(items.sheetnames, ['Items'])
        self.assertEqual(items.active['B1'].value, 'category_id')
        category = self.restaurant.categories.get(name='Main Course')
        items.active.append(['Thali', category.pk, 'Daily special', True, 199])
        response = self.upload_menu(items, items_url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {'created': 1, 'updated': 0})
        self.assertEqual(self.restaurant.items.get().category_id, category.pk)
        exported_items = load_workbook(BytesIO(self.client.get(items_url).content))
        self.assertEqual(exported_items.active['C2'].value, category.pk)

        foreign_category = self.other_restaurant.categories.create(name='Other Main Course')
        items.active['B2'] = foreign_category.pk
        response = self.upload_menu(items, items_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('category_id', response.data['Items']['row 2'])
        self.assertEqual(self.restaurant.items.count(), 1)

        exported = load_workbook(BytesIO(self.client.get(categories_url).content))
        self.assertEqual(exported.sheetnames, ['Categories'])
        self.assertEqual(exported.active['A1'].value, 'id')
        self.assertEqual(exported.active['B2'].value, 'Starters')

    def test_excel_template_import_and_export_round_trip(self):
        url = '/api/restaurants/partner/menu-workbook/'
        template = self.client.get(url, {'template': '1'})
        self.assertEqual(template.status_code, 200)
        workbook = load_workbook(BytesIO(template.content))
        workbook['Categories'].append([None, 'Lunch', 2])
        workbook['Items']['C1'] = 'category_name'  # Previously downloaded combined workbook.
        workbook['Items'].append([None, 'Thali', 'Lunch', 'Daily special', False, 199])
        response = self.upload_menu(workbook)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], {'created': 1, 'updated': 0})
        item = self.restaurant.items.get()
        self.assertEqual(item.category.name, 'Lunch')
        self.assertFalse(item.is_veg)
        self.assertTrue(item.is_available)

        item.name = '=Lunch'
        item.image = 'restaurants/items/lunch.png'
        item.save()
        export = self.client.get(url)
        self.assertEqual(export.status_code, 200)
        workbook = load_workbook(BytesIO(export.content))
        self.assertEqual(workbook['Items']['B2'].data_type, 's')
        self.assertEqual(workbook['Items']['B2'].value, '=Lunch')
        workbook['Items']['F2'] = 209
        response = self.upload_menu(workbook)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['items'], {'created': 0, 'updated': 1})
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal('209.00'))
        self.assertEqual(item.image.name, 'restaurants/items/lunch.png')
        self.assertEqual(self.restaurant.items.count(), 1)

    def test_excel_rejects_foreign_item_id_and_rolls_back_new_categories(self):
        item = self.other_restaurant.items.create(name='Other dish', price=100)
        workbook = Workbook()
        categories = workbook.active
        categories.title = 'Categories'
        categories.append(['name'])
        categories.append(['Lunch'])
        items = workbook.create_sheet('Items')
        items.append(['id', 'name', 'price'])
        items.append([item.pk, 'Updated', 150])

        response = self.upload_menu(workbook)
        self.assertEqual(response.status_code, 400)
        self.assertIn('id', response.data['Items']['row 2'])
        self.assertFalse(self.restaurant.categories.exists())
        item.refresh_from_db()
        self.assertEqual(item.name, 'Other dish')

    @override_settings(DEBUG=True)
    def test_django_admin_menu_workbook_page_download_and_upload(self):
        admin_user = get_user_model().objects.create_superuser(
            username='menu-admin', password='StrongPass123', phone='9876543230',
        )
        self.client.force_login(admin_user)
        change_url = f'/admin/restaurants/restaurant/{self.restaurant.pk}/change/'
        workbook_url = f'/admin/restaurants/restaurant/{self.restaurant.pk}/menu-workbook/'
        self.assertContains(self.client.get(change_url), workbook_url)
        self.assertContains(self.client.get(workbook_url), 'Upload menu')
        download = self.client.get(workbook_url, {'download': 'template'})
        self.assertEqual(download.status_code, 200)
        workbook = load_workbook(BytesIO(download.content))
        self.assertEqual(workbook.sheetnames, ['Categories', 'Items'])
        workbook['Categories'].append([None, 'Breakfast'])
        output = BytesIO()
        workbook.save(output)
        response = self.client.post(
            workbook_url,
            {'file': SimpleUploadedFile('menu.xlsx', output.getvalue())},
            format='multipart',
        )
        self.assertRedirects(response, workbook_url)
        self.assertTrue(self.restaurant.categories.filter(name='Breakfast').exists())

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


class RestaurantAddOnAPITests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(
            username='addons-owner', phone='9876567001', role='RESTAURANT',
        )
        self.customer = users.objects.create_user(
            username='addons-customer', phone='9876567002', role='CUSTOMER',
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner, name='Add-On Restaurant', status=Restaurant.Status.APPROVED,
            opens_at=time(0), closes_at=time(0),
        )
        self.item = self.restaurant.items.create(name='Burger', price=180, packaging_charge=5)
        self.group_url = f'/api/restaurants/partner/items/{self.item.pk}/addon-groups/'
        self.orders_url = '/api/restaurants/orders/'
        self.client = APIClient()

    def test_partner_configures_addons_and_checkout_saves_each_variant(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(self.group_url, {'name': 'Extras', 'max_selections': 2})
        self.assertEqual(response.status_code, 201, response.data)
        options_url = f'{self.group_url}{response.data["id"]}/options/'
        response = self.client.post(options_url, {'name': 'Cheese', 'price': '30.00'})
        self.assertEqual(response.status_code, 201, response.data)
        cheese_id = response.data['id']
        response = self.client.post(options_url, {'name': 'Sauce', 'is_available': False})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(self.client.get(self.group_url).data[0]['options']), 2)

        address = Address.objects.create(user=self.customer, full_address='1 Main Road')
        self.client.force_authenticate(user=self.customer)
        menu = self.client.get(f'/api/restaurants/{self.restaurant.pk}/menu/')
        self.assertEqual(menu.status_code, 200, menu.data)
        self.assertEqual([opt['id'] for opt in menu.data[0]['addon_groups'][0]['options']], [cheese_id])
        cart = {
            'restaurant_id': self.restaurant.pk,
            'address_id': address.pk,
            'items': [
                {'menu_item_id': self.item.pk, 'quantity': 2, 'addon_option_ids': [cheese_id]},
                {'menu_item_id': self.item.pk, 'quantity': 1},
            ],
        }
        quote = self.client.post(f'{self.orders_url}quote/', cart, format='json')
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertEqual(quote.data['item_total'], '600.00')
        self.assertEqual(quote.data['packaging_charge'], '5.00')
        self.assertEqual(quote.data['total_amount'], '660.00')
        with patch('restaurants.services.cashfree.create_order', return_value={
            'order_id': 'test-order', 'payment_session_id': 'test-session',
        }) as cashfree_order:
            online = self.client.post(self.orders_url, {
                **cart, 'payment_method': RestaurantOrder.PaymentMethod.ONLINE,
            }, format='json')
        self.assertEqual(online.status_code, 201, online.data)
        self.assertEqual(cashfree_order.call_args.kwargs['amount'], Decimal('660.00'))

        placed = self.client.post(self.orders_url, {
            **cart, 'payment_method': RestaurantOrder.PaymentMethod.COD,
        }, format='json')
        self.assertEqual(placed.status_code, 201, placed.data)
        self.assertEqual(placed.data['total_amount'], quote.data['total_amount'])
        lines = {line['quantity']: line for line in placed.data['items']}
        self.assertEqual(lines[2]['line_total'], '420.00')
        self.assertEqual(lines[1]['addons'], [])
        expected = [{'group_name': 'Extras', 'name': 'Cheese', 'unit_price': '30.00'}]
        self.assertEqual(lines[2]['addons'], expected)

        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.delete(f'{options_url}{cheese_id}/').status_code, 204)
        partner_order = self.client.get(f'/api/restaurants/partner/orders/{placed.data["id"]}/')
        self.assertEqual(partner_order.status_code, 200)
        lines = {line['quantity']: line for line in partner_order.data['items']}
        self.assertEqual(lines[2]['addons'], expected)

    def test_addon_management_and_checkout_validate_scope_and_limits(self):
        another_owner = get_user_model().objects.create_user(
            username='addons-other-owner', phone='9876567003', role='RESTAURANT',
        )
        another_restaurant = Restaurant.objects.create(owner=another_owner, name='Other Restaurant')
        another_item = another_restaurant.items.create(name='Other Burger', price=150)
        foreign_group = another_item.addon_groups.create(name='Extras')
        foreign_option = foreign_group.options.create(name='Cheese')
        group = self.item.addon_groups.create(name='Sauce', min_selections=1, max_selections=1)
        mayo = group.options.create(name='Mayo')
        mustard = group.options.create(name='Mustard')
        unavailable = group.options.create(name='Ketchup', is_available=False)

        self.client.force_authenticate(user=self.owner)
        self.assertEqual(
            self.client.get(f'/api/restaurants/partner/items/{another_item.pk}/addon-groups/').status_code,
            404,
        )
        foreign_options_url = f'{self.group_url}{foreign_group.pk}/options/'
        self.assertEqual(self.client.post(foreign_options_url, {'name': 'Other'}).status_code, 404)
        self.assertEqual(self.client.patch(
            f'{self.group_url}{group.pk}/', {'min_selections': 2},
        ).status_code, 400)

        self.client.force_authenticate(user=self.customer)
        for ids in ([], [mayo.pk, mustard.pk], [mayo.pk, mayo.pk], [mayo.pk, foreign_option.pk],
                    [unavailable.pk]):
            with self.subTest(option_ids=ids):
                response = self.client.post(f'{self.orders_url}quote/', {
                    'restaurant_id': self.restaurant.pk,
                    'items': [{'menu_item_id': self.item.pk, 'quantity': 1, 'addon_option_ids': ids}],
                }, format='json')
                self.assertEqual(response.status_code, 400, response.data)


class PartnerRestaurantAPITests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='restaurant-profile-owner',
            password='StrongPass123',
            phone='9876543221',
            role='RESTAURANT',
        )
        self.other_owner = user_model.objects.create_user(
            username='restaurant-profile-other',
            password='StrongPass123',
            phone='9876543222',
            role='RESTAURANT',
        )
        self.customer = user_model.objects.create_user(
            username='restaurant-profile-customer',
            password='StrongPass123',
            phone='9876543223',
            role='CUSTOMER',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_owner_onboards_and_can_load_and_update_linked_restaurant(self):
        create_response = self.client.post(
            '/api/restaurants/partner/onboard/',
            {
                'name': 'Owner Restaurant',
                'phone': '9876543224',
                'address_line': '1 Main Road',
                'city': 'Bengaluru',
                'fssai_number': '12345678901234',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201, create_response.data)
        restaurant = Restaurant.objects.get(pk=create_response.data['id'])
        self.assertEqual(restaurant.owner, self.owner)
        self.assertEqual(create_response.data['status'], Restaurant.Status.PENDING)

        get_response = self.client.get('/api/restaurants/')

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(len(get_response.data), 1)
        self.assertEqual(get_response.data[0]['id'], restaurant.id)
        self.assertEqual(get_response.data[0]['name'], 'Owner Restaurant')

        detail_response = self.client.get(f'/api/restaurants/{restaurant.id}/')

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['id'], restaurant.id)
        self.assertEqual(detail_response.data['status'], Restaurant.Status.PENDING)

        update_response = self.client.patch(
            f'/api/restaurants/{restaurant.id}/',
            {'name': 'Updated Restaurant', 'city': 'Mysuru'},
            format='json',
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data['name'], 'Updated Restaurant')
        self.assertEqual(update_response.data['city'], 'Mysuru')
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.owner, self.owner)

    def test_non_restaurant_role_cannot_onboard_a_restaurant(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            '/api/restaurants/partner/onboard/',
            {
                'name': 'Customer Restaurant',
                'phone': '9876543225',
                'address_line': '1 Main Road',
                'city': 'Bengaluru',
                'fssai_number': '12345678901235',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Restaurant.objects.filter(owner=self.customer).exists())

    def test_owner_only_loads_their_linked_restaurant(self):
        other_restaurant = Restaurant.objects.create(
            owner=self.other_owner,
            name='Other Restaurant',
            phone='9876543226',
            address_line='2 Main Road',
            city='Bengaluru',
        )

        response = self.client.get('/api/restaurants/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
        self.assertTrue(Restaurant.objects.filter(pk=other_restaurant.pk).exists())

    def test_owner_cannot_retrieve_or_edit_another_owners_restaurant(self):
        other_restaurant = Restaurant.objects.create(
            owner=self.other_owner,
            name='Other Restaurant',
            phone='9876543226',
            address_line='2 Main Road',
            city='Bengaluru',
        )

        get_response = self.client.get(f'/api/restaurants/{other_restaurant.id}/')
        patch_response = self.client.patch(
            f'/api/restaurants/{other_restaurant.id}/',
            {'name': 'Hijacked Restaurant'},
            format='json',
        )

        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(patch_response.status_code, 404)
        other_restaurant.refresh_from_db()
        self.assertEqual(other_restaurant.name, 'Other Restaurant')


class RestaurantOrderDispatchTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username='dispatch-restaurant-owner',
            password='StrongPass123',
            phone='9876543228',
            role='RESTAURANT',
            fcm_token='restaurant-fcm-token',
        )
        self.customer = user_model.objects.create_user(
            username='dispatch-customer',
            password='StrongPass123',
            phone='9876543229',
            role='CUSTOMER',
        )
        self.driver = user_model.objects.create_user(
            username='dispatch-driver',
            password='StrongPass123',
            phone='9876543230',
            role='DELIVERY',
            is_online=True,
            fcm_token='driver-fcm-token',
        )
        self.restaurant = Restaurant.objects.create(
            owner=self.owner,
            name='Dispatch Restaurant',
            phone='9876543231',
            address_line='1 Main Road',
            city='Bengaluru',
            status=Restaurant.Status.APPROVED,
        )
        self.client = APIClient()

    def create_order(self, status=RestaurantOrder.Status.PLACED):
        return RestaurantOrder.objects.create(
            customer=self.customer,
            restaurant=self.restaurant,
            status=status,
            payment_method=RestaurantOrder.PaymentMethod.COD,
            item_total=Decimal('100.00'),
            total_amount=Decimal('125.00'),
            customer_name='Dispatch Customer',
            customer_phone=self.customer.phone,
            delivery_address={'address': '2 Main Road'},
        )

    def test_owner_gets_push_when_cod_order_is_placed(self):
        menu_item = MenuItem.objects.create(
            restaurant=self.restaurant,
            name='Soup',
            price=Decimal('100.00'),
        )
        quote = {
            'restaurant': self.restaurant,
            'lines': [services.PricedMenuLine(menu_item, 1)],
            'bill': SimpleNamespace(
                item_total=Decimal('100.00'),
                discount=Decimal('0.00'),
                delivery_fee=Decimal('25.00'),
                packaging=Decimal('0.00'),
                gst=Decimal('5.00'),
                total=Decimal('130.00'),
            ),
            'address': {
                'snapshot': {},
                'lat': None,
                'lng': None,
                'name': '',
                'phone': '',
            },
        }
        with patch('orders.utils.notify_restaurant_owner') as send_notification:
            with self.captureOnCommitCallbacks(execute=True):
                order = services.create_order(
                    self.customer,
                    quote,
                    RestaurantOrder.PaymentMethod.COD,
                )

        send_notification.assert_called_once()
        args = send_notification.call_args.args
        self.assertEqual(args[0], self.owner.id)
        self.assertEqual(args[1]['type'], 'restaurant_order_placed')
        self.assertEqual(args[1]['order_id'], str(order.id))

    def test_owner_gets_push_when_online_order_becomes_placed(self):
        order = self.create_order(status=RestaurantOrder.Status.AWAITING_PAYMENT)
        order.payment_method = RestaurantOrder.PaymentMethod.ONLINE
        order.razorpay_order_id = 'razorpay-order-1'
        order.save(update_fields=['payment_method', 'razorpay_order_id'])
        self.client.force_authenticate(user=self.customer)

        with (
            patch('restaurants.services.verify_razorpay_signature', return_value=True),
            patch('orders.utils.notify_restaurant_owner') as send_notification,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                f'/api/restaurants/orders/{order.id}/verify-payment/',
                {
                    'razorpay_payment_id': 'razorpay-payment-1',
                    'razorpay_signature': 'valid-signature',
                },
                format='json',
            )

        self.assertEqual(response.status_code, 200, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, RestaurantOrder.Status.PLACED)
        send_notification.assert_called_once()
        self.assertEqual(
            send_notification.call_args.args[0],
            self.owner.id,
        )

    def test_accepting_order_assigns_and_notifies_driver(self):
        order = self.create_order()
        self.client.force_authenticate(user=self.owner)

        with patch('orders.utils.notify_driver') as send_notification:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f'/api/restaurants/partner/orders/{order.id}/status/',
                    {'status': RestaurantOrder.Status.ACCEPTED},
                    format='json',
                )

        self.assertEqual(response.status_code, 200, response.data)
        assignment = RestaurantDeliveryAssignment.objects.get(order=order)
        self.assertEqual(assignment.driver, self.driver)
        self.assertEqual(response.data['delivery_assignment']['driver_id'], self.driver.id)
        send_notification.assert_called_once()
        args = send_notification.call_args.args
        self.assertEqual(args[0], self.driver.id)
        self.assertEqual(args[1]['type'], 'restaurant_delivery_assigned')
        self.assertEqual(args[1]['order_id'], str(order.id))

    def test_driver_can_list_and_retrieve_assigned_restaurant_orders(self):
        order = self.create_order(status=RestaurantOrder.Status.ACCEPTED)
        RestaurantDeliveryAssignment.objects.create(order=order, driver=self.driver)
        self.client.force_authenticate(user=self.driver)

        list_response = self.client.get('/api/restaurants/driver/orders/')
        detail_response = self.client.get(f'/api/restaurants/driver/orders/{order.id}/')

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]['order_type'], 'restaurant')
        self.assertEqual(list_response.data[0]['order_number'], order.order_number)
        self.assertEqual(list_response.data[0]['delivery_otp'], order.delivery_otp)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['restaurant']['name'], self.restaurant.name)
        self.assertEqual(detail_response.data['delivery_otp'], order.delivery_otp)

    def test_customer_can_read_restaurant_order_otp(self):
        order = self.create_order()
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(f'/api/restaurants/orders/{order.id}/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertRegex(response.data['delivery_otp'], r'^\d{6}$')
        self.assertEqual(response.data['delivery_otp'], order.delivery_otp)

    def test_driver_can_mark_assigned_restaurant_order_picked_up_and_delivered(self):
        order = self.create_order(status=RestaurantOrder.Status.READY)
        RestaurantDeliveryAssignment.objects.create(order=order, driver=self.driver)
        self.client.force_authenticate(user=self.driver)

        picked_up_response = self.client.post(
            f'/api/restaurants/driver/orders/{order.id}/status/',
            {'status': 'picked_up'},
            format='json',
        )
        delivered_response = self.client.post(
            f'/api/restaurants/driver/orders/{order.id}/status/',
            {'status': 'delivered', 'otp': order.delivery_otp},
            format='json',
        )

        self.assertEqual(picked_up_response.status_code, 200, picked_up_response.data)
        self.assertEqual(
            picked_up_response.data['status'],
            RestaurantOrder.Status.OUT_FOR_DELIVERY,
        )
        self.assertEqual(delivered_response.status_code, 200, delivered_response.data)
        self.assertEqual(delivered_response.data['status'], RestaurantOrder.Status.DELIVERED)
        order.refresh_from_db()
        self.assertTrue(order.delivery_otp_verified)

    def test_driver_cannot_deliver_restaurant_order_with_invalid_otp(self):
        order = self.create_order(status=RestaurantOrder.Status.OUT_FOR_DELIVERY)
        RestaurantDeliveryAssignment.objects.create(order=order, driver=self.driver)
        self.client.force_authenticate(user=self.driver)

        response = self.client.post(
            f'/api/restaurants/driver/orders/{order.id}/status/',
            {'status': 'delivered', 'otp': '000000' if order.delivery_otp != '000000' else '111111'},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.data)
        order.refresh_from_db()
        self.assertEqual(order.status, RestaurantOrder.Status.OUT_FOR_DELIVERY)
        self.assertFalse(order.delivery_otp_verified)

    def test_driver_cannot_update_unassigned_restaurant_order(self):
        order = self.create_order(status=RestaurantOrder.Status.READY)
        self.client.force_authenticate(user=self.driver)

        response = self.client.post(
            f'/api/restaurants/driver/orders/{order.id}/status/',
            {'status': 'picked_up'},
            format='json',
        )

        self.assertEqual(response.status_code, 404)

    def test_accepting_order_reports_when_no_delivery_agent_is_online(self):
        self.driver.is_online = False
        self.driver.save(update_fields=['is_online'])
        order = self.create_order()
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f'/api/restaurants/partner/orders/{order.id}/status/',
            {'status': RestaurantOrder.Status.ACCEPTED},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['delivery_assignment']['status'], 'unassigned')
        self.assertFalse(RestaurantDeliveryAssignment.objects.filter(order=order).exists())

    def test_customer_cannot_patch_restaurant_through_public_api(self):
        restaurant = Restaurant.objects.create(
            owner=self.owner,
            name='Approved Restaurant',
            phone='9876543227',
            address_line='1 Main Road',
            city='Bengaluru',
            status=Restaurant.Status.APPROVED,
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.patch(
            f'/api/restaurants/{restaurant.id}/',
            {'name': 'Unauthorized Change'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        restaurant.refresh_from_db()
        self.assertEqual(restaurant.name, 'Approved Restaurant')


class RestaurantOwnerWebsocketTests(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username='restaurant-websocket-owner',
            password='StrongPass123',
            phone='9876543232',
            role='RESTAURANT',
        )
        self.other_owner = get_user_model().objects.create_user(
            username='restaurant-websocket-other',
            password='StrongPass123',
            phone='9876543233',
            role='RESTAURANT',
        )

    def test_owner_receives_new_order_event_over_jwt_authenticated_websocket(self):
        token = str(RefreshToken.for_user(self.owner).access_token)

        async def exercise_socket():
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                f'/ws/restaurant-owner/{self.owner.id}/?token={token}',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await get_channel_layer().group_send(
                f'restaurant_owner_{self.owner.id}',
                {
                    'type': 'new_order',
                    'order': {'type': 'restaurant_order_placed', 'order_id': '42'},
                },
            )
            event = await communicator.receive_json_from()
            await communicator.disconnect()
            return event

        event = async_to_sync(exercise_socket)()
        self.assertEqual(event['type'], 'new_order')
        self.assertEqual(event['order']['type'], 'restaurant_order_placed')
        self.assertEqual(event['order']['order_id'], '42')

    def test_owner_cannot_subscribe_to_another_owners_order_events(self):
        token = str(RefreshToken.for_user(self.owner).access_token)

        async def exercise_socket():
            communicator = WebsocketCommunicator(
                URLRouter(websocket_urlpatterns),
                f'/ws/restaurant-owner/{self.other_owner.id}/?token={token}',
            )
            return await communicator.connect()

        connected, _ = async_to_sync(exercise_socket)()
        self.assertFalse(connected)
