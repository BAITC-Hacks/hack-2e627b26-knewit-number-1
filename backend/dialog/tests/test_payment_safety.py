import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.test import override_settings

from assistant.service import generate_reply
from dialog.llm import _history_input
from dialog.payment_safety import (
    PAYMENT_DATA_REDACTED,
    contains_payment_data,
    redact_payment_data,
)


class PaymentDataDetectorTests(SimpleTestCase):
    def test_detects_card_cvv_and_bank_requisites(self):
        self.assertTrue(contains_payment_data("Карта 4111 1111 1111 1111"))
        self.assertTrue(contains_payment_data("CVV: 123"))
        self.assertTrue(contains_payment_data("IBAN KZ86125A000000000000"))
        self.assertTrue(contains_payment_data("БИК 123456789, ИИК 123456789012345678"))
        self.assertTrue(contains_payment_data("bank account 123456789012"))
        self.assertFalse(contains_payment_data("Найдите автоматический выключатель 515291"))

    def test_redaction_never_returns_the_original_payment_text(self):
        raw = "Оплата картой 4111 1111 1111 1111, CVV 123"
        redacted = redact_payment_data(raw)
        self.assertEqual(redacted, PAYMENT_DATA_REDACTED)
        self.assertNotIn("4111", redacted)
        self.assertNotIn("123", redacted)

    def test_llm_history_boundary_redacts_legacy_session_content(self):
        raw = "Оплата картой 4111 1111 1111 1111, CVV 123"
        payload = _history_input([{"role": "user", "content": raw}], 2000)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("4111", serialized)
        self.assertNotIn("CVV 123", serialized)
        self.assertIn(PAYMENT_DATA_REDACTED, serialized)


class PaymentDataApiTests(TestCase):
    def post_message(self, text):
        return self.client.post(
            "/api/dialog/messages",
            data=json.dumps({"text": text}),
            content_type="application/json",
        )

    def test_payment_message_is_rejected_before_session_and_llm(self):
        raw = "Оплатить картой 4111 1111 1111 1111, CVV 123"
        with patch("dialog.views._process") as process:
            response = self.post_message(raw)

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["state"], "blocked")
        self.assertEqual(body["error"]["code"], "payment_data_detected")
        self.assertNotIn("4111", json.dumps(body, ensure_ascii=False))
        self.assertNotIn("CVV 123", json.dumps(body, ensure_ascii=False))
        process.assert_not_called()

        history = self.client.get("/api/dialog").json()["history"]
        serialized = json.dumps(history, ensure_ascii=False)
        self.assertNotIn("4111", serialized)
        self.assertNotIn("CVV 123", serialized)
        self.assertEqual(len([item for item in history if item.get("role") == "user"]), 0)

    def test_stream_payment_message_is_rejected_before_persisting(self):
        raw = "Мои банковские реквизиты: IBAN KZ86125A000000000000"
        response = self.client.post(
            "/api/dialog/messages/stream",
            data=json.dumps({"text": raw}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "payment_data_detected")
        history = self.client.get("/api/dialog").json()["history"]
        self.assertNotIn("KZ86125A000000000000", json.dumps(history, ensure_ascii=False))

    @override_settings(ASSISTANT_LLM_PROVIDER="openai", OPENAI_API_KEY="test-key", OPENAI_MODEL="test-model")
    @patch("assistant.views.generate_reply")
    def test_legacy_chat_api_rejects_payment_data_before_language_session_or_llm(self, generate):
        raw = "Карта 4111 1111 1111 1111, CVV 123"
        response = self.client.post(
            "/api/chat/messages",
            data=json.dumps({"dialog_id": "legacy-dialog", "text": raw}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "payment_data_detected")
        self.assertNotIn("4111", json.dumps(response.json(), ensure_ascii=False))
        generate.assert_not_called()
        self.assertNotIn("legacy-dialog", self.client.session.get("assistant_dialog_languages", {}))

    @override_settings(ASSISTANT_LLM_PROVIDER="openai", OPENAI_API_KEY="test-key", OPENAI_MODEL="test-model")
    @patch("assistant.openai_client.OpenAIResponsesClient.create_response", return_value="ok")
    def test_legacy_service_redacts_payment_data_at_llm_boundary(self, create_response):
        raw = "Карта 4111 1111 1111 1111, CVV 123"
        generate_reply(text=raw, language="ru")

        sent = create_response.call_args.kwargs["input_text"]
        self.assertNotIn("4111", sent)
        self.assertNotIn("CVV 123", sent)
        self.assertEqual(sent, PAYMENT_DATA_REDACTED)
