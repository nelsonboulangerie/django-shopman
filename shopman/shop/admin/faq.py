"""Canonical Unfold CRUD for public frequently asked questions."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.concierge_verification import date_warning, origin_of
from shopman.shop.models import FAQEntry


@admin.register(FAQEntry)
class FAQEntryAdmin(ModelAdmin):
    list_display = ("question", "position", "is_published", "origin_label", "updated_at")
    list_editable = ("position", "is_published")
    list_filter = ("is_published",)
    search_fields = ("question", "answer", "search_terms")
    ordering = ("position", "id")
    readonly_fields = ("origin", "date_warning", "ref", "created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": ("question", "answer", "search_terms"),
                "description": (
                    "Esta resposta é pública: aparece no site e pode ser consultada pela Concierge. "
                    "Preço, estoque, taxa, cobertura e horários operacionais continuam vindo das projeções da loja."
                ),
            },
        ),
        # WP-15: o rascunho que nasceu de uma pergunta respondida pela equipe diz de onde veio.
        ("De onde veio", {"fields": ("origin", "date_warning")}),
        ("Publicação", {"fields": ("is_published", "position", "ref", "created_at", "updated_at")}),
    )

    @display(description="origem")
    def origin_label(self, obj: FAQEntry) -> str:
        return "Conversa da Concierge" if origin_of(obj.ref) else "Cadastrada no Admin"

    @display(description="de onde veio")
    def origin(self, obj: FAQEntry):
        found = origin_of(obj.ref) if obj and obj.pk else None
        if found is None:
            return "Cadastrada no Admin."
        conversation_pk, _record = found
        url = reverse("admin:shop_conversation_change", args=[conversation_pk])
        return format_html(
            'Promovida de uma pergunta que a equipe respondeu na <a href="{}">conversa #{}</a>.',
            url,
            conversation_pk,
        )

    @display(description="aviso")
    def date_warning(self, obj: FAQEntry) -> str:
        return (date_warning(obj.answer) if obj else "") or "Nenhum."
