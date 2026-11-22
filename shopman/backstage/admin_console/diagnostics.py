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
2. **Timeout curto e explícito**, pelo alias `diagnostics` do `MAILERS`. A saída
   de rede de um PaaS pode bloquear a porta 587, e a política não recusa — ela
   silencia. Sem timeout, o clique pendura dois minutos segurando um worker.
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

from django import forms
from django.contrib import admin, messages
from django.core.mail import EmailMessage
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.views.generic import TemplateView
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminIntegerFieldWidget, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from shopman.backstage.projections.diagnostics import build_diagnostics
from shopman.backstage.services import courier_probe
from shopman.shop.mailers import DIAGNOSTICS_ALIAS

logger = logging.getLogger(__name__)


class CourierProbeForm(forms.Form):
    """O que a sonda da central de entregas pergunta: as opções do comando, com nome de gente."""

    action = forms.ChoiceField(
        label="O que fazer",
        required=False,
        choices=(
            ("read", "Ler a conta e as corridas (só leitura)"),
            ("webhooks", "Ler os avisos cadastrados (só leitura)"),
            *((key, f"ESCREVE: {label}") for key, (label, _hint) in courier_probe.WRITE_ACTIONS.items()),
            (courier_probe.REGISTER_WEBHOOKS, "ESCREVE: cadastrar os avisos que faltam"),
        ),
        widget=UnfoldAdminSelectWidget,
    )
    rides = forms.CharField(
        label="Corridas",
        required=False,
        help_text=f"O número da corrida na TaOn, até {courier_probe.MAX_RIDES}, separados por vírgula. A escrita pede uma só.",
        widget=UnfoldAdminTextInputWidget,
    )
    window = forms.IntegerField(
        label="Corridas abertas nos últimos minutos",
        required=False, min_value=0, max_value=240,
        widget=UnfoldAdminIntegerFieldWidget,
    )
    recent = forms.IntegerField(
        label="Últimas corridas gravadas nos pedidos",
        required=False, min_value=0, max_value=5,
        widget=UnfoldAdminIntegerFieldWidget,
    )
    value = forms.CharField(
        label="Valor da escrita",
        required=False,
        help_text="; ".join(f"{label}: {hint}" for label, hint in courier_probe.WRITE_ACTIONS.values()) + ".",
        widget=UnfoldAdminTextInputWidget,
    )
    confirm = forms.CharField(
        label="Confirmação da escrita",
        required=False,
        help_text=(
            "Repita o número da corrida. Para cadastrar os avisos, escreva "
            f"{courier_probe.REGISTER_CONFIRMATION}. Sem isto nada é enviado."
        ),
        widget=UnfoldAdminTextInputWidget,
    )


class DiagnosticsView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Diagnóstico"
    permission_required = "shop.view_shop"
    template_name = "admin_console/diagnostics/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["diagnostics"] = build_diagnostics()
        user = getattr(self.request, "user", None)
        context["courier_probe_allowed"] = bool(getattr(user, "is_superuser", False))
        context.setdefault("courier_form", CourierProbeForm(initial={"action": "read"}))
        return context

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if request.POST.get("probe") == "courier":
            return self._courier_probe(request)
        return self._email_probe(request)

    def _courier_probe(self, request: HttpRequest) -> HttpResponse:
        """A sonda da central de entregas: só superusuário, porque também escreve na TaOn."""
        if not request.user.is_superuser:
            messages.error(request, "A sonda da central de entregas é só para superusuário.")
            return self._redirect()
        form = CourierProbeForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(courier_form=form))
        data = form.cleaned_data
        action = data.get("action") or "read"
        rides = courier_probe.rides_from(data.get("rides", ""))
        public_base = f"https://{request.get_host()}"
        if action == "read":
            result = courier_probe.read(rides=rides, window=data.get("window") or 0, recent=data.get("recent") or 0)
        elif action == "webhooks":
            result = courier_probe.webhooks(public_base)
        elif action == courier_probe.REGISTER_WEBHOOKS:
            if str(data.get("confirm") or "").strip().upper() != courier_probe.REGISTER_CONFIRMATION:
                result = courier_probe.CourierProbeResult(
                    ok=False, wrote=False,
                    report=f"Para cadastrar os avisos, escreva {courier_probe.REGISTER_CONFIRMATION} na confirmação. Nada foi enviado.",
                )
            else:
                result = courier_probe.register_webhooks(public_base)
        elif len(rides) != 1:
            result = courier_probe.CourierProbeResult(
                ok=False, wrote=False, report="A escrita pede exatamente uma corrida. Nada foi enviado.",
            )
        else:
            result = courier_probe.write(
                ride=rides[0], action=action, value=str(data.get("value") or ""), confirm=str(data.get("confirm") or ""),
            )
        logger.info(
            "diagnostics.courier_probe user=%s action=%s rides=%s ok=%s wrote=%s",
            request.user.pk, action, ",".join(rides), result.ok, result.wrote,
        )
        # A confirmação não volta preenchida: cada escrita pede o gesto de novo.
        refilled = CourierProbeForm(initial={**{k: v for k, v in data.items() if v not in (None, "")}, "confirm": ""})
        return self.render_to_response(self.get_context_data(courier_form=refilled, courier_result=result))

    def _email_probe(self, request: HttpRequest) -> HttpResponse:
        destino = str(getattr(request.user, "email", "") or "").strip()
        if not destino:
            messages.error(
                request,
                "Seu usuário do Admin não tem e-mail cadastrado. O teste envia "
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
            # ⚠️ `using=<alias>`, e não uma conexão montada aqui: o
            # `get_connection()` e o argumento `connection=` do `EmailMessage`
            # são deprecados no Django 6.1 e somem no 7. O teto de espera curto
            # que este botão precisa vem do próprio alias, declarado em
            # `config/settings.py` ao lado do teto do worker.
            enviados = EmailMessage(
                subject="Shopman: teste de envio",
                body=(
                    "Se esta mensagem chegou, o e-mail da loja está funcionando.\n\n"
                    f"Remetente: {projection.email.sender}\n"
                    f"Servidor: {projection.email.host}:{projection.email.port}\n"
                    f"Ambiente: {projection.environment}\n"
                ),
                to=[destino],
            ).send(using=DIAGNOSTICS_ALIAS)
        except Exception as exc:  # o erro É o resultado do teste
            # Vai para a tela E para o log: quem clicou vê agora, e quem for
            # investigar amanhã encontra sem depender da memória de quem clicou.
            logger.warning("diagnostics: teste de e-mail falhou — %s", exc, exc_info=True)
            decorrido = time.monotonic() - inicio
            messages.error(
                request,
                f"Falhou em {decorrido:.1f}s ({type(exc).__name__}: {exc})",
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
            "Se não aparecer na entrada, procure no spam: aí o problema é "
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
