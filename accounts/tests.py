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
