import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent

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
INSTALLED_APPS = ["django.contrib.staticfiles", "catalog"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

USE_TZ = True
TIME_ZONE = os.environ.get("TZ", "Asia/Almaty")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CATALOG_PROVIDER = os.environ.get("CATALOG_PROVIDER", "fixture").strip().lower()
EKT_API_BASE_URL = os.environ.get("EKT_API_BASE_URL", "https://ekt.kz/api").rstrip("/")
EKT_API_USERNAME = os.environ.get("EKT_API_USERNAME", "")
EKT_API_PASSWORD = os.environ.get("EKT_API_PASSWORD", "")
EKT_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("EKT_CONNECT_TIMEOUT_SECONDS", "1"))
EKT_READ_TIMEOUT_SECONDS = float(os.environ.get("EKT_READ_TIMEOUT_SECONDS", "3"))
EKT_MAX_RETRIES = int(os.environ.get("EKT_MAX_RETRIES", "2"))
EKT_MAX_RESPONSE_BYTES = int(os.environ.get("EKT_MAX_RESPONSE_BYTES", "5000000"))

SELLABLE_STORE_IDS = tuple(
    int(value.strip())
    for value in os.environ.get("SELLABLE_STORE_IDS", "1,2,3").split(",")
    if value.strip()
)
AVAILABILITY_RULE_VERSION = os.environ.get("AVAILABILITY_RULE_VERSION", "fixture-allowlist-v1")
FIXTURE_TIMEOUT_SECONDS = float(os.environ.get("FIXTURE_TIMEOUT_SECONDS", "3.1"))
