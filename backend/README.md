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
- `GET /api/cart`
- `POST /api/cart/actions`
- `POST /api/cart/actions/{action_id}/confirm`
- `POST /api/cart/actions/confirm-text`
- `GET /demo/cart/`
- `GET /health`

Both providers expose the same routes. Set `CATALOG_PROVIDER=ekt` and configure
`EKT_API_USERNAME` / `EKT_API_PASSWORD` to proxy the live read-only API.
The live adapter rejects redirects, requires an HTTPS base URL, caps response
size, and applies separate connect/read timeouts. Set `DJANGO_ENV=production`
with a strong `DJANGO_SECRET_KEY` in deployed environments.

## Full catalog index

Build or refresh the local ID-deduplicated index with:

```bash
cd backend
python manage.py sync_catalog
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

The fixture adapter atomically checks price, availability, and cart version.
When any value changes it expires the old action and returns a replacement
proposal. With `CATALOG_PROVIDER=ekt`, cart proposals and mutations fail closed
until ekt.kz provides a conditional cart API contract; the existing catalog
read routes remain available.

Fixture sales rules are bound into every action: pieces only, minimum/step/
multiple of 1, and a configurable `CART_MAX_QUANTITY` (10,000 by default).
SQLite uses `BEGIN IMMEDIATE` plus bounded lock retries so concurrent demo
requests serialize safely; production deployment should use a database with
real row-level locking before enabling a non-fixture cart adapter.

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
