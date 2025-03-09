import os

environment = os.getenv("DJANGO_ENVIRONMENT", "dev")

if environment == "production" or environment == "prod":
    from .prod import *
else:
    from .dev import *
