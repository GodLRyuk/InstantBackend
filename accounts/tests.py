from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from orders.models import DeliveryAssignment, Order


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', EMAIL_HOST_USER='noreply@example.com')
class RegisterAPITest(TestCase):
    def test_register_saves_first_and_last_name(self):
        client = APIClient()
        payload = {
            'username': 'alice',
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'StrongPass123',
            'phone': '9876543210',
            'address': 'Test Address',
            'zip_code': '560001',
            'role': 'CUSTOMER',
        }

        response = client.post('/api/accounts/register/', payload, format='json')

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(email='alice@example.com')
        self.assertEqual(user.first_name, 'Alice')
        self.assertEqual(user.last_name, 'Smith')

    def test_register_restaurant_role_without_staff_access(self):
        client = APIClient()
        payload = {
            'username': 'restaurant-owner',
            'first_name': 'Restaurant',
            'last_name': 'Owner',
            'email': 'restaurant@example.com',
            'password': 'StrongPass123',
            'phone': '9876543214',
            'role': 'RESTAURANT',
        }

        response = client.post('/api/accounts/register/', payload, format='json')

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(email='restaurant@example.com')
        self.assertEqual(user.role, 'RESTAURANT')
        self.assertFalse(user.is_staff)

    def test_public_registration_cannot_create_admin(self):
        payload = {
            'username': 'not-admin',
            'first_name': 'Not',
            'last_name': 'Admin',
            'email': 'not-admin@example.com',
            'password': 'StrongPass123',
            'phone': '9876543215',
            'role': 'ADMIN',
        }

        response = self.client.post('/api/accounts/register/', payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email='not-admin@example.com').exists())


class AdminLoginAPITest(TestCase):
    def setUp(self):
        self.restaurant_user = get_user_model().objects.create_user(
            username='restaurant-login',
            email='restaurant-login@example.com',
            password='StrongPass123',
            phone='9876543216',
            role='RESTAURANT',
        )
        self.client = APIClient()

    def test_restaurant_role_can_login_to_custom_admin_panel_not_django_admin(self):
        response = self.client.post(
            '/api/accounts/admin-login/',
            {'email': self.restaurant_user.email, 'password': 'StrongPass123'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role'], 'RESTAURANT')
        self.assertTrue(response.data['is_restaurant'])
        self.assertFalse(response.data['is_staff'])
        self.assertFalse(self.restaurant_user.is_staff)
        self.assertTrue(
            self.client.login(
                username=self.restaurant_user.username,
                password='StrongPass123',
            )
        )
        django_admin_response = self.client.get('/admin/')
        self.assertEqual(django_admin_response.status_code, 302)
        self.assertIn('/admin/login/', django_admin_response['Location'])


class UserListAPITest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="admin",
            password="StrongPass123",
            phone="9876543211",
            role="ADMIN",
            is_staff=True,
        )
        self.customer = user_model.objects.create_user(
            username="customer",
            password="StrongPass123",
            phone="9876543212",
            role="CUSTOMER",
        )
        self.delivery = user_model.objects.create_user(
            username="delivery",
            password="StrongPass123",
            phone="9876543213",
            role="DELIVERY",
        )
        self.client = APIClient()

    def test_staff_can_list_all_user_roles(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/accounts/users/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(
            {user["role"] for user in response.data["results"]},
            {"ADMIN", "CUSTOMER", "DELIVERY"},
        )
        self.assertNotIn("password", response.data["results"][0])
        self.assertNotIn("otp", response.data["results"][0])

    def test_staff_can_filter_users_by_role(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/accounts/users/?role=CUSTOMER")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "customer")

    def test_invalid_role_returns_bad_request(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/accounts/users/?role=UNKNOWN")

        self.assertEqual(response.status_code, 400)

    def test_non_staff_cannot_list_users(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get("/api/accounts/users/")

        self.assertEqual(response.status_code, 403)


class DriverOrderDetailAPITest(TestCase):
    def test_assigned_driver_order_detail_includes_delivery_otp(self):
        user_model = get_user_model()
        customer = user_model.objects.create_user(
            username="otp-customer",
            password="StrongPass123",
            phone="9876543291",
            role="CUSTOMER",
        )
        driver = user_model.objects.create_user(
            username="otp-driver",
            password="StrongPass123",
            phone="9876543292",
            role="DELIVERY",
        )
        order = Order.objects.create(user=customer, total_amount="10.00")
        DeliveryAssignment.objects.create(order=order, driver=driver)
        client = APIClient()
        client.force_authenticate(user=driver)

        response = client.get(f"/api/accounts/driver/order/{order.id}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["delivery_otp"], order.delivery_otp)
        self.assertRegex(response.data["delivery_otp"], r"^\d{6}$")
