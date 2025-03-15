"""
Django production settings for core project.
"""

import os

from .base import *

# Email settings - Amazon SES for production
EMAIL_BACKEND = "django_ses.SESBackend"
AWS_SES_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SES_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SES_REGION_NAME = os.getenv("AWS_SES_REGION_NAME", "us-east-2")
DEFAULT_FROM_EMAIL = "bettingonalaskasite@gmail.com"

# Cache settings - using Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,  # Prevent cache failures from breaking the site
        },
        "KEY_PREFIX": "youtuber_bidding_prod",
        "TIMEOUT": 60 * 60 * 24,  # 24 hours default timeout
    }
}

# Session settings - using Redis
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 1209600  # 2 weeks
