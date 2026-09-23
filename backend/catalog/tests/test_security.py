from django.test import SimpleTestCase

from catalog.safety import sanitize_catalog_payload, sanitize_url


class CatalogSafetyTests(SimpleTestCase):
    def test_html_markdown_and_dangerous_urls_are_sanitized(self):
        cleaned = sanitize_catalog_payload(
            {
                "name": "<script>alert('x')</script>Safe <b>lamp</b>",
                "description": "[open](javascript:alert(1))",
                "certificate": "javascript:alert(1)",
                "external": "https://evil.example/file.pdf",
                "relative": "/api/products/detail?id=1",
            }
        )
        self.assertNotIn("script", cleaned["name"].casefold())
        self.assertNotIn("<b>", cleaned["name"])
        self.assertNotIn("javascript:", cleaned["description"].casefold())
        self.assertIsNone(cleaned["certificate"])
        self.assertIsNone(cleaned["external"])
        self.assertEqual(cleaned["relative"], "/api/products/detail?id=1")

    def test_only_ekt_https_or_single_slash_relative_urls_are_allowed(self):
        self.assertEqual(sanitize_url("https://ekt.kz/docs/a.pdf"), "https://ekt.kz/docs/a.pdf")
        self.assertIsNone(sanitize_url("http://ekt.kz/docs/a.pdf"))
        self.assertIsNone(sanitize_url("//evil.example/file"))
        self.assertIsNone(sanitize_url("data:text/html,alert(1)"))
