"""Trilha de acessos — somente leitura, no Admin.

Onde alguém olharia quando a pergunta é "o crachá do fulano destravou o PDV num
dia de folga?". Fica na Auditoria, ao lado dos alertas do operador, porque é
exatamente isso: o que já aconteceu, para conferir.

**Nada aqui se cria, se edita ou se apaga pela tela.** Não é zelo: uma trilha que
o Admin pode apagar não serve de trilha — quem usasse um crachá esquecido teria,
na aba ao lado, o botão de sumir com a própria linha. O envelhecimento é por
retenção (``sign_in_audit.purge``), não por clique.
"""

from __future__ import annotations

from django.contrib import admin
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import SignInEvent, SignInMethod, SignInOutcome
from shopman.backstage.services.sign_in_audit import ANOMALY_LABELS


@admin.register(SignInEvent)
class SignInEventAdmin(ModelAdmin):
    list_display = (
        "created_at",
        "username",
        "method_badge",
        "outcome_badge",
        "station_display",
        "highlight_display",
        "ip_address",
    )
    list_filter = ("method", "outcome", "station_ref", "created_at")
    search_fields = ("username", "ip_address", "station_ref")
    readonly_fields = (
        "user", "username", "method", "outcome", "station_ref",
        "ip_address", "created_at", "notified", "data",
    )
    date_hierarchy = "created_at"
    list_per_page = 50
    ordering = ("-created_at",)
    list_fullwidth = True
    compressed_fields = True
    list_select_related = ("user",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="método")
    def method_badge(self, obj):
        # O crachá é destacado porque é a única credencial de POSSE pura da casa:
        # não tem segundo fator e se perde no chão. Quem varre a lista procurando
        # o que investigar procura por ele.
        cores = {
            SignInMethod.BADGE: "orange",
            SignInMethod.PIN: "blue",
            SignInMethod.PASSWORD: "base",
        }
        return unfold_badge(obj.get_method_display(), cores.get(obj.method, "base"))

    @display(description="resultado")
    def outcome_badge(self, obj):
        if obj.outcome == SignInOutcome.FAILED:
            return unfold_badge("recusado", "red")
        if obj.outcome == SignInOutcome.REVOKED:
            # `primary` e não uma cor de erro: revogado é o desfecho de uma
            # AÇÃO tomada pelo dono da conta, não uma falha do sistema.
            return unfold_badge("revogado", "primary")
        return unfold_badge("entrou", "green")

    @display(description="atenção")
    def highlight_display(self, obj):
        """O que fez este acesso ser destacado — a mesma leitura do aviso.

        A coluna existe para a varredura visual: quem abre a Auditoria procurando
        o que investigar não deveria ter que abrir linha por linha para descobrir
        qual delas era estranha.
        """
        codigos = obj.anomalies
        if not codigos:
            return ""
        return unfold_badge(
            "; ".join(ANOMALY_LABELS.get(c, c) for c in codigos), "orange"
        )

    @display(description="estação")
    def station_display(self, obj):
        # Vazio não é lacuna: quer dizer "de fora da loja" — um navegador
        # qualquer, o Admin de casa — e essa é a informação.
        return obj.station_ref or unfold_badge("fora da loja", "yellow")
