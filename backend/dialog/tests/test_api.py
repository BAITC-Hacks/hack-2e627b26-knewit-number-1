import json
from copy import deepcopy
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from catalog.errors import CatalogError
from catalog.providers.fixture import PRODUCTS_BY_ID


class DialogApiTests(TestCase):
    def post_message(self, text, dialog_id=None):
        payload = {"text": text}
        if dialog_id:
            payload["dialog_id"] = dialog_id
        return self.client.post(
            "/api/dialog/messages",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_new_dialog_returns_welcome_and_examples(self):
        response = self.client.get("/api/dialog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "idle")
        self.assertEqual(body["history"][0]["role"], "assistant")
        self.assertTrue(body["history"][0]["suggestions"])

    def test_context_resolves_second_variant_and_add_quantity(self):
        first = self.post_message("светильник")
        self.assertEqual(first.status_code, 200)
        dialog_id = first.json()["dialog_id"]
        second = self.post_message("второй вариант", dialog_id)
        self.assertEqual(second.status_code, 200)
        product_id = second.json()["message"]["resolved_reference"]["product_id"]
        self.assertTrue(product_id)

        add = self.post_message("добавь два", dialog_id)
        self.assertEqual(add.status_code, 200)
        message = add.json()["message"]
        self.assertEqual(message["state"], "done")
        self.assertEqual(message["resolved_reference"]["quantity"], 2)
        self.assertEqual(message["resolved_reference"]["product_id"], product_id)

    def test_cancel_and_clear_only_affect_current_dialog(self):
        response = self.post_message("найди кабель")
        dialog_id = response.json()["dialog_id"]
        cancelled = self.client.post("/api/dialog/cancel")
        self.assertEqual(cancelled.json()["state"], "cancelled")
        cleared = self.client.delete("/api/dialog/history")
        self.assertEqual(cleared.status_code, 200)
        self.assertNotEqual(cleared.json()["dialog_id"], dialog_id)
        self.assertEqual(len(cleared.json()["history"]), 1)

    def test_invalid_message_is_retryable_only_for_processing_failure(self):
        response = self.post_message("")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["state"], "error")
        self.assertFalse(response.json()["retryable"])

    def test_retry_reprocesses_previous_user_message(self):
        response = self.post_message("найди кабель")
        user_id = next(item["id"] for item in self.client.get("/api/dialog").json()["history"] if item["role"] == "user")
        retry = self.client.post(f"/api/dialog/messages/{user_id}/retry")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["state"], "done")

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="", CATALOG_PROVIDER="fixture")
    def test_numeric_selected_product_uses_detail_for_verified_fallback_facts(self):
        response = self.post_message("900001")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["source_status"], "sourced")
        self.assertEqual(message["products"][0]["id"], 900001)
        fact = message["facts"][0]
        self.assertEqual(fact["source"], "catalog_detail_api")
        self.assertEqual(fact["availability"]["status"], "available")
        self.assertIn("RATED_CURRENT", fact["characteristics"])

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="", CATALOG_PROVIDER="fixture")
    def test_selected_search_result_is_refreshed_from_detail_api(self):
        session = self.client.session
        session["dialog_context"] = {
            "dialog_id": "test-dialog",
            "version": 1,
            "state": "done",
            "history": [
                {"id": "welcome", "role": "assistant", "content": "Здравствуйте"},
                {
                    "id": "search-result",
                    "role": "assistant",
                    "content": "Нашёл вариант",
                    "products": [{"id": 900001, "name": "Устаревший поисковый снимок"}],
                },
            ],
            "attachments": {},
        }
        session.save()

        response = self.post_message("этот товар", "test-dialog")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["resolved_reference"], {"product_id": 900001})
        self.assertEqual(message["facts"][0]["source"], "catalog_detail_api")
        self.assertNotEqual(message["products"][0]["name"], "Устаревший поисковый снимок")

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="")
    @patch("dialog.views.get_catalog_provider")
    def test_detail_fallback_tolerates_missing_fields_and_returns_safe_documents(self, provider_factory):
        detail = deepcopy(PRODUCTS_BY_ID[900001])
        detail.pop("description")
        detail["properties"] = None
        detail["availability"] = None
        detail["certificates"] = [
            "https://ekt.kz/docs/certificate.pdf",
            "javascript:alert(1)",
        ]
        provider_factory.return_value = Mock(get_product=Mock(return_value=detail))

        response = self.post_message("900001")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        fact = message["facts"][0]
        self.assertEqual(fact["documents"], [{"label": "Сертификат", "url": "https://ekt.kz/docs/certificate.pdf"}])
        self.assertNotIn("description", message["products"][0])
        self.assertIsNone(fact["availability"])
        self.assertEqual(fact["characteristics"], {})

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="")
    @patch("dialog.views.get_catalog_provider")
    def test_numeric_selected_product_hides_search_snapshot_when_detail_is_unavailable(self, provider_factory):
        provider_factory.return_value = Mock(
            get_product=Mock(side_effect=CatalogError(502, "catalog_unavailable", "unavailable"))
        )

        response = self.post_message("900001")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["source_status"], "missing")
        self.assertEqual(message["products"], [])
        self.assertEqual(message["facts"], [])

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="")
    @patch("dialog.views.get_catalog_provider")
    def test_selected_reference_hides_snapshot_when_detail_is_unavailable(self, provider_factory):
        provider_factory.return_value = Mock(
            get_product=Mock(side_effect=CatalogError(502, "catalog_unavailable", "unavailable"))
        )
        session = self.client.session
        session["dialog_context"] = {
            "dialog_id": "test-dialog",
            "version": 1,
            "state": "done",
            "history": [
                {"id": "welcome", "role": "assistant", "content": "Здравствуйте"},
                {
                    "id": "search-result",
                    "role": "assistant",
                    "content": "Нашёл вариант",
                    "products": [{"id": 900001, "name": "Устаревший поисковый снимок"}],
                },
            ],
            "attachments": {},
        }
        session.save()

        response = self.post_message("этот товар", "test-dialog")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["source_status"], "missing")
        self.assertEqual(message["products"], [])
        self.assertEqual(message["facts"], [])
