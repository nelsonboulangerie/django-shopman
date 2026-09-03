"""Concierge de WhatsApp no Admin: a transcrição, lida; a conversa, devolvida.

Aqui o gestor faz duas coisas, e só duas: LÊ o que o concierge conversou com o
cliente (transcrição em ordem, com as chamadas de ferramenta resumidas) e
DEVOLVE ao bot uma conversa que está com a equipe. Nada se edita: a conversa é
registro do que aconteceu, e o único verbo que muda estado passa pelo service
(``return_to_concierge``), que também limpa o campo no ManyChat.

``ConversationMessage`` não tem admin próprio de propósito: a mensagem só faz
sentido dentro da conversa, e é ali que ela é lida.
"""

from __future__ import annotations

import json

from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from shopman.utils import unfold_badge, unfold_component
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import Conversation, ConversationMessage

#: Copy de cliente que o concierge usa (``service.copy_message`` e o prompt do
#: agente). Documentada aqui como literal para o guardrail de chaves órfãs
#: (``test_omotenashi_copy_keys``) enxergar o consumidor mesmo antes do prompt
#: existir, e para o gestor saber o que editar em Copy Omotenashi.
CONCIERGE_COPY_KEYS = (
    "CONCIERGE_GREETING",
    "CONCIERGE_UNAVAILABLE",
    "CONCIERGE_MEDIA_UNSUPPORTED",
    "CONCIERGE_HANDOFF_ACK",
    "CONCIERGE_TURN_LIMIT",
    "CONCIERGE_NO_PHONE",
)

_STATE_LABEL = {
    Conversation.State.ACTIVE: "Ativa",
    Conversation.State.HANDOFF: "Com a equipe",
    Conversation.State.CLOSED: "Encerrada",
}

_KIND_COLOR = {
    ConversationMessage.Kind.INBOUND: "blue",
    ConversationMessage.Kind.REPLY: "green",
    ConversationMessage.Kind.TOOL_CALL: "base",
    ConversationMessage.Kind.TOOL_RESULT: "base",
    ConversationMessage.Kind.NOTE: "yellow",
}

_SUMMARY_CHARS = 200


def _compact_json(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(value)


def _clip(text: str, limit: int = _SUMMARY_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def message_summary(message: ConversationMessage) -> str:
    """Uma linha por mensagem, sempre texto puro (quem escapa é o template).

    Cliente e resposta: o próprio texto. Chamada de ferramenta: nome + input.
    Resultado: os primeiros 200 caracteres do conteúdo devolvido.
    """
    if message.text:
        return message.text
    blocks = message.content if isinstance(message.content, list) else []
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "tool_use":
            parts.append(f"{block.get('name') or '?'}({_compact_json(block.get('input') or {})})")
        elif kind == "tool_result":
            raw = block.get("content")
            if isinstance(raw, list):
                raw = " ".join(str(b.get("text", "")) for b in raw if isinstance(b, dict))
            elif not isinstance(raw, str):
                raw = _compact_json(raw)
            parts.append(_clip(raw))
        elif kind == "text":
            parts.append(_clip(str(block.get("text") or "")))
    return " · ".join(p for p in parts if p) or "(vazio)"


@admin.register(Conversation)
class ConversationAdmin(ModelAdmin):
    list_display = (
        "who_display",
        "state_badge",
        "last_inbound_at",
        "turns_today",
        "handoff_reason",
        "tokens_display",
    )
    list_filter = ("state", "last_inbound_at")
    search_fields = ("phone", "customer_name", "subscriber_id", "customer_ref")
    ordering = ("-last_inbound_at", "-id")
    date_hierarchy = "last_inbound_at"
    list_per_page = 50
    actions = ["return_to_concierge_selected"]

    readonly_fields = (
        "subscriber_id",
        "phone",
        "customer_name",
        "customer_ref",
        "channel_ref",
        "state",
        "handoff_reason",
        "handoff_at",
        "session_key",
        "quote_display",
        "summary",
        "turns_day",
        "turns_today",
        "consecutive_failures",
        "tokens_display",
        "last_inbound_at",
        "last_outbound_at",
        "created_at",
        "updated_at",
        "transcript_display",
    )
    fieldsets = (
        (None, {
            "fields": (
                ("customer_name", "phone"),
                ("subscriber_id", "customer_ref"),
                ("state", "channel_ref"),
                ("handoff_reason", "handoff_at"),
                ("last_inbound_at", "last_outbound_at"),
            ),
        }),
        (_("Transcrição"), {"fields": ("transcript_display",), "classes": ("tab",)}),
        (_("Pedido em andamento"), {"fields": ("session_key", "quote_display", "summary"), "classes": ("tab",)}),
        (_("Consumo"), {
            "fields": (("turns_day", "turns_today"), "consecutive_failures", "tokens_display", ("created_at", "updated_at")),
            "classes": ("tab",),
        }),
    )

    # ── Permissões: leitura, e um verbo só ─────────────────────────────

    def has_add_permission(self, request):
        # Conversa nasce da mensagem do cliente no WhatsApp, nunca à mão.
        return False

    def has_delete_permission(self, request, obj=None):
        # A transcrição é registro de atendimento (LGPD: qualidade do serviço);
        # apagar é rotina de retenção, não gesto de tela.
        return False

    def has_change_permission(self, request, obj=None):
        # Nada se edita; o único verbo é a action, que passa pelo service.
        return False

    # ── Colunas ────────────────────────────────────────────────────────

    @display(description="cliente", ordering="customer_name")
    def who_display(self, obj):
        name = obj.customer_name or "(sem nome)"
        return f"{name} · {obj.phone}" if obj.phone else name

    @display(description="estado", ordering="state", label={"Ativa": "success", "Com a equipe": "warning", "Encerrada": "base"})
    def state_badge(self, obj):
        return _STATE_LABEL.get(obj.state, obj.state)

    @display(description="tokens (in / out / cache)")
    def tokens_display(self, obj):
        return f"{obj.input_tokens:,} / {obj.output_tokens:,} / {obj.cache_read_tokens:,}".replace(",", ".")

    # ── Detalhe ────────────────────────────────────────────────────────

    @display(description="orçamento vigente")
    def quote_display(self, obj):
        if not obj.quote:
            return "—"
        return format_html("<pre class=\"text-xs whitespace-pre-wrap\">{}</pre>", json.dumps(obj.quote, ensure_ascii=False, indent=2, default=str))

    @display(description="transcrição")
    def transcript_display(self, obj):
        if obj.pk is None:
            return "—"
        rows = list(obj.messages.order_by("id"))
        if not rows:
            return unfold_component(
                "unfold/components/text.html",
                children=str(_("Sem mensagens ainda.")),
                **{"class": "text-base-500"},
            )
        body = format_html_join(
            "",
            '<li class="border-b border-base-200 dark:border-base-700 py-1.5 text-sm">'
            '<span class="font-mono text-base-500">{}</span> '
            "{} "
            '<span class="break-words whitespace-pre-wrap">{}</span>'
            "{}"
            "</li>",
            (
                (
                    m.created_at.strftime("%d/%m %H:%M:%S") if m.created_at else "—",
                    unfold_badge(m.get_kind_display(), _KIND_COLOR.get(m.kind, "base")),
                    message_summary(m),
                    format_html(' <span class="text-base-500">· {}</span>', "não entregue") if m.delivered is False else "",
                )
                for m in rows
            ),
        )
        return format_html('<ul class="flex flex-col">{}</ul>', body)

    # ── Action ─────────────────────────────────────────────────────────

    @admin.action(description=_("Devolver ao concierge"), permissions=["view"])
    def return_to_concierge_selected(self, request, queryset):
        from shopman.shop.concierge.service import return_to_concierge

        done = 0
        skipped = 0
        for conversation in queryset:
            if conversation.state != Conversation.State.HANDOFF:
                skipped += 1
                continue
            return_to_concierge(conversation)
            done += 1
        if done:
            messages.success(request, _("%(n)d conversa(s) devolvida(s) ao concierge.") % {"n": done})
        if skipped:
            messages.warning(
                request,
                _("%(n)d conversa(s) ignorada(s): só conversas com a equipe podem ser devolvidas.") % {"n": skipped},
            )
