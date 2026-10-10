from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


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
