# P0 + WIN acceptance matrix

The executable source of truth is [`acceptance/matrix.py`](../acceptance/matrix.py);
the test runner verifies that every AT-001..AT-036 row is present, versioned and
has a result/evidence reference. The sample data is
`acceptance-sample-v1` over `catalog-fixture-v1` with 200 rows and quotas:
40 exact article/ID (20%), 50 name/typo (25%), 60 characteristics (30%), and
50 absence/analogs (25%).

| AT | Requirement → test case | Data/version | Result/evidence |
|---|---|---|---|
| AT-001 | FR-CAT-001,005-006 → exact article/detail | fixture-v1/live-contract | product, freshness, official URL |
| AT-002 | FR-CAT-001 → case-insensitive article | acceptance-sample-v1 | same product identity |
| AT-003 | FR-CAT-002,004 → typo search top-5 | acceptance-sample-v1 | reference in top-5 |
| AT-004 | FR-ALT-001, FR-CART-007 → zero sellable stock | fixture-allowlist-v1 | unavailable, no proposal |
| AT-005 | FR-CART-006-007 → non-allowlisted store | fixture-allowlist-v1 | not sellable |
| AT-006 | FR-ALT-002-006 → compatible analog | lighting-v1 | matches and differences |
| AT-007 | FR-CART-001-004 → intent without confirmation | cart-rules-v1 | proposal only, cart unchanged |
| AT-008 | FR-CART-005-010,013 → explicit action | cart-rules-v1 | one mutation, cart URL |
| AT-009 | FR-CART-009,011 → retry/idempotency | cart-rules-v1 | no duplicate |
| AT-010 | FR-CART-004-006 → changed price | catalog-fixture-v2 | old action expired, replacement |
| AT-011 | FR-CART-007-008,013 → excess quantity | fixture-allowlist-v1 | rejected, valid replacement |
| AT-012 | FR-CAT-005,007 → detail timeout | fixture timeout | controlled non-current response |
| AT-013 | FR-DOC-003-004 → missing certificate | knowledge-base-v1 | missing + manager route |
| AT-014 | AI-9, SEC-5-6 → prompt injection in catalog | untrusted catalog text | instruction ignored |
| AT-015 | FR-CHAT-006, SEC-1-2 → Basic Auth request | secret redaction fixture | secret absent |
| AT-016 | FR-CART-007, API-9 → invalid input | cart validation fixtures | rejected, no side effect |
| AT-017 | FR-KB-001-004 → payment question | knowledge-base-v1 | published answer |
| AT-018 | FR-FILE-003-004 → macro/bad signature | file safety fixtures | safely rejected |
| AT-019 | NFR-13.3 → 320px viewport | viewport-320 | no horizontal overflow |
| AT-020 | NFR-13.4 → keyboard navigation | keyboard-only | focus path available |
| AT-021 | FR-CHAT-002 → second reference | dialog-context-v1 | current context resolved |
| AT-022 | FR-CHAT-003-005 → dialog states | dialog-state-v1 | welcome/error/retry/cancel/clear |
| AT-023 | FR-CAT-003,008 → semantic + cache metadata | acceptance-sample-v1 | top-k + verified_at/age |
| AT-024 | FR-DOC-001-002 → unit extraction | description-trace-v1 | source trace, no unverified conversion |
| AT-025 | FR-ALT-004-005 → missing critical parameter | lighting-v1 | not a full safe replacement |
| AT-026 | RBAC-14.1 → admin boundary | gateway-rbac-v1 | 403/no leak |
| AT-027 | NFR-13.1 → latency/failure metrics | observability-v1 | metrics/evidence exposed |
| AT-028 | FR-CART-004-005,013 → two dialogs/versions | cart-concurrency-v1 | only chosen action, stale rejected |
| AT-029 | FR-CART-005-006,013 → atomic price race | catalog-fixture-v2 | no unverified-price mutation |
| AT-030 | FR-CART-001-004 → price/purchase intent | cart-intent-v1 | answer/proposal only |
| AT-031 | FR-CART-004-005 → ambiguous “да” | cart-ambiguity-v1 | no action executed |
| AT-032 | FR-ALT-003,008 → comparison card | lighting-v1 | fit/matches/differences/live facts |
| AT-033 | FR-KB-001-004 → conflicting delivery thresholds | knowledge-base-v1/conflict | qualified answer + both sources |
| AT-034 | FR-KB-001-004 → missing minimum batch | knowledge-base-v1/missing | no invented number |
| AT-035 | FR-KK-001-005 → Kazakh flow | assistant-localization-v1 | facts preserved, explicit confirmation |
| AT-036 | section 8.7 → live unavailable fallback | fixture-v1 | `DEMO FIXTURE` is explicit |

AT-001..AT-036 are acceptance IDs; `CAT-*`, `CART-*`, and other names in the
machine-readable source are stable evidence references, not replacement IDs.
