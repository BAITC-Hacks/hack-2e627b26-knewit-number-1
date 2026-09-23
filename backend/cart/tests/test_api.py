import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from catalog.providers.fixture import PRODUCTS_BY_ID
from cart.errors import CartApiError
from cart.models import CartAction, CartItem, CartMutation
from cart.service import _maximum_valid_quantity, _sales_rules, _validate_sales_quantity


@override_settings(CATALOG_PROVIDER="fixture", FIXTURE_TIMEOUT_SECONDS=0)
class CartApiTests(TestCase):
    def payload(self, **overrides):
        payload = {
            "dialog_id": "dialog-1",
            "message_id": "message-1",
            "message_version": 1,
            "product_id": 900001,
            "offer_id": None,
            "quantity": 2,
        }
        payload.update(overrides)
        return payload

    def post_json(self, path, payload, client=None, **headers):
        return (client or self.client).post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def propose(self, **overrides):
        return self.post_json("/api/cart/actions", self.payload(**overrides))

    def confirm(self, action_id, payload=None, client=None):
        return self.post_json(
            f"/api/cart/actions/{action_id}/confirm",
            {} if payload is None else payload,
            client=client,
        )

    def test_proposal_contains_bound_summary_and_has_at_most_five_minute_ttl(self):
        before = timezone.now()
        response = self.propose()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "proposed")
        self.assertEqual(body["dialog_id"], "dialog-1")
        self.assertEqual(body["message_id"], "message-1")
        self.assertEqual(body["message_version"], 1)
        self.assertEqual(body["product_id"], 900001)
        self.assertEqual(body["quantity"], 2)
        fixture_price = Decimal(str(PRODUCTS_BY_ID[900001]["price"]))
        self.assertEqual(body["unit_price"], format(fixture_price, ".2f"))
        self.assertEqual(body["currency"], "KZT")
        self.assertEqual(body["total"], format(fixture_price * 2, ".2f"))
        self.assertEqual(body["expected_cart_version"], 0)
        self.assertNotIn("idempotency_key", body)
        expires_at = timezone.datetime.fromisoformat(body["expires_at"])
        self.assertGreater(expires_at, before)
        self.assertLessEqual(expires_at, before + timedelta(minutes=5, seconds=1))

    def test_repeated_proposal_for_same_message_is_idempotent(self):
        first = self.propose()
        second = self.propose()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["action_id"], first.json()["action_id"])
        self.assertEqual(CartAction.objects.count(), 1)

    def test_proposal_retry_recovers_existing_action_without_catalog_call(self):
        first = self.propose()

        with patch("cart.service._load_detail", side_effect=AssertionError("must not be called")):
            second = self.propose()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["action_id"], first.json()["action_id"])

    def test_same_message_version_cannot_be_rebound(self):
        self.propose()
        response = self.propose(product_id=900005)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "message_version_conflict")

    def test_new_summary_expires_previous_proposal_in_same_dialog(self):
        first = self.propose().json()
        second = self.propose(message_id="message-2", message_version=2).json()

        self.assertNotEqual(first["action_id"], second["action_id"])
        self.assertEqual(CartAction.objects.get(pk=first["action_id"]).status, "expired")
        self.assertEqual(CartAction.objects.get(pk=second["action_id"]).status, "proposed")

    def test_foreign_session_gets_404_and_cart_is_unchanged(self):
        action_id = self.propose().json()["action_id"]
        other = Client()

        response = self.confirm(action_id, client=other)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "action_not_found")
        self.assertEqual(CartItem.objects.count(), 0)

    def test_malformed_action_id_returns_json_404(self):
        response = self.confirm("not-a-uuid")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "action_not_found")

    def test_confirm_adds_once_and_replay_returns_saved_result(self):
        action_id = self.propose().json()["action_id"]

        first = self.confirm(action_id)
        second = self.confirm(action_id)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(first.json()["added_quantity"], 2)
        self.assertEqual(first.json()["cart"]["version"], 1)
        self.assertEqual(first.json()["cart"]["url"], "/demo/cart/")
        self.assertEqual(CartItem.objects.get().quantity, 2)
        self.assertEqual(CartMutation.objects.count(), 1)

    def test_proposal_and_confirmation_each_perform_a_live_catalog_read(self):
        from cart import service

        with patch("cart.service._load_detail", wraps=service._load_detail) as live_read:
            action_id = self.propose().json()["action_id"]
            response = self.confirm(action_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(live_read.call_count, 2)

    def test_confirmation_body_cannot_change_proposal(self):
        action_id = self.propose().json()["action_id"]
        response = self.confirm(action_id, {"quantity": 7})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "immutable_action")
        self.assertEqual(CartItem.objects.count(), 0)

    def test_expired_action_is_rejected_and_persistently_marked_expired(self):
        action_id = self.propose().json()["action_id"]
        CartAction.objects.filter(pk=action_id).update(expires_at=timezone.now() - timedelta(seconds=1))

        response = self.confirm(action_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "action_expired")
        self.assertEqual(CartAction.objects.get(pk=action_id).status, "expired")
        self.assertEqual(CartItem.objects.count(), 0)

    def test_intent_and_question_phrases_are_not_confirmations(self):
        self.propose()
        for text in ("хочу купить", "можно добавить?", "сколько будет?"):
            with self.subTest(text=text):
                response = self.post_json(
                    "/api/cart/actions/confirm-text",
                    {"dialog_id": "dialog-1", "text": text},
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "confirmation_required")
        self.assertEqual(CartItem.objects.count(), 0)

    def test_allowlisted_text_confirms_single_active_action(self):
        self.propose()

        response = self.post_json(
            "/api/cart/actions/confirm-text",
            {"dialog_id": "dialog-1", "text": "  Подтверждаю  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "succeeded")

    def test_text_confirmation_without_active_action_is_rejected(self):
        response = self.post_json(
            "/api/cart/actions/confirm-text",
            {"dialog_id": "dialog-1", "text": "да"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "no_active_action")

    def test_text_confirmation_rejects_ambiguous_active_actions(self):
        first = self.propose(dialog_id="dialog-a", message_id="a").json()
        second = self.propose(dialog_id="dialog-b", message_id="b").json()
        CartAction.objects.filter(pk=second["action_id"]).update(dialog_id="dialog-a")

        response = self.post_json(
            "/api/cart/actions/confirm-text",
            {"dialog_id": "dialog-a", "text": "да"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ambiguous_confirmation")
        self.assertEqual(CartAction.objects.get(pk=first["action_id"]).status, "proposed")
        self.assertEqual(CartItem.objects.count(), 0)

    def test_changed_cart_version_expires_action_and_returns_replacement(self):
        first = self.propose(dialog_id="dialog-a", message_id="a").json()
        second = self.propose(dialog_id="dialog-b", message_id="b").json()
        self.confirm(first["action_id"])

        response = self.confirm(second["action_id"])

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"]["code"], "action_stale")
        self.assertEqual(body["replacement_action"]["expected_cart_version"], 1)
        self.assertEqual(CartAction.objects.get(pk=second["action_id"]).status, "expired")
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_reduced_stock_returns_replacement_with_maximum_additional_quantity(self):
        action_id = self.propose(quantity=8).json()["action_id"]
        changed = copy.deepcopy(PRODUCTS_BY_ID[900001])
        changed["stores"][0]["quantity"] = 3
        changed["quantity"] = 5
        changed["availability"] = {
            "status": "available",
            "sellable_quantity": 3,
            "rule_version": "fixture-allowlist-v1",
        }

        with patch("cart.service._load_detail", return_value=changed):
            response = self.confirm(action_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["replacement_action"]["quantity"], 3)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_price_change_returns_new_summary_without_mutation(self):
        action_id = self.propose().json()["action_id"]
        changed = copy.deepcopy(PRODUCTS_BY_ID[900001])
        changed["price"] += 100
        changed["availability"] = {
            "status": "available",
            "sellable_quantity": 8,
            "rule_version": "fixture-allowlist-v1",
        }

        with patch("cart.service._load_detail", return_value=changed):
            response = self.confirm(action_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["replacement_action"]["unit_price"],
            format(Decimal(str(changed["price"])), ".2f"),
        )
        self.assertEqual(CartItem.objects.count(), 0)

    def test_price_version_change_returns_new_summary_without_mutation(self):
        action_id = self.propose().json()["action_id"]
        changed = copy.deepcopy(PRODUCTS_BY_ID[900001])
        changed["fixture_version"] = "catalog-fixture-v2"
        changed["availability"] = {
            "status": "available",
            "sellable_quantity": 8,
            "rule_version": "fixture-allowlist-v1",
        }

        with patch("cart.service._load_detail", return_value=changed):
            response = self.confirm(action_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "action_stale")
        self.assertEqual(
            response.json()["replacement_action"]["price_version"],
            "catalog-fixture-v2",
        )
        self.assertEqual(CartItem.objects.count(), 0)

    def test_currency_change_rebinds_empty_cart_before_replacement_confirmation(self):
        action_id = self.propose().json()["action_id"]

        with override_settings(CART_CURRENCY="USD"):
            response = self.confirm(action_id)
            replacement_response = self.confirm(response.json()["replacement_action"]["action_id"])

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "action_stale")
        self.assertEqual(response.json()["replacement_action"]["currency"], "USD")
        self.assertEqual(response.json()["replacement_action"]["expected_cart_version"], 1)
        self.assertEqual(replacement_response.status_code, 200)
        self.assertEqual(replacement_response.json()["cart"]["currency"], "USD")
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_currency_change_is_rejected_for_nonempty_cart(self):
        first = self.propose(dialog_id="dialog-a", message_id="message-a").json()
        self.confirm(first["action_id"])

        with override_settings(CART_CURRENCY="USD"):
            response = self.propose(
                dialog_id="dialog-b",
                message_id="message-b",
                product_id=900005,
                quantity=1,
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "cart_currency_mismatch")
        self.assertEqual(response.json()["cart"]["currency"], "KZT")
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_confirmation_rejects_mismatched_product_and_nonempty_offers(self):
        for suffix, mutate in (
            ("wrong-product", lambda detail: detail.update(id=900005)),
            ("offers", lambda detail: detail.update(offers=[{"id": "offer-1"}])),
        ):
            with self.subTest(case=suffix):
                proposal = self.propose(
                    dialog_id=f"dialog-{suffix}",
                    message_id=f"message-{suffix}",
                    message_version=2,
                ).json()
                changed = copy.deepcopy(PRODUCTS_BY_ID[900001])
                changed["availability"] = {
                    "status": "available",
                    "sellable_quantity": 8,
                    "rule_version": "fixture-allowlist-v1",
                }
                mutate(changed)
                with patch("cart.service._load_detail", return_value=changed):
                    response = self.confirm(proposal["action_id"])
                expected_status = 409 if suffix == "offers" else 503
                expected_code = "action_stale" if suffix == "offers" else "catalog_verification_failed"
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json()["error"]["code"], expected_code)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_catalog_failure_marks_action_failed_and_returns_actual_cart(self):
        action_id = self.propose().json()["action_id"]

        with patch(
            "cart.service._load_detail",
            side_effect=CartApiError(504, "catalog_timeout", "Catalog timed out"),
        ):
            response = self.confirm(action_id)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "catalog_verification_failed")
        self.assertEqual(response.json()["cart"]["items"], [])
        self.assertEqual(CartAction.objects.get(pk=action_id).status, "failed")

    def test_unavailable_and_unknown_products_do_not_create_actions(self):
        cases = ((900002, 1, "product_unavailable"), (900004, 1, "product_unavailable"))
        for index, (product_id, quantity, code) in enumerate(cases, start=1):
            with self.subTest(product_id=product_id):
                response = self.propose(
                    message_id=f"message-{index}",
                    message_version=index,
                    product_id=product_id,
                    quantity=quantity,
                )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["error"]["code"], code)
        self.assertEqual(CartAction.objects.count(), 0)

    def test_initial_shortage_creates_confirmable_replacement(self):
        response = self.propose(quantity=9)

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"]["code"], "insufficient_stock")
        self.assertEqual(body["status"], "expired")
        self.assertEqual(body["maximum_quantity"], 8)
        self.assertEqual(body["replacement_action"]["quantity"], 8)
        self.assertEqual(body["replacement_action"]["status"], "proposed")
        source = CartAction.objects.get(pk=body["action_id"])
        replacement = CartAction.objects.get(pk=body["replacement_action"]["action_id"])
        self.assertEqual(source.status, CartAction.Status.EXPIRED)
        self.assertEqual(source.failure_code, "insufficient_stock")
        self.assertEqual(replacement.replacement_for_id, source.id)

        rejected = self.confirm(source.id)
        first = self.confirm(replacement.id)
        second = self.confirm(replacement.id)

        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["error"]["code"], "action_expired")
        self.assertEqual(rejected.json()["replacement_action"]["action_id"], str(replacement.id))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(CartItem.objects.get().quantity, 8)
        self.assertEqual(CartMutation.objects.count(), 1)

    def test_initial_shortage_retry_returns_same_actions_without_catalog_read(self):
        first = self.propose(quantity=9)

        with patch("cart.service._load_detail", side_effect=AssertionError("must not be called")):
            second = self.propose(quantity=9)

        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["action_id"], first.json()["action_id"])
        self.assertEqual(
            second.json()["replacement_action"]["action_id"],
            first.json()["replacement_action"]["action_id"],
        )
        self.assertEqual(CartAction.objects.count(), 2)

    def test_existing_cart_quantity_reduces_shortage_replacement(self):
        first = self.propose(dialog_id="dialog-a", message_id="message-a", quantity=6).json()
        self.confirm(first["action_id"])

        response = self.propose(dialog_id="dialog-b", message_id="message-b", quantity=3)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["maximum_quantity"], 2)
        self.assertEqual(response.json()["replacement_action"]["quantity"], 2)

    def test_exhausted_stock_creates_no_replacement(self):
        first = self.propose(dialog_id="dialog-a", message_id="message-a", quantity=8).json()
        self.confirm(first["action_id"])

        response = self.propose(dialog_id="dialog-b", message_id="message-b", quantity=1)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["maximum_quantity"], 0)
        self.assertNotIn("replacement_action", response.json())
        source = CartAction.objects.get(pk=response.json()["action_id"])
        self.assertEqual(source.failure_code, "insufficient_stock")

    def test_quantity_payload_rejects_zero_boolean_fraction_and_string(self):
        for index, quantity in enumerate((0, True, 1.5, "2"), start=1):
            with self.subTest(quantity=quantity):
                response = self.propose(message_id=f"invalid-{index}", quantity=quantity)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertEqual(CartAction.objects.count(), 0)

    def test_shared_quantity_rules_cover_unit_minimum_step_multiple_and_maximum(self):
        rules = {
            "unit": "piece",
            "minimum": 3,
            "step": 2,
            "multiple": 3,
            "maximum": 12,
        }
        detail_values = {"pricing_context": {"sales_rules": rules}}

        normalized = _sales_rules(detail_values)
        self.assertEqual(_maximum_valid_quantity(11, normalized), 6)
        _validate_sales_quantity(6, normalized)
        for quantity in (1, 3, 4, 13):
            with self.subTest(quantity=quantity):
                with self.assertRaises(CartApiError):
                    _validate_sales_quantity(quantity, normalized)
        for unsupported in (
            {**rules, "unit": "meter"},
            {**rules, "step": 0},
            {**rules, "minimum": 13},
        ):
            with self.subTest(rules=unsupported):
                with self.assertRaises(CartApiError) as caught:
                    _sales_rules({"pricing_context": {"sales_rules": unsupported}})
                self.assertEqual(caught.exception.code, "unsupported_sales_rules")

    @override_settings(CART_MAX_QUANTITY=3)
    def test_fixture_platform_quantity_limit_is_enforced(self):
        response = self.propose(quantity=4)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "quantity_limit_exceeded")
        self.assertEqual(response.json()["maximum_quantity"], 3)

    def test_recovery_uses_existing_mutation_without_adding_again(self):
        action_id = self.propose().json()["action_id"]
        expected = self.confirm(action_id).json()
        CartAction.objects.filter(pk=action_id).update(status="executing", result={})

        response = self.confirm(action_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertEqual(CartItem.objects.get().quantity, 2)
        self.assertEqual(CartMutation.objects.count(), 1)

    def test_cart_endpoint_is_session_scoped_and_demo_url_resolves(self):
        action_id = self.propose().json()["action_id"]
        self.confirm(action_id)

        own = self.client.get("/api/cart")
        foreign = Client().get("/api/cart")
        demo = self.client.get("/demo/cart/")

        self.assertEqual(own.json()["items"][0]["quantity"], 2)
        self.assertEqual(foreign.json()["items"], [])
        self.assertContains(demo, "DEMO FIXTURE")
        self.assertContains(demo, "Корзина")

    @override_settings(CATALOG_PROVIDER="ekt")
    def test_production_cart_fails_closed_without_cart_contract(self):
        response = self.propose()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "cart_integration_unavailable")
        self.assertEqual(CartAction.objects.count(), 0)

    def test_existing_fixture_proposal_is_not_exposed_after_switch_to_ekt(self):
        self.propose()

        with override_settings(CATALOG_PROVIDER="ekt"):
            response = self.propose()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "cart_integration_unavailable")

    @override_settings(CART_MAX_QUANTITY=10)
    def test_changed_sales_limit_caps_replacement_to_new_valid_quantity(self):
        action_id = self.propose(quantity=8).json()["action_id"]

        with override_settings(CART_MAX_QUANTITY=3):
            response = self.confirm(action_id)

        self.assertEqual(response.status_code, 409)
        replacement = response.json()["replacement_action"]
        self.assertEqual(replacement["quantity"], 3)
        self.assertEqual(replacement["pricing_context"]["sales_rules"]["maximum"], 3)
        self.assertEqual(CartItem.objects.count(), 0)

    def test_failure_reconciliation_returns_latest_cart_snapshot(self):
        successful = self.propose(dialog_id="dialog-a", message_id="message-a").json()
        self.confirm(successful["action_id"])
        failing = self.propose(
            dialog_id="dialog-b",
            message_id="message-b",
            product_id=900005,
            quantity=1,
        ).json()

        with patch(
            "cart.service._load_detail",
            side_effect=CartApiError(504, "catalog_timeout", "Catalog timed out"),
        ):
            response = self.confirm(failing["action_id"])

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["cart"]["version"], 1)
        self.assertEqual(response.json()["cart"]["items"][0]["quantity"], 2)


@override_settings(CATALOG_PROVIDER="fixture", FIXTURE_TIMEOUT_SECONDS=0)
class CartCsrfTests(TestCase):
    def test_json_mutation_requires_matching_csrf_header(self):
        client = Client(enforce_csrf_checks=True)
        payload = {
            "dialog_id": "dialog-1",
            "message_id": "message-1",
            "message_version": 1,
            "product_id": 900001,
            "offer_id": None,
            "quantity": 1,
        }

        rejected = client.post(
            "/api/cart/actions", data=json.dumps(payload), content_type="application/json"
        )
        client.get("/api/cart")
        token = client.cookies["csrftoken"].value
        accepted = client.post(
            "/api/cart/actions",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json()["error"]["code"], "csrf_failed")
        self.assertEqual(accepted.status_code, 201)

    def test_confirmation_endpoints_also_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/api/cart")
        token = client.cookies["csrftoken"].value
        proposal = client.post(
            "/api/cart/actions",
            data=json.dumps(
                {
                    "dialog_id": "dialog-1",
                    "message_id": "message-1",
                    "message_version": 1,
                    "product_id": 900001,
                    "offer_id": None,
                    "quantity": 1,
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        ).json()

        button = client.post(
            f"/api/cart/actions/{proposal['action_id']}/confirm",
            data="{}",
            content_type="application/json",
        )
        text = client.post(
            "/api/cart/actions/confirm-text",
            data=json.dumps({"dialog_id": "dialog-1", "text": "да"}),
            content_type="application/json",
        )

        self.assertEqual(button.status_code, 403)
        self.assertEqual(button.json()["error"]["code"], "csrf_failed")
        self.assertEqual(text.status_code, 403)
        self.assertEqual(text.json()["error"]["code"], "csrf_failed")


@override_settings(CATALOG_PROVIDER="fixture", FIXTURE_TIMEOUT_SECONDS=0)
class CartConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def post_json(self, client, path, payload):
        return client.post(path, data=json.dumps(payload), content_type="application/json")

    def test_two_actions_for_same_cart_cannot_both_mutate_old_version(self):
        client = Client()
        base = {
            "message_version": 1,
            "product_id": 900001,
            "offer_id": None,
            "quantity": 1,
        }
        first = self.post_json(
            client,
            "/api/cart/actions",
            {**base, "dialog_id": "dialog-a", "message_id": "message-a"},
        ).json()
        second = self.post_json(
            client,
            "/api/cart/actions",
            {**base, "dialog_id": "dialog-b", "message_id": "message-b"},
        ).json()
        session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        barrier = Barrier(2)

        def confirm(action_id):
            close_old_connections()
            worker = Client()
            worker.cookies[settings.SESSION_COOKIE_NAME] = session_cookie
            barrier.wait(timeout=5)
            response = self.post_json(worker, f"/api/cart/actions/{action_id}/confirm", {})
            close_old_connections()
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, (first["action_id"], second["action_id"])))

        self.assertEqual(sorted(status for status, _ in results), [200, 409])
        stale = next(body for status, body in results if status == 409)
        self.assertEqual(stale["error"]["code"], "action_stale")
        self.assertEqual(CartItem.objects.get().quantity, 1)
        self.assertEqual(CartMutation.objects.count(), 1)
