"""O registro da decisão em sombra (N5), somente leitura.

A linha é evidência: o que o framework de comércio conversacional faria com uma entrada da
Concierge, e os pedidos do cliente depois. Editar ou apagar mudaria a medida que a sombra
existe para dar, então o Admin só mostra. O que deriva de uma observação sai junto com ela,
pela retenção (``service.purge_observations``), nunca por aqui.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import ConversationalDecision, ConversationalOutcome


class _ReadOnly(ModelAdmin):
    actions = ()
    list_per_page = 50
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConversationalDecision)
class ConversationalDecisionAdmin(_ReadOnly):
    list_display = ("decided_at", "conversation_id", "moves", "profile_version", "lag")
    list_filter = ("environment", "profile_version", "decided_at")
    search_fields = ("decision_id", "customer_ref")
    ordering = ("-decided_at", "-pk")
    date_hierarchy = "decided_at"
    readonly_fields = ("decision_id", "conversation_id", "environment", "profile_version", "acts", "chosen_moves",
                       "blocked", "unknown_facts", "customer_ref", "entry_at", "decided_at", "decision_hash",
                       "snapshot_hash", "document")
    fieldsets = (
        ("Decisão", {"fields": ("decision_id", "decided_at", "entry_at", "environment", "profile_version")}),
        ("O que o framework faria", {"fields": ("acts", "chosen_moves", "blocked", "unknown_facts")}),
        ("Prova", {"fields": ("decision_hash", "snapshot_hash", "document")}),
    )

    @display(description="movimentos")
    def moves(self, obj):
        return ", ".join(obj.chosen_moves or []) or "nenhum"

    @display(description="atraso")
    def lag(self, obj):
        return obj.decided_at - obj.entry_at


@admin.register(ConversationalOutcome)
class ConversationalOutcomeAdmin(_ReadOnly):
    list_display = ("recorded_at", "decision", "metric", "observation", "value", "window_end")
    list_filter = ("metric", "observation")
    ordering = ("-recorded_at", "-pk")
    readonly_fields = ("decision", "outcome_id", "metric", "definition_version", "window_start", "window_end",
                       "observation", "value", "source", "supersedes", "recorded_at")
