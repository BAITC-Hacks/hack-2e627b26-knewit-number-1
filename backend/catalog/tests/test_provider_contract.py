from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from catalog.providers.ekt import EktCatalogProvider
from catalog.providers.fixture import FixtureCatalogProvider


def _live_list_payload() -> dict:
    return {
        "page": 1,
        "per_page": 20,
        "count": 1,
        "items": [
            {
                "id": 515291,
                "name": "027228 АВ DRX250 MT 3ф 160А 18ka Legrand (1)",
                "article": "200300285_",
                "price": 64920,
                "image": "https://ekt.kz/upload/product.jpg",
                "url": "https://ekt.kz/catalog/product/",
                "offers": [],
            }
        ],
    }


def _live_detail_payload() -> dict:
    payload = _live_list_payload()["items"][0].copy()
    payload.update(
        {
            "description": "Live product detail",
            "quantity": 23,
            "stores": [{"id": 1, "name": "Алматы", "quantity": 5}],
            "properties": {"TORGOVAYA_MARKA": "Legrand", "KOLICHESTVO_POLYUSOV": "3"},
        }
    )
    return payload


class CatalogProviderContractMixin:
    provider = None
    expected_source = ""

    def test_list_has_common_catalog_contract(self):
        payload = self.provider.list_products(1, 20)
        self.assertEqual(set(("page", "per_page", "count", "items", "data_source")) - set(payload), set())
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["per_page"], 20)
        self.assertIsInstance(payload["items"], list)
        self.assertEqual(payload["data_source"], self.expected_source)
        for item in payload["items"]:
            self.assertIsInstance(item.get("id"), int)
            self.assertIsInstance(item.get("name"), str)
            self.assertIsInstance(item.get("article"), str)
            self.assertIn("offers", item)

    def test_detail_has_common_normalized_contract_and_cart_guard(self):
        detail = self.provider.get_product(self.product_id)
        for field in ("id", "name", "article", "data_source", "availability", "normalized", "offers", "cart_policy"):
            self.assertIn(field, detail)
        self.assertEqual(detail["data_source"], self.expected_source)
        self.assertIn(detail["availability"]["status"], {"available", "unavailable", "availability_unknown", "stale"})
        self.assertEqual(detail["normalized"]["id"], detail["id"])
        self.assertFalse(detail["cart_policy"]["automatic_add_allowed"])
        self.assertTrue(detail["cart_policy"]["requires_explicit_confirmation"])


class FixtureProviderContractTests(CatalogProviderContractMixin, SimpleTestCase):
    expected_source = "fixture"
    product_id = 900001

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = FixtureCatalogProvider(
            sellable_store_ids=(1, 2, 3),
            availability_rule_version="fixture-allowlist-v1",
            timeout_seconds=0,
            default_currency="KZT",
        )


class LiveProviderContractTests(CatalogProviderContractMixin, SimpleTestCase):
    expected_source = "ekt"
    product_id = 515291

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = EktCatalogProvider(
            base_url="https://ekt.kz/api",
            username="contract-user",
            password="contract-password",
            connect_timeout=1,
            read_timeout=3,
            sellable_store_ids=(1,),
            availability_rule_version="ekt-allowlist-v1",
        )

    def test_list_has_common_catalog_contract(self):
        with patch.object(EktCatalogProvider, "_request", return_value=_live_list_payload()):
            super().test_list_has_common_catalog_contract()

    def test_detail_has_common_normalized_contract_and_cart_guard(self):
        with patch.object(EktCatalogProvider, "_request", return_value=_live_detail_payload()):
            super().test_detail_has_common_normalized_contract_and_cart_guard()

    def test_live_difference_is_documented_and_does_not_change_common_fields(self):
        with patch.object(EktCatalogProvider, "_request", return_value=_live_detail_payload()):
            detail = self.provider.get_product(self.product_id)
        self.assertEqual(detail["data_source"], "ekt")
        self.assertNotIn("fixture_version", detail)
        self.assertNotIn("fixture_seed", detail)
