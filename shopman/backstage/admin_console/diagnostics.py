"""Diagnóstico — prontidão das integrações, e o botão que prova o e-mail.

## Por que um botão, e não um comando

O jeito de provar que o e-mail sai era `manage.py shell` no console da
DigitalOcean. Ele **não funciona**, e falha de um jeito que engana: o console
não recebe as variáveis marcadas `SECRET`, então a senha chega vazia e o erro
que aparece é ``SECRET_KEY must be set in production`` — que fala de outra
coisa. Quem vê isso conclui que o app está quebrado, enquanto o app servindo
está com `/health/` em 200.

O processo que **tem** os segredos é o que serve o Admin. Então a prova tem de
sair de dentro dele, e o gesto mais barato que existe é um botão.

## Três decisões que fazem este botão ser seguro

1. **O destino é o e-mail de quem está logado**, nunca um campo aberto. Um campo
   de destinatário num painel de gestor é um convite a mandar teste para o
   cliente errado. Quem quer testar outro endereço, entra com outro usuário.
2. **Conexão com timeout curto e explícito.** A saída de rede de um PaaS pode
   bloquear a porta 587, e a política não recusa — ela silencia. Sem timeout, o
   clique pendura dois minutos segurando um worker.
3. **O erro aparece inteiro na tela.** Autenticação recusada, porta fechada e
   domínio sem SPF produzem sintomas diferentes, e esconder a mensagem
   transformaria os três no mesmo "não funcionou".

⚠️ Isto **não** dispara Directive nem executa lógica de negócio — a casa mantém
o Admin fora do lifecycle. É diagnóstico: abre uma conexão, manda uma mensagem
para o próprio operador, e conta o que aconteceu.
"""

from __future__ import annotations

import logging
import time

from django.contrib import admin, messages
from django.core.mail import EmailMessage, get_connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin

from shopman.backstage.projections.diagnostics import build_diagnostics

logger = logging.getLogger(__name__)

#: Teto de espera do teste. Independente de `EMAIL_TIMEOUT` porque aqui há
#: alguém olhando a tela: um gestor não espera quinze segundos por um clique
#: sem achar que travou.
_TESTE_TIMEOUT_SEGUNDOS = 10


class DiagnosticsView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Diagnóstico"
    permission_required = "shop.view_shop"
    template_name = "admin_console/diagnostics/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["diagnostics"] = build_diagnostics()
        return context

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        destino = str(getattr(request.user, "email", "") or "").strip()
        if not destino:
            messages.error(
                request,
                "Seu usuário do Admin não tem e-mail cadastrado — o teste envia "
                "para você mesmo, e sem endereço não há para onde mandar.",
            )
            return self._redirect()

        projection = build_diagnostics()
        if not projection.email.entrega:
            messages.warning(
                request,
                f"O canal de e-mail está inerte: {projection.email.motivo} "
                "Enviar agora não provaria nada.",
            )
            return self._redirect()

        inicio = time.monotonic()
        try:
            conexao = get_connection(timeout=_TESTE_TIMEOUT_SEGUNDOS)
            enviados = EmailMessage(
                subject="Shopman — teste de envio",
                body=(
                    "Se esta mensagem chegou, o e-mail da loja está funcionando.\n\n"
                    f"Remetente: {projection.email.sender}\n"
                    f"Servidor: {projection.email.host}:{projection.email.port}\n"
                    f"Ambiente: {projection.environment}\n"
                ),
                to=[destino],
                connection=conexao,
            ).send(fail_silently=False)
        except Exception as exc:  # o erro É o resultado do teste
            # Vai para a tela E para o log: quem clicou vê agora, e quem for
            # investigar amanhã encontra sem depender da memória de quem clicou.
            logger.warning("diagnostics: teste de e-mail falhou — %s", exc, exc_info=True)
            decorrido = time.monotonic() - inicio
            messages.error(
                request,
                f"Falhou em {decorrido:.1f}s — {type(exc).__name__}: {exc}",
            )
            return self._redirect()

        decorrido = time.monotonic() - inicio
        if not enviados:
            messages.warning(
                request,
                f"O servidor aceitou a conexão mas não enviou nada ({decorrido:.1f}s).",
            )
            return self._redirect()

        messages.success(
            request,
            f"Enviado para {destino} em {decorrido:.1f}s. "
            "Se não aparecer na entrada, procure no spam — aí o problema é "
            "entregabilidade, não configuração.",
        )
        return self._redirect()

    def _redirect(self) -> HttpResponseRedirect:
        return HttpResponseRedirect(reverse("admin_console_diagnostics"))


def _shop_model_admin():
    from shopman.shop.models import Shop

    return admin.site._registry[Shop]


def diagnostics_as_view():
    return DiagnosticsView.as_view(model_admin=_shop_model_admin())


def diagnostics_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    """Resolve o ModelAdmin de Shop tardiamente (ordem de import do URLConf)."""
    return diagnostics_as_view()(request, *args, **kwargs)
