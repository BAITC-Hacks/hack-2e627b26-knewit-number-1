# Catalog API (Django)

Backend proxy for the EKT product API with a deterministic demo-fixture provider.

The verified upstream contract and unresolved integration questions are recorded
in [docs/ekt-api-contract.md](docs/ekt-api-contract.md).

## Run locally

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
CATALOG_PROVIDER=fixture .venv/bin/python manage.py runserver 127.0.0.1:8000
```

Routes:

- `GET /api/products?page=1&per_page=20`
- `GET /api/products/detail?id=900001`
- `GET /api/search?q=автоматический выключатл`
- `GET /api/search/semantic?q=автоматический выключатель 16А`
- `GET /api/cart`
- `GET /api/analogs?id=900001`
- `GET /api/knowledge-base?q=оплата`
- `GET /api/session`
- `GET /api/dialog`
- `POST /api/dialog/messages`
- `POST /api/dialog/messages/{message_id}/retry`
- `POST /api/dialog/cancel`
- `DELETE /api/dialog/history`
- `POST /api/cart/actions`
- `POST /api/cart/actions/{action_id}/confirm`
- `POST /api/cart/actions/confirm-text`
- `POST /api/chat/language`
- `POST /api/chat/messages`
- `GET /demo/cart/`
- `GET /health`
- `GET /ready`
- `GET /metrics`

Both providers expose the same routes. Set `CATALOG_PROVIDER=ekt` and configure
`EKT_API_USERNAME` / `EKT_API_PASSWORD` to proxy the live read-only API.
The live adapter rejects redirects, requires an HTTPS base URL, caps response
size, and applies separate connect/read timeouts. Set `DJANGO_ENV=production`
with a strong `DJANGO_SECRET_KEY` in deployed environments.

Product detail responses keep every original provider field and add a separate
`normalized` object. It contains structured price and availability snapshots,
raw properties plus approved normalized attributes, opaque `offers`, and source
timestamps. When the source omits currency, `CATALOG_DEFAULT_CURRENCY` is used;
missing price, unit, step, and source update time remain `null`.

Provider contract tests are shared by fixture and live adapters; their
intentional differences are documented in
[docs/catalog-provider-contract.md](docs/catalog-provider-contract.md). The
P0+WIN acceptance evidence is versioned in
[docs/acceptance-matrix.md](docs/acceptance-matrix.md). The executable sample
contains 200 requests with the required 20% exact article/ID, 25% name/typo,
30% characteristic, and 25% absence/analog quotas.
## Observability

`/health` is a liveness probe and does not call the upstream catalog. `/ready`
returns HTTP 200 only when the configured provider and local catalog index are
available; otherwise it returns HTTP 503. `/metrics` returns the in-process
counters and latency percentiles (p50/p95/p99), plus the persisted last-sync
status. The HTTP middleware returns `X-Request-ID` and writes structured JSON
events with a hashed session identifier. Passwords, cookies, tokens, request
bodies and file contents are not logged. Cart action and idempotency identifiers
are hashed before logging.

## Full catalog index

Build or refresh the local ID-deduplicated index with:

```bash
cd backend
python manage.py sync_catalog --include-details
```

The command walks pages until an empty page or a repeated page-ID signature.
`CATALOG_SYNC_MAX_PAGES` is a safety guard; reaching it fails the run and does
not replace the last successful index. The persisted files are written under
`backend/var/` by default and are ignored by git:

- `catalog_index.json` — sorted-by-ID product index; upstream order is not used;
- `catalog_sync_status.json` — last successful sync, pages, products, errors,
  duration, stop reason and warnings.

The intended refresh interval is 24 hours (`CATALOG_SYNC_INTERVAL_HOURS=24`).
The command is deliberately scheduler-agnostic: run it from Windows Task
Scheduler, cron, or a container scheduler once per day. Example cron entry:

```cron
0 3 * * * cd /path/to/project/backend && /path/to/venv/bin/python manage.py sync_catalog
```

## Local catalog search

`GET /api/search?q=...` reads the persisted local index and keeps it cached in
memory until the index file changes. Numeric IDs and exact articles are returned
as one `exact` top-1 result. Other queries use case-insensitive partial/fuzzy
matching against product names and return no more than five `fuzzy` candidates.
If the index has not been synchronized yet, the endpoint returns HTTP 503 with
`search_index_unavailable`.

`GET /api/analogs?id=...` applies the approved `lighting-v1` compatibility
matrix for lighting products. It checks purpose, mounting, power, voltage,
color temperature, luminous flux, IP rating and dimensions when those fields
are present. A critical mismatch excludes a candidate; missing values are
reported as unverified in the explanation. Categories without an approved
matrix return `manager_review_required` and do not produce automatic analogs.
Candidates with `sellable_quantity <= 0`, unknown availability or stale stock
are excluded. Remaining candidates are ranked by parameter similarity,
availability and price, and include `ranking`, `comparison` (matched values and
material differences), `sellable_quantity` and a recommendation label.

`GET /api/search/semantic?q=...` additionally reads `description` and
`properties` from an index built with `--include-details`. It separates required
and desired parameters, returns at most five candidates and explains matched or
unconfirmed parameters. Without detail enrichment, semantic results can only
use the list fields that are present in the index.

## Dialog orchestration

The dialog API stores only the current conversation context in the Django
session. `GET /api/dialog` creates a new dialog with a welcome message and
allowed-query examples. `POST /api/dialog/messages` accepts `{ "text": "..." }`
and returns a final `done` or `error` state after processing. References such
as “этот товар”, “второй вариант” and “добавь два” are resolved from the latest
catalog results. A cart proposal may be returned, but the cart is not mutated
until the existing explicit confirmation endpoint is called. `POST
/api/dialog/cancel` marks the current operation cancelled; `DELETE
/api/dialog/history` starts a fresh dialog without touching other session data.

## Knowledge base

`GET /api/knowledge-base?q=...&lang=ru` searches the current knowledge
entries. Only current published `approved` and
`approved_with_qualification` entries can produce a direct answer. `missing`
and `conflicted` entries return a safe qualification and
`manager_required=true`; conflicting source versions are returned for audit,
but the engine never selects one condition. The starter migration contains 11
entries verified on 2026-09-23, including both conflicting minimum-order
versions (15,000 and 30,000 KZT).

## BFF gateway

All `/api/*` routes pass through the gateway. `GET /api/session` identifies the
request as `guest` or `authenticated` using Django authentication without
returning the raw session key. Requests are throttled by source IP and, once a
session exists, by session key. The limit is configured with
`API_RATE_LIMIT_PER_MINUTE`; exceeded requests return HTTP 429 with
`Retry-After`, `X-RateLimit-Limit` and `X-RateLimit-Remaining`. The prototype
limiter is process-local; a multi-instance deployment should move the counter
to shared Redis or another shared rate-limit store. EKT credentials are read
only from backend environment variables and are never accepted from browser
requests.

## Security boundary

Catalog, uploaded-file and web-page values are treated as untrusted data. The
response sanitizer removes executable HTML/Markdown and rejects dangerous,
non-allowlisted URLs; catalog text is never interpreted as an instruction or a
tool command. Cart tools accept only server-validated integer IDs, quantities,
message identifiers and the approved offer contract, and cart mutations remain
protected by CSRF and session ownership checks. Basic Auth is created only by
the server-side EKT adapter and is not returned in errors, logs or responses.

## Fixture data

The fixture dataset is deterministic: version `catalog-fixture-v1`, seed
`20260923`, 120 products, 12 analog groups, 10 products in each group. Every
fixture response is marked with `data_source=fixture`; product links and images
are local demo paths.

Availability is calculated for both providers by the same conservative,
versioned rule. For live EKT data, `SELLABLE_STORE_IDS` is empty by default and
must be approved by the product owner; positive stock without an approved
allowlist produces `availability_unknown`. The fixture uses the separate
`FIXTURE_SELLABLE_STORE_IDS` setting. Known service warehouses such as `Брак`
and `перемещение` never count. An expired snapshot produces `stale`.

## Fixture cart confirmation

Cart state is isolated by the database-backed Django session. Fetch
`GET /api/cart` first to establish the session and CSRF cookie, then send the
cookie value in `X-CSRFToken` for JSON POST requests.

Create a five-minute proposal with:

```json
{
  "dialog_id": "dialog-1",
  "message_id": "message-7",
  "message_version": 1,
  "product_id": 900001,
  "offer_id": null,
  "quantity": 2
}
```

Only the returned `action_id` can confirm that exact snapshot. Replays use the
same server-side idempotency key and return the stored result without adding a
duplicate. Strict text confirmations are limited to `да`, `подтверждаю`, and
`добавить в корзину` when the dialog has exactly one active proposal.

If the requested quantity exceeds the current additional sellable stock, the
proposal endpoint returns `409 insufficient_stock`. The requested action is
stored as expired and, when at least one valid sales increment remains, the
response includes a separately confirmable replacement:

```json
{
  "error": {"code": "insufficient_stock", "message": "..."},
  "action_id": "<expired-source-id>",
  "status": "expired",
  "maximum_quantity": 3,
  "cart": {},
  "replacement_action": {
    "action_id": "<new-id>",
    "status": "proposed",
    "quantity": 3
  }
}
```

Confirm only `replacement_action.action_id`; the source action remains expired.
When no positive quantity satisfies stock and sales rules, `maximum_quantity`
is `0` and `replacement_action` is omitted. Retrying the original request
returns the same source and replacement action IDs without another catalog read.

The fixture adapter atomically checks price, availability, and cart version.
When any value changes it expires the old action and returns a replacement
proposal. With `CATALOG_PROVIDER=ekt`, cart proposals and mutations fail closed
until ekt.kz provides a conditional cart API contract; the existing catalog
read routes remain available.

Cart, action, and live product currency must match at mutation time. An empty
cart can be rebound to a newly configured currency (which increments its
version); a non-empty cart rejects mixed-currency proposals with
`409 cart_currency_mismatch`.

Fixture sales rules are bound into every action: pieces only, minimum/step/
multiple of 1, and a configurable `CART_MAX_QUANTITY` (10,000 by default).
SQLite uses `BEGIN IMMEDIATE` plus bounded lock retries so concurrent demo
requests serialize safely; production deployment should use a database with
real row-level locking before enabling a non-fixture cart adapter.

## Kazakh chat locale

The chat service keeps a locale per browser session and dialog. A client can
set it explicitly with `POST /api/chat/language`:

```json
{"dialog_id":"dialog-1","language":"kk"}
```

Otherwise, the first substantive message chooses Kazakh (`kk`) or Russian
(`ru`). Kazakh need phrases are converted to catalog lookup terms while the
article, brand, and official product name stay unchanged. This is only a query
normalization layer: catalog price, stock, and certificate facts must always be
obtained from the same catalog source for either language.

Changing an established dialog language expires every still-proposed cart
action for that dialog. The response contains a localized, non-confirmable
summary and requires a new cart proposal plus a fresh explicit confirmation.
Kazakh exact confirmations include `иә`, `растаймын`, and `себетке қосыңыз`.

The Responses API adapter is disabled by default. To use it in a deployed
environment, set `ASSISTANT_LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and
`OPENAI_MODEL` in the deployment secret store. The client sends requests only
to the fixed HTTPS OpenAI Responses endpoint, uses `store: false`, and returns
a generic localized availability message instead of a provider error. Static
Kazakh KB entries have a review gate: copy without a named reviewer and review
date is never returned.

Error/data fixtures are selected with either `fixture_case=...` or the
`X-Fixture-Scenario` header:

| Value | Result |
|---|---|
| `unauthorized` | HTTP 401 + `WWW-Authenticate` |
| `not_found` | HTTP 404 |
| `rate_limited` | HTTP 429 + `Retry-After` |
| `server_error` | HTTP 503 |
| `timeout` | configured delay + HTTP 504 |
| `missing_field` | first product misses `name` |
| `null_field` | first product has `price: null` |

Run tests:

```bash
cd backend
.venv/bin/python manage.py test
```
