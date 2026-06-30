from datetime import datetime, timedelta
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from crestpoint_credit.accounts.models import BankAccount, User
from crestpoint_credit.transactions.models import Transaction


class Command(BaseCommand):
    help = (
        "Backdate transactions for a given user so that created_at dates are "
        "spread between START_DATE and END_DATE instead of all being now()."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="Email of the user whose transactions should be backdated",
        )
        parser.add_argument(
            "--start",
            type=str,
            default="2025-11-01",
            help="Start date (YYYY-MM-DD). Default: 2025-11-01",
        )
        parser.add_argument(
            "--end",
            type=str,
            default="2026-03-31",
            help="End date (YYYY-MM-DD). Default: 2026-03-31",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving",
        )

    def handle(self, *args, **options):
        email = options["email"]
        start_date = datetime.strptime(options["start"], "%Y-%m-%d")
        end_date = datetime.strptime(options["end"], "%Y-%m-%d")
        dry_run = options["dry_run"]

        # Find user
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User with email '{email}' not found."))
            return

        # Get all account IDs for this user
        account_ids = list(
            BankAccount.objects.filter(user=user).values_list("id", flat=True)
        )
        if not account_ids:
            self.stderr.write(self.style.ERROR(f"No accounts found for user '{email}'."))
            return

        # Get all transactions for these accounts, ordered by PK (creation order)
        transactions = list(
            Transaction.objects.filter(account_id__in=account_ids).order_by("id")
        )

        if not transactions:
            self.stderr.write(self.style.WARNING("No transactions found for this user."))
            return

        # Calculate total seconds in the date range
        total_seconds = (end_date - start_date).total_seconds()
        if total_seconds <= 0:
            self.stderr.write(self.style.ERROR("End date must be after start date."))
            return

        self.stdout.write(
            f"Found {len(transactions)} transaction(s) for {email} "
            f"across {len(account_ids)} account(s)."
        )
        self.stdout.write(f"Date range: {start_date.date()} -> {end_date.date()}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be saved."))

        # Distribute transactions evenly across the date range with random jitter
        updated_count = 0
        for i, txn in enumerate(transactions):
            # Base position: spread evenly, then add random offset within each slot
            slot_size = total_seconds / max(len(transactions), 1)
            base_offset = i * slot_size
            # Add random jitter within the slot (0 to slot_size)
            jitter = random.uniform(0, slot_size)
            offset_seconds = min(base_offset + jitter, total_seconds)

            # Random time of day (8am to 8pm business hours)
            hour = random.randint(8, 19)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)

            new_created_at = start_date + timedelta(seconds=offset_seconds)
            # Replace time with random business hour
            new_created_at = new_created_at.replace(
                hour=hour, minute=minute, second=second, microsecond=random.randint(0, 999999)
            )
            # Make timezone-aware
            new_created_at = timezone.make_aware(new_created_at)

            # updated_at must be >= created_at
            new_updated_at = new_created_at + timedelta(minutes=random.randint(0, 5))

            if dry_run:
                self.stdout.write(
                    f"  TX {txn.id} ({txn.reference}): "
                    f"{txn.created_at} -> {new_created_at}"
                )
            else:
                txn.created_at = new_created_at
                txn.updated_at = new_updated_at
                txn.save(update_fields=["created_at", "updated_at"])

            updated_count += 1

        action = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {updated_count} transaction(s) for '{email}'."
            )
        )
