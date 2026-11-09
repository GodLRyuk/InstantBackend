from django.test import TestCase, override_settings


class SecurityHeadersTests(TestCase):
    def test_api_response_has_restrictive_content_security_policy(self):
        response = self.client.get('/api/stock/')

        self.assertIn("default-src 'self'", response['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'none'", response['Content-Security-Policy'])
        self.assertIn("object-src 'none'", response['Content-Security-Policy'])

    def test_unlisted_origin_does_not_receive_cors_access(self):
        response = self.client.get(
            '/api/stock/',
            HTTP_ORIGIN='https://untrusted.example',
        )

        self.assertNotIn('Access-Control-Allow-Origin', response)

    @override_settings(
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=['https://frontend.example'],
    )
    def test_configured_frontend_origin_receives_cors_access(self):
        response = self.client.get(
            '/api/stock/',
            HTTP_ORIGIN='https://frontend.example',
        )

        self.assertEqual(
            response['Access-Control-Allow-Origin'],
            'https://frontend.example',
        )
