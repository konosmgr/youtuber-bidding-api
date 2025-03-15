"""
Django base settings for core project.
Common settings shared across all environments.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "storages",  # For S3 storage
]

LOCAL_APPS = [
    "auctions",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # For admin static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
]

# URLs
ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

# Custom User Model
AUTH_USER_MODEL = "auctions.User"

# Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
    # Custom validators
    {
        "NAME": "auctions.validators.SpecialCharacterValidator",
    },
    {
        "NAME": "auctions.validators.UppercaseValidator",
    },
    {
        "NAME": "auctions.validators.LowercaseValidator",
    },
    {
        "NAME": "auctions.validators.NumberValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
SITE_ID = 1

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Static files - needed for admin
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

# Media files
# Media URL constructed in environment-specific settings
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB"),
        "USER": os.environ.get("POSTGRES_USER"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST"),
        "PORT": os.environ.get("POSTGRES_PORT"),
    }
}

# S3 Storage Configuration
AWS_LOCATION = ""
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL")
AWS_S3_FILE_OVERWRITE = False
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-2")
AWS_DEFAULT_ACL = None
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",
}
AWS_QUERYSTRING_AUTH = False

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "auctions.storage": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "storages": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "boto3": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "botocore": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
    },
}

# REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440  # 2.5 MB
FILE_UPLOAD_PERMISSIONS = 0o644

# Google Auth settings
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

# Frontend URL for email verification links
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Content Security Policy settings
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = (
    "'self'",
    "https://accounts.google.com",
    "https://apis.google.com",
    "https://ssl.gstatic.com",
    "https://*.googleusercontent.com",
    "https://cdnjs.cloudflare.com",
)
CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",
)
CSP_IMG_SRC = (
    "'self'",
    "data:",
    "https://*.s3.amazonaws.com",
    "https://s3.konosmgr.com",  # Allow MinIO images
)
CSP_CONNECT_SRC = (
    "'self'",
    "https://accounts.google.com",
    "https://*.s3.amazonaws.com",
    "https://s3.konosmgr.com",  # Allow MinIO connections
)
CSP_FONT_SRC = (
    "'self'",
    "https://cdnjs.cloudflare.com",
)
CSP_FRAME_SRC = (
    "'self'",
    "https://accounts.google.com",
)
