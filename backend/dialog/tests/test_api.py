import json

from django.test import TestCase, override_settings


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

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="")
    def test_greeting_does_not_search_catalog_or_return_products(self):
        response = self.post_message("\u0441\u0430\u043b\u0430\u043c")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["products"], [])
        self.assertIn("\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435", message["content"])

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="")
    def test_capability_question_is_text_only(self):
        response = self.post_message("\u0447\u0442\u043e \u0442\u044b \u0443\u043c\u0435\u0435\u0448\u044c")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["products"], [])
        self.assertIn("\u043d\u0430\u0439\u0442\u0438 \u0442\u043e\u0432\u0430\u0440", message["content"])

    @override_settings(OPENAI_ENABLED=False, OPENAI_API_KEY="")
    def test_bare_find_product_request_asks_for_product_details(self):
        response = self.post_message("\u043d\u0430\u0439\u0434\u0438 \u0442\u043e\u0432\u0430\u0440")

        self.assertEqual(response.status_code, 200)
        message = response.json()["message"]
        self.assertEqual(message["products"], [])
        self.assertIn("\u0430\u0440\u0442\u0438\u043a\u0443\u043b", message["content"])

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
