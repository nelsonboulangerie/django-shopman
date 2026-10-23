from __future__ import annotations

from shopman.doorman.protocols.identity import IdentityHandle, IdentityView


class CapturingSender:
    """Explicit development-only OTP sink for behavioral tests."""

    reveals_code = True
    last_code = ""

    def send_code(self, target: str, code: str, method: str) -> bool:
        type(self).last_code = code
        return True


class FailingSender:
    """Canal que recusa todo envio: força a cadeia a cair para o seguinte."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        return False


def make_identity_view(
    *,
    subject_id,
    name: str,
    phone=None,
    email=None,
    is_active: bool = True,
) -> IdentityView:
    """Build the explicit multi-handle contract for surface tests."""
    handles = []
    if phone:
        handles.append(IdentityHandle("phone", phone, True, True))
    if email:
        handles.append(IdentityHandle("email", email, True, True))
    return IdentityView(subject_id, name, tuple(handles), is_active)


def grant_recent_step_up(client, customer_uuid, purpose: str) -> None:
    """A marca que o ``POST /account/step-up/`` deixa depois do código no número atual.

    Para os testes que exercitam a troca de contato DEPOIS da cerca. A cerca em si (e o
    caminho real do código) é provada em ``web/test_identity_strength_fences.py``.
    """
    from django.utils import timezone

    from shopman.storefront.api.account import STEP_UP_SESSION_KEY

    session = client.session
    session[STEP_UP_SESSION_KEY] = {
        "customer_uuid": str(customer_uuid),
        "purpose": purpose,
        "accepted_at": timezone.now().isoformat(),
    }
    session.save()
