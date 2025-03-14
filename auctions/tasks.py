from celery import shared_task
from django.core.management import call_command

@shared_task
def update_auction_winners():
    call_command('update_auction_winners')