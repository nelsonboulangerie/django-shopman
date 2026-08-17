"""Instalar o agente do balcão — página Admin canônica (Unfold).

O dono já está no Admin colando a config do terminal. Mandá-lo caçar um arquivo
no repositório para completar a tarefa é atrito bobo: aqui ele baixa o agente e
lê o comando **já preenchido** com o token, a fila e a origem daquele balcão.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.urls import reverse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from shopman.backstage.projections.pos_agent import (
    AGENT_FILENAME,
    AGENT_SOURCE,
    build_agent_install,
)

#: Mesmo gate do resto da config de terminal. Quem pode configurar a gaveta pode
#: baixar o agente — o arquivo não guarda segredo (o token vive no Admin).
REQUIRED_PERM = "backstage.change_posterminal"


def _terminal(ref: str):
    from shopman.backstage.models import POSTerminal

    try:
        return POSTerminal.objects.get(ref=ref)
    except POSTerminal.DoesNotExist as exc:
        raise Http404("Terminal não encontrado.") from exc


class PosCounterAgentView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Instalar o agente do balcão"
    permission_required = REQUIRED_PERM
    template_name = "admin_console/pos_counter_agent/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        terminal = _terminal(self.kwargs["ref"])
        context["agent_install"] = build_agent_install(
            terminal,
            download_url=reverse("admin_console_pos_counter_agent_download", args=[terminal.ref]),
            # O SO é do COMPUTADOR, não do terminal: a mesma loja pode instalar
            # no caixa Windows hoje e no Linux depois. Por isso vive na URL, e
            # não vira mais um campo na config do terminal.
            os_key=self.request.GET.get("so", ""),
        )
        # Copiar é ato de DOM, então o estado vive no Alpine e a ação usa o
        # clipboard — exceção explícita do CLAUDE.md, por não ter equivalente
        # Alpine. Vem por `attrs` para o controle continuar sendo o componente
        # canônico do Unfold, em vez de marcação escrita à mão.
        context["copy_button_attrs"] = {
            "@click": (
                "navigator.clipboard.writeText($refs.cmd.textContent.trim());"
                " copiado = true; setTimeout(() => copiado = false, 2000)"
            ),
        }
        context["terminal_change_url"] = reverse(
            "admin:backstage_posterminal_change", args=[terminal.pk]
        )
        return context


def _terminal_model_admin():
    from shopman.backstage.models import POSTerminal

    return admin.site._registry[POSTerminal]


def pos_counter_agent_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve o ModelAdmin tardiamente (ordem de import do URLConf)."""
    return PosCounterAgentView.as_view(model_admin=_terminal_model_admin())(request, *args, **kwargs)


def pos_counter_agent_download(request: HttpRequest, ref: str) -> HttpResponse:
    """Serve o agente como anexo.

    Gate explícito: `admin.site.admin_view` já garante staff logado, mas quem
    não pode configurar o terminal também não precisa do agente dele.
    """
    if not request.user.has_perm(REQUIRED_PERM):
        raise Http404("Sem permissão.")
    _terminal(ref)  # 404 para terminal inexistente, antes de servir o arquivo
    if not AGENT_SOURCE.is_file():
        raise Http404("O arquivo do agente não veio nesta instalação.")
    return FileResponse(
        AGENT_SOURCE.open("rb"),
        as_attachment=True,
        filename=AGENT_FILENAME,
        content_type="text/x-python",
    )
