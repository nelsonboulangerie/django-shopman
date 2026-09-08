"""Desfazer a unificação de cadastros — a janela de 24h ganha uma porta.

O balcão unifica dois cadastros pelo PDV (``POST /api/v1/backstage/pos/customer/
merge/``). O ``MergeService`` do Guestman migra tudo, grava um ``MergeAudit`` com
snapshot e aceita ``undo`` por 24h. Até aqui esse desfazer só era alcançável pelo
shell do Django — e desfazer que ninguém alcança é o mesmo que não desfazer: o
operador unificava os cadastros errados às 14h de um sábado e a janela fechava
sozinha, sem que ninguém tivesse onde clicar.

Esta tela é a porta. Ela mora no backstage de propósito: ``packages/guestman`` é
Core, o ``MergeService.undo`` já estava pronto, e o que faltava era superfície.
Nada em ``packages/`` foi tocado.

**Duas permissões, e a distinção é a régua da casa.** Abrir a trilha é
``customer_merge.view_mergeaudit``; desfazer é ``shop.manage_customers`` — a
mesma que governa criar e editar cliente, e que o Caixa não tem. Quem unifica no
balcão não desfaz sozinho: o desfazer mexe no cadastro de duas pessoas e é gesto
de gestão.

⚠️ O ``dialog`` não é enfeite de UX, é o que faz a ação exigir POST. O Unfold
monta a URL de ``actions_row`` embrulhada só em ``admin_site.admin_view`` e a
renderiza como ``<a href>``; sem ``dialog`` o corpo executaria em GET, e com
``SESSION_COOKIE_SAMESITE = "Lax"`` um link mandado num WhatsApp e clicado pelo
gestor logado desfaria a unificação. Mesma lição do estorno em ``payman``.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from shopman.guestman.contrib.merge.models import MergeAudit, MergeStatus
from shopman.guestman.exceptions import CustomerError
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import BaseDialogForm

#: Desfazer reescreve o cadastro de duas pessoas — é a mesma permissão que
#: governa criar e editar cliente. O Caixa (quem unifica no balcão) não a tem, e
#: essa é a decisão: unificar sai de um beco sem saída no meio da venda; desfazer
#: é revisão, e revisão tem dono.
UNDO_PERMISSION = "shop.manage_customers"

#: O que o ``undo`` devolve ao cadastro absorvido — a lista sai do próprio
#: ``MergeService.undo``, na ordem em que ele reverte. Singular e plural porque a
#: frase é lida por gente: "1 contatos" é o tipo de descuido que faz o operador
#: desconfiar do resto da tela.
RESTAURADO = (
    ("migrated_contact_points", "contato", "contatos"),
    ("migrated_external_identities", "identidade externa", "identidades externas"),
    ("migrated_identifiers", "identificador", "identificadores"),
    ("migrated_addresses", "endereço", "endereços"),
    ("migrated_preferences", "preferência", "preferências"),
    ("migrated_consents", "consentimento", "consentimentos"),
    ("migrated_timeline_events", "evento de histórico", "eventos de histórico"),
)


def _restante(deadline) -> str:
    """Quanto ainda dá para desfazer, no formato que se lê de relance: 6h12, 43min."""
    segundos = int((deadline - timezone.now()).total_seconds())
    if segundos <= 0:
        return ""
    horas, minutos = divmod(segundos // 60, 60)
    return f"{horas}h{minutos:02d}" if horas else f"{minutos}min"


def _quando(momento) -> str:
    return timezone.localtime(momento).strftime("%d/%m/%Y às %H:%M")


def _de_volta_para_a_lista(request: HttpRequest) -> HttpResponse:
    """Volta para a lista de um jeito que a MENSAGEM chegue junto.

    O diálogo do Unfold envia por HTMX com ``hx-select="#dialog-form"``. Um
    ``HttpResponseRedirect`` comum é seguido pelo próprio HTMX: ele busca a
    changelist, não acha ``#dialog-form`` nela, e esvazia o modal — a página não
    troca, e a mensagem (o "desfeita" ou a recusa) fica presa numa resposta que
    ninguém vê. ``HX-Redirect`` manda o NAVEGADOR navegar, e aí a mensagem
    aparece onde ela existe para aparecer.

    Fora do HTMX (POST direto, teste) o redirect comum continua valendo.
    """
    url = reverse("admin:customer_merge_mergeaudit_changelist")
    if request.headers.get("HX-Request"):
        resposta = HttpResponse(status=204)
        resposta["HX-Redirect"] = url
        return resposta
    return HttpResponseRedirect(url)


def _recusa(audit: MergeAudit | None) -> str:
    """A frase que o gestor lê quando o desfazer não pode acontecer.

    O ``MergeService.undo`` recusa em três casos com o mesmo código
    (``UNDO_FAILED``) e uma mensagem de engenharia. Aqui cada caso vira a frase
    que diz o que aconteceu e o que ainda dá para fazer — quem está na tela
    precisa saber se procura outra linha, se já resolveram por ele, ou se o
    conserto virou trabalho manual.
    """
    if audit is None:
        return (
            "Esta unificação não está mais no sistema. Recarregue a lista: "
            "ou o registro foi apagado por fora, ou o link é de outra loja."
        )
    if audit.status != MergeStatus.COMPLETED:
        quem = f" por {audit.reverted_by}" if audit.reverted_by else ""
        quando = f" em {_quando(audit.reverted_at)}" if audit.reverted_at else ""
        return f"Esta unificação já foi desfeita{quando}{quem}. Não há o que desfazer de novo."
    if not audit.can_undo:
        return (
            f"O prazo de {MergeAudit.UNDO_WINDOW_HOURS}h para desfazer terminou em "
            f"{_quando(audit.undo_deadline)}. A partir daqui a separação é manual: "
            f"cadastre {audit.source_ref} de novo e mova o que for dele."
        )
    return ""


class UndoMergeConfirmForm(BaseDialogForm):
    """A confirmação — sem campo além do próprio "eu confirmo".

    O ``BaseDialogForm`` já carrega o ``_form_submitted`` obrigatório, que é o
    que torna o GET incapaz de validar. A subclasse existe para pendurar o
    ``form_before_template``: o prazo que resta e o que NÃO volta são a
    informação que o gestor precisa ter ANTES de confirmar, não depois.
    """

    form_before_template = "admin_console/merge_undo/dialog.html"

    def get_before_template_context(self, request, object_id=None) -> dict:
        audit = MergeAudit.objects.filter(pk=object_id).first() if object_id else None
        if audit is None:
            return {"recusa": _recusa(None)}

        restaurado = [
            f"{contagem} {singular if contagem == 1 else plural}"
            for campo, singular, plural in RESTAURADO
            if (contagem := getattr(audit, campo, 0))
        ]
        pedidos = len(audit.snapshot.get("orders") or [])
        if pedidos:
            restaurado.append(f"{pedidos} {'pedido' if pedidos == 1 else 'pedidos'}")

        return {
            "recusa": _recusa(audit),
            "source_ref": audit.source_ref,
            "target_ref": audit.target_ref,
            "restante": _restante(audit.undo_deadline),
            "deadline": _quando(audit.undo_deadline),
            "loyalty_merged": audit.loyalty_merged,
            "pontos_somados": (audit.snapshot.get("loyalty") or {}).get("source_points"),
            "restaurado": ", ".join(restaurado),
        }


@admin.register(MergeAudit)
class MergeAuditAdmin(ModelAdmin):
    """A trilha das unificações, com o desfazer ao lado de cada linha.

    Somente leitura: a unificação nasce no balcão e a única escrita que a tela
    oferece é o ``undo``, que passa pelo service. Editar a auditoria à mão seria
    apagar o rastro que ela existe para guardar.
    """

    list_display = (
        "unified_display",
        "actor_display",
        "merged_at_display",
        "status_badge",
        "undo_window_badge",
    )
    list_filter = ("status",)
    search_fields = ("source_ref", "target_ref", "actor")
    ordering = ("-merged_at",)
    list_per_page = 50
    list_fullwidth = True
    compressed_fields = True
    readonly_fields = (
        "source_ref",
        "target_ref",
        "source_id",
        "target_id",
        "actor",
        "evidence",
        "status",
        "merged_at",
        "reverted_at",
        "reverted_by",
        "migrated_contact_points",
        "migrated_external_identities",
        "migrated_identifiers",
        "migrated_addresses",
        "migrated_preferences",
        "migrated_consents",
        "migrated_timeline_events",
        "loyalty_merged",
        "snapshot",
    )
    fieldsets = (
        ("Quem virou quem", {"fields": ("source_ref", "target_ref", "actor", "merged_at")}),
        (
            "Estado",
            {
                "fields": ("status", "reverted_at", "reverted_by", "evidence"),
                "description": (
                    "Desfazer devolve contatos, endereços, preferências, consentimentos, "
                    "histórico e pedidos ao cadastro absorvido, e o reativa. A FIDELIDADE "
                    "não volta: pontos, selos e faixa somados no cadastro sobrevivente "
                    "ficam lá, e o acerto é manual."
                ),
            },
        ),
        (
            "O que foi migrado",
            {
                "fields": (
                    "migrated_contact_points",
                    "migrated_external_identities",
                    "migrated_identifiers",
                    "migrated_addresses",
                    "migrated_preferences",
                    "migrated_consents",
                    "migrated_timeline_events",
                    "loyalty_merged",
                ),
            },
        ),
        ("Snapshot", {"fields": ("snapshot", "source_id", "target_id"), "classes": ["collapse"]}),
    )
    actions_row = ["undo_merge_row"]

    def has_add_permission(self, request) -> bool:
        # Unificação nasce no balcão, nunca digitada aqui.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        # Auditoria não se edita: a única escrita da tela é o `undo`, e ele passa
        # pelo service, que grava quem desfez e quando.
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    # ── Colunas ──────────────────────────────────────────────────────────────

    @display(description="Unificação")
    def unified_display(self, obj) -> str:
        return f"{obj.source_ref} → {obj.target_ref}"

    @display(description="Quem unificou")
    def actor_display(self, obj) -> str:
        return obj.actor or "—"

    @display(description="Quando")
    def merged_at_display(self, obj) -> str:
        return _quando(obj.merged_at)

    @display(description="Estado")
    def status_badge(self, obj):
        if obj.status == MergeStatus.REVERTED:
            return unfold_badge("desfeita", "base")
        return unfold_badge("unificada", "green")

    @display(description="Desfazer até")
    def undo_window_badge(self, obj):
        """O prazo é a informação mais perecível da tela: fica na lista.

        Sem ela o gestor descobre que perdeu a janela ao clicar. Com ela, a
        linha já diz se ainda dá — e quanto tempo sobra.
        """
        if obj.status == MergeStatus.REVERTED:
            return unfold_badge("—", "base")
        if not obj.can_undo:
            return unfold_badge("prazo encerrado", "base")
        # Só o quanto falta: o badge é caixa-alta e curto por desenho, e a data
        # cheia está no diálogo, a um clique — que é onde ela decide algo.
        return unfold_badge(f"faltam {_restante(obj.undo_deadline)}", "green")

    # ── A ação ───────────────────────────────────────────────────────────────

    @action(
        description="Desfazer unificação",
        url_path="undo",
        icon="undo",
        variant=ActionVariant.DANGER,
        # Pontuada de propósito: o Unfold confere permissão pontuada direto com
        # `request.user.has_perm` e não passa pelos métodos `has_*_permission`
        # deste admin — que são `False` incondicionalmente, e matariam a ação até
        # para superusuário. Ela também some da linha para quem não tem, então o
        # botão não é placa de porta trancada.
        permissions=[UNDO_PERMISSION],
        dialog={
            "title": "Desfazer esta unificação?",
            # Sem descrição fixa de propósito: ela apareceria acima do corpo em
            # TODOS os casos, inclusive quando o corpo é uma recusa — e o gestor
            # leria uma promessa ("os dois cadastros voltam") seguida de "o prazo
            # terminou". Quem fala aqui é o `form_before_template`, que sabe de
            # qual auditoria se trata.
            "description": "",
            "form_class": UndoMergeConfirmForm,
            "form_submit_text": "Desfazer",
        },
    )
    def undo_merge_row(self, request, form, object_id):
        from shopman.guestman.contrib.merge.service import MergeService

        destino = _de_volta_para_a_lista(request)
        audit = MergeAudit.objects.filter(pk=object_id).first()

        recusa = _recusa(audit)
        if recusa:
            self.message_user(request, recusa, messages.ERROR)
            return destino

        try:
            MergeService.undo(str(audit.pk), actor=f"admin:{request.user}")
        except CustomerError:
            # A janela pode ter fechado (ou outro gestor ter desfeito) entre a
            # abertura do diálogo e o POST. Relemos o estado para dizer QUAL dos
            # três casos aconteceu, em vez de repassar o texto do Core.
            audit.refresh_from_db()
            self.message_user(
                request,
                _recusa(audit) or "Não foi possível desfazer esta unificação.",
                messages.ERROR,
            )
            return destino

        aviso = (
            f"Unificação desfeita: {audit.source_ref} voltou a ser um cadastro ativo, "
            f"separado de {audit.target_ref}."
        )
        if audit.loyalty_merged:
            aviso += " A fidelidade NÃO foi separada — os pontos ficaram no cadastro que sobreviveu."
        self.message_user(request, aviso, messages.SUCCESS)
        return destino
