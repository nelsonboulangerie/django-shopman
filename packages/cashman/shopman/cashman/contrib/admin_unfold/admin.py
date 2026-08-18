"""Cashman Admin (Unfold): terminal editável, turno e livro só leitura.

O turno e o livro são mutados exclusivamente pelos services do pacote; o Admin
mostra e não corrige. A linha do tempo do turno é o inline de lançamentos, em
ordem cronológica de propósito: a pergunta que ela responde é "o que houve
neste turno", e isso se lê de cima para baixo como aconteceu.

⚠️ Esperado, contado e diferença aparecem AQUI (retaguarda, ``audit_shift``) e
nunca numa projection de terminal: é o fechamento cego (ADR-011 §4).
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.utils.translation import gettext_lazy as _
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.cashman.services import ledger
from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.decorators import display

_KIND_COLORS = {
    Entry.Kind.FLOAT_IN: "base",
    Entry.Kind.SALE: "green",
    Entry.Kind.COD_SETTLED: "green",
    Entry.Kind.CASH_IN: "green",
    Entry.Kind.REFUND: "orange",
    Entry.Kind.CASH_OUT: "orange",
    Entry.Kind.COUNT: "blue",
    Entry.Kind.COUNT_CORRECTION: "blue",
    Entry.Kind.DRAWER_UNLOCK: "yellow",
}


def _money(amount_q: int) -> str:
    sign = "+" if amount_q > 0 else ("" if amount_q == 0 else "−")
    return f"{sign}R$ {format_money(abs(amount_q))}"


def entry_detail(entry: Entry) -> str:
    """Uma frase por lançamento, a partir do payload de cada tipo."""
    payload = entry.payload or {}
    kind = entry.kind
    parts: list[str] = []
    if kind == Entry.Kind.SALE:
        received, change = payload.get("received_q"), payload.get("change_q")
        if payload.get("method"):
            parts.append(str(payload["method"]))
        if received:
            parts.append(f"recebido R$ {format_money(int(received))}")
        if change:
            parts.append(f"troco R$ {format_money(int(change))}")
    elif kind == Entry.Kind.COUNT:
        parts.append(f"contado R$ {format_money(int(payload.get('counted_q') or 0))}")
        if payload.get("supervisory"):
            parts.append("fechamento supervisório")
        if payload.get("notes"):
            parts.append(str(payload["notes"]))
    elif kind == Entry.Kind.CHANGE_REQUESTED:
        parts.append(str(payload.get("kind") or ""))
        if payload.get("amount_q"):
            parts.append(f"R$ {format_money(int(payload['amount_q']))}")
        if payload.get("note"):
            parts.append(str(payload["note"]))
    elif kind == Entry.Kind.DRAWER_UNLOCK and payload.get("drawer_raw"):
        parts.append(f"sensor {payload['drawer_raw']}")
    elif kind == Entry.Kind.RECEIPT_RESULT:
        parts.append(str(payload.get("status") or ""))
        if payload.get("detail"):
            parts.append(str(payload["detail"]))
    elif kind == Entry.Kind.NOTE and payload.get("text"):
        parts.append(str(payload["text"]))
    if entry.reason:
        parts.append(entry.reason)
    if entry.approved_by_id:
        parts.append(f"autorizado por {entry.approved_by.get_username()}")
    if entry.order_ref:
        parts.append(f"pedido {entry.order_ref}")
    return " · ".join(p for p in parts if p)


class EntryInline(BaseTabularInline):
    """A linha do tempo do turno. Só leitura, em ordem cronológica."""

    model = Entry
    fk_name = "shift"
    extra = 0
    can_delete = False
    verbose_name = _("lançamento")
    verbose_name_plural = _("linha do tempo do turno")
    fields = ("at_display", "kind_badge", "amount_display", "operator", "detail_display")
    readonly_fields = fields
    ordering = ("at", "id")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(description=_("Quando"))
    def at_display(self, obj):
        return obj.at.strftime("%d/%m %H:%M")

    @display(description=_("Tipo"))
    def kind_badge(self, obj):
        return unfold_badge(obj.get_kind_display(), _KIND_COLORS.get(obj.kind, "base"))

    @display(description=_("Efeito"))
    def amount_display(self, obj):
        if obj.amount_q == 0:
            return "—"
        return unfold_badge_numeric(_money(obj.amount_q), "green" if obj.amount_q > 0 else "orange")

    @display(description=_("Detalhe"))
    def detail_display(self, obj):
        return entry_detail(obj)


@admin.register(Terminal)
class TerminalAdmin(BaseModelAdmin):
    list_display = ("ref", "label", "channel_ref", "location_ref", "active_badge")
    list_filter = ("is_active", "channel_ref")
    search_fields = ("ref", "label", "location_ref")
    ordering = ("ref",)
    compressed_fields = True

    @display(description=_("Ativo"))
    def active_badge(self, obj):
        return unfold_badge("ativo" if obj.is_active else "inativo", "green" if obj.is_active else "base")


@admin.register(Shift)
class ShiftAdmin(BaseModelAdmin):
    """Só leitura: o turno nasce e fecha pelo PDV; aqui se confere."""

    list_display = (
        "operator",
        "terminal",
        "opened_at",
        "status_badge",
        "expected_display",
        "counted_display",
        "difference_display",
    )
    list_filter = ("status", "terminal", "opened_at")
    # ``operator`` é FK para User: buscar nele direto vira ``operator__icontains``,
    # que o Django recusa em relação e derruba a busca global inteira.
    search_fields = ("operator__username", "operator__first_name", "operator__last_name", "terminal__ref", "terminal__label")
    readonly_fields = (
        "terminal",
        "operator",
        "opened_at",
        "closed_at",
        "status",
        "expected_display",
        "counted_display",
        "difference_display",
    )
    inlines = [EntryInline]
    ordering = ("-opened_at",)
    list_fullwidth = True
    compressed_fields = True

    def get_queryset(self, request):
        # Esperado, diferença e "houve contagem?" são somas do livro. Anotar
        # aqui evita um `Σ` por linha na lista sem criar coluna no turno (não
        # ter a coluna é o que garante o fechamento cego por construção).
        counting = Q(entries__kind__in=[Entry.Kind.COUNT, Entry.Kind.COUNT_CORRECTION])
        return (
            super()
            .get_queryset(request)
            .select_related("operator", "terminal")
            .annotate(
                _expected_q=Sum("entries__amount_q", filter=~counting),
                _difference_q=Sum("entries__amount_q", filter=counting),
                _counts=Count("entries", filter=Q(entries__kind=Entry.Kind.COUNT)),
            )
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("cashman.operate_pos") or request.user.has_perm("cashman.audit_shift")

    @display(description=_("Status"))
    def status_badge(self, obj):
        return unfold_badge(obj.get_status_display().lower(), "yellow" if obj.is_open else "green")

    @display(description=_("Esperado"))
    def expected_display(self, obj):
        return f"R$ {format_money(int(_annotated(obj, '_expected_q', lambda: ledger.expected_before_count(obj)) or 0))}"

    @display(description=_("Contado"))
    def counted_display(self, obj):
        if not _has_count(obj):
            return "—"
        expected = int(_annotated(obj, "_expected_q", lambda: ledger.expected_before_count(obj)) or 0)
        difference = int(_annotated(obj, "_difference_q", lambda: ledger.difference(obj)) or 0)
        return f"R$ {format_money(expected + difference)}"

    @display(description=_("Diferença"))
    def difference_display(self, obj):
        if not _has_count(obj):
            return "—"
        difference = int(_annotated(obj, "_difference_q", lambda: ledger.difference(obj)) or 0)
        return unfold_badge_numeric(_money(difference), "green" if difference == 0 else "yellow")


def _annotated(obj, name: str, fallback):
    """Usa a anotação da lista quando existe; na tela de detalhe, calcula do livro."""
    value = getattr(obj, name, None)
    return fallback() if value is None and not hasattr(obj, name) else value


def _has_count(obj) -> bool:
    if hasattr(obj, "_counts"):
        return bool(obj._counts)
    return obj.entries.filter(kind=Entry.Kind.COUNT).exists()
