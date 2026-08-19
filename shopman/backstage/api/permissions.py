"""Backstage API auth gate.

All backstage endpoints require an authenticated staff user. We rely on
Django's session auth (DRF SessionAuthentication or middleware-set
``request.user``).
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsBackstageOperator(BasePermission):
    """Allow any authenticated staff user."""

    message = "Acesso restrito a operadores."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)


#: Código estável da recusa por estação travada. A superfície REAGE a ele (sobe a
#: tela de identificação) em vez de casar a mensagem em português, que muda com a
#: copy. Sem um código, a tela só sabia "403" — indistinguível de falta de
#: permissão — e seguia desenhando um PDV vazio enquanto toda leitura era negada.
STATION_LOCKED_CODE = "station_locked"


class HasBackstagePermission(BasePermission):
    """Check a specific Django permission code declared on the view.

    The view must define ``required_permission = "backstage.operate_kds"``
    (or similar) — or a tuple of codes, ALL required (e.g. the B.I. cash panel:
    ``("backstage.view_bi", "cashman.audit_shift")``, because apuração de caixa
    é mais restrita que o resto do B.I.). Falls back to staff-only when no
    permission is declared.

    **Opção C (gated by ``SHOPMAN_REQUIRE_ACTIVE_OPERATOR``):** when ON, the device
    session only provides station trust — the permission is checked against the
    ACTIVE OPERATOR (established by PIN/badge), and the action is attributed to
    them (``request.active_operator_user``). No active operator → 403 (locked);
    active operator without the permission → 403 (forbidden). When OFF (default),
    the device session user decides — today's behaviour, unchanged.
    """

    message = "Acesso restrito a operadores."
    code = None

    def has_permission(self, request, view) -> bool:
        self.code = None
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_staff):
            return False
        perm = getattr(view, "required_permission", None)
        perms = _required_codes(perm)

        if not getattr(settings, "SHOPMAN_REQUIRE_ACTIVE_OPERATOR", False):
            # Default / legacy: the authenticated device session decides.
            return all(user.has_perm(code) for code in perms)

        # Opção C: authorize against the operator who unlocked the terminal.
        from shopman.backstage.services.operator import resolve_active_operator_user

        operator = resolve_active_operator_user(request)
        if operator is None:
            self.message = "Estação travada. Identifique-se com PIN ou crachá."
            self.code = STATION_LOCKED_CODE
            return False
        request.active_operator_user = operator
        if not all(operator.has_perm(code) for code in perms):
            self.message = "Operador sem permissão para esta ação."
            return False
        return True


def _required_codes(perm) -> tuple[str, ...]:
    """``None`` → nada exigido; string → uma; tupla/lista → todas."""
    if perm is None:
        return ()
    if isinstance(perm, str):
        return (perm,)
    return tuple(perm)


class CanViewOperatorAlerts(BasePermission):
    """Any operator persona that may see operator alerts.

    Wraps the canonical ``can_view_operator_alerts`` predicate (staff + any
    operator capability) so alert endpoints share the same rule as the sidebar
    badge and the legacy HTMX panel.
    """

    message = "Acesso restrito a operadores."

    def has_permission(self, request, view) -> bool:
        from shopman.backstage.permissions import can_view_operator_alerts

        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and can_view_operator_alerts(user))
