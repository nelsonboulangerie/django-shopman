"""A curadoria dos de-paras do B.I. — onde a pessoa confirma o que a máquina propôs.

Três telas, uma disciplina: tudo o que chega aqui é PROPOSTA até alguém dizer
que sim. `suggest_aliases` preenche a fila com o melhor palpite e a confiança;
o gestor confirma, corrige o alvo ou rejeita. Só o confirmado entra na leitura
do B.I. — por isso a coluna de estado é a primeira coisa que se vê, e por isso
"confirmar" carimba quem e quando (a assinatura da curadoria).

Categoria e forma de pagamento são vocabulários por trecho, **em ordem**: a
posição decide quem vence quando dois trechos casam. A lista já vem ordenada
por posição para que a pessoa veja a fila do jeito que a regra a lê.
"""

from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import (
    AliasStatus,
    CategoryAlias,
    PaymentMethodAlias,
    ProductAlias,
)

_STATUS_LABELS = {
    "proposto": "warning",
    "confirmado": "success",
    "rejeitado": "danger",
}


class _AliasAdmin(ModelAdmin):
    """O que as três telas compartilham: estado visível, ações, assinatura."""

    actions = ("confirm_selected", "reject_selected")
    list_per_page = 100

    @display(description="estado", label=_STATUS_LABELS)
    def status_display(self, obj):
        return obj.get_status_display()

    @display(description="confiança")
    def score_display(self, obj):
        return f"{obj.score}%" if obj.score is not None else "à mão"

    def save_model(self, request, obj, form, change):
        # Confirmar pelo formulário assina igual a confirmar pela ação: quem
        # confirmou e quando não podem depender do caminho que a pessoa tomou.
        if obj.status == AliasStatus.CONFIRMED and obj.confirmed_at is None:
            obj.mark_confirmed(request.user)
        elif obj.status != AliasStatus.CONFIRMED:
            obj.confirmed_by = None
            obj.confirmed_at = None
        super().save_model(request, obj, form, change)

    @admin.action(description="Confirmar selecionados")
    def confirm_selected(self, request, queryset):
        confirmed, refused = 0, 0
        for alias in queryset:
            alias.mark_confirmed(request.user)
            try:
                alias.full_clean()
            except ValidationError:
                refused += 1
                continue
            alias.save()
            confirmed += 1
        message = f"{confirmed} de-para(s) confirmado(s)."
        if refused:
            message += f" {refused} recusado(s): falta dizer o que significam (alvo, leitura ou forma)."
        self.message_user(request, message)

    @admin.action(description="Rejeitar selecionados")
    def reject_selected(self, request, queryset):
        count = 0
        for alias in queryset:
            alias.mark_rejected()
            alias.save()
            count += 1
        self.message_user(request, f"{count} de-para(s) rejeitado(s).")


@admin.register(ProductAlias)
class ProductAliasAdmin(_AliasAdmin):
    list_display = (
        "external_sku", "external_name", "product", "score_display", "status_display", "note",
    )
    list_filter = ("status", "source")
    search_fields = ("external_sku", "external_name", "product__sku", "product__name", "note")
    ordering = ("status", "-score", "external_sku")
    autocomplete_fields = ("product",)
    fields = (
        "source", "external_sku", "external_name", "product",
        "status", "score", "note", "confirmed_by", "confirmed_at",
    )
    readonly_fields = ("score", "confirmed_by", "confirmed_at")


@admin.register(CategoryAlias)
class CategoryAliasAdmin(_AliasAdmin):
    list_display = ("position", "pattern", "reading", "collection", "status_display", "note")
    list_display_links = ("pattern",)
    list_editable = ("position",)
    list_filter = ("status", "reading")
    search_fields = ("pattern", "note")
    ordering = ("position", "id")
    autocomplete_fields = ("collection",)
    fields = ("pattern", "position", "reading", "collection", "status", "note", "confirmed_by", "confirmed_at")
    readonly_fields = ("confirmed_by", "confirmed_at")


@admin.register(PaymentMethodAlias)
class PaymentMethodAliasAdmin(_AliasAdmin):
    list_display = ("position", "pattern", "method_key", "status_display", "note")
    list_display_links = ("pattern",)
    list_editable = ("position",)
    list_filter = ("status", "method_key")
    search_fields = ("pattern", "method_key", "note")
    ordering = ("position", "id")
    fields = ("pattern", "position", "method_key", "status", "note", "confirmed_by", "confirmed_at")
    readonly_fields = ("confirmed_by", "confirmed_at")
