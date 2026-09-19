"""Age-proof helpers shared by marketing audience and direct deliveries.

Two proofs of adulthood, one veto:

- ``Customer.birthday`` (optional, canonical) proves adult when it says so;
- the declaration the person makes when signing in to the store
  (``Customer.metadata["adult_declaration"]``, written by
  ``shop/services/account.record_adult_declaration``) proves adult by itself —
  the store never asks for a birth date to send news;
- a birthday that proves a minor ALWAYS wins over any declaration.

This module never asks for or persists additional personal data.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone

#: Onde a declaração feita no login mora em ``Customer.metadata``.
ADULT_DECLARATION_KEY = "adult_declaration"
#: Versões dos termos da entrada cujo aceite declara maioridade. A versão
#: gravada mora em ``shop/services/account.LOGIN_TERMS_VERSION``; mudou a frase
#: da entrada, sobe a versão lá E acrescenta a nova aqui — quem aceitou a antiga
#: continua declarado, porque o carimbo guarda a versão que a pessoa leu.
ADULT_DECLARING_TERMS_VERSIONS = frozenset({"login-terms-pt-BR-v1"})


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


def declares_adult(metadata) -> bool:
    """Whether ``Customer.metadata`` carries a login declaration of adulthood.

    Only a declaration under a known terms version counts: a stray dict with the
    right key but an unknown (or empty) version proves nothing.
    """

    if not isinstance(metadata, dict):
        return False
    declaration = metadata.get(ADULT_DECLARATION_KEY)
    if not isinstance(declaration, dict):
        return False
    return str(declaration.get("terms_version") or "") in ADULT_DECLARING_TERMS_VERSIONS


def is_proved_adult(
    birthday: date | None, metadata, *, today: date | None = None
) -> bool:
    """Adult by birthday OR by the login declaration; a minor birthday vetoes both."""

    if is_known_minor(birthday, today=today):
        return False
    return is_known_adult(birthday, today=today) or declares_adult(metadata)


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


def canonical_age_evidence_for_customer_id(
    customer_id: int | None,
) -> tuple[date | None, dict]:
    """Read the current birthday AND login declaration for a final delivery decision.

    One query, both proofs. Callers deliberately handle database failures as
    retryable. ``(None, {})`` is reserved for a missing customer (or one with
    neither proof) and therefore can never be confused with a proven adult.
    """

    if customer_id is None:
        return None, {}

    from shopman.guestman.models import Customer

    row = (
        Customer.objects.filter(pk=customer_id)
        .values_list("birthday", "metadata")
        .first()
    )
    if row is None:
        return None, {}
    birthday, metadata = row
    return birthday, metadata if isinstance(metadata, dict) else {}
