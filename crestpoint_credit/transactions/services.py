import logging
from datetime import date, datetime

from decimal import Decimal

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import F
from django.core.cache import cache

from crestpoint_credit.accounts.models import BankAccount
from .models import Transaction, TransactionType, TransactionStatus
from crestpoint_credit.core.exceptions import (
    InsufficientFundsError,
    AccountLockedError,
    DailyLimitExceededError,
    TransferLimitExceededError,
    InvalidTransferError,
)
from crestpoint_credit.core.utils import generate_transaction_ref

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache helpers for daily limits
# ---------------------------------------------------------------------------

_CACHE_TTL = 86400  # 24 hours – enough to cover the rest of the day


def _get_daily_key(prefix: str, account_id: int) -> str:
    today = date.today().isoformat()
    return f"{prefix}_{account_id}_{today}"


def _get_daily_total(prefix: str, account_id: int) -> Decimal:
    key = _get_daily_key(prefix, account_id)
    total = cache.get(key, 0)
    return Decimal(str(total))


def _increment_daily_total(prefix: str, account_id: int, amount):
    key = _get_daily_key(prefix, account_id)
    cache.add(key, 0, _CACHE_TTL)
    # Use cache.incr for atomic increment within the cache backend
    try:
        cache.incr(key, float(amount))
    except (ValueError, TypeError):
        # Fallback if the backend doesn't support float incr
        current = cache.get(key, 0)
        cache.set(key, float(current) + float(amount), _CACHE_TTL)


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------

def _send_notification(txn: Transaction):
    """Fire-and-forget notification via Celery (if available)."""
    try:
        from core.tasks import send_transaction_notification

        send_transaction_notification.delay(txn.id)
    except (ImportError, Exception):
        logger.warning(
            "Could not enqueue transaction notification for %s", txn.reference
        )


# ---------------------------------------------------------------------------
# Pre-flight validations (non-atomic, fast checks before locking rows)
# ---------------------------------------------------------------------------

def _validate_amount_positive(amount):
    if amount <= 0:
        raise InvalidTransferError("Amount must be greater than zero.")


def _validate_account_not_frozen(account: BankAccount):
    if getattr(account, "is_frozen", False):
        raise AccountLockedError(
            f"Account {account.account_number} is frozen and cannot process transactions."
        )


def _validate_account_active(account: BankAccount):
    if not getattr(account, "is_active", False):
        raise InvalidTransferError(
            f"Account {account.account_number} is not active."
        )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def execute_deposit(account: BankAccount, amount, description="") -> Transaction:
    """
    Credit *account* with *amount* and record a completed deposit transaction.
    The entire operation is wrapped in a database transaction with row-level
    locking on the BankAccount row.
    """
    _validate_amount_positive(amount)
    _validate_account_not_frozen(account)

    with db_transaction.atomic():
        locked = (
            BankAccount.objects
            .select_for_update()
            .filter(pk=account.pk)
            .first()
        )
        if locked is None:
            raise InvalidTransferError("Account does not exist.")

        balance_before = locked.balance
        locked.balance = F("balance") + amount
        locked.save(update_fields=["balance"])

        # Re-fetch to get the computed value for the snapshot
        locked.refresh_from_db(fields=["balance"])
        balance_after = locked.balance

        txn = Transaction.objects.create(
            transaction_type=TransactionType.DEPOSIT,
            status=TransactionStatus.COMPLETED,
            account=locked,
            amount=amount,
            description=description or "",
            balance_before=balance_before,
            balance_after=balance_after,
        )

    _send_notification(txn)
    return txn


def execute_withdrawal(account: BankAccount, amount, description="") -> Transaction:
    """
    Debit *account* by *amount* and record a completed withdrawal transaction.
    Enforces daily withdrawal limit via the cache layer.
    """
    _validate_amount_positive(amount)
    _validate_account_not_frozen(account)

    # Daily withdrawal limit check (before acquiring DB lock)
    daily_limit = getattr(settings, "DAILY_WITHDRAWAL_LIMIT", None)
    if daily_limit is not None:
        daily_total = _get_daily_total("daily_withdrawal", account.id)
        if daily_total + amount > daily_limit:
            raise DailyLimitExceededError(
                f"Daily withdrawal limit of {daily_limit} would be exceeded."
            )

    with db_transaction.atomic():
        locked = (
            BankAccount.objects
            .select_for_update()
            .filter(pk=account.pk)
            .first()
        )
        if locked is None:
            raise InvalidTransferError("Account does not exist.")

        # Re-validate under lock
        _validate_account_not_frozen(locked)

        balance_before = locked.balance
        if balance_before < amount:
            raise InsufficientFundsError("Insufficient funds for this withdrawal.")

        locked.balance = F("balance") - amount
        locked.save(update_fields=["balance"])

        locked.refresh_from_db(fields=["balance"])
        balance_after = locked.balance

        txn = Transaction.objects.create(
            transaction_type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.COMPLETED,
            account=locked,
            amount=amount,
            description=description or "",
            balance_before=balance_before,
            balance_after=balance_after,
        )

    # Increment daily total only after successful commit
    if daily_limit is not None:
        _increment_daily_total("daily_withdrawal", account.id, amount)

    _send_notification(txn)
    return txn


def execute_transfer(
    sender_account: BankAccount,
    recipient_account_number: str,
    amount,
    description="",
) -> tuple:
    """
    Transfer *amount* from *sender_account* to the account identified by
    *recipient_account_number*.  Returns a ``(sender_txn, recipient_txn)`` tuple.

    The entire debit/credit pair is performed inside a single database
    transaction with row-level locking on **both** accounts (ordered by PK to
    prevent deadlocks).
    """
    _validate_amount_positive(amount)
    _validate_account_not_frozen(sender_account)

    if sender_account.account_number == recipient_account_number:
        raise InvalidTransferError("Cannot transfer to the same account.")

    # Look up recipient
    try:
        recipient_account = BankAccount.objects.get(
            account_number=recipient_account_number
        )
    except BankAccount.DoesNotExist:
        raise InvalidTransferError(
            f"Recipient account {recipient_account_number} does not exist."
        )

    _validate_account_active(recipient_account)
    _validate_account_not_frozen(recipient_account)

    # --- Limit checks (before DB lock) ---
    daily_limit = getattr(settings, "DAILY_TRANSFER_LIMIT", None)
    single_limit = getattr(settings, "SINGLE_TRANSFER_LIMIT", None)

    if daily_limit is not None:
        daily_total = _get_daily_total("daily_transfer", sender_account.id)
        if daily_total + amount > daily_limit:
            raise DailyLimitExceededError(
                f"Daily transfer limit of {daily_limit} would be exceeded."
            )

    if single_limit is not None and amount > single_limit:
        raise TransferLimitExceededError(
            f"Single transfer amount exceeds the limit of {single_limit}."
        )

    # Fraud flag: amount exceeds 50 % of daily limit
    is_flagged = False
    flag_reason = ""
    if daily_limit is not None and amount > (0.5 * daily_limit):
        is_flagged = True
        flag_reason = (
            f"Transaction amount ({amount}) exceeds 50% of daily transfer "
            f"limit ({daily_limit}). Flagged for review."
        )

    # --- Atomic transfer ---
    with db_transaction.atomic():
        # Lock both accounts ordered by PK to prevent deadlocks
        if sender_account.pk <= recipient_account.pk:
            first_pk, second_pk = sender_account.pk, recipient_account.pk
        else:
            first_pk, second_pk = recipient_account.pk, sender_account.pk

        locked_accounts = list(
            BankAccount.objects
            .select_for_update()
            .filter(pk__in=[first_pk, second_pk])
            .order_by("pk")
        )
        locked_map = {acc.pk: acc for acc in locked_accounts}

        sender = locked_map.get(sender_account.pk)
        recipient = locked_map.get(recipient_account.pk)

        if sender is None or recipient is None:
            raise InvalidTransferError("One or both accounts could not be locked.")

        # Re-validate under lock
        _validate_account_not_frozen(sender)
        _validate_account_active(recipient)

        sender_balance_before = sender.balance
        recipient_balance_before = recipient.balance

        if sender.balance < amount:
            raise InsufficientFundsError("Insufficient funds for this transfer.")

        # Debit sender
        sender.balance = F("balance") - amount
        sender.save(update_fields=["balance"])

        # Credit recipient
        recipient.balance = F("balance") + amount
        recipient.save(update_fields=["balance"])

        # Refresh to get computed balances
        sender.refresh_from_db(fields=["balance"])
        recipient.refresh_from_db(fields=["balance"])

        sender_balance_after = sender.balance
        recipient_balance_after = recipient.balance

        # Sender transaction (transfer_out)
        sender_txn = Transaction.objects.create(
            transaction_type=TransactionType.TRANSFER_OUT,
            status=TransactionStatus.COMPLETED,
            account=sender,
            recipient_account=recipient,
            amount=amount,
            description=description or "",
            balance_before=sender_balance_before,
            balance_after=sender_balance_after,
            is_flagged=is_flagged,
            flag_reason=flag_reason,
            metadata={"recipient_account_number": recipient_account_number},
        )

        # Recipient transaction (transfer_in)
        recipient_txn = Transaction.objects.create(
            transaction_type=TransactionType.TRANSFER_IN,
            status=TransactionStatus.COMPLETED,
            account=recipient,
            recipient_account=sender,
            amount=amount,
            description=description or "",
            balance_before=recipient_balance_before,
            balance_after=recipient_balance_after,
            metadata={"sender_account_number": sender_account.account_number},
        )

    # Increment daily total after successful commit
    if daily_limit is not None:
        _increment_daily_total("daily_transfer", sender_account.id, amount)

    # Notifications (fire-and-forget, outside atomic block)
    _send_notification(sender_txn)
    _send_notification(recipient_txn)

    return sender_txn, recipient_txn


def get_transaction_history(account: BankAccount, filters: dict = None):
    """
    Return a QuerySet of transactions for *account*, optionally filtered.
    Supported filter keys:
        - transaction_type
        - status
        - from_date  (datetime / date)
        - to_date    (datetime / date)
        - min_amount (Decimal)
        - max_amount (Decimal)
    """
    qs = Transaction.objects.filter(account=account).order_by("-created_at")

    if filters is None:
        return qs

    transaction_type = filters.get("transaction_type")
    if transaction_type:
        qs = qs.filter(transaction_type=transaction_type)

    status = filters.get("status")
    if status:
        qs = qs.filter(status=status)

    from_date = filters.get("from_date")
    if from_date is not None:
        qs = qs.filter(created_at__date__gte=from_date)

    to_date = filters.get("to_date")
    if to_date is not None:
        qs = qs.filter(created_at__date__lte=to_date)

    min_amount = filters.get("min_amount")
    if min_amount is not None:
        qs = qs.filter(amount__gte=min_amount)

    max_amount = filters.get("max_amount")
    if max_amount is not None:
        qs = qs.filter(amount__lte=max_amount)

    return qs


def reverse_transaction(transaction: Transaction, reason: str = "") -> Transaction:
    """
    Reverse a completed transaction by creating the opposite entry and marking
    the original as ``reversed``.  The entire reversal is atomic.

    Supported original types: deposit, withdrawal, transfer_out.
    """
    if transaction.status != TransactionStatus.COMPLETED:
        raise InvalidTransferError(
            "Only completed transactions can be reversed."
        )

    with db_transaction.atomic():
        # Re-fetch under lock
        txn = (
            Transaction.objects
            .select_for_update()
            .filter(pk=transaction.pk)
            .first()
        )
        if txn is None:
            raise InvalidTransferError("Transaction not found.")
        if txn.status != TransactionStatus.COMPLETED:
            raise InvalidTransferError("Transaction is no longer in completed state.")

        if txn.transaction_type == TransactionType.DEPOSIT:
            # Reverse a deposit → create a withdrawal
            reverse_txn = _create_reverse_withdrawal(txn, reason)

        elif txn.transaction_type == TransactionType.WITHDRAWAL:
            # Reverse a withdrawal → create a deposit
            reverse_txn = _create_reverse_deposit(txn, reason)

        elif txn.transaction_type == TransactionType.TRANSFER_OUT:
            # Reverse a transfer → reverse both sides
            reverse_txn = _create_reverse_transfer(txn, reason)

        else:
            raise InvalidTransferError(
                f"Reversal for transaction type '{txn.transaction_type}' is not supported."
            )

        # Mark original as reversed
        txn.status = TransactionStatus.REVERSED
        txn.metadata = {
            **(txn.metadata or {}),
            "reversal_reason": reason,
            "reversal_transaction_id": reverse_txn.id if reverse_txn else None,
        }
        txn.save(update_fields=["status", "metadata", "updated_at"])

    return txn


# ---------------------------------------------------------------------------
# Reversal helpers (always called inside an atomic block)
# ---------------------------------------------------------------------------

def _create_reverse_withdrawal(original: Transaction, reason: str) -> Transaction:
    """Create a withdrawal that undoes a deposit."""
    account = (
        BankAccount.objects
        .select_for_update()
        .filter(pk=original.account_id)
        .first()
    )
    balance_before = account.balance
    account.balance = F("balance") - original.amount
    account.save(update_fields=["balance"])
    account.refresh_from_db(fields=["balance"])

    return Transaction.objects.create(
        transaction_type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.COMPLETED,
        account=account,
        amount=original.amount,
        description=f"Reversal of deposit {original.reference}. {reason}".strip(),
        balance_before=balance_before,
        balance_after=account.balance,
        metadata={"reversal_of": original.reference},
    )


def _create_reverse_deposit(original: Transaction, reason: str) -> Transaction:
    """Create a deposit that undoes a withdrawal."""
    account = (
        BankAccount.objects
        .select_for_update()
        .filter(pk=original.account_id)
        .first()
    )
    balance_before = account.balance
    account.balance = F("balance") + original.amount
    account.save(update_fields=["balance"])
    account.refresh_from_db(fields=["balance"])

    return Transaction.objects.create(
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        account=account,
        amount=original.amount,
        description=f"Reversal of withdrawal {original.reference}. {reason}".strip(),
        balance_before=balance_before,
        balance_after=account.balance,
        metadata={"reversal_of": original.reference},
    )


def _create_reverse_transfer(original: Transaction, reason: str) -> Transaction:
    """Reverse both sides of a transfer_out transaction."""
    sender = (
        BankAccount.objects
        .select_for_update()
        .filter(pk=original.account_id)
        .first()
    )
    recipient = (
        BankAccount.objects
        .select_for_update()
        .filter(pk=original.recipient_account_id)
        .first()
    )

    # Credit the original sender back
    sender_balance_before = sender.balance
    sender.balance = F("balance") + original.amount
    sender.save(update_fields=["balance"])

    # Debit the original recipient
    recipient_balance_before = recipient.balance
    recipient.balance = F("balance") - original.amount
    recipient.save(update_fields=["balance"])

    sender.refresh_from_db(fields=["balance"])
    recipient.refresh_from_db(fields=["balance"])

    # Sender gets a transfer_in (reversal credit)
    sender_reverse = Transaction.objects.create(
        transaction_type=TransactionType.TRANSFER_IN,
        status=TransactionStatus.COMPLETED,
        account=sender,
        recipient_account=recipient,
        amount=original.amount,
        description=(
            f"Reversal of transfer {original.reference}. {reason}"
        ).strip(),
        balance_before=sender_balance_before,
        balance_after=sender.balance,
        metadata={"reversal_of": original.reference},
    )

    # Recipient gets a transfer_out (reversal debit)
    recipient_reverse = Transaction.objects.create(
        transaction_type=TransactionType.TRANSFER_OUT,
        status=TransactionStatus.COMPLETED,
        account=recipient,
        recipient_account=sender,
        amount=original.amount,
        description=(
            f"Reversal of transfer {original.reference}. {reason}"
        ).strip(),
        balance_before=recipient_balance_before,
        balance_after=recipient.balance,
        metadata={"reversal_of": original.reference},
    )

    return sender_reverse
