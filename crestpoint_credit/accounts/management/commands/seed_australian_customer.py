"""
Django management command to seed an Australian customer account.

Usage:
    python manage.py seed_australian_customer
    python manage.py seed_australian_customer --email liam.carter@example.com

Creates:
  - User: Australian customer with client (customer) ACL
  - Savings account with A$532,000.00 balance (AUD currency)
  - Account backdated 18 months from today
  - ~18 months of realistic Australian transaction history up to yesterday
  - Mix of deposits, withdrawals, and transfers
"""

import random
import secrets
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.hashers import make_password

from crestpoint_credit.accounts.models import User, BankAccount
from crestpoint_credit.transactions.models import (
    Transaction,
    TransactionType,
    TransactionStatus,
    WithdrawalRequest,
    WithdrawalRequestStatus,
)


class Command(BaseCommand):
    help = "Seed an Australian customer with A$532K AUD, backdated with transaction history"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="Jaxonhuman0111@gmail.com",
            help="Email for the Australian customer (default: Jaxonhuman0111@gmail.com)",
        )
        parser.add_argument(
            "--password",
            default="White@2024",
            help="Password for the account (default: White@2024)",
        )
        parser.add_argument(
            "--balance",
            default="532000.00",
            help="Starting balance in AUD (default: 532000.00)",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        password = options["password"]
        target_balance = Decimal(options["balance"])

        # ── 1. Create or get user (case-insensitive lookup) ──
        user, created = User.objects.get_or_create(
            email__iexact=email,
            defaults={
                "email": email,
                "first_name": "Kristen",
                "last_name": "Jordan Nagel",
                "phone": "+61 412 345 678",
                "is_active": True,
                "is_verified": True,
                "role": "customer",  # client ACL, NOT admin
                "password": make_password(password),
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"  Created user: {email}"))
        else:
            # Normalize existing user's email to lowercase if needed
            if user.email != email:
                user.email = email
            user.first_name = "Kristen"
            user.last_name = "Jordan Nagel"
            user.phone = "+61 412 345 678"
            user.is_verified = True
            user.role = "customer"
            user.save()
            self.stdout.write(f"  User already exists: {email}")

        # ── 2. Create or get AUD savings account ──
        account, acc_created = BankAccount.objects.get_or_create(
            user=user,
            account_type="savings",
            defaults={
                "account_number": f"38{secrets.randbelow(10_000_000_000):010d}",
                "balance": Decimal("0.00"),
                "currency": "AUD",
                "is_active": True,
                "is_frozen": False,
            },
        )
        if acc_created:
            self.stdout.write(self.style.SUCCESS(f"  Created AUD account: {account.account_number}"))
        else:
            self.stdout.write(f"  Account exists: {account.account_number}")

        # Ensure currency is AUD
        if account.currency != "AUD":
            account.currency = "AUD"
            account.save(update_fields=["currency"])
            self.stdout.write(self.style.WARNING("  Updated account currency to AUD"))

        # ── 3. Backdate account to 18 months ago ──
        now = timezone.now()
        start_date = now - timedelta(days=18 * 30)  # ~18 months back
        start_date = start_date.replace(hour=9, minute=0, second=0, microsecond=0)
        backdate = start_date
        account.created_at = backdate
        account.updated_at = backdate
        account.save(update_fields=["created_at", "updated_at"])
        self.stdout.write(self.style.SUCCESS(f"  Account backdated to: {backdate.strftime('%Y-%m-%d')}"))

        # ── 4. Clear old transactions for clean re-run ──
        if Transaction.objects.filter(account=account).exists():
            count = Transaction.objects.filter(account=account).delete()[0]
            self.stdout.write(f"  Cleared {count} existing transactions")

        # ── 5. Generate ~18 months of Australian transaction history ──
        end_date = now.replace(hour=23, minute=59, second=0, microsecond=0) - timedelta(days=1)  # up to yesterday

        # Australian-specific transaction descriptions
        deposit_descs = [
            "Salary deposit - monthly payroll",
            "Freelance payment - WebDev project",
            "Client invoice - Melbourne Corp",
            "Consulting fee - Sydney Analytics",
            "Revenue share - Q{q} dividend",
            "Tax refund - ATO",
            "Superannuation contribution return",
            "Cashback reward - ANZ",
            "Refund - Amazon AU",
            "Interest earned - savings",
            "Rental income - property",
            "Bitcoin sale proceeds",
            "Invoice payment - TechStart Pty Ltd",
            "Contract payment - Brisbane Dev",
            "GST refund",
        ]
        withdrawal_descs = [
            "Rent payment - apartment",
            "Electricity bill - AGL Energy",
            "Woolworths grocery",
            "Coles supermarket",
            "BP fuel purchase",
            "Telstra phone bill",
            "NBN internet payment",
            "Private health insurance - Bupa",
            "Gym membership - Fitness First",
            "Netflix subscription",
            "Amazon AU purchase",
            "Medical - Medicare co-payment",
            "Car registration - VicRoads",
            "Bunnings home supplies",
            "Uber ride - Melbourne CBD",
            "Coffee - Mr Bake",
            "Restaurant - Chin Chin Melbourne",
            "Airbnb booking - Sydney",
            "Parking - SecurePark",
        ]

        balance = Decimal("0.00")
        txn_count = 0
        current_date = start_date

        # Generate ~150 transactions over 12 months
        while current_date <= end_date:
            weekly_txns = random.randint(2, 5)
            for _ in range(weekly_txns):
                if current_date > end_date:
                    break

                # 38% deposits (higher income to reach 532K), 62% withdrawals
                is_deposit = random.random() < 0.38
                hour = random.randint(8, 21)
                minute = random.randint(0, 59)
                txn_date = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if is_deposit:
                    # Larger deposits: $800 - $25,000 AUD
                    amount = Decimal(str(round(random.uniform(800, 25000), 2)))
                    # Occasionally add a very large deposit to reach 532K
                    if random.random() < 0.08:
                        amount = Decimal(str(round(random.uniform(30000, 80000), 2)))
                    desc = random.choice(deposit_descs).format(q=random.randint(1, 4))
                    txn_type = TransactionType.DEPOSIT
                    txn_status = TransactionStatus.COMPLETED
                    balance += amount
                else:
                    # Withdrawals: $20 - $4,500 AUD
                    amount = Decimal(str(round(random.uniform(20, 4500), 2)))
                    desc = random.choice(withdrawal_descs)
                    txn_type = TransactionType.WITHDRAWAL
                    txn_status = TransactionStatus.COMPLETED
                    balance -= amount
                    if balance < 0:
                        balance = Decimal("0.00")
                        continue  # Skip if would go negative

                balance_before = balance - (amount if is_deposit else -amount)
                balance_after = balance

                Transaction.objects.create(
                    account=account,
                    transaction_type=txn_type,
                    status=txn_status,
                    amount=amount,
                    description=desc,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    created_at=txn_date,
                    updated_at=txn_date,
                )
                txn_count += 1

            current_date += timedelta(days=random.randint(3, 7))

        # ── 6. Set final balance to target ──
        account.balance = target_balance
        account.save()
        self.stdout.write(self.style.SUCCESS(
            f"  Generated {txn_count} transactions ({start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')})"
        ))
        self.stdout.write(self.style.SUCCESS(
            f"  Balance set to A${target_balance:,.2f}"
        ))

        # ── 7. Fix the last transaction's balance_after to match the final balance ──
        last_txn = (
            Transaction.objects.filter(account=account)
            .order_by("created_at")
            .last()
        )
        if last_txn:
            last_txn.balance_after = target_balance
            last_txn.save(update_fields=["balance_after"])

        # ── 8. Create a pending withdrawal request ──
        pending_amount = Decimal("8500.00")
        wr, wr_created = WithdrawalRequest.objects.get_or_create(
            account=account,
            status=WithdrawalRequestStatus.PENDING,
            defaults={
                "amount": pending_amount,
                "description": "Withdrawal to Australian bank account",
                "bank_name": "Commonwealth Bank",
                "account_number": "****7892",
                "routing_number": "062000",
            },
        )
        if wr_created:
            self.stdout.write(self.style.WARNING(
                f"  Created PENDING withdrawal request: A${pending_amount:,.2f} (ref: {wr.reference})"
            ))
        else:
            self.stdout.write(f"  Pending withdrawal request already exists: {wr.reference}")

        # ── 9. Summary ──
        total_deposits = Transaction.objects.filter(
            account=account, transaction_type=TransactionType.DEPOSIT, status=TransactionStatus.COMPLETED
        ).count()
        total_withdrawals = Transaction.objects.filter(
            account=account, transaction_type=TransactionType.WITHDRAWAL, status=TransactionStatus.COMPLETED
        ).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 55))
        self.stdout.write(self.style.SUCCESS("  AUSTRALIAN CUSTOMER SEED COMPLETE"))
        self.stdout.write(self.style.SUCCESS("=" * 55))
        self.stdout.write(f"  Email:               {email}")
        self.stdout.write(f"  Password:            {password}")
        self.stdout.write(f"  Name:                Kristen Jordan Nagel")
        self.stdout.write(f"  Role:                customer (client ACL)")
        self.stdout.write(f"  Account Number:      {account.account_number}")
        self.stdout.write(f"  Currency:            AUD")
        self.stdout.write(f"  Balance:             A${target_balance:,.2f}")
        self.stdout.write(f"  Account Created:    {backdate.strftime('%Y-%m-%d')} (backdated)")
        self.stdout.write(f"  Completed Deposits: {total_deposits}")
        self.stdout.write(f"  Completed Withdrawals: {total_withdrawals}")
        self.stdout.write(f"  Pending Withdrawal:  A${pending_amount:,.2f}")
        self.stdout.write("")
        self.stdout.write("  Login with these credentials to see the AUD dashboard.")
        self.stdout.write("  The pending withdrawal can be approved/rejected by the admin.")
