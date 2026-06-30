"""
Django management command to adjust a user's bank account balance to a
target amount by creating a compensating deposit or withdrawal transaction.

Usage:
    python manage.py adjust_balance --email christina@example.com --target 79429.43
    python manage.py adjust_balance --email christina@example.com --target 79429.43 --reason "Balance adjustment"
    python manage.py adjust_balance --email christina@example.com --target 79429.43 --dry-run
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from crestpoint_credit.accounts.models import BankAccount, User
from crestpoint_credit.transactions.models import Transaction
from crestpoint_credit.core.utils import generate_transaction_ref


class Command(BaseCommand):
    help = (
        "Adjust a user's primary bank account balance to a target amount "
        "by creating a compensating deposit or withdrawal transaction."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="Email of the user whose balance should be adjusted",
        )
        parser.add_argument(
            "--target",
            type=str,
            required=True,
            help="Target balance amount (e.g., 79429.43)",
        )
        parser.add_argument(
            "--reason",
            type=str,
            default="System balance adjustment",
            help="Description for the adjustment transaction",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving",
        )

    def handle(self, *args, **options):
        email = options["email"]
        target_amount = Decimal(options["target"])
        reason = options["reason"]
        dry_run = options["dry_run"]

        # Find user
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User with email '{email}' not found."))
            return

        # Get the user's first active, non-frozen account
        account = BankAccount.objects.filter(
            user=user, is_active=True, is_frozen=False
        ).first()

        if not account:
            self.stderr.write(self.style.ERROR(f"No active account found for '{email}'."))
            return

        current_balance = account.balance
        difference = target_amount - current_balance

        self.stdout.write(f"User: {email}")
        self.stdout.write(f"Account: {account.account_number}")
        self.stdout.write(f"Current balance: {current_balance}")
        self.stdout.write(f"Target balance: {target_amount}")
        self.stdout.write(f"Difference: {difference:+.2f}")

        if difference == 0:
            self.stdout.write(self.style.SUCCESS("Balance already at target. No adjustment needed."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be saved."))
            action = "Credit" if difference > 0 else "Debit"
            self.stdout.write(f"Would {action}: {abs(difference):.2f}")
            return

        # Create the adjustment transaction
        if difference > 0:
            # Credit: deposit
            txn_type = "deposit"
            new_balance = current_balance + difference
            desc = f"{reason} (+{difference:.2f})"
        else:
            # Debit: withdrawal
            txn_type = "withdrawal"
            new_balance = current_balance + difference  # difference is negative
            desc = f"{reason} ({difference:.2f})"

        if new_balance < 0:
            self.stderr.write(self.style.ERROR(
                f"Adjustment would result in negative balance ({new_balance}). Aborting."
            ))
            return

        # Create transaction
        txn = Transaction.objects.create(
            account=account,
            transaction_type=txn_type,
            status="completed",
            amount=abs(difference),
            description=desc,
            balance_before=current_balance,
            balance_after=new_balance,
            metadata={"adjustment": True, "reason": reason},
        )

        # Update account balance
        account.balance = new_balance
        account.save(update_fields=["balance", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Adjustment complete!\n"
            f"  Transaction: {txn.reference}\n"
            f"  Type: {txn_type}\n"
            f"  Amount: {abs(difference):.2f}\n"
            f"  New balance: {new_balance:.2f}"
        ))