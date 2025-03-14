"""
Django development settings for core project.
"""

print("=== LOADING DEV SETTINGS ===")
import logging

import boto3

from .base import *

boto3.set_stream_logger("", logging.DEBUG)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-development-key")

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = os.getenv("DEBUG", "True") == "True"
DEBUG = True
# ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,api").split(",")
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "api",
    "youtuber-bidding-api-api-1",
    "0.0.0.0",
    "*",  # For development only, remove in production
]

# Development-specific apps
INSTALLED_APPS += ["django_celery_beat", "debug_toolbar"]

# Development-specific middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

# Development recaptcha key
RECAPTCHA_SECRET_KEY = "temporary-dev-key"

# CORS settings for development
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://youtuber-bidding-app-app-1:5173",
    "http://172.19.0.2:5173",  # This is the IP we saw in your docker network inspect
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = True  # Changed from False to True for development

# CORS expose and allow headers
CORS_EXPOSE_HEADERS = [
    "Content-Type",
    "X-CSRFToken",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]

# CSRF settings for development
CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_DOMAIN = None
CSRF_USE_SESSIONS = False
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://youtuber-bidding-app-app-1:5173",
    "http://172.19.0.2:5173",
]

# Session settings for development
SESSION_COOKIE_NAME = "sessionid"
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_COOKIE_AGE = 1209600

# Make sure these are defined from base settings before using them
if "AWS_S3_ENDPOINT_URL" in globals() and "AWS_STORAGE_BUCKET_NAME" in globals():
    # S3 media URL construction
    MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"
    print(f"MEDIA_URL set to: {MEDIA_URL}")
else:
    print("WARNING: AWS S3 settings not found, using local media URL")
    MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

# Set a shorter cache timeout to ensure deleted items don't show up for long
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 3,
            "SOCKET_TIMEOUT": 3,
            "IGNORE_EXCEPTIONS": True,
            "MAX_CONNECTIONS": 50,
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "CONNECTION_POOL_KWARGS": {"max_connections": 50},
        },
        "KEY_PREFIX": "youtuber_bid_dev_",
        "TIMEOUT": 30,  # 30 seconds instead of 600
    },
    "fallback": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fallback",
        "TIMEOUT": 30,  # 30 seconds instead of 300
    },
}

# Security settings for development
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = None
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Email settings for development (console backend)
EMAIL_BACKEND = "django_ses.SESBackend"
AWS_SES_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-2")
DEFAULT_FROM_EMAIL = "bettingonalaskasite@gmail.com"

# Debug print S3 settings before using them
print(f"S3 Settings Check - AWS_S3_ENDPOINT_URL: {os.getenv('AWS_S3_ENDPOINT_URL', 'Not set')}")
print(
    f"S3 Settings Check - AWS_STORAGE_BUCKET_NAME: {os.getenv('AWS_STORAGE_BUCKET_NAME', 'Not set')}"
)

# Add logging configuration to see S3 uploads
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "core.storage_backends": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "botocore": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "s3transfer": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# Set this for conditional URL patterns
USE_S3 = True

# added stuff from here on


# Celery settings
CELERY_BROKER_URL = "redis://redis:6379/0"
CELERY_RESULT_BACKEND = "redis://redis:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# Update CSP settings for development
CSP_SCRIPT_SRC += (
    "'unsafe-inline'",
    "'unsafe-eval'",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://backend:8000",
)

CSP_STYLE_SRC += (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

CSP_IMG_SRC += (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "blob:",
)

CSP_CONNECT_SRC += (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "ws://localhost:5173",
    "ws://127.0.0.1:5173",
)

CSP_FONT_SRC += (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

# Debug toolbar settings
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: True,
}

INTERNAL_IPS = ["127.0.0.1", "localhost", "0.0.0.0", "*"]

# Override database settings for development
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "youtuber_bidding_dev",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "db",  # Use the service name from docker-compose
        "PORT": "5432",
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 5,  # Reduced timeout for local connections
        },
    }
}
