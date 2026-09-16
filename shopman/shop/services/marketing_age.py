"""Age-proof helpers shared by marketing audience and direct deliveries.

The customer birthday is an existing canonical fact.  This module never asks
for or persists additional personal data; it only prevents a specific 18+
self-declaration from overriding a birthday that already proves the customer
is a minor.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone


def is_known_minor(birthday: date | None, *, today: date | None = None) -> bool:
    """Return whether a stored birthday proves the customer is under 18."""

    if birthday is None:
        return False
    today = today or timezone.localdate()
    try:
        adult_cutoff = today.replace(year=today.year - 18)
    except ValueError:  # 29/02: keep the conservative boundary through 01/03.
        adult_cutoff = today.replace(year=today.year - 18, day=28)
    return birthday > adult_cutoff


def is_known_adult(birthday: date | None, *, today: date | None = None) -> bool:
    """Return whether a stored birthday proves the customer is at least 18."""

    return birthday is not None and not is_known_minor(birthday, today=today)


def customer_is_known_minor(customer_ref: str, *, today: date | None = None) -> bool:
    """Check an existing canonical birthday without exposing or copying it.

    Missing customers and birthdays remain unknown, so an alert-specific 18+
    declaration can still be the proof.  Database failures deliberately bubble
    to delivery callers, which must retry instead of sending without the check.
    """

    customer_ref = str(customer_ref or "").strip()
    if not customer_ref:
        return False

    from shopman.guestman.models import Customer

    birthday = (
        Customer.objects.filter(ref=customer_ref)
        .values_list("birthday", flat=True)
        .first()
    )
    return is_known_minor(birthday, today=today)


def canonical_birthday_for_customer_id(customer_id: int | None) -> date | None:
    """Read the current canonical birthday for a final delivery decision.

    Callers deliberately handle database failures as retryable. Returning
    ``None`` is reserved for a missing customer or birthday and therefore can
    never be confused with a successfully proven adult.
    """

    if customer_id is None:
        return None

    from shopman.guestman.models import Customer

    return (
        Customer.objects.filter(pk=customer_id)
        .values_list("birthday", flat=True)
        .first()
    )
