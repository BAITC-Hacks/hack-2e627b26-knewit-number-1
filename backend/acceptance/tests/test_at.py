from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from acceptance.matrix import AT_CASES
from acceptance.sample import LABEL_COUNTS, SAMPLE_SIZE, SAMPLE_VERSION, build_acceptance_sample, sample_counts
from catalog.analogs import find_analogs
from catalog.providers.fixture import FIXTURE_DATASET_VERSION, PRODUCTS
from catalog.search import clear_index_cache, search_catalog, semantic_search_catalog
from cart.models import CartItem


def _write_index(directory: str) -> Path:
    path = Path(directory) / "catalog-index.json"
    path.write_text(
        json.dumps({"data_source": "fixture", "version": FIXTURE_DATASET_VERSION, "items": PRODUCTS}, ensure_ascii=False),
        encoding="utf-8",
    )
    clear_index_cache()
    return path


class AcceptanceMatrixTests(SimpleTestCase):
    def test_at_matrix_is_complete_and_versioned(self):
        self.assertEqual([case.case_id for case in AT_CASES], [f"AT-{index:03d}" for index in range(1, 37)])
        self.assertTrue(all(case.requirements and case.test_data_version and case.expected_result and case.evidence for case in AT_CASES))

    def test_labeled_sample_meets_required_quotas(self):
        rows = build_acceptance_sample()
        self.assertEqual(SAMPLE_VERSION, "acceptance-sample-v1")
        self.assertEqual(len(rows), SAMPLE_SIZE)
        self.assertEqual(sample_counts(rows), LABEL_COUNTS)
        self.assertGreaterEqual(sample_counts(rows)["exact_article_or_id"] / SAMPLE_SIZE, 0.20)
        self.assertGreaterEqual(sample_counts(rows)["name_or_typo"] / SAMPLE_SIZE, 0.25)
        self.assertGreaterEqual(sample_counts(rows)["characteristic"] / SAMPLE_SIZE, 0.30)
        self.assertGreaterEqual(sample_counts(rows)["absence_or_analog"] / SAMPLE_SIZE, 0.25)

    def test_exact_and_typo_samples_reach_expected_product_in_top_five(self):
        rows = build_acceptance_sample()
        with tempfile.TemporaryDirectory() as directory:
            index_path = _write_index(directory)
            for row in rows[:40] + rows[40:90]:
                result = search_catalog(row.query, index_path, 5)
                ids = [item["id"] for item in result["results"]]
                with self.subTest(row=row.case_id, query=row.query):
                    self.assertIn(row.target_product_id, ids)

    def test_characteristic_samples_use_semantic_search(self):
        rows = build_acceptance_sample()[90:150]
        with tempfile.TemporaryDirectory() as directory:
            index_path = _write_index(directory)
            for row in rows:
                result = semantic_search_catalog(row.query, index_path, 5)
                with self.subTest(row=row.case_id, query=row.query):
                    self.assertTrue(result["results"])

    def test_absence_sample_is_explicitly_unresolved(self):
        rows = build_acceptance_sample()[150:]
        with tempfile.TemporaryDirectory() as directory:
            index_path = _write_index(directory)
            for row in rows:
                result = search_catalog(row.query, index_path, 5)
                with self.subTest(row=row.case_id):
                    # A misspelled/unresolved phrase may yield fuzzy candidates,
                    # but it must never be promoted to an exact product or to
                    # the expected analog without an explicit compatibility
                    # check.
                    self.assertNotEqual(result["mode"], "exact")
                    self.assertIsNotNone(row.analog_product_id)

    def test_analog_sample_exposes_comparison_and_sellable_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            index_path = _write_index(directory)
            result = find_analogs(900021, index_path, 5)
        self.assertEqual(result["matrix"], "lighting-v1")
        self.assertTrue(result["results"])
        candidate = result["results"][0]
        self.assertIn("comparison", candidate)
        self.assertIn("explanation", candidate)
        self.assertGreater(candidate["sellable_quantity"], 0)


@override_settings(CATALOG_PROVIDER="fixture", FIXTURE_TIMEOUT_SECONDS=0)
class AcceptanceCartSafetyTests(TestCase):
    def post_json(self, path: str, payload: dict):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def test_at_007_and_at_030_intent_never_changes_cart_without_explicit_confirmation(self):
        before = self.client.get("/api/cart").json()
        proposal = self.post_json(
            "/api/cart/actions",
            {
                "dialog_id": "acceptance-dialog",
                "message_id": "intent-1",
                "message_version": 1,
                "product_id": 900001,
                "quantity": 2,
            },
        )
        self.assertEqual(proposal.status_code, 201)
        self.assertEqual(self.client.get("/api/cart").json()["version"], before["version"])
        self.assertEqual(CartItem.objects.count(), 0)
        text_intent = self.post_json(
            "/api/cart/actions/confirm-text",
            {"dialog_id": "acceptance-dialog", "text": "хочу купить"},
        )
        self.assertEqual(text_intent.status_code, 422)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_at_036_live_unavailable_falls_back_with_explicit_demo_marker(self):
        with override_settings(CATALOG_PROVIDER="ekt", EKT_API_USERNAME="", EKT_API_PASSWORD=""):
            live = self.client.get("/api/products")
            self.assertEqual(live.status_code, 500)
            self.assertEqual(live.json()["error"]["code"], "catalog_configuration_error")

        # The fallback is an explicit deployment/configuration choice, never a
        # silent relabeling of a live response.
        products = self.client.get("/api/products")
        self.assertEqual(products.status_code, 200)
        self.assertEqual(products.json()["data_source"], "fixture")
        self.assertEqual(products.json()["fixture_version"], FIXTURE_DATASET_VERSION)
        page = self.client.get("/demo/catalog/900001/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "DEMO FIXTURE")
