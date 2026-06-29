"""Payment provider integrations (mock implementations) and payment service layer.

Each mock provider simulates a realistic success/failure rate and processing
delay so the rest of the system can be exercised end-to-end without real
external dependencies.
"""

import logging
import random
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from crestpoint_credit.accounts.models import BankAccount
from crestpoint_credit.core.exceptions import AccountLockedError, InvalidTransferError
from crestpoint_credit.transactions.models import Transaction, TransactionType, TransactionStatus
from crestpoint_credit.transactions.services import reverse_transaction

from .models import Payment, PaymentStatus, PaymentMethod, PaymentProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base Provider
# ---------------------------------------------------------------------------


class BasePaymentProvider:
    """Abstract base class that every payment provider must extend."""

    name: str = ""

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        payment_method: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Process a payment and return a standardised result dict.

        Returns:
            dict with keys:
                - success (bool)
                - provider_id (str)
                - response (dict)
                - error (str | None)
        """
        raise NotImplementedError

    def verify_payment(self, provider_payment_id: str) -> dict:
        """Verify the status of a previously submitted payment."""
        raise NotImplementedError

    def refund_payment(
        self,
        provider_payment_id: str,
        amount: Optional[Decimal] = None,
    ) -> dict:
        """Refund a completed payment (full or partial)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock Providers
# ---------------------------------------------------------------------------


class MockStripeProvider(BasePaymentProvider):
    """Stripe-like mock provider — 80 % success rate."""

    name = "Stripe (Mock)"

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        payment_method: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        time.sleep(0.1)  # simulate processing delay
        provider_id = f"stripe_mock_{uuid.uuid4().hex[:16]}"

        if random.random() < 0.80:
            return {
                "success": True,
                "provider_id": provider_id,
                "response": {
                    "id": provider_id,
                    "object": "payment_intent",
                    "amount": str(int(amount * 100)),  # cents
                    "currency": currency.lower(),
                    "status": "succeeded",
                    "payment_method_types": [payment_method],
                    "created": int(time.time()),
                    "livemode": False,
                    "metadata": metadata or {},
                },
                "error": None,
            }

        return {
            "success": False,
            "provider_id": provider_id,
            "response": {
                "id": provider_id,
                "object": "payment_intent",
                "amount": str(int(amount * 100)),
                "currency": currency.lower(),
                "status": "failed",
                "last_payment_error": {
                    "code": "card_declined",
                    "message": "Your card was declined.",
                },
                "created": int(time.time()),
                "livemode": False,
            },
            "error": "card_declined: Your card was declined.",
        }

    def verify_payment(self, provider_payment_id: str) -> dict:
        time.sleep(0.05)
        return {
            "success": True,
            "provider_id": provider_payment_id,
            "response": {
                "id": provider_payment_id,
                "status": "succeeded",
            },
            "error": None,
        }

    def refund_payment(
        self,
        provider_payment_id: str,
        amount: Optional[Decimal] = None,
    ) -> dict:
        time.sleep(0.1)
        refund_id = f"re_{uuid.uuid4().hex[:16]}"
        return {
            "success": True,
            "provider_id": provider_payment_id,
            "response": {
                "id": refund_id,
                "object": "refund",
                "payment_intent": provider_payment_id,
                "amount": str(int((amount or 0) * 100)),
                "status": "succeeded",
                "created": int(time.time()),
            },
            "error": None,
        }


class MockPaypalProvider(BasePaymentProvider):
    """PayPal-like mock provider — 85 % success rate."""

    name = "PayPal (Mock)"

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        payment_method: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        time.sleep(0.1)
        provider_id = f"paypal_mock_{uuid.uuid4().hex[:16]}"

        if random.random() < 0.85:
            return {
                "success": True,
                "provider_id": provider_id,
                "response": {
                    "id": provider_id,
                    "intent": "CAPTURE",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "amount": {
                                "currency_code": currency.upper(),
                                "value": str(amount),
                            }
                        }
                    ],
                    "create_time": datetime.utcnow().isoformat() + "Z",
                    "metadata": metadata or {},
                },
                "error": None,
            }

        return {
            "success": False,
            "provider_id": provider_id,
            "response": {
                "id": provider_id,
                "intent": "CAPTURE",
                "status": "DECLINED",
                "purchase_units": [
                    {
                        "amount": {
                            "currency_code": currency.upper(),
                            "value": str(amount),
                        }
                    }
                ],
                "create_time": datetime.utcnow().isoformat() + "Z",
            },
            "error": "PAYMENT_DECLINED: The transaction was declined.",
        }

    def verify_payment(self, provider_payment_id: str) -> dict:
        time.sleep(0.05)
        return {
            "success": True,
            "provider_id": provider_payment_id,
            "response": {
                "id": provider_payment_id,
                "status": "COMPLETED",
            },
            "error": None,
        }

    def refund_payment(
        self,
        provider_payment_id: str,
        amount: Optional[Decimal] = None,
    ) -> dict:
        time.sleep(0.1)
        refund_id = f"paypal_refund_{uuid.uuid4().hex[:16]}"
        return {
            "success": True,
            "provider_id": provider_payment_id,
            "response": {
                "id": refund_id,
                "status": "COMPLETED",
                "amount": {
                    "currency_code": "USD",
                    "value": str(amount or 0),
                },
                "links": [
                    {
                        "href": f"https://api-m.paypal.com/v2/payments/captures/{provider_payment_id}/refund",
                        "rel": "self",
                    }
                ],
            },
            "error": None,
        }


class MockBankProvider(BasePaymentProvider):
    """Bank-transfer mock provider — 90 % success rate."""

    name = "Bank (Mock)"

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        payment_method: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        time.sleep(0.1)
        provider_id = f"bank_mock_{uuid.uuid4().hex[:16]}"

        if random.random() < 0.90:
            return {
                "success": True,
                "provider_id": provider_id,
                "response": {
                    "transaction_id": provider_id,
                    "status": "PROCESSED",
                    "amount": str(amount),
                    "currency": currency.upper(),
                    "payment_method": payment_method,
                    "processed_at": datetime.utcnow().isoformat() + "Z",
                    "settled": False,
                    "settlement_date": None,
                    "metadata": metadata or {},
                },
                "error": None,
            }

        return {
            "success": False,
            "provider_id": provider_id,
            "response": {
                "transaction_id": provider_id,
                "status": "REJECTED",
                "amount": str(amount),
                "currency": currency.upper(),
                "payment_method": payment_method,
                "rejection_reason": "INSUFFICIENT_CLEARING_BALANCE",
                "processed_at": datetime.utcnow().isoformat() + "Z",
            },
            "error": "REJECTED: INSUFFICIENT_CLEARING_BALANCE",
        }

    def verify_payment(self, provider_payment_id: str) -> dict:
        time.sleep(0.05)
        return {
            "success": True,
            "provider_id": provider_payment_id,
            "response": {
                "transaction_id": provider_payment_id,
                "status": "PROCESSED",
                "settled": True,
                "settlement_date": datetime.utcnow().isoformat() + "Z",
            },
            "error": None,
        }

    def refund_payment(
        self,
        provider_payment_id: str,
        amount: Optional[Decimal] = None,
    ) -> dict:
        time.sleep(0.1)
        refund_id = f"bank_refund_{uuid.uuid4().hex[:16]}"
        return {
            "success": True,
            "provider_id": provider_payment_id,
            "response": {
                "refund_id": refund_id,
                "original_transaction_id": provider_payment_id,
                "status": "PROCESSED",
                "amount": str(amount or 0),
                "processed_at": datetime.utcnow().isoformat() + "Z",
            },
            "error": None,
        }


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, BasePaymentProvider] = {
    PaymentProvider.STRIPE_MOCK: MockStripeProvider(),
    PaymentProvider.PAYPAL_MOCK: MockPaypalProvider(),
    PaymentProvider.BANK_MOCK: MockBankProvider(),
}


# ---------------------------------------------------------------------------
# Notification helper
# ---------------------------------------------------------------------------


def _send_notification(payment: Payment, event: str = "payment_completed"):
    """Fire-and-forget notification via Celery (if available)."""
    try:
        from core.tasks import send_transaction_notification

        # Payments create their own Transaction record; we can notify via
        # that transaction or directly via a payment notification task.
        send_transaction_notification.delay(payment.reference)
    except (ImportError, Exception):
        logger.warning(
            "Could not enqueue payment notification for %s (%s)",
            payment.reference,
            event,
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_payment_inputs(
    user,
    account: BankAccount,
    amount,
) -> None:
    """Raise if the payment request is invalid."""
    if account.user_id != user.id:
        raise InvalidTransferError(
            "This account does not belong to you."
        )
    if not account.is_active:
        raise InvalidTransferError(
            f"Account {account.account_number} is not active."
        )
    if account.is_frozen:
        raise AccountLockedError(
            f"Account {account.account_number} is frozen and cannot process payments."
        )
    if amount is None or amount <= 0:
        raise InvalidTransferError("Amount must be greater than zero.")


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def initiate_payment(
    user,
    account: BankAccount,
    amount: Decimal,
    payment_method: str,
    provider: str = PaymentProvider.BANK_MOCK,
    metadata: Optional[dict] = None,
) -> Payment:
    """Validate, create, and process a new payment.

    Steps:
        1. Validate inputs (ownership, active, not frozen, amount > 0).
        2. Create a Payment record with status ``initiated``.
        3. Update status to ``processing``.
        4. Delegate to the chosen provider.
        5. On success → ``completed``, create Transaction, notify.
        6. On failure → ``failed``, store error message.
        7. Return the Payment instance.
    """
    _validate_payment_inputs(user, account, amount)

    provider_instance = PROVIDERS.get(provider)
    if provider_instance is None:
        raise InvalidTransferError(f"Unknown payment provider: {provider}")

    payment = Payment.objects.create(
        user=user,
        account=account,
        amount=amount,
        currency=account.currency,
        payment_method=payment_method,
        provider=provider,
        status=PaymentStatus.INITIATED,
        metadata=metadata or {},
    )

    # Move to processing
    payment.status = PaymentStatus.PROCESSING
    payment.save(update_fields=["status", "updated_at"])

    # Call provider
    result = provider_instance.process_payment(
        amount=amount,
        currency=payment.currency,
        payment_method=payment_method,
        metadata=metadata,
    )

    if result["success"]:
        payment.status = PaymentStatus.COMPLETED
        payment.provider_payment_id = result["provider_id"]
        payment.provider_response = result["response"]
        payment.completed_at = timezone.now()
        payment.save(
            update_fields=[
                "status",
                "provider_payment_id",
                "provider_response",
                "completed_at",
                "updated_at",
            ]
        )

        # Create a Transaction record for the payment
        Transaction.objects.create(
            transaction_type=TransactionType.PAYMENT,
            status=TransactionStatus.COMPLETED,
            account=account,
            amount=amount,
            description=f"Payment {payment.reference}",
            balance_before=account.balance,
            balance_after=account.balance,
            metadata={
                "payment_id": str(payment.id),
                "payment_reference": payment.reference,
                "provider": provider,
                "provider_payment_id": result["provider_id"],
            },
        )

        _send_notification(payment, event="payment_completed")
    else:
        payment.status = PaymentStatus.FAILED
        payment.provider_payment_id = result["provider_id"]
        payment.provider_response = result["response"]
        payment.error_message = result["error"] or "Payment failed."
        payment.save(
            update_fields=[
                "status",
                "provider_payment_id",
                "provider_response",
                "error_message",
                "updated_at",
            ]
        )

    return payment


def verify_payment(payment_id: int) -> Payment:
    """Verify an existing payment with its provider.

    Calls the provider's ``verify_payment`` method and updates the local
    Payment status accordingly.

    Returns:
        The updated Payment instance.

    Raises:
        Payment.DoesNotExist: If no payment with *payment_id* exists.
        InvalidTransferError: If the payment is not in a verifiable state.
    """
    try:
        payment = Payment.objects.get(pk=payment_id)
    except Payment.DoesNotExist:
        raise InvalidTransferError("Payment not found.")

    if payment.status not in (
        PaymentStatus.PROCESSING,
        PaymentStatus.COMPLETED,
    ):
        raise InvalidTransferError(
            f"Payment in '{payment.status}' status cannot be verified."
        )

    provider_instance = PROVIDERS.get(payment.provider)
    if provider_instance is None:
        raise InvalidTransferError(
            f"Unknown payment provider: {payment.provider}"
        )

    result = provider_instance.verify_payment(payment.provider_payment_id)

    if result["success"]:
        if payment.status == PaymentStatus.PROCESSING:
            payment.status = PaymentStatus.COMPLETED
            payment.completed_at = timezone.now()
            payment.provider_response = result["response"]
            payment.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "provider_response",
                    "updated_at",
                ]
            )
    else:
        payment.status = PaymentStatus.FAILED
        payment.error_message = result["error"] or "Verification failed."
        payment.provider_response = result["response"]
        payment.save(
            update_fields=[
                "status",
                "error_message",
                "provider_response",
                "updated_at",
            ]
        )

    return payment


def refund_payment(payment_id: int, reason: str = "") -> Payment:
    """Refund a completed payment.

    Steps:
        1. Fetch the Payment (must be ``completed``).
        2. Call the provider's ``refund_payment`` method.
        3. On success → update to ``refunded``, reverse the associated
           Transaction, and trigger a notification.
        4. Return the updated Payment.

    Returns:
        The updated Payment instance.

    Raises:
        Payment.DoesNotExist: If no payment with *payment_id* exists.
        InvalidTransferError: If the payment is not in ``completed`` status.
    """
    try:
        payment = Payment.objects.get(pk=payment_id)
    except Payment.DoesNotExist:
        raise InvalidTransferError("Payment not found.")

    if payment.status != PaymentStatus.COMPLETED:
        raise InvalidTransferError(
            f"Only completed payments can be refunded. Current status: '{payment.status}'."
        )

    provider_instance = PROVIDERS.get(payment.provider)
    if provider_instance is None:
        raise InvalidTransferError(
            f"Unknown payment provider: {payment.provider}"
        )

    result = provider_instance.refund_payment(
        provider_payment_id=payment.provider_payment_id,
        amount=payment.amount,
    )

    if result["success"]:
        payment.status = PaymentStatus.REFUNDED
        payment.completed_at = timezone.now()
        payment.provider_response = {
            **(payment.provider_response or {}),
            "refund": result["response"],
        }
        payment.metadata = {
            **(payment.metadata or {}),
            "refund_reason": reason,
        }
        payment.save(
            update_fields=[
                "status",
                "completed_at",
                "provider_response",
                "metadata",
                "updated_at",
            ]
        )

        # Reverse the associated Transaction
        try:
            txn = Transaction.objects.filter(
                transaction_type=TransactionType.PAYMENT,
                metadata__payment_id=str(payment.id),
                status=TransactionStatus.COMPLETED,
            ).order_by("-created_at").first()

            if txn is not None:
                reverse_transaction(txn, reason=reason or f"Refund for payment {payment.reference}")
        except Exception:
            logger.exception(
                "Failed to reverse transaction for payment %s",
                payment.reference,
            )

        _send_notification(payment, event="payment_refunded")
    else:
        payment.error_message = result["error"] or "Refund failed."
        payment.save(update_fields=["error_message", "updated_at"])

    return payment
