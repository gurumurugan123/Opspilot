import os
import sys
from pathlib import Path

# Fault Injection Hook 1: Simulate immediate startup crash
if os.getenv("SIMULATE_STARTUP_CRASH", "false").lower() == "true":
    print("FATAL: SIMULATE_STARTUP_CRASH is enabled. Service crashing on launch!", file=sys.stderr)
    sys.exit(1)

# Fault Injection Hook 2: Strictly require DB_PASSWORD if configured
if os.getenv("REQUIRE_DB_PASSWORD", "false").lower() == "true":
    if not os.getenv("DB_PASSWORD"):
        raise KeyError("DB_PASSWORD environment variable is required but missing!")

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-opspilot-payments-secret-key-12345")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "payments_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "urls"

WSGI_APPLICATION = "wsgi.application"

# Database Configuration
DB_HOST = os.getenv("DB_HOST")
if DB_HOST:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "opspilot"),
            "USER": os.getenv("DB_USER", "opspilot"),
            "PASSWORD": os.getenv("DB_PASSWORD", "opspilot_secret"),
            "HOST": DB_HOST,
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    # Local fallback when PostgreSQL is not configured
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "payments.sqlite3",
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
