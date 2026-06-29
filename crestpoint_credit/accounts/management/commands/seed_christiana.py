"""
Django management command to seed Christiana Black's account.

Usage:
    python manage.py seed_christiana

Creates:
  - User: Christiana Black (christiana.black@crestpointcredit.com / Black@2024)
  - Savings account with $79,000 balance
  - 6 months of transaction history (Oct 2025 - Mar 2026)
  - A pending withdrawal request for admin to approve/reject
"""

import random
import secrets
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.hashers import make_password

from crestpoint_credit.accounts.models import User, BankAccount
from crestpoint_credit.transactions.models import Transaction, TransactionType, TransactionStatus, WithdrawalRequest, WithdrawalRequestStatus


class Command(BaseCommand):
    help = "Seed Christiana Black account with $79K balance and 6 months of history"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Black@2024",
            help="Password for Christiana's account (default: Black@2024)",
        )

    def handle(self, *args, **options):
        email = "c45562766@gmail.com"
        password = options["password"]

        # ── 1. Create or get user ──
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": "Christiana",
                "last_name": "Black",
                "phone": "+1 (555) 234-8901",
                "is_active": True,
                "is_verified": True,
                "role": "customer",
                "password": make_password(password),
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"  Created user: {email}"))
        else:
            user.first_name = "Christiana"
            user.last_name = "Black"
            user.phone = "+1 (555) 234-8901"
            user.is_verified = True
            user.save()
            self.stdout.write(f"  User already exists: {email}")

        # ── 2. Create or get bank account ──
        account, acc_created = BankAccount.objects.get_or_create(
            user=user,
            account_type="savings",
            defaults={
                "account_number": f"10{secrets.randbelow(10_000_000_000):010d}",
                "balance": Decimal("0.00"),
                "currency": "USD",
                "is_active": True,
                "is_frozen": False,
            },
        )
        if acc_created:
            self.stdout.write(self.style.SUCCESS(f"  Created account: {account.account_number}"))
        else:
            self.stdout.write(f"  Account exists: {account.account_number}")

        # ── 3. Clear old transactions for clean re-run ──
        if Transaction.objects.filter(account=account).exists():
            count = Transaction.objects.filter(account=account).delete()[0]
            self.stdout.write(f"  Cleared {count} existing transactions")

        # ── 4. Generate 6 months of transaction history ──
        now = timezone.now()
        start_date = now.replace(year=2025, month=11, day=1, hour=9, minute=0, second=0, microsecond=0)
        end_date = now.replace(year=2026, month=3, day=31, hour=23, minute=59, second=0, microsecond=0)

        # Transaction templates with realistic descriptions
        deposit_descs = [
            "Salary deposit - monthly payroll",
            "Freelance payment received",
            "Client invoice payment",
            "Consulting fee - Apex Corp",
            "Revenue share deposit",
            "Dividend income",
            "Tax refund",
            "Cashback reward deposit",
            "Refund from merchant",
            "Interest earned",
        ]
        withdrawal_descs = [
            "Rent payment",
            "Electricity bill payment",
            "Grocery store purchase",
            "Restaurant and dining",
            "Gas station fuel",
            "Phone bill payment",
            "Internet service payment",
            "Insurance premium",
            "Gym membership",
            "Subscription service",
            "Online shopping purchase",
            "Medical co-payment",
            "Car maintenance",
            "Home supplies",
        ]

        balance = Decimal("0.00")
        txn_count = 0
        current_date = start_date

        # Generate ~120 transactions over 6 months
        while current_date <= end_date:
            # 2-6 transactions per week
            weekly_txns = random.randint(2, 5)
            for _ in range(weekly_txns):
                if current_date > end_date:
                    break

                is_deposit = random.random() < 0.35  # 35% deposits, 65% withdrawals
                hour = random.randint(8, 20)
                minute = random.randint(0, 59)
                txn_date = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if is_deposit:
                    amount = Decimal(str(round(random.uniform(500, 8500), 2)))
                    desc = random.choice(deposit_descs)
                    txn_type = TransactionType.DEPOSIT
                    status = TransactionStatus.COMPLETED
                    balance += amount
                else:
                    amount = Decimal(str(round(random.uniform(50, 3000), 2)))
                    desc = random.choice(withdrawal_descs)
                    txn_type = TransactionType.WITHDRAWAL
                    status = TransactionStatus.COMPLETED
                    balance -= amount
                    if balance < 0:
                        balance = Decimal("0.00")
                        continue  # Skip if would go negative

                balance_before = balance - (amount if is_deposit else -amount)
                balance_after = balance

                Transaction.objects.create(
                    account=account,
                    transaction_type=txn_type,
                    status=status,
                    amount=amount,
                    description=desc,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    created_at=txn_date,
                    updated_at=txn_date,
                )
                txn_count += 1

            current_date += timedelta(days=random.randint(3, 7))

        # ── 5. Set final balance to $79,000 ──
        account.balance = Decimal("79000.00")
        account.save()
        self.stdout.write(self.style.SUCCESS(f"  Generated {txn_count} transactions (Oct 2025 - Mar 2026)"))
        self.stdout.write(self.style.SUCCESS(f"  Balance set to $79,000.00"))

        # ── 6. Create a PENDING WithdrawalRequest for admin to approve/reject ──
        pending_amount = Decimal("4500.00")
        wr, wr_created = WithdrawalRequest.objects.get_or_create(
            account=account,
            status=WithdrawalRequestStatus.PENDING,
            defaults={
                "amount": pending_amount,
                "description": "Withdrawal to external bank account",
                "bank_name": "Chase Bank",
                "account_number": "****4521",
                "routing_number": "021000021",
            },
        )
        if wr_created:
            self.stdout.write(self.style.WARNING(
                f"  Created PENDING withdrawal request: ${pending_amount} (ref: {wr.reference})"
            ))
        else:
            self.stdout.write(f"  Pending withdrawal request already exists: {wr.reference}")

        # ── 7. Summary ──
        total_deposits = Transaction.objects.filter(
            account=account, transaction_type=TransactionType.DEPOSIT, status=TransactionStatus.COMPLETED
        ).count()
        total_withdrawals = Transaction.objects.filter(
            account=account, transaction_type=TransactionType.WITHDRAWAL, status=TransactionStatus.COMPLETED
        ).count()
        pending_count = Transaction.objects.filter(
            account=account, status=TransactionStatus.PENDING
        ).count()
        wr_pending_count = WithdrawalRequest.objects.filter(
            account=account, status=WithdrawalRequestStatus.PENDING
        ).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("  SEED COMPLETE"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"  Email:              {email}")
        self.stdout.write(f"  Password:           {password}")
        self.stdout.write(f"  Account Number:     {account.account_number}")
        self.stdout.write(f"  Balance:            $79,000.00")
        self.stdout.write(f"  Completed Deposits: {total_deposits}")
        self.stdout.write(f"  Completed Withdrawals: {total_withdrawals}")
        self.stdout.write(f"  Pending Withdrawals:  {pending_count}")
        self.stdout.write(f"  Pending Withdrawal Requests: {wr_pending_count}")
        self.stdout.write("")
        self.stdout.write("  Login with these credentials to see the dashboard.")
        self.stdout.write("  The pending withdrawal request can be approved/rejected by the admin")
        self.stdout.write("  via POST /api/transactions/withdrawal-requests/<id>/review/")