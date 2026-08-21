"""Operator identification via PIN or badge for backstage surfaces.

Thin policy layer over doorman's generic ``PinCredential``: which staff users may
operate, and resolving/verifying a credential (PIN typed, or badge scanned) for a
given permission. No credential storage lives here — credentials belong to
doorman. Shared across every operational surface (POS/KDS/orders/production).

Modelo de autorização (D1-B, 21/08/2026): **uma identidade só**. Quem prova o PIN
ou passa o crachá vira a sessão (``login``), e é contra essa pessoa que toda
permissão é conferida. O aparelho é reconhecido por confiança de dispositivo
(``backstage.station_trust``), que diz de onde a requisição veio e não concede nada.

Existiu aqui um par ``set_active_operator``/``resolve_active_operator_user`` que
guardava um segundo sujeito num dicionário de sessão, ao lado da conta logada.
Duas identidades significam que sempre há um caminho que pergunta para a errada —
foi assim que o balcão logado como ``admin`` deu chave-mestra a quem chegasse.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from shopman.doorman.models import PinCredential

User = get_user_model()

OPERATE_POS = "cashman.operate_pos"
ADJUST_SHIFT = "cashman.adjust_shift"

def eligible_operators(*, perm: str = OPERATE_POS):
    """Active staff users with a credential who may operate the given surface.

    ``perm`` filters to the surface's permission (default POS). Pass ``None`` for
    every credentialed staff operator (the per-action gate enforces the rest).
    """
    qs = User.objects.filter(is_staff=True, is_active=True, pin_credential__isnull=False)
    if perm:
        qs = qs.filter(
            pk__in=User.objects.with_perm(
                perm,
                is_active=True,
                backend="django.contrib.auth.backends.ModelBackend",
            ).values("pk")
        )
    return qs.order_by("first_name", "username").distinct()


def _eligible(user, perm: str | None) -> bool:
    if user is None or not user.is_active or not user.is_staff:
        return False
    if perm and not user.has_perm(perm):
        return False
    return True


def _verify_with_perm(user, raw_pin: str, perm: str | None) -> bool:
    if not _eligible(user, perm):
        return False
    try:
        cred = user.pin_credential
    except PinCredential.DoesNotExist:
        return False
    return cred.verify(raw_pin)


def verify_operator_pin(user, raw_pin: str, *, required_perm: str | None = OPERATE_POS) -> bool:
    """True if ``user`` is an eligible operator (for ``required_perm``) and the PIN matches."""
    return _verify_with_perm(user, raw_pin, required_perm)


def resolve_operator_by_badge(raw_token: str, *, required_perm: str | None = OPERATE_POS):
    """Resolve the operator whose badge matches, eligible for ``required_perm``, or None.

    The badge is a possession-based alternative to typing the PIN (a barcode on the
    operator's crachá). Eligibility (active/staff/perm) is enforced here.
    """
    user = PinCredential.resolve_by_badge(raw_token)
    return user if _eligible(user, required_perm) else None


def verify_manager_pin(user, raw_pin: str) -> bool:
    """True if ``user`` may authorize overrides (cash-shift adjust) and the PIN matches.

    Used by the anti-fraud override gates (void sent item, discount/price,
    refund/cancel, cash-out/no-sale).
    """
    return _verify_with_perm(user, raw_pin, ADJUST_SHIFT)


# ── PIN self-service (change) + manager reset ────────────────────────────────

MANAGE_OPERATORS = "cashman.manage_operators"


class PinChangeError(ValueError):
    """A self-service PIN change/reset failed, with a stable ``code`` for the UI."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def pin_must_change(user) -> bool:
    """Whether ``user`` was handed a temp PIN and must rotate it before operating."""
    if user is None:
        return False
    try:
        return bool(user.pin_credential.must_change)
    except PinCredential.DoesNotExist:
        return False


def resolve_target_for_pin_change(request, operator_id=None):
    """De quem é o PIN que está sendo trocado: o ``operator_id`` explícito, ou quem está logado.

    O id explícito atende a troca forçada da tela de identificação (PIN temporário
    como "atual"), quando ainda não há ninguém logado. Não é escalada: a troca
    continua exigindo provar o PIN atual daquele operador.
    """
    raw_id = str(operator_id or "").strip()
    if raw_id:
        return User.objects.filter(pk=raw_id, is_active=True, is_staff=True).first()
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return user
    return None


def change_own_pin(user, current_pin: str, new_pin: str) -> None:
    """Prove the current PIN and rotate to a new one (self-service).

    Proving ``current_pin`` *is* the authorization — you can only rotate a PIN you
    already know. A wrong current PIN counts toward lockout (brute-force defense).
    ``set_pin`` clears ``must_change``, so a real rotation satisfies a forced change.
    Raises :class:`PinChangeError` (wrong/locked/no credential) or
    :class:`PinCredentialError` (new PIN violates policy).
    """
    if user is None:
        raise PinChangeError("no_credential", "Operador não identificado.")
    try:
        cred = user.pin_credential
    except PinCredential.DoesNotExist:
        raise PinChangeError(
            "no_credential", "Você ainda não tem um PIN. Peça ao gerente para provisionar."
        ) from None
    if cred.is_locked:
        raise PinChangeError(
            "locked", "PIN bloqueado por tentativas. Aguarde ou peça desbloqueio ao gerente."
        )
    if not cred.verify(current_pin):
        raise PinChangeError("invalid_current", "PIN atual incorreto.")
    # validate_raw (via set_pin) raises PinCredentialError before mutating on policy failure.
    cred.set_pin(new_pin)


def _generate_temp_pin() -> str:
    """A random numeric temp PIN that satisfies the configured minimum length."""
    import secrets

    from shopman.doorman.conf import doorman_settings

    length = max(4, doorman_settings.PIN_MIN_LENGTH)
    return "".join(secrets.choice("0123456789") for _ in range(length))


def reset_operator_pin(target_user, *, temp_pin: str | None = None) -> str:
    """Manager reset: set a temp PIN on ``target_user`` and force a change on first use.

    Returns the temp PIN (generated when not supplied) — shown to the manager once,
    never stored in plaintext. Authorization (``manage_operators``) is the caller's
    responsibility (the API gate). Raises :class:`PinChangeError` on a bad target or
    :class:`PinCredentialError` when a supplied temp PIN violates policy.
    """
    if target_user is None or not getattr(target_user, "is_active", False):
        raise PinChangeError("no_target", "Operador não encontrado.")
    temp = (temp_pin or "").strip() or _generate_temp_pin()
    PinCredential.validate_raw(temp)  # policy check before writing (raises PinCredentialError)
    PinCredential.set_for(target_user, temp, must_change=True)
    return temp
