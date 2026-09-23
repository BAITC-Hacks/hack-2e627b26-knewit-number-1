import json

from django.test import TestCase


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
