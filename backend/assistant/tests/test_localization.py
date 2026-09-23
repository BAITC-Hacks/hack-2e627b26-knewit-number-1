from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase, override_settings

from assistant.kb import StaticKnowledgeEntry, publishable_static_answer
from assistant.localization import catalog_search_context, detect_language
from cart.models import CartAction, CartItem


@override_settings(CATALOG_PROVIDER="fixture", FIXTURE_TIMEOUT_SECONDS=0)
class AssistantLanguageApiTests(TestCase):
    def post_json(self, path: str, payload: dict):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def propose(self):
        return self.post_json(
            "/api/cart/actions",
            {
                "dialog_id": "dialog-kk",
                "message_id": "message-1",
                "message_version": 1,
                "product_id": 900001,
                "quantity": 2,
            },
        )

    def test_first_substantive_kazakh_message_sets_kazakh_and_search_context(self):
        response = self.post_json(
            "/api/chat/messages",
            {"dialog_id": "dialog-kk", "text": "Маған автоматты ажыратқыш керек, 027228 бар ма?"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["language"], "kk")
        self.assertEqual(body["language_source"], "first_meaningful_message")
        self.assertEqual(body["reply"]["status"], "unavailable")
        self.assertIn("автоматический выключатель", body["reply"]["catalog_search"]["canonical_terms"])
        self.assertIn("027228", body["reply"]["catalog_search"]["canonical_terms"])

    def test_explicit_language_switch_expires_proposal_and_requires_a_new_one(self):
        self.post_json("/api/chat/language", {"dialog_id": "dialog-kk", "language": "ru"})
        proposal = self.propose()
        self.assertEqual(proposal.status_code, 201)

        response = self.post_json("/api/chat/language", {"dialog_id": "dialog-kk", "language": "kk"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["language_changed"])
        self.assertEqual(body["language"], "kk")
        self.assertEqual(len(body["expired_cart_proposals"]), 1)
        self.assertEqual(body["expired_cart_proposals"][0]["status"], "expired")
        self.assertTrue(body["cart_summary"]["requires_new_proposal"])
        self.assertEqual(CartAction.objects.get().status, "expired")

        confirmation = self.post_json(
            "/api/cart/actions/confirm-text", {"dialog_id": "dialog-kk", "text": "иә"}
        )
        self.assertEqual(confirmation.status_code, 409)
        self.assertEqual(confirmation.json()["error"]["code"], "no_active_action")
        self.assertEqual(CartItem.objects.count(), 0)

    def test_kazakh_confirmation_is_accepted_for_a_fresh_single_proposal(self):
        self.propose()

        confirmation = self.post_json(
            "/api/cart/actions/confirm-text", {"dialog_id": "dialog-kk", "text": "Себетке қосыңыз"}
        )

        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.json()["status"], "succeeded")

    @override_settings(
        ASSISTANT_LLM_PROVIDER="openai",
        OPENAI_API_KEY="test-key-only",
        OPENAI_MODEL="test-model",
    )
    @patch("assistant.openai_client.OpenAIResponsesClient.create_response", return_value="Қоймадағы қалдық тексерілді.")
    def test_configured_openai_reply_uses_selected_locale_without_exposing_instructions(self, create_response):
        response = self.post_json(
            "/api/chat/messages",
            {"dialog_id": "dialog-model", "language": "kk", "text": "Қоймада бар ма?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"]["text"], "Қоймадағы қалдық тексерілді.")
        instructions = create_response.call_args.kwargs["instructions"]
        self.assertIn("Kazakh", instructions)
        self.assertNotIn("test-key-only", instructions)


class LocalizationUnitTests(TestCase):
    def test_detection_defaults_to_russian_for_ambiguous_text(self):
        self.assertEqual(detect_language("DRX250 160A"), "ru")
        self.assertEqual(detect_language("Маған керек"), "kk")

    def test_search_context_preserves_articles_and_does_not_translate_official_identifiers(self):
        context = catalog_search_context("Legrand 027228 үшін балама", "kk")
        self.assertIn("аналог", context["canonical_terms"])
        self.assertIn("Legrand", context["canonical_terms"])
        self.assertIn("027228", context["canonical_terms"])

    def test_unreviewed_static_kazakh_copy_is_not_publishable(self):
        draft = StaticKnowledgeEntry("kk", "Жеткізу туралы жоба", None, None)
        approved = StaticKnowledgeEntry("kk", "Жеткізу шарттары", "Редактор", datetime.now(timezone.utc))
        self.assertIsNone(publishable_static_answer(draft))
        self.assertEqual(publishable_static_answer(approved), "Жеткізу шарттары")
