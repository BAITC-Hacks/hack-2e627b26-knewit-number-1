import copy
from datetime import datetime, timezone

from django.test import SimpleTestCase, override_settings

from catalog.normalization import normalize_product


class ProductNormalizationTests(SimpleTestCase):
    def test_normalization_preserves_raw_values_and_opaque_offers(self):
        fetched_at = datetime(2026, 9, 23, 12, 30, tzinfo=timezone.utc)
        source = {
            "id": 515291,
            "article": "200300285_",
            "name": "DRX250",
            "description": "Source description",
            "price": 64920,
            "quantity": 23,
            "stores": [{"id": 13, "name": "Almaty", "quantity": 5}],
            "image": "https://ekt.kz/image.jpg",
            "url": "https://ekt.kz/catalog/product/",
            "offers": [{"unconfirmed_shape": {"keep": True}}],
            "properties": {
                "TORGOVAYA_MARKA": "Legrand",
                "KOLICHESTVO_POLYUSOV": "3",
                "NOMINALNYY_TOK": "250 А",
                "KRATNOST_MIN": "1",
                "UNKNOWN_SOURCE_FIELD": ["raw", 7],
            },
            "updated_at": "2026-09-22T08:00:00+00:00",
        }
        original = copy.deepcopy(source)

        normalized = normalize_product(
            source,
            default_currency="KZT",
            availability={
                "status": "available",
                "sellable_quantity": 5,
                "rule_version": "v1",
            },
            fetched_at=fetched_at,
        )

        self.assertEqual(source, original)
        self.assertEqual(normalized["price"], {
            "amount": 64920,
            "currency": "KZT",
            "verified_at": "2026-09-23T12:30:00+00:00",
        })
        self.assertEqual(normalized["availability"]["sellable_quantity"], 5)
        self.assertIsNone(normalized["availability"]["unit"])
        self.assertIsNone(normalized["availability"]["step"])
        self.assertEqual(normalized["availability"]["minimum"], 1)
        self.assertEqual(normalized["availability"]["stores"], source["stores"])
        self.assertEqual(normalized["properties_raw"], source["properties"])
        self.assertEqual(normalized["attributes_normalized"]["brand"], "Legrand")
        self.assertEqual(normalized["attributes_normalized"]["pole_count"], "3")
        self.assertEqual(normalized["offers"], source["offers"])
        self.assertEqual(normalized["source_fetched_at"], "2026-09-23T12:30:00+00:00")
        self.assertEqual(normalized["source_updated_at"], source["updated_at"])

    def test_missing_values_remain_explicitly_unknown(self):
        normalized = normalize_product(
            {"id": 7, "price": None, "offers": "invalid", "properties": None},
            default_currency="KZT",
            availability=None,
            fetched_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        )

        self.assertIsNone(normalized["price"]["amount"])
        self.assertEqual(normalized["price"]["currency"], "KZT")
        self.assertEqual(normalized["availability"]["status"], "availability_unknown")
        self.assertIsNone(normalized["availability"]["sellable_quantity"])
        self.assertEqual(normalized["offers"], [])
        self.assertEqual(normalized["properties_raw"], {})
        self.assertEqual(normalized["attributes_normalized"], {})
        self.assertIsNone(normalized["source_updated_at"])


@override_settings(
    CATALOG_PROVIDER="fixture",
    FIXTURE_TIMEOUT_SECONDS=0,
    CATALOG_DEFAULT_CURRENCY="KZT",
)
class NormalizedCatalogApiTests(SimpleTestCase):
    def test_detail_keeps_raw_contract_and_adds_normalized_model(self):
        body = self.client.get("/api/products/detail", {"id": 900001}).json()

        self.assertIsInstance(body["price"], int)
        self.assertIsInstance(body["properties"], dict)
        normalized = body["normalized"]
        self.assertEqual(normalized["id"], body["id"])
        self.assertEqual(normalized["article"], body["article"])
        self.assertEqual(normalized["price"]["amount"], body["price"])
        self.assertEqual(normalized["price"]["currency"], "KZT")
        self.assertEqual(normalized["properties_raw"], body["properties"])
        self.assertEqual(normalized["offers"], body["offers"])
        self.assertEqual(normalized["availability"]["stores"], body["stores"])
        self.assertEqual(
            normalized["availability"]["verified_at"],
            normalized["source_fetched_at"],
        )

    def test_null_price_is_not_invented(self):
        body = self.client.get(
            "/api/products/detail",
            {"id": 900001, "fixture_case": "null_field"},
        ).json()

        self.assertIsNone(body["price"])
        self.assertIsNone(body["normalized"]["price"]["amount"])
        self.assertEqual(body["normalized"]["price"]["currency"], "KZT")
