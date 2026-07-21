"""Django management command to reset daily transfer/withdrawal limits.

Since limits are tracked in Django's cache framework, they auto-reset at
midnight (new date = new cache key). This command forces an immediate reset.

Usage:
    python manage.py reset_transfer_limits                    # reset ALL users
    python manage.py reset_transfer_limits --email user@x.com  # reset one user
    python manage.py reset_transfer_limits --account-id 42     # reset one account
"""

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from crestpoint_credit.accounts.models import User, BankAccount


class Command(BaseCommand):
    help = "Reset daily transfer and withdrawal limits (cache-based)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=None,
            help="Reset limits for a specific user (by email)",
        )
        parser.add_argument(
            "--account-id",
            default=None,
            type=int,
            help="Reset limits for a specific account ID",
        )

    def handle(self, *args, **options):
        today = timezone.now().strftime("%Y-%m-%d")
        accounts = []

        if options["account_id"]:
            try:
                accounts = [BankAccount.objects.get(id=options["account-id"])]
            except BankAccount.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Account {options['account-id']} not found"))
                return
        elif options["email"]:
            email = options["email"].strip().lower()
            accounts = list(
                BankAccount.objects.filter(
                    user__email__iexact=email,
                )
            )
            if not accounts:
                self.stdout.write(self.style.ERROR(f"No accounts found for '{email}'"))
                return
        else:
            accounts = list(BankAccount.objects.all())

        cleared = 0
        for acc in accounts:
            for prefix in ("daily_transfer", "daily_withdrawal"):
                key = f"{prefix}_{acc.id}_{today}"
                if cache.delete(key):
                    cleared += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared {cleared} limit cache entries for {len(accounts)} account(s)"
            )
        )
