import html
import re
import secrets
from datetime import date
from decimal import Decimal


def generate_account_number():
    """Generate a unique 12-digit account number starting with ``'10'``.

    The remaining 10 digits are cryptographically random, giving
    approximately 10 billion unique values (10^10).

    Returns:
        str: A 12-character string, e.g. ``'109384726183'``.
    """
    prefix = "10"
    suffix = str(secrets.randbelow(10_000_000_000)).zfill(10)
    return f"{prefix}{suffix}"


def generate_transaction_ref():
    """Generate a unique transaction reference in the format ``LC-YYYYMMDD-XXXXXXXX``.

    The last segment is an 8-character hexadecimal string derived from
    ``secrets.token_hex``.

    Returns:
        str: e.g. ``'LC-20250115-3f8a92c1'``
    """
    today = date.today().strftime("%Y%m%d")
    token = secrets.token_hex(4)  # 8 hex characters
    return f"LC-{today}-{token}"


def mask_account_number(account_number: str) -> str:
    """Return the account number with all but the last 4 digits masked.

    Args:
        account_number: The full account number string.

    Returns:
        str: Masked account number, e.g. ``'************3847'``.

    Raises:
        ValueError: If the account number has fewer than 4 characters.
    """
    if not account_number or len(account_number) < 4:
        raise ValueError("Account number must be at least 4 characters long.")
    mask_length = len(account_number) - 4
    return "*" * mask_length + account_number[-4:]


def format_currency(amount) -> str:
    """Format a numeric amount as a currency string.

    Args:
        amount: A ``Decimal``, ``int``, ``float``, or string representation
                of a monetary value.

    Returns:
        str: Formatted string with dollar sign and two decimal places,
             e.g. ``'$1,234.56'``.
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    # Quantize to two decimal places
    amount = amount.quantize(Decimal("0.01"))
    formatted = f"{amount:,.2f}"
    return f"${formatted}"


def validate_phone_number(phone: str) -> bool:
    """Basic phone number validation.

    Accepts E.164 international format (e.g. ``'+1234567890'``) as well as
    common domestic formats containing digits, spaces, hyphens, parentheses,
    and an optional leading ``+``.

    Args:
        phone: The phone number string to validate.

    Returns:
        bool: ``True`` if the phone number appears valid, ``False`` otherwise.
    """
    if not phone:
        return False
    # Strip whitespace
    phone = phone.strip()
    # Must start with + or a digit, contain 7-15 digits total
    pattern = r"^\+?[\d\s\-().]{7,20}$"
    if not re.match(pattern, phone):
        return False
    # Count only digit characters
    digit_count = sum(c.isdigit() for c in phone)
    return 7 <= digit_count <= 15


def sanitize_input(value: str) -> str:
    """Sanitize a user-supplied string.

    Strips leading/trailing whitespace and escapes HTML entities so the
    value is safe for rendering or storage.

    Args:
        value: Raw user input.

    Returns:
        str: Cleaned and escaped string.
    """
    if not isinstance(value, str):
        value = str(value)
    return html.escape(value.strip())


def get_client_ip(request) -> str:
    """Extract the client's IP address from the request.

    Checks ``X-Forwarded-For`` first (for proxied setups), falling back
    to ``REMOTE_ADDR``.

    Args:
        request: A Django HTTP request object.

    Returns:
        str: The client IP address as a string.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # X-Forwarded-For may contain a comma-separated list; the first
        # entry is the original client IP.
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip
