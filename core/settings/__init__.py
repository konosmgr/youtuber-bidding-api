"""
Django settings module initialization.
This module selects the appropriate settings based on the DJANGO_ENVIRONMENT environment variable.
"""
import os

# Get environment setting from environment variable, default to 'dev'
environment = os.environ.get('DJANGO_ENVIRONMENT', 'dev')

# Import the appropriate settings
if environment == 'prod':
    from .prod import *
else:
    # Default to dev settings for any non-production environment
    from .dev import *

# Import celery app after settings are loaded to avoid circular imports
try:
    from core.celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery not installed or not configured, continue without it
    __all__ = ()
