"""Canonical runtime policy for Pix provider-test mode.

The Efí sandbox confirms only small homologation charges.  This module owns
that temporary product constraint so every surface and mutation applies the
same rule without leaking it into Payman or other payment methods/providers.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from shopman.utils.monetary import format_money

from shopman.shop.adapters import get_adapter

EFI_PIX_ADAPTER_PATH = "shopman.shop.adapters.payment_efi"
PIX_PROVIDER_TEST_MAX_AMOUNT_Q = 1000
PIX_PROVIDER_TEST_ERROR_CODE = "pix_test_amount_limit"
PIX_PROVIDER_TEST_MIXED_ERROR_CODE = "pix_test_mixed_payment_unsupported"


@dataclass(frozen=True)
class PixPaymentConstraint:
    provider: str = "efi"
    environment: str = "sandbox"
    mode: str = "provider_test"
    is_test: bool = True
    max_amount_q: int = PIX_PROVIDER_TEST_MAX_AMOUNT_Q
    max_amount_display: str = "R$ 10,00"
    message: str = (
        "Ambiente de testes: a Efí simula a confirmação de Pix de até R$ 10,00. "
        "Para continuar, troque a forma de pagamento ou ajuste os itens do pedido."
    )

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "environment": self.environment,
            "mode": self.mode,
            "is_test": self.is_test,
            "max_amount_q": self.max_amount_q,
            "max_amount_display": self.max_amount_display,
            "message": self.message,
        }


class PixPaymentPolicyError(ValueError):
    """Stable, structured refusal raised before money/order side effects."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        current_amount_q: int,
        max_amount_q: int = PIX_PROVIDER_TEST_MAX_AMOUNT_Q,
    ) -> None:
        self.code = code
        self.message = message
        self.current_amount_q = int(current_amount_q)
        self.max_amount_q = int(max_amount_q)
        self.context = {
            "method": "pix",
            "provider": "efi",
            "environment": "sandbox",
            "mode": "provider_test",
            "current_amount_q": self.current_amount_q,
            "max_amount_q": self.max_amount_q,
            "actions": ["change_payment_method", "edit_cart"],
        }
        super().__init__(message)


def _adapter_path(adapter) -> str:
    if isinstance(adapter, str):
        return adapter.strip()
    return str(getattr(adapter, "__name__", "") or "").strip()


def _efi_sandbox_enabled() -> bool:
    config = getattr(settings, "SHOPMAN_EFI", {}) or {}
    # Same default as ``payment_efi._base_url``: missing mode is sandbox.  The
    # policy and network destination must never disagree on that boundary.
    return isinstance(config, dict) and config.get("sandbox", True) is True


def pix_payment_constraint(*, adapter=None) -> PixPaymentConstraint | None:
    """Return the constraint only for the *effective* Efí Pix adapter in sandbox.

    When ``adapter`` is omitted, resolution honours ``Shop.integrations`` before
    deploy settings, exactly like payment initiation.  Adapters may pass their
    own ``__name__`` to avoid a redundant registry/DB lookup.
    """
    if adapter is None:
        adapter = get_adapter("payment", method="pix")
    if _adapter_path(adapter) != EFI_PIX_ADAPTER_PATH or not _efi_sandbox_enabled():
        return None
    return PixPaymentConstraint()


def payment_constraints_payload() -> dict:
    constraint = pix_payment_constraint()
    return {"pix": constraint.as_dict()} if constraint is not None else {}


def enforce_pix_test_amount_limit(amount_q: int, *, adapter_path: str | None = None) -> None:
    """Reject an Efí sandbox charge above the homologation ceiling."""
    constraint = pix_payment_constraint(adapter=adapter_path) if adapter_path else pix_payment_constraint()
    amount_q = int(amount_q)
    if constraint is None or amount_q <= constraint.max_amount_q:
        return
    raise PixPaymentPolicyError(
        code=PIX_PROVIDER_TEST_ERROR_CODE,
        current_amount_q=amount_q,
        max_amount_q=constraint.max_amount_q,
        message=(
            "Ambiente de testes: a Efí simula a confirmação de Pix de até "
            f"R$ {format_money(constraint.max_amount_q)}; o total deste pedido é "
            f"R$ {format_money(amount_q)}. Para continuar, troque a forma de "
            "pagamento ou ajuste os itens do pedido."
        ),
    )


def reject_pix_in_mixed_payment(*, current_amount_q: int) -> None:
    """Temporarily reject mixed tenders containing Pix in Efí sandbox."""
    constraint = pix_payment_constraint()
    if constraint is None:
        return
    raise PixPaymentPolicyError(
        code=PIX_PROVIDER_TEST_MIXED_ERROR_CODE,
        current_amount_q=current_amount_q,
        max_amount_q=constraint.max_amount_q,
        message=(
            "Ambiente de testes: Pix Efí ainda não pode ser combinado com outra forma de pagamento. "
            "Use Pix para o total inteiro ou escolha outras formas."
        ),
    )
