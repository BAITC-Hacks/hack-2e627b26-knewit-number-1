# Catalog provider contract

`FixtureCatalogProvider` and `EktCatalogProvider` are tested through the same
contract in `catalog/tests/test_provider_contract.py`. Both adapters expose:

- list fields `page`, `per_page`, `count`, `items`, and `data_source`;
- product list identity (`id`, `name`, `article`) and opaque `offers`;
- detail identity, `availability`, `normalized`, `offers`, and `cart_policy`;
- `cart_policy.automatic_add_allowed=false` and
  `requires_explicit_confirmation=true`.

The fixture-specific differences are deliberate: it has `data_source=fixture`,
`fixture_version`, `fixture_seed`, deterministic synthetic IDs and a local demo
image/page. The live adapter has `data_source=ekt`, upstream IDs/values and
allowlisted HTTPS assets; it does not invent fixture metadata. Live availability
can be `availability_unknown` when no approved sellable-store allowlist is
configured. Live network, authentication, timeout and redirect failures are
tested with a transport stub; no real credentials are required to run CI.

The same normalizer and cart guard are applied to both detail responses. A
provider may add upstream fields, but it may not remove the common fields or
turn on automatic cart mutation.
