"""Canonical Unfold CRUD for public frequently asked questions."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.shop.models import FAQEntry


@admin.register(FAQEntry)
class FAQEntryAdmin(ModelAdmin):
    list_display = ("question", "position", "is_published", "updated_at")
    list_editable = ("position", "is_published")
    list_filter = ("is_published",)
    search_fields = ("question", "answer", "search_terms")
    ordering = ("position", "id")
    readonly_fields = ("ref", "created_at", "updated_at")
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
        ("Publicação", {"fields": ("is_published", "position", "ref", "created_at", "updated_at")}),
    )
