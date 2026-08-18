"""Crachá do operador — página Admin canônica (Unfold) para imprimir.

Fecha o buraco que o repasse de hardware apontava: o `issue_badge` existia no doorman
desde o WP-AUTH-2a e não tinha chamador fora dos testes, então na prática o gerente
dependia da CLI com um token que ele mesmo inventava (e que ficava no histórico do
shell). Agora a emissão acontece na tela, o token é sorteado pelo sistema e sai daqui
direto para a impressora.

⚠️ O token vive só nesta requisição. A ação de emitir o guarda na sessão do gerente e
esta view o **retira** ao mostrar (`pop`), então recarregar a página não repete a
credencial — é o mesmo contrato do PIN temporário. Perdeu, emite outro; emitir outro
invalida o anterior, porque o digest é sobrescrito.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from shopman.backstage.projections.operator_badge import build_operator_badge

#: Chave de sessão onde a ação do changelist deixa o token recém-sorteado.
BADGE_SESSION_KEY = "pending_operator_badge"

MANAGE_OPERATORS = "cashman.manage_operators"


class OperatorBadgeView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Crachá do operador"
    permission_required = MANAGE_OPERATORS
    template_name = "admin_console/operator_badge/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pending = self.request.session.pop(BADGE_SESSION_KEY, None) or {}
        token = str(pending.get("token") or "")
        badge = (
            build_operator_badge(
                operator_name=str(pending.get("name") or ""),
                operator_username=str(pending.get("username") or ""),
                token=token,
            )
            if token
            else None
        )
        context.update(
            {
                "badge": badge,
                # Alpine, nunca `onclick` (invariante do projeto). O atributo é montado
                # aqui e não no template porque configuração de controle mora em Python.
                "print_button_attrs": {"@click": "window.print()"},
            }
        )
        return context


def _pin_credential_model_admin():
    from shopman.doorman.models import PinCredential

    return admin.site._registry[PinCredential]


def operator_badge_as_view():
    return OperatorBadgeView.as_view(model_admin=_pin_credential_model_admin())


def operator_badge_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve o ModelAdmin de PinCredential tardiamente (ordem de import do URLConf)."""
    return operator_badge_as_view()(request, *args, **kwargs)
