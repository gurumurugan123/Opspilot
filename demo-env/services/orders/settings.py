import os
import sys
from pathlib import Path

# Fault Injection Hook 1: Simulate immediate startup crash
if os.getenv("SIMULATE_STARTUP_CRASH", "false").lower() == "true":
    print("FATAL: SIMULATE_STARTUP_CRASH is enabled in orders-service!", file=sys.stderr)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-opspilot-orders-secret-key-12345")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "orders_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "urls"
WSGI_APPLICATION = "wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "orders.sqlite3",
    }
}

# Downstream Service URLs (overridable in Kubernetes via ConfigMap)
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8000")
PAYMENTS_SERVICE_URL = os.getenv("PAYMENTS_SERVICE_URL", "http://payments-service:8000")
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT", "3.0"))

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
