import os
import sys
from pathlib import Path

# Fault Injection Hook 1: Simulate immediate startup crash
if os.getenv("SIMULATE_STARTUP_CRASH", "false").lower() == "true":
    print("FATAL: SIMULATE_STARTUP_CRASH is enabled in inventory-service!", file=sys.stderr)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-opspilot-inventory-secret-key-12345")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "inventory_app",
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
        "NAME": BASE_DIR / "inventory.sqlite3",
    }
}

# Redis Configuration (Used for stock cache & lock)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
