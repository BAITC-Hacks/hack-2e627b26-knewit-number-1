from django.conf import settings

from catalog.errors import CatalogConfigurationError
from catalog.providers.ekt import EktCatalogProvider
from catalog.providers.fixture import FixtureCatalogProvider


def get_catalog_provider():
    if settings.CATALOG_PROVIDER == "fixture":
        return FixtureCatalogProvider(
            sellable_store_ids=settings.FIXTURE_SELLABLE_STORE_IDS,
            availability_rule_version=settings.FIXTURE_AVAILABILITY_RULE_VERSION,
            timeout_seconds=settings.FIXTURE_TIMEOUT_SECONDS,
        )
    if settings.CATALOG_PROVIDER == "ekt":
        return EktCatalogProvider(
            base_url=settings.EKT_API_BASE_URL,
            username=settings.EKT_API_USERNAME,
            password=settings.EKT_API_PASSWORD,
            connect_timeout=settings.EKT_CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.EKT_READ_TIMEOUT_SECONDS,
            sellable_store_ids=settings.SELLABLE_STORE_IDS,
            availability_rule_version=settings.AVAILABILITY_RULE_VERSION,
            asset_allowed_hosts=settings.EKT_ASSET_ALLOWED_HOSTS,
            deadline_seconds=settings.EKT_DEADLINE_SECONDS,
            availability_stale_after_seconds=settings.AVAILABILITY_STALE_AFTER_SECONDS,
            max_retries=settings.EKT_MAX_RETRIES,
            retry_jitter_seconds=settings.EKT_RETRY_JITTER_SECONDS,
            max_response_bytes=settings.EKT_MAX_RESPONSE_BYTES,
        )
    raise CatalogConfigurationError(
        f"Unsupported CATALOG_PROVIDER={settings.CATALOG_PROVIDER!r}; expected 'ekt' or 'fixture'"
    )
