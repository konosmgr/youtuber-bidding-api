"""
Django production settings for core project.
"""

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["www.konosmgr.com", "konosmgr.com"]

# Production-specific apps
INSTALLED_APPS += []

# Production-specific middleware
MIDDLEWARE += []

# Wait for PostgreSQL to be available
if os.environ.get("POSTGRES_HOST"):
    import socket
    import time

    postgres_host = os.environ.get("POSTGRES_HOST", "db")
    postgres_port = int(os.environ.get("POSTGRES_PORT", "5432"))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            s.connect((postgres_host, postgres_port))
            s.close()
            break
        except socket.error:
            time.sleep(0.1)

# Production recaptcha key (from environment)
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")

# CORS settings for production
CORS_ALLOWED_ORIGINS = [
    "https://www.konosmgr.com",
    "http://www.konosmgr.com",
    "https://konosmgr.com",
    "http://konosmgr.com",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False

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

# CSRF settings for production
CSRF_COOKIE_NAME = "csrftoken"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_DOMAIN = None
CSRF_USE_SESSIONS = False
CSRF_TRUSTED_ORIGINS = [
    "https://www.konosmgr.com",
    "https://konosmgr.com",
]

# Session settings for production
SESSION_COOKIE_NAME = "sessionid"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 1209600

# Security settings for production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# S3 media URL construction for production
MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"

# Email settings - Amazon SES for production
EMAIL_BACKEND = "django_ses.SESBackend"
AWS_SES_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SES_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SES_REGION_NAME = os.getenv("AWS_SES_REGION_NAME", "us-east-2")
DEFAULT_FROM_EMAIL = "bettingonalaskasite@gmail.com"
