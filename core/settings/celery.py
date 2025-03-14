from core.celery import app
from core.celery import app as celery_app

__all__ = ['celery_app', 'app']
#i made this because something is trying to import Celery from the wrong path so this acts as a bridge file to /core/celery.py
