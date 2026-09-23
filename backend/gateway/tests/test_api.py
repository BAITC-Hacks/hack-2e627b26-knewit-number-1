from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model


class GatewayApiTests(TestCase):
    def test_guest_session_is_identified_without_exposing_session_key(self):
        response = self.client.get("/api/session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_type"], "guest")
        self.assertFalse(response.json()["authenticated"])
        self.assertNotIn("session_key", response.json())

    def test_session_becomes_active_after_a_session_scoped_endpoint(self):
        self.client.get("/api/cart")
        response = self.client.get("/api/session")
        self.assertTrue(response.json()["session_active"])
        self.assertEqual(response.json()["session_type"], "guest")

    def test_authenticated_session_is_identified_by_django_auth(self):
        user = get_user_model().objects.create_user(username="buyer", password="test-password")
        self.client.force_login(user)
        response = self.client.get("/api/session")
        self.assertEqual(response.json()["session_type"], "authenticated")
        self.assertTrue(response.json()["authenticated"])

    @override_settings(API_RATE_LIMIT_PER_MINUTE=2)
    def test_api_rate_limit_returns_retry_after_and_does_not_trust_forwarded_ip(self):
        headers = {"REMOTE_ADDR": "198.51.100.42", "HTTP_X_FORWARDED_FOR": "127.0.0.1"}
        self.assertEqual(self.client.get("/api/products", **headers).status_code, 200)
        self.assertEqual(self.client.get("/api/products", **headers).status_code, 200)
        limited = self.client.get("/api/products", **headers)
        self.assertEqual(limited.status_code, 429)
        self.assertTrue(int(limited["Retry-After"]) >= 1)
        self.assertEqual(limited["X-RateLimit-Remaining"], "0")
