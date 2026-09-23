"""Conferência do piloto de intenções — a máquina sugere, a casa confere.

Três telas. **Intenções** é o vocabulário (editável: é a decisão do dono, e muda
sem código). **Mensagens para rotular** é a fila que o ciclo automático enche e
pré-marca: a pessoa lê a mensagem **redigida** (o mesmo texto que os
classificadores recebem), vê as intenções sugeridas, corrige o que discorda e
salva — ou, na lista, confere várias de uma vez com "Confirmar sugestões". Salvar
carimba quem e quando; a fila anda sozinha para a próxima. **Placar das
intenções** é só leitura: o que o ciclo mediu, sem texto de cliente.

A mensagem nunca é editada aqui, nem copiada: a amostra aponta para ela, e
apagar a mensagem (retenção, pedido do titular) apaga a amostra junto.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.widgets import UnfoldAdminCheckboxSelectMultipleWidget

from shopman.storefront.models import IntentCategory, IntentPilotReport, MessageIntentSample, SampleStatus

_STATUS_LABELS = {
    "a rotular": "warning",
    "sugerida": "info",
    "conferida": "success",
    "pulada": "danger",
}
_OPEN = (SampleStatus.PROPOSED, SampleStatus.PENDING)


@admin.register(IntentCategory)
class IntentCategoryAdmin(ModelAdmin):
    list_display = ("position", "name", "ref", "description", "sensitive", "active")
    list_display_links = ("name",)
    list_editable = ("position",)
    list_filter = ("active", "sensitive")
    search_fields = ("ref", "name", "description")
    ordering = ("position", "id")
    fields = ("name", "ref", "description", "sensitive", "position", "active")


class MessageIntentSampleForm(forms.ModelForm):
    class Meta:
        model = MessageIntentSample
        fields = ("intents", "status", "note")
        widgets = {"intents": UnfoldAdminCheckboxSelectMultipleWidget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["intents"].queryset = IntentCategory.objects.filter(active=True).order_by("position", "id")
        # Quem abre para conferir está conferindo: o default do formulário já é o
        # estado que o salvar vai gravar.
        if self.instance.status in _OPEN:
            self.initial["status"] = SampleStatus.LABELED


@admin.register(MessageIntentSample)
class MessageIntentSampleAdmin(ModelAdmin):
    form = MessageIntentSampleForm
    list_display = ("id", "text_preview", "intents_display", "status_display", "labeled_by", "labeled_at")
    list_display_links = ("id", "text_preview")
    list_filter = ("status", "intents")
    ordering = ("status", "id")
    list_per_page = 50
    fields = ("redacted_text_display", "intents", "status", "note", "suggested_by", "labeled_by", "labeled_at")
    readonly_fields = ("redacted_text_display", "suggested_by", "labeled_by", "labeled_at")
    actions = ("confirm_suggestions", "skip_selected")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("message", "labeled_by").prefetch_related("intents")

    def has_add_permission(self, request):
        return False  # a fila nasce do sorteio, não à mão

    @display(description="mensagem (redigida)")
    def text_preview(self, obj):
        text = obj.redacted_text()
        return text if len(text) <= 90 else f"{text[:87]}…"

    @display(description="mensagem do cliente (redigida)")
    def redacted_text_display(self, obj):
        return obj.redacted_text() or "—"

    @display(description="intenções")
    def intents_display(self, obj):
        if obj.status not in (SampleStatus.LABELED, SampleStatus.PROPOSED):
            return "—"
        names = ", ".join(intent.name for intent in obj.intents.all()) or "nenhuma da lista"
        return f"sugerido: {names}" if obj.status == SampleStatus.PROPOSED else names

    @display(description="estado", label=_STATUS_LABELS)
    def status_display(self, obj):
        return obj.get_status_display()

    def save_model(self, request, obj, form, change):
        # Rotular pelo formulário assina sempre; voltar para "a rotular" apaga a
        # assinatura, para o gabarito nunca ter rótulo sem dono.
        if obj.status == SampleStatus.LABELED:
            obj.mark_labeled(request.user)
        else:
            obj.labeled_by = None
            obj.labeled_at = None
        super().save_model(request, obj, form, change)

    def response_change(self, request, obj):
        # Depois de salvar uma, a próxima da fila — rotular 200 mensagens não
        # pode custar 200 voltas pela lista.
        if "_continue" not in request.POST and "_addanother" not in request.POST:
            queue = MessageIntentSample.objects.exclude(pk=obj.pk).order_by("id")
            # Primeiro as sugeridas (conferir é rápido), depois as que a máquina não marcou.
            following = (
                queue.filter(status=SampleStatus.PROPOSED).first()
                or queue.filter(status=SampleStatus.PENDING).first()
            )
            if following is not None:
                self.message_user(request, f"Mensagem {obj.pk} conferida. Esta é a próxima.")
                return HttpResponseRedirect(
                    reverse("admin:storefront_messageintentsample_change", args=[following.pk])
                )
        return super().response_change(request, obj)

    @admin.action(description="Confirmar sugestões selecionadas como estão")
    def confirm_suggestions(self, request, queryset):
        count = 0
        for sample in queryset.filter(status=SampleStatus.PROPOSED):
            sample.mark_labeled(request.user)
            sample.save(update_fields=["status", "labeled_by", "labeled_at"])
            count += 1
        ignored = queryset.count() - count
        message = f"{count} sugestão(ões) confirmada(s): entram no gabarito."
        if ignored:
            message += f" {ignored} ignorada(s): só se confirma o que a máquina sugeriu."
        self.message_user(request, message)

    @admin.action(description="Pular selecionadas (ininteligível, fora de contexto)")
    def skip_selected(self, request, queryset):
        count = queryset.update(status=SampleStatus.SKIPPED, labeled_by=None, labeled_at=None)
        self.message_user(request, f"{count} mensagem(ns) pulada(s): ficam fora do gabarito.")


@admin.register(IntentPilotReport)
class IntentPilotReportAdmin(ModelAdmin):
    list_display = ("created_at", "samples", "contenders")
    ordering = ("-created_at",)
    fields = ("created_at", "samples", "contenders", "report", "skipped")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
