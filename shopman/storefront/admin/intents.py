"""Rotulagem do piloto de intenções — onde a casa diz o que o cliente quis.

Duas telas. **Intenções** é o vocabulário (editável: é a decisão do dono, e muda
sem código). **Mensagens para rotular** é a fila que o ``sample_intent_messages``
preenche: a pessoa lê a mensagem **redigida** (o mesmo texto que os
classificadores recebem), marca TODAS as intenções que ela carrega — ou nenhuma
— e salva. Salvar carimba quem e quando; a fila anda sozinha para a próxima a
rotular.

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

from shopman.storefront.models import IntentCategory, MessageIntentSample, SampleStatus

_STATUS_LABELS = {
    "a rotular": "warning",
    "rotulada": "success",
    "pulada": "info",
}


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
        # Quem abre para rotular está rotulando: o default do formulário já é o
        # estado que o salvar vai gravar.
        if self.instance.status == SampleStatus.PENDING:
            self.initial["status"] = SampleStatus.LABELED


@admin.register(MessageIntentSample)
class MessageIntentSampleAdmin(ModelAdmin):
    form = MessageIntentSampleForm
    list_display = ("id", "text_preview", "intents_display", "status_display", "labeled_by", "labeled_at")
    list_display_links = ("id", "text_preview")
    list_filter = ("status", "intents")
    ordering = ("status", "id")
    list_per_page = 50
    fields = ("redacted_text_display", "intents", "status", "note", "labeled_by", "labeled_at")
    readonly_fields = ("redacted_text_display", "labeled_by", "labeled_at")
    actions = ("skip_selected",)

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
        names = [intent.name for intent in obj.intents.all()]
        if obj.status != SampleStatus.LABELED:
            return "—"
        return ", ".join(names) or "nenhuma da lista"

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
            following = (
                MessageIntentSample.objects.filter(status=SampleStatus.PENDING).exclude(pk=obj.pk).order_by("id").first()
            )
            if following is not None:
                self.message_user(request, f"Mensagem {obj.pk} salva. Esta é a próxima a rotular.")
                return HttpResponseRedirect(
                    reverse("admin:storefront_messageintentsample_change", args=[following.pk])
                )
        return super().response_change(request, obj)

    @admin.action(description="Pular selecionadas (ininteligível, fora de contexto)")
    def skip_selected(self, request, queryset):
        count = queryset.update(status=SampleStatus.SKIPPED, labeled_by=None, labeled_at=None)
        self.message_user(request, f"{count} mensagem(ns) pulada(s): ficam fora do gabarito.")
