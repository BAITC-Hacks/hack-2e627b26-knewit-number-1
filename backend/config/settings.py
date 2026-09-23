import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import load_env_file


BASE_DIR = Path(__file__).resolve().parent.parent
# Tests must not accidentally consume developer secrets or target live APIs.
# CI can still provide explicit environment variables when a test needs them.
RUNNING_TESTS = any(
    argument == "test" or argument.endswith(("pytest", "pytest.exe"))
    for argument in sys.argv
)
if not RUNNING_TESTS:
    load_env_file(BASE_DIR / ".env")

DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").strip().lower()
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DJANGO_ENV == "production":
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_ENV=production")
    SECRET_KEY = "fixture-development-only"
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]

ROOT_URLCONF = "config.urls"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "catalog",
    "cart",
    "dialog",
    "gateway",
    "knowledge_base",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "gateway.middleware.ApiGatewayMiddleware",
    "config.observability.ObservabilityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

API_RATE_LIMIT_PER_MINUTE = max(1, int(os.environ.get("API_RATE_LIMIT_PER_MINUTE", "1000")))
API_MAX_BODY_BYTES = max(1024, int(os.environ.get("API_MAX_BODY_BYTES", "262144")))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
        # BEGIN IMMEDIATE serializes fixture cart writes before their first read.
        "OPTIONS": {"timeout": 5, "transaction_mode": "IMMEDIATE"},
    }
}

USE_TZ = True
TIME_ZONE = os.environ.get("TZ", "Asia/Almaty")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = DJANGO_ENV == "production"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = DJANGO_ENV == "production"
CSRF_FAILURE_VIEW = "cart.views.csrf_failure"

CART_ACTION_TTL_SECONDS = min(
    300, max(1, int(os.environ.get("CART_ACTION_TTL_SECONDS", "300")))
)
CART_CURRENCY = "KZT"
CART_URL = "/demo/cart/"
CART_MAX_QUANTITY = max(1, int(os.environ.get("CART_MAX_QUANTITY", "10000")))

# The chat is disabled until a deployment explicitly supplies an OpenAI key and
# model.  Keeping this opt-in prevents a local demo from accidentally sending
# customer messages to an external service.
ASSISTANT_LLM_PROVIDER = os.environ.get("ASSISTANT_LLM_PROVIDER", "disabled").strip().lower()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "").strip()
OPENAI_TIMEOUT_SECONDS = min(30.0, max(1.0, float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "12"))))

CATALOG_PROVIDER = os.environ.get("CATALOG_PROVIDER", "fixture").strip().lower()
CATALOG_DEFAULT_CURRENCY = os.environ.get("CATALOG_DEFAULT_CURRENCY", "KZT").strip() or None
EKT_API_BASE_URL = os.environ.get("EKT_API_BASE_URL", "https://ekt.kz/api").rstrip("/")
EKT_API_USERNAME = os.environ.get("EKT_API_USERNAME", "")
EKT_API_PASSWORD = os.environ.get("EKT_API_PASSWORD", "")
EKT_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("EKT_CONNECT_TIMEOUT_SECONDS", "1"))
EKT_READ_TIMEOUT_SECONDS = float(os.environ.get("EKT_READ_TIMEOUT_SECONDS", "3"))
EKT_DEADLINE_SECONDS = float(os.environ.get("EKT_DEADLINE_SECONDS", "5"))
EKT_MAX_RETRIES = int(os.environ.get("EKT_MAX_RETRIES", "2"))
EKT_RETRY_JITTER_SECONDS = float(os.environ.get("EKT_RETRY_JITTER_SECONDS", "0.1"))
EKT_MAX_RESPONSE_BYTES = int(os.environ.get("EKT_MAX_RESPONSE_BYTES", "5000000"))
EKT_ASSET_ALLOWED_HOSTS = tuple(
    host.strip().casefold()
    for host in os.environ.get("EKT_ASSET_ALLOWED_HOSTS", "ekt.kz").split(",")
    if host.strip()
)

SELLABLE_STORE_IDS = tuple(
    int(value.strip())
    for value in os.environ.get("SELLABLE_STORE_IDS", "").split(",")
    if value.strip()
)
FIXTURE_SELLABLE_STORE_IDS = tuple(
    int(value.strip())
    for value in os.environ.get("FIXTURE_SELLABLE_STORE_IDS", "1,2,3").split(",")
    if value.strip()
)
AVAILABILITY_RULE_VERSION = os.environ.get("AVAILABILITY_RULE_VERSION", "ekt-allowlist-unapproved-v1")
FIXTURE_AVAILABILITY_RULE_VERSION = os.environ.get(
    "FIXTURE_AVAILABILITY_RULE_VERSION", "fixture-allowlist-v1"
)
AVAILABILITY_STALE_AFTER_SECONDS = float(
    os.environ.get("AVAILABILITY_STALE_AFTER_SECONDS", "300")
)
FIXTURE_TIMEOUT_SECONDS = float(os.environ.get("FIXTURE_TIMEOUT_SECONDS", "3.1"))

CATALOG_INDEX_PATH = Path(
    os.environ.get("CATALOG_INDEX_PATH", str(BASE_DIR / "var" / "catalog_index.json"))
)
CATALOG_SYNC_STATUS_PATH = Path(
    os.environ.get("CATALOG_SYNC_STATUS_PATH", str(BASE_DIR / "var" / "catalog_sync_status.json"))
)
CATALOG_SYNC_MAX_PAGES = int(os.environ.get("CATALOG_SYNC_MAX_PAGES", "1000"))
CATALOG_SYNC_PER_PAGE = int(os.environ.get("CATALOG_SYNC_PER_PAGE", "100"))
CATALOG_SYNC_INTERVAL_HOURS = float(os.environ.get("CATALOG_SYNC_INTERVAL_HOURS", "24"))
CATALOG_SYNC_INCLUDE_DETAILS = os.environ.get("CATALOG_SYNC_INCLUDE_DETAILS", "false").lower() in {"1", "true", "yes"}
CATALOG_SEARCH_MAX_RESULTS = max(1, int(os.environ.get("CATALOG_SEARCH_MAX_RESULTS", "5")))

# OpenAI is an optional server-side capability. The deterministic catalog/KB
# path remains available when it is disabled or temporarily unavailable.
OPENAI_ENABLED = os.environ.get("OPENAI_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_API_BASE_URL = os.environ.get(
    "OPENAI_API_BASE_URL", "https://api.openai.com/v1"
).strip().rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-astra").strip()
OPENAI_CONNECT_TIMEOUT_SECONDS = max(
    0.1, float(os.environ.get("OPENAI_CONNECT_TIMEOUT_SECONDS", "1"))
)
OPENAI_READ_TIMEOUT_SECONDS = max(
    0.1, float(os.environ.get("OPENAI_READ_TIMEOUT_SECONDS", "12"))
)
OPENAI_DEADLINE_SECONDS = max(
    1.0, float(os.environ.get("OPENAI_DEADLINE_SECONDS", "20"))
)
OPENAI_MAX_RETRIES = min(2, max(0, int(os.environ.get("OPENAI_MAX_RETRIES", "2"))))
OPENAI_RETRY_JITTER_SECONDS = max(
    0.0, float(os.environ.get("OPENAI_RETRY_JITTER_SECONDS", "0.15"))
)
OPENAI_MAX_OUTPUT_TOKENS = min(
    4000, max(128, int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "900")))
)
OPENAI_MAX_TOOL_ROUNDS = min(
    4, max(1, int(os.environ.get("OPENAI_MAX_TOOL_ROUNDS", "3")))
)
OPENAI_MAX_TOOL_CALLS_PER_ROUND = min(
    8, max(1, int(os.environ.get("OPENAI_MAX_TOOL_CALLS_PER_ROUND", "5")))
)
OPENAI_MAX_CONTEXT_CHARS = min(
    30000, max(2000, int(os.environ.get("OPENAI_MAX_CONTEXT_CHARS", "12000")))
)
OPENAI_MAX_TOOL_OUTPUT_CHARS = min(
    200000, max(4000, int(os.environ.get("OPENAI_MAX_TOOL_OUTPUT_CHARS", "60000")))
)
OPENAI_MAX_RESPONSE_BYTES = min(
    5000000, max(65536, int(os.environ.get("OPENAI_MAX_RESPONSE_BYTES", "1000000")))
)

PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "dialog-rag-v1")
MODEL_VERSION = os.environ.get(
    "MODEL_VERSION", OPENAI_MODEL if OPENAI_ENABLED else "deterministic-rag-v1"
)
CATALOG_INDEX_VERSION = os.environ.get("CATALOG_INDEX_VERSION", "catalog-index-v1")
