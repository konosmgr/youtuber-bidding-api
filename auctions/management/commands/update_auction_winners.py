from django.core.management.base import BaseCommand
from django.utils import timezone
from auctions.models import Item

class Command(BaseCommand):
    help = 'Set winners for ended auctions'

    def handle(self, *args, **options):
        # Find ended auctions with no winner set
        ended_auctions = Item.objects.filter(
            end_date__lt=timezone.now(),
            winner__isnull=True,
            is_active=True
        )
        
        for auction in ended_auctions:
            if auction.bids.exists():
                # Get highest bid
                highest_bid = auction.bids.order_by('-amount').first()
                # Set winner
                auction.winner = highest_bid.user
                auction.save()
                self.stdout.write(f"Winner set for auction #{auction.id}: {auction.winner.email}")
            else:
                self.stdout.write(f"No bids for auction #{auction.id}")