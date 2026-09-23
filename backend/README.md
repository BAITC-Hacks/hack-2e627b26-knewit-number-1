# Catalog API (Django)

Backend proxy for the EKT product API with a deterministic demo-fixture provider.

## Run locally

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
CATALOG_PROVIDER=fixture .venv/bin/python manage.py runserver 127.0.0.1:8000
```

Routes:

- `GET /api/products?page=1&per_page=20`
- `GET /api/products/detail?id=900001`
- `GET /health`

Both providers expose the same routes. Set `CATALOG_PROVIDER=ekt` and configure
`EKT_API_USERNAME` / `EKT_API_PASSWORD` to proxy the live read-only API.
The live adapter rejects redirects, requires an HTTPS base URL, caps response
size, and applies separate connect/read timeouts. Set `DJANGO_ENV=production`
with a strong `DJANGO_SECRET_KEY` in deployed environments.

## Fixture data

The fixture dataset is deterministic: version `catalog-fixture-v1`, seed
`20260923`, 120 products, 12 analog groups, 10 products in each group. Every
fixture response is marked with `data_source=fixture`; product links and images
are local demo paths.

Availability is calculated for both providers by the same conservative rule.
Only IDs from `SELLABLE_STORE_IDS` (default: `1,2,3`) count as sellable stock.
Known service warehouses such as `Брак` and `перемещение` never count. Positive
stock at an unclassified warehouse produces `availability_unknown`.

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
