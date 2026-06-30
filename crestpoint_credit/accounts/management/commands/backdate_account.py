"""
Django management command to backdate a bank account's created_at timestamp.

Usage:
    python manage.py backdate_account --email christina@example.com --date 2025-01-15
    python manage.py backdate_account --email christina@example.com --date 2025-01-15 --dry-run
"""

from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from crestpoint_credit.accounts.models import BankAccount, User


class Command(BaseCommand):
    help = "Backdate a bank account's created_at (and updated_at) to a specific date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="Email of the account owner",
        )
        parser.add_argument(
            "--date",
            type=str,
            required=True,
            help="Target date in YYYY-MM-DD format (e.g., 2025-01-15)",
        )
        parser.add_argument(
            "--account-type",
            type=str,
            default=None,
            help="Filter by account type: savings or current (default: all accounts)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving",
        )

    def handle(self, *args, **options):
        email = options["email"]
        date_str = options["date"]
        account_type = options.get("account_type")
        dry_run = options["dry_run"]

        # Parse date
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.stderr.write(self.style.ERROR(
                f"Invalid date format '{date_str}'. Use YYYY-MM-DD."
            ))
            return

        # Make it timezone-aware
        target_date = timezone.make_aware(target_date)

        # Find user
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User with email '{email}' not found."))
            return

        # Find accounts
        qs = BankAccount.objects.filter(user=user)
        if account_type:
            qs = qs.filter(account_type=account_type.lower())

        accounts = list(qs)
        if not accounts:
            self.stderr.write(self.style.ERROR(
                f"No accounts found for '{email}'"
                + (f" with type '{account_type}'" if account_type else "")
                + "."
            ))
            return

        self.stdout.write(f"User: {email}")
        self.stdout.write(f"Target date: {target_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.stdout.write(f"Accounts to update: {len(accounts)}")
        self.stdout.write("")

        for account in accounts:
            self.stdout.write(
                f"  Account: {account.account_number} "
                f"({account.account_type}) "
                f"| Current created_at: {account.created_at}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - no changes will be saved."))
            return

        # Update accounts
        for account in accounts:
            old_created = account.created_at
            account.created_at = target_date
            if account.updated_at < target_date:
                account.updated_at = target_date
            account.save(update_fields=["created_at", "updated_at"])
            self.stdout.write(self.style.SUCCESS(
                f"  Updated {account.account_number}: "
                f"created_at {old_created} -> {target_date.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            ))

        self.stdout.write(self.style.SUCCESS("\nBackdate complete!"))
