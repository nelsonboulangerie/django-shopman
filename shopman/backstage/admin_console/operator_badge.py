"""Crachá do operador — página Admin canônica (Unfold) para imprimir.

Fecha o buraco que o repasse de hardware apontava: o `issue_badge` existia no doorman
desde o WP-AUTH-2a e não tinha chamador fora dos testes, então na prática o gerente
dependia da CLI com um token que ele mesmo inventava (e que ficava no histórico do
shell). Agora a emissão acontece na tela, o token é sorteado pelo sistema e sai daqui
direto para a impressora.

REEXIBIR NÃO É REEMITIR — e a diferença é a razão desta página existir como está.

O token vivia só na primeira requisição (`pop` ao mostrar). A intenção era boa e a
consequência era ruim: se a impressão falhasse — papel acabou, impressora offline,
aba fechada sem querer — o crachá **já estava emitido** e o código **já se perdera**.
O crachá antigo tinha morrido e o novo não existia em papel. Numa padaria em hora de
pico, isso é uma pessoa sem conseguir entrar no PDV.

Agora o token fica na sessão por ``JANELA_DE_REIMPRESSAO`` e a página pode ser
recarregada dentro dela:

- **Reexibir** mostra o MESMO token. Não cria credencial nenhuma, e quem emitiu já
  viu esse código — reexibir não conta nada novo a ninguém.
- **Reemitir** sorteia outro e mata o anterior. É o ato consequente, e é o único que
  deixa linha no histórico.

⚠️ **A janela não é segurança, é ergonomia** — e vale dizer isso alto para ninguém
confundir. Contra a cópia não declarada (quem emite fotografa a tela e guarda) o
prazo não faz nada: trinta segundos e cinco minutos protegem igualmente mal. O que
cerca aquele risco é a permissão de emitir, a TRILHA de quem emitiu para quem
(``registrar_no_historico``), e poder matar um crachá a qualquer momento.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from shopman.backstage.projections.operator_badge import build_operator_badge

#: Chave de sessão onde a ação do changelist deixa o token recém-sorteado.
BADGE_SESSION_KEY = "pending_operator_badge"

#: Por quanto tempo o mesmo crachá pode ser reexibido para reimpressão.
#:
#: Cinco minutos cobre o ritual inteiro com folga — abrir a gaveta de papel,
#: trocar o rolo, chamar quem sabe mexer na impressora. Passou disso, o gerente
#: já saiu de perto e a sessão não deve mais carregar credencial.
JANELA_DE_REIMPRESSAO = timedelta(minutes=5)

MANAGE_OPERATORS = "cashman.manage_operators"


def dentro_da_janela(issued_at_iso, agora=None) -> bool:
    """O crachá guardado na sessão ainda pode ser reexibido?

    Puro de propósito (recebe o "agora"), para a regra de tempo ser testável sem
    relógio falso. Carimbo ausente ou ilegível responde **não**: é sessão de uma
    versão anterior, e na dúvida a credencial não se mostra.
    """
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    if not issued_at_iso:
        return False
    carimbo = parse_datetime(str(issued_at_iso))
    if carimbo is None:
        return False
    return (agora or timezone.now()) - carimbo <= JANELA_DE_REIMPRESSAO


class OperatorBadgeView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Crachá do operador"
    permission_required = MANAGE_OPERATORS
    template_name = "admin_console/operator_badge/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pending = self.request.session.get(BADGE_SESSION_KEY) or {}
        token = str(pending.get("token") or "")

        expirou = token and not dentro_da_janela(pending.get("issued_at"))
        if expirou or not token:
            # Fora da janela a credencial some da sessão. Ficar guardada sem
            # utilidade é superfície de risco por nada.
            self.request.session.pop(BADGE_SESSION_KEY, None)
            token = ""

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
                "expirou": bool(expirou),
                "minutos_da_janela": int(JANELA_DE_REIMPRESSAO.total_seconds() // 60),
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
