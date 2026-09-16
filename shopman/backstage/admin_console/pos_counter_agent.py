"""Instalar o agente do balcão — página Admin canônica (Unfold).

O dono já está no Admin colando a config do terminal. Mandá-lo caçar um arquivo
no repositório para completar a tarefa é atrito bobo: aqui ele baixa o agente e
lê o comando **já preenchido** com o token, a fila e a origem daquele balcão.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from shopman.backstage.projections.pos_agent import (
    AGENT_FILENAME,
    AGENT_SOURCE,
    build_agent_install,
)

#: Mesmo gate do resto da config de terminal. Quem pode configurar a gaveta pode
#: baixar o agente — o arquivo não guarda segredo (o token vive no Admin).
REQUIRED_PERM = "cashman.change_terminal"
RELAY_ISSUE_PERM = "cashman.manage_operators"


def _terminal(ref: str):
    from shopman.cashman.models import Terminal

    try:
        return Terminal.objects.get(ref=ref)
    except Terminal.DoesNotExist as exc:
        raise Http404("Terminal não encontrado.") from exc


class PosCounterAgentView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Instalar o agente do balcão"
    permission_required = REQUIRED_PERM
    template_name = "admin_console/pos_counter_agent/index.html"
    relay_bearer = ""
    confirm_relay_issue = False

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
            # Só existe na resposta do POST que acabou de criar o par. Reabrir
            # a página não consegue reconstruir o segredo armazenado como HMAC.
            relay_bearer=self.relay_bearer,
        )
        context["confirm_relay_issue"] = self.confirm_relay_issue
        context["agent_install_url"] = f"?so={context['agent_install'].os_key}"
        context["relay_issue_allowed"] = self.request.user.has_perms((REQUIRED_PERM, RELAY_ISSUE_PERM))
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
        context["terminal_change_url"] = reverse("admin:cashman_terminal_change", args=[terminal.pk])
        return context

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.has_perms((REQUIRED_PERM, RELAY_ISSUE_PERM)):
            raise PermissionDenied
        action = str(request.POST.get("action") or "").strip()
        if action == "prepare_relay_issue":
            # Confirmação separada: trocar um par existente interrompe o relay
            # antigo. O primeiro POST não muda nada.
            self.confirm_relay_issue = True
            return self.get(request, *args, **kwargs)
        if action != "issue_relay":
            return HttpResponse(status=400)

        terminal_ref = str(kwargs.get("ref") or "").strip()
        expected_version = str(request.POST.get("expected_credential_version") or "").strip()
        with transaction.atomic():
            from shopman.cashman.models import Terminal

            from shopman.backstage.models import PrintAgentCredential

            terminal = (
                Terminal.objects.select_for_update()
                .filter(
                    ref=terminal_ref,
                    is_active=True,
                )
                .first()
            )
            if terminal is None:
                raise Http404("Terminal ativo não encontrado.")

            guide = build_agent_install(
                terminal,
                download_url=reverse(
                    "admin_console_pos_counter_agent_download",
                    args=[terminal.ref],
                ),
                os_key=request.GET.get("so", ""),
            )
            if not guide.relay_can_issue:
                messages.error(request, guide.relay_blocker or "O relay não pode ser pareado agora.")
                return HttpResponseRedirect(request.get_full_path())

            active = list(
                PrintAgentCredential.objects.select_for_update()
                .filter(terminal=terminal, is_active=True)
                .order_by("-last_seen_at", "-pk")
            )
            current_version = f"{active[0].ref}:{active[0].rotated_at.isoformat()}" if active else ""
            if current_version != expected_version:
                messages.error(
                    request,
                    "O pareamento mudou enquanto esta confirmação estava aberta. Confira o estado atual antes de continuar.",
                )
                return HttpResponseRedirect(request.get_full_path())

            if active:
                credential = active[0]
                # Preservar a mesma credencial mantém o FK de leases ainda no
                # journal. Depois da reinstalação, o bearer novo consegue
                # concluir o ACK antigo sem reimprimir.
                PrintAgentCredential.objects.filter(pk__in=[item.pk for item in active[1:]]).update(
                    is_active=False,
                    revoked_at=timezone.now(),
                )
                self.relay_bearer = credential.rotate()
            else:
                credential, self.relay_bearer = PrintAgentCredential.issue(
                    terminal=terminal,
                    label=f"{terminal.label or terminal.ref} · relay de impressão",
                )

        # O LogEntry registra quem substituiu o par, sem bearer nem token.
        self.model_admin.log_change(
            request,
            terminal,
            f"Credencial do relay de impressão emitida ({credential.ref}).",
        )
        messages.success(
            request,
            "Comando completo gerado. Copie agora: a credencial não será mostrada novamente.",
        )
        response = self.get(request, *args, **kwargs)
        # O segredo exibido uma vez fica apenas neste corpo autenticado.
        patch_cache_control(response, no_store=True, private=True)
        response["Referrer-Policy"] = "no-referrer"
        return response


def _terminal_model_admin():
    from shopman.cashman.models import Terminal

    return admin.site._registry[Terminal]


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
