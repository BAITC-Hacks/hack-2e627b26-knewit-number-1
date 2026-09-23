from django.test import TestCase

from knowledge_base.engine import answer_query
from knowledge_base.models import KnowledgeEntry


class KnowledgeBaseTests(TestCase):
    def test_migration_contains_eleven_starting_entries(self):
        self.assertEqual(KnowledgeEntry.objects.count(), 11)
        self.assertEqual(
            KnowledgeEntry.objects.filter(status=KnowledgeEntry.Status.CONFLICTED).count(), 2
        )

    def test_approved_answer_returns_current_source(self):
        result = answer_query("как оплатить физическому лицу")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["intent"], "payment_individual")
        self.assertFalse(result["manager_required"])
        self.assertEqual(result["verified_at"].isoformat(), "2026-09-23")

    def test_missing_condition_is_safe_and_escalates(self):
        entry = KnowledgeEntry.objects.get(intent="minimum_order", status=KnowledgeEntry.Status.MISSING)
        entry.variants = ["минимальная партия подтверждена"]
        entry.save(update_fields=("variants",))
        result = answer_query("минимальная партия подтверждена")
        self.assertEqual(result["status"], "missing")
        self.assertTrue(result["manager_required"])
        self.assertIn("не подтверждено", result["answer"])

    def test_conflict_never_selects_a_condition_and_keeps_both_sources(self):
        result = answer_query("минимальная партия")
        self.assertEqual(result["status"], "conflicted")
        self.assertTrue(result["manager_required"])
        self.assertEqual(len(result["sources"]), 2)
        self.assertNotIn("15 000", result["answer"])
        self.assertNotIn("30 000", result["answer"])

    def test_kazakh_answer_uses_answer_kk(self):
        result = answer_query("самовывоз", language="kk")
        self.assertEqual(result["status"], "qualified")
        self.assertIn("алып кету", result["answer"])

    def test_endpoint_rejects_empty_query(self):
        response = self.client.get("/api/knowledge-base")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_query")
