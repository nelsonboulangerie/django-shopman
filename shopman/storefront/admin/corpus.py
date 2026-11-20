"""A conferência do corpus anonimizado (dono, 20/11/2026, #2851).

O curador (``shop.review_conversation_observations``, a mesma permissão de quem revisa a
observação) confere a amostra da semana: sem dado pessoal, ou achou dado pessoal. Achar
pausa a cópia (``concierge.corpus.paused``) até o curador apagar a linha: apagar é o
tratamento, e só o achado pode ser apagado à mão.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.storefront.models import ConversationCorpusEntry, CorpusReview

OBSERVATION_PERMISSION = "shop.review_conversation_observations"

_REVIEW_LABELS = {
    CorpusReview.NOT_SAMPLED.label: "info",
    CorpusReview.PENDING.label: "warning",
    CorpusReview.CLEAN.label: "success",
    CorpusReview.PERSONAL_DATA.label: "danger",
}
_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@admin.register(ConversationCorpusEntry)
class ConversationCorpusEntryAdmin(ModelAdmin):
    list_display = ("id", "text_preview", "intent", "outcome", "when_display", "review_display")
    list_display_links = ("id", "text_preview")
    list_filter = ("review", "outcome", "sample_week")
    ordering = ("review", "-id")
    list_per_page = 50
    fields = ("text", "redactions", "intent", "outcome", "channel", "when_display", "review", "review_note",
              "reviewed_by")
    readonly_fields = ("text", "redactions", "intent", "outcome", "channel", "when_display", "reviewed_by")
    actions = ("mark_clean", "mark_personal_data")

    def has_add_permission(self, request):
        return False  # o corpus nasce da cópia, não à mão

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(OBSERVATION_PERMISSION) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(OBSERVATION_PERMISSION) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Só a linha com dado pessoal achado: apagá-la é o que despausa a cópia.
        if obj is not None and obj.review != CorpusReview.PERSONAL_DATA:
            return False
        return request.user.has_perm(OBSERVATION_PERMISSION) and super().has_delete_permission(request, obj)

    def has_module_permission(self, request):
        return request.user.has_perm(OBSERVATION_PERMISSION) and super().has_module_permission(request)

    @display(description="mensagem (anonimizada)")
    def text_preview(self, obj):
        return obj.text if len(obj.text) <= 90 else f"{obj.text[:87]}…"

    @display(description="quando")
    def when_display(self, obj):
        return f"{_WEEKDAYS[obj.weekday]}, das {obj.hour_band}h às {obj.hour_band + 3}h"

    @display(description="conferência", label=_REVIEW_LABELS)
    def review_display(self, obj):
        return obj.get_review_display()

    def save_model(self, request, obj, form, change):
        if obj.review in (CorpusReview.CLEAN, CorpusReview.PERSONAL_DATA):
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Conferidas: sem dado pessoal", permissions=["change"])
    def mark_clean(self, request, queryset):
        count = queryset.update(review=CorpusReview.CLEAN, reviewed_by=request.user)
        self.message_user(request, f"{count} mensagem(ns) conferida(s), sem dado pessoal.")

    @admin.action(description="Achou dado pessoal (pausa a cópia)", permissions=["change"])
    def mark_personal_data(self, request, queryset):
        count = queryset.update(review=CorpusReview.PERSONAL_DATA, reviewed_by=request.user)
        self.message_user(
            request,
            f"{count} mensagem(ns) com dado pessoal. A cópia para o corpus está pausada até essas linhas serem apagadas.",
        )
