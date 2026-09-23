from __future__ import annotations

import re
from typing import Any


PAYMENT_DATA_MESSAGE = (
    "Платёжные данные нельзя отправлять в чат. Удалите номер карты, CVV и банковские реквизиты."
)
PAYMENT_DATA_REDACTED = "[платёжные данные удалены]"

_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[\s-]?){13,19}(?!\d)")
_CVV_WITH_CONTEXT = re.compile(
    r"(?:cvv|cvc|cvn|security\s*code|код\s+безопасности|код\s+с\s+обратной\s+стороны)"
    r"[^\d]{0,24}(\d{3,4})\b",
    re.IGNORECASE,
)
# Kazakhstan IBANs are 20 characters after the country code and may contain
# letters in the bank/account segments, so do not assume an all-numeric value.
_IBAN = re.compile(r"\bKZ[A-Z0-9][A-Z0-9\s-]{17,21}\b", re.IGNORECASE)
_REQUISITE_CONTEXT = re.compile(
    r"(?:iban|иин|бин|р\s*/\s*с|расч[её]тн(?:ый|ого)?\s+сч[её]т|банковск(?:ие|их)\s+реквизит|"
    r"бик|иик|кбе|кнп|swift(?:\s+code)?|номер\s+сч[её]та|банк(?:овский)?\s+сч[её]т|"
    r"bank\s+account|account\s+number|routing\s+number|sort\s+code|bank\s+details|beneficiary)"
    r"[^\d]{0,48}\d(?:[\d\s-]{5,})",
    re.IGNORECASE,
)
_CARD_CONTEXT = re.compile(
    r"(?:номер\s+карты|карта|card|visa|mastercard|мир|amex)",
    re.IGNORECASE,
)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _luhn(value: str) -> bool:
    checksum = 0
    parity = len(value) % 2
    for index, char in enumerate(value):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def contains_payment_data(value: Any) -> bool:
    """Detect payment credentials without returning or logging their source text."""

    if not isinstance(value, str) or not value:
        return False

    for match in _CARD_CANDIDATE.finditer(value):
        digits = _digits(match.group(0))
        if 13 <= len(digits) <= 19 and (_luhn(digits) or len(digits) >= 15 or _CARD_CONTEXT.search(value)):
            return True
    if _CVV_WITH_CONTEXT.search(value) or _IBAN.search(value) or _REQUISITE_CONTEXT.search(value):
        return True
    return False


def redact_payment_data(value: Any) -> str:
    """Return a safe placeholder for a message that must enter an internal path."""

    text = value if isinstance(value, str) else str(value or "")
    return PAYMENT_DATA_REDACTED if contains_payment_data(text) else text


class PaymentDataDetected(ValueError):
    """Raised before a payment-bearing message can enter session or an LLM request."""
