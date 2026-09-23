from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcceptanceCase:
    case_id: str
    requirements: str
    priority: str
    test_data_version: str
    expected_result: str
    evidence: str


_ROWS = (
    ("CAT-001", "FR-CAT-001, FR-CAT-005-006", "P0", "fixture-v1/live-contract", "exact article returns product, freshness status and official URL", "catalog.tests.test_provider_contract"),
    ("CAT-002", "FR-CAT-001", "P0", "acceptance-sample-v1/exact_article_or_id", "case changes do not alter the article match", "acceptance.tests.test_at"),
    ("CAT-003", "FR-CAT-002, FR-CAT-004", "P0", "acceptance-sample-v1/name_or_typo", "reference is in the top-five candidates", "acceptance.tests.test_at"),
    ("CAT-004", "FR-ALT-001, FR-CART-007", "P0", "fixture-allowlist-v1", "zero sellable quantity is not available and cannot be proposed", "catalog.tests.test_api, cart.tests.test_api"),
    ("CAT-005", "FR-CART-006-007", "P0", "fixture-allowlist-v1", "stock outside the allowlist is not sellable", "catalog.tests.test_api"),
    ("ALT-006", "FR-ALT-002-006", "P0", "fixture-v1/lighting-v1", "compatible analog includes matched and different parameters", "catalog.tests.test_api"),
    ("CART-007", "FR-CART-001-004", "P0", "cart-rules-v1", "intent creates a proposal but does not mutate cart", "cart.tests.test_api, acceptance.tests.test_at"),
    ("CART-008", "FR-CART-005-010, FR-CART-013", "P0", "cart-rules-v1", "one explicit action id adds exactly once", "cart.tests.test_api"),
    ("CART-009", "FR-CART-009, FR-CART-011", "P0", "cart-rules-v1", "retry/idempotency does not duplicate item", "cart.tests.test_api"),
    ("CART-010", "FR-CART-004-006", "P0", "catalog-fixture-v2", "price change expires old action and creates replacement", "cart.tests.test_api"),
    ("CART-011", "FR-CART-007-008, FR-CART-013", "P0", "fixture-allowlist-v1", "excess quantity is rejected without mutation", "cart.tests.test_api"),
    ("CAT-012", "FR-CAT-005, FR-CAT-007", "P0", "fixture timeout scenario", "controlled error never claims current price or stock", "catalog.tests.test_api"),
    ("DOC-013", "FR-DOC-003-004", "P0", "knowledge-base-v1", "missing certificate is reported as missing", "knowledge_base.tests.test_engine"),
    ("SEC-014", "AI-9, SEC-5-6", "P0", "untrusted catalog text", "catalog instructions are treated as data", "catalog.tests.test_security"),
    ("SEC-015", "FR-CHAT-006, SEC-1-2", "P0", "secret redaction fixture", "Basic Auth never appears in response/log evidence", "catalog.tests.test_security"),
    ("SEC-016", "FR-CART-007, API-9", "P0", "cart validation fixtures", "invalid ids/quantities/URLs have no side effect", "cart.tests.test_api, catalog.tests.test_security"),
    ("KB-017", "FR-KB-001-004", "P0", "knowledge-base-v1", "published payment answer matches reviewed entry", "knowledge_base.tests.test_engine"),
    ("FILE-018", "FR-FILE-003-004", "P1", "file safety fixtures", "macro or invalid signature is rejected", "dialog.tests.test_attachments"),
    ("UI-019", "NFR-13.3", "P0", "viewport-320", "chat and confirmation fit without horizontal overflow", "frontend/src/App.test.jsx"),
    ("UI-020", "NFR-13.4", "P0", "keyboard-only", "focusable controls have keyboard path", "frontend/src/App.test.jsx"),
    ("CHAT-021", "FR-CHAT-002", "P0", "dialog-context-v1", "second reference resolves in current dialog", "dialog.tests.test_api"),
    ("CHAT-022", "FR-CHAT-003-005", "P0", "dialog-state-v1", "welcome/error/retry/cancel/clear states are observable", "dialog.tests.test_api, frontend/src/App.test.jsx"),
    ("CAT-023", "FR-CAT-003, FR-CAT-008", "P0", "acceptance-sample-v1/characteristic", "semantic match exposes freshness metadata", "catalog.tests.test_api"),
    ("DOC-024", "FR-DOC-001-002", "P0", "description-trace-v1", "unit-bearing value retains source trace", "catalog.tests.test_normalization"),
    ("ALT-025", "FR-ALT-004-005", "P0", "lighting-v1", "unknown critical parameter is not a full safe replacement", "catalog.tests.test_api"),
    ("SEC-026", "RBAC-14.1", "P0", "gateway-rbac-v1", "unauthorized admin call is 403 with no data leak", "gateway.tests.test_api"),
    ("NFR-027", "NFR-13.1", "P0", "observability-v1", "latency/failure metrics are exposed", "catalog.tests.test_api, gateway.tests.test_api"),
    ("CART-028", "FR-CART-004-005, FR-CART-013", "P0", "cart-concurrency-v1", "two actions cannot both mutate stale cart version", "cart.tests.test_api"),
    ("CART-029", "FR-CART-005-006, FR-CART-013", "P0", "catalog-fixture-v2", "atomic stale-price rejection prevents mutation", "cart.tests.test_api"),
    ("CART-030", "FR-CART-001-004", "P0", "cart-intent-v1", "price question and purchase intent do not mutate cart", "cart.tests.test_api, frontend/src/App.test.jsx"),
    ("CART-031", "FR-CART-004-005", "P0", "cart-ambiguity-v1", "ambiguous text confirmation mutates nothing", "cart.tests.test_api"),
    ("ALT-032", "FR-ALT-003, FR-ALT-008", "P0", "lighting-v1", "analog card explains fit, matches, differences, live price/stock", "catalog.tests.test_api, frontend/src/App.test.jsx"),
    ("KB-033", "FR-KB-001-004", "P0", "knowledge-base-v1/conflict", "conflicting delivery thresholds are qualified, not guessed", "knowledge_base.tests.test_engine"),
    ("KB-034", "FR-KB-001-004", "P0", "knowledge-base-v1/missing", "unconfirmed minimum batch is not invented", "knowledge_base.tests.test_engine"),
    ("KK-035", "FR-KK-001-005", "P1/WIN", "assistant-localization-v1", "Kazakh flow preserves factual values and requires explicit confirmation", "assistant.tests.test_localization"),
    ("FALLBACK-036", "section-8.7", "P0 fallback", "fixture-v1", "read-only demo works and visibly identifies DEMO FIXTURE", "acceptance.tests.test_at"),
)


AT_CASES = tuple(
    AcceptanceCase(
        case_id=f"AT-{index:03d}",
        requirements=row[1],
        priority=row[2],
        test_data_version=row[3],
        expected_result=row[4],
        evidence=row[5],
    )
    for index, row in enumerate(_ROWS, start=1)
)
