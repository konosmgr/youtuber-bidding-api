import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from auctions.models import BidAttempt, LoginAttempt


class Command(BaseCommand):
    """
    Management command to clean up old database records.

    This command removes old tracking records (login attempts, bid attempts)
    to prevent database bloat. Run this periodically via cron or scheduled task.
    """

    help = "Cleans up old tracking records to improve database performance"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete records older than this many days",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run in dry-run mode (no actual deletion)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]
        cutoff_date = timezone.now() - timedelta(days=days)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"Running in DRY RUN mode - no records will be deleted")
            )

        self.stdout.write(self.style.NOTICE(f"Deleting records older than {cutoff_date}"))

        # Clean up login attempts
        login_count = LoginAttempt.objects.filter(timestamp__lt=cutoff_date).count()
        self.stdout.write(f"Found {login_count} old login attempts")

        if not dry_run and login_count > 0:
            LoginAttempt.objects.filter(timestamp__lt=cutoff_date).delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {login_count} old login attempts"))

        # Clean up bid attempts
        bid_count = BidAttempt.objects.filter(timestamp__lt=cutoff_date).count()
        self.stdout.write(f"Found {bid_count} old bid attempts")

        if not dry_run and bid_count > 0:
            BidAttempt.objects.filter(timestamp__lt=cutoff_date).delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {bid_count} old bid attempts"))

        self.stdout.write(self.style.SUCCESS(f"Database cleanup completed successfully"))
