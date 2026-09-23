from datetime import datetime, timedelta, timezone
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from catalog.availability import calculate_availability
from catalog.errors import CatalogConfigurationError, CatalogError, CatalogTransportError
from catalog.index_sync import sync_catalog
from catalog.providers.ekt import EktCatalogProvider
from catalog.providers.fixture import FIXTURE_DATASET_VERSION, FIXTURE_SEED, FixtureCatalogProvider


@contextmanager
def sync_test_paths():
    root = Path(__file__).resolve().parents[2]
    index_path = root / ".test_catalog_index.json"
    status_path = root / ".test_catalog_sync_status.json"
    for path in (index_path, status_path):
        path.unlink(missing_ok=True)
    try:
        yield index_path, status_path
    finally:
        for path in (index_path, status_path):
            path.unlink(missing_ok=True)


@override_settings(CATALOG_PROVIDER="fixture", FIXTURE_TIMEOUT_SECONDS=0)
class FixtureCatalogApiTests(SimpleTestCase):
    def test_first_page_matches_catalog_contract(self):
        response = self.client.get("/api/products")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["per_page"], 20)
        self.assertEqual(body["count"], 20)
        self.assertEqual(body["data_source"], "fixture")
        self.assertEqual(body["fixture_version"], FIXTURE_DATASET_VERSION)
        self.assertEqual(body["fixture_seed"], FIXTURE_SEED)
        self.assertEqual(
            set(body["items"][0]),
            {
                "id",
                "name",
                "article",
                "price",
                "image",
                "url",
                "url_api_detail",
                "offers",
                "data_source",
                "fixture_version",
            },
        )
        self.assertEqual(body["items"][0]["offers"], [])

    def test_catalog_has_at_least_five_non_empty_pages(self):
        ids = []
        for page in range(1, 7):
            body = self.client.get("/api/products", {"page": page}).json()
            self.assertEqual(body["count"], 20)
            ids.extend(item["id"] for item in body["items"])
        self.assertEqual(len(ids), 120)
        self.assertEqual(len(set(ids)), 120)

    def test_detail_has_required_fields_and_computed_availability(self):
        response = self.client.get("/api/products/detail", {"id": 900001})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(
            {
                "id",
                "name",
                "article",
                "description",
                "price",
                "quantity",
                "stores",
                "image",
                "url",
                "offers",
                "properties",
                "availability",
                "data_source",
            }.issubset(body)
        )
        self.assertEqual(body["availability"]["status"], "available")
        self.assertEqual(body["availability"]["sellable_quantity"], 8)

    def test_non_sellable_stock_is_unavailable(self):
        body = self.client.get("/api/products/detail", {"id": 900003}).json()
        self.assertEqual(body["quantity"], 11)
        self.assertEqual(body["availability"]["status"], "unavailable")
        self.assertEqual(body["availability"]["sellable_quantity"], 0)

    def test_unclassified_store_is_availability_unknown(self):
        body = self.client.get("/api/products/detail", {"id": 900004}).json()
        self.assertEqual(body["availability"]["status"], "availability_unknown")
        self.assertIsNone(body["availability"]["sellable_quantity"])

    def test_analog_groups_are_versioned_and_have_ten_members(self):
        products = []
        for page in range(1, 7):
            products.extend(self.client.get("/api/products", {"page": page}).json()["items"])
        details = [self.client.get("/api/products/detail", {"id": p["id"]}).json() for p in products]
        groups = {}
        for detail in details:
            groups.setdefault(detail["properties"]["ANALOG_GROUP"], []).append(detail)
        self.assertEqual(len(groups), 12)
        self.assertTrue(all(len(group) == 10 for group in groups.values()))

    def test_catalog_contains_cyrillic_articles_and_typo_search_aliases(self):
        first = self.client.get("/api/products/detail", {"id": 900001}).json()
        second = self.client.get("/api/products/detail", {"id": 900002}).json()
        self.assertTrue(any("А" <= char <= "я" for char in first["article"]))
        self.assertIn("автомтический выключатель", first["properties"]["SEARCH_ALIASES"])
        self.assertEqual(first["properties"]["ANALOG_GROUP"], second["properties"]["ANALOG_GROUP"])

    def test_unknown_product_returns_404(self):
        response = self.client.get("/api/products/detail", {"id": 42})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "product_not_found")

    def test_invalid_query_parameters_return_400(self):
        self.assertEqual(self.client.get("/api/products", {"page": "nope"}).status_code, 400)
        self.assertEqual(self.client.get("/api/products", {"per_page": 101}).status_code, 400)
        self.assertEqual(self.client.get("/api/products/detail").status_code, 400)

    def test_error_fixtures_cover_http_and_transport_cases(self):
        cases = {
            "unauthorized": 401,
            "not_found": 404,
            "rate_limited": 429,
            "server_error": 503,
            "timeout": 504,
        }
        with patch("catalog.providers.fixture.time.sleep"):
            for fixture_case, expected_status in cases.items():
                with self.subTest(fixture_case=fixture_case):
                    response = self.client.get("/api/products", {"fixture_case": fixture_case})
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(response.json()["data_source"], "fixture")
        self.assertEqual(
            self.client.get("/api/products", {"fixture_case": "rate_limited"})["Retry-After"],
            "2",
        )

    def test_malformed_data_fixtures(self):
        missing = self.client.get("/api/products", {"fixture_case": "missing_field"}).json()
        null = self.client.get("/api/products", {"fixture_case": "null_field"}).json()
        self.assertNotIn("name", missing["items"][0])
        self.assertIsNone(null["items"][0]["price"])

        missing_detail = self.client.get(
            "/api/products/detail", {"id": 900001, "fixture_case": "missing_field"}
        ).json()
        null_detail = self.client.get(
            "/api/products/detail", {"id": 900001, "fixture_case": "null_field"}
        ).json()
        self.assertNotIn("description", missing_detail)
        self.assertIsNone(null_detail["price"])

    def test_scenario_can_be_selected_by_header(self):
        response = self.client.get("/api/products", headers={"X-Fixture-Scenario": "unauthorized"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], 'Basic realm="Fixture API"')

    def test_fixture_image_and_product_links_are_resolvable(self):
        detail = self.client.get("/api/products/detail", {"id": 900001}).json()
        image = self.client.get(detail["image"])
        product_page = self.client.get(detail["url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/svg+xml")
        self.assertEqual(product_page.status_code, 200)
        self.assertContains(product_page, "DEMO FIXTURE")


class AvailabilityRuleTests(SimpleTestCase):
    def test_missing_quantity_is_unknown(self):
        result = calculate_availability([], None, (1,), "v1")
        self.assertEqual(result["status"], "availability_unknown")
        self.assertIsNone(result["sellable_quantity"])

    def test_service_store_name_overrides_accidental_allowlist_entry(self):
        result = calculate_availability(
            [{"id": 900, "name": "Брак", "quantity": 4}], 4, (900,), "v1"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["sellable_quantity"], 0)

    def test_positive_stock_without_approved_allowlist_is_unknown(self):
        result = calculate_availability(
            [{"id": 13, "name": "Алматы", "quantity": 5}], 5, (), "ekt-unapproved-v1"
        )
        self.assertEqual(result["status"], "availability_unknown")
        self.assertIsNone(result["sellable_quantity"])

    def test_expired_snapshot_is_stale(self):
        now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
        result = calculate_availability(
            [{"id": 1, "name": "Алматы", "quantity": 5}],
            5,
            (1,),
            "v1",
            observed_at=now - timedelta(seconds=301),
            stale_after_seconds=300,
            now=now,
        )
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["sellable_quantity"])

    def test_cyrillic_service_store_is_excluded(self):
        result = calculate_availability(
            [{"id": 900, "name": "Брак", "quantity": 4}], 4, (900,), "v1"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["sellable_quantity"], 0)


class EktProviderTests(SimpleTestCase):
    def make_provider(self, base_url="https://ekt.kz/api"):
        return EktCatalogProvider(
            base_url=base_url,
            username="user",
            password="secret",
            connect_timeout=1,
            read_timeout=3,
            sellable_store_ids=(1, 2, 3),
            availability_rule_version="v1",
        )

    @patch("catalog.providers.ekt.http.client.HTTPSConnection")
    def test_rejects_non_https_base_url_before_network(self, mocked_connection):
        provider = self.make_provider("http://ekt.kz/api")
        with self.assertRaises(CatalogConfigurationError):
            provider.list_products(1, 20)
        mocked_connection.assert_not_called()

    def test_redirects_are_not_followed(self):
        provider = self.make_provider()
        response = Mock(status=302)
        response.read.return_value = b""
        connection = Mock()
        connection.sock = Mock()
        connection.getresponse.return_value = response
        with patch("catalog.providers.ekt.http.client.HTTPSConnection", return_value=connection) as factory:
            with self.assertRaises(CatalogTransportError):
                provider._request_once("products", {"page": 1})
        factory.assert_called_once_with("ekt.kz", port=None, timeout=1)
        connection.sock.settimeout.assert_called_once_with(3)
        connection.request.assert_called_once()

    def test_live_detail_url_is_normalized_to_backend_route(self):
        provider = self.make_provider()
        upstream = {
            "id": 515291,
            "url_api_detail": "https://ekt.kz/api/products/detail?id=515291",
            "quantity": 3,
            "stores": [{"id": 1, "name": "Алматы", "quantity": 3}],
        }
        with patch.object(EktCatalogProvider, "_request", return_value=upstream):
            result = provider.get_product(515291)
        self.assertEqual(result["url_api_detail"], "/api/products/detail?id=515291")
        self.assertEqual(result["data_source"], "ekt")

    def test_empty_offers_disable_automatic_add_and_require_confirmation(self):
        provider = self.make_provider()
        upstream = {
            "id": 515291,
            "offers": [],
            "quantity": 3,
            "stores": [{"id": 1, "name": "Алматы", "quantity": 3}],
        }
        with patch.object(EktCatalogProvider, "_request", return_value=upstream):
            result = provider.get_product(515291)
        self.assertFalse(result["cart_policy"]["automatic_add_allowed"])
        self.assertTrue(result["cart_policy"]["requires_explicit_confirmation"])
        self.assertFalse(result["cart_policy"]["offers_schema_supported"])

    @patch(
        "catalog.providers.ekt.socket.getaddrinfo",
        side_effect=[
            [(None, None, None, None, ("8.8.8.8", 443))],
            [(None, None, None, None, ("8.8.8.8", 443))],
            [(None, None, None, None, ("10.0.0.1", 443))],
        ],
    )
    def test_external_urls_are_restricted_to_https_allowlisted_public_hosts(self, mocked_getaddrinfo):
        provider = self.make_provider()
        payload = {
            "id": 515291,
            "image": "https://ekt.kz/upload/image.jpg",
            "properties": {
                "CERTIFICATE": "https://ekt.kz/docs/certificate.pdf",
                "EVIL": "https://evil.example/file.pdf",
                "PRIVATE": "https://ekt.kz/private/file.pdf",
            },
        }

        result = provider._mark_source(payload)

        self.assertEqual(result["image"], "https://ekt.kz/upload/image.jpg")
        self.assertEqual(result["properties"]["CERTIFICATE"], "https://ekt.kz/docs/certificate.pdf")
        self.assertIsNone(result["properties"]["EVIL"])
        self.assertIsNone(result["properties"]["PRIVATE"])
        self.assertTrue(mocked_getaddrinfo.called)

    def test_missing_items_are_tolerated_and_unknown_properties_are_preserved(self):
        provider = self.make_provider()
        payload = {"page": 1, "items": None, "unknown_field": {"value": 7}}

        result = provider._mark_source(payload)

        self.assertIsNone(result["items"])
        self.assertEqual(result["unknown_field"], {"value": 7})
        self.assertEqual(result["data_source"], "ekt")

    def test_authorization_errors_are_not_retried(self):
        provider = self.make_provider()
        failure = CatalogError(401, "upstream_unauthorized", "unauthorized")
        with patch.object(EktCatalogProvider, "_request_once", side_effect=failure) as request:
            with self.assertRaises(CatalogError):
                provider._request("products", {"page": 1})
        request.assert_called_once()

    @patch("catalog.providers.ekt.time.sleep")
    @patch("catalog.providers.ekt.random.uniform", return_value=0.05)
    def test_retry_uses_exponential_backoff_with_jitter(self, mocked_jitter, mocked_sleep):
        provider = self.make_provider()
        failure = CatalogError(503, "ekt_api_error", "upstream")
        success = {"page": 1, "items": []}
        with patch.object(EktCatalogProvider, "_request_once", side_effect=[failure, failure, success]) as request:
            self.assertEqual(provider._request("products", {"page": 1}), success)
        self.assertEqual(request.call_count, 3)
        delays = [call.args[0] for call in mocked_sleep.call_args_list]
        self.assertAlmostEqual(delays[0], 0.15)
        self.assertAlmostEqual(delays[1], 0.25)
        self.assertEqual(mocked_jitter.call_count, 2)


class ProviderSwitchTests(SimpleTestCase):
    @override_settings(CATALOG_PROVIDER="invalid")
    def test_invalid_provider_fails_with_controlled_error(self):
        response = self.client.get("/api/products")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "catalog_configuration_error")

    @override_settings(CATALOG_PROVIDER="ekt", EKT_API_USERNAME="", EKT_API_PASSWORD="")
    def test_ekt_provider_never_uses_placeholder_credentials(self):
        response = self.client.get("/api/products")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "catalog_configuration_error")


class CatalogIndexSyncTests(SimpleTestCase):
    def test_fixture_catalog_is_fully_indexed_and_deduplicated(self):
        provider = FixtureCatalogProvider(
            sellable_store_ids=(1, 2, 3),
            availability_rule_version="fixture-v1",
            timeout_seconds=0,
        )
        with sync_test_paths() as (index_path, status_path):
            result = sync_catalog(provider, index_path, status_path, max_pages=20, per_page=20)

            self.assertTrue(result.success)
            self.assertEqual(result.stop_reason, "empty_page")
            self.assertEqual(result.pages, 7)
            self.assertEqual(result.products, 120)
            index = json.loads(index_path.read_text(encoding="utf-8"))
            ids = [item["id"] for item in index["items"]]
            self.assertEqual(len(ids), 120)
            self.assertEqual(len(set(ids)), 120)
            self.assertEqual(ids, sorted(ids))
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["last_successful_products"], 120)
            self.assertEqual(status["last_errors"], 0)

    def test_repeated_page_ids_are_an_end_condition(self):
        class RepeatingProvider:
            data_source = "fixture"

            def list_products(self, page, per_page):
                del page, per_page
                return {"items": [{"id": 1, "name": "one"}]}

        with sync_test_paths() as (index_path, status_path):
            result = sync_catalog(
                RepeatingProvider(),
                index_path,
                status_path,
                max_pages=10,
                per_page=20,
            )
            self.assertTrue(result.success)
            self.assertEqual(result.stop_reason, "repeated_page_ids")
            self.assertEqual(result.pages, 2)
            self.assertEqual(result.products, 1)

    def test_max_pages_guard_does_not_replace_last_successful_index(self):
        class EndlessProvider:
            data_source = "fixture"

            def list_products(self, page, per_page):
                del per_page
                return {"items": [{"id": page, "name": str(page)}]}

        with sync_test_paths() as (index_path, status_path):
            initial = sync_catalog(EndlessProvider(), index_path, status_path, max_pages=2, per_page=20)
            self.assertFalse(initial.success)
            self.assertEqual(initial.stop_reason, "max_pages_guard")
            self.assertFalse(index_path.exists())
