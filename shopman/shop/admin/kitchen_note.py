"""Os atalhos da nota da cozinha, com o "vale para" de cada um (decisão do dono, 21/11/2026)."""

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import KitchenNoteTag


@admin.register(KitchenNoteTag)
class KitchenNoteTagAdmin(ModelAdmin):
    list_display = ("label", "position", "applies_to")
    list_editable = ("position",)
    search_fields = ("label",)
    ordering = ("position", "label")
    autocomplete_fields = ("collections", "products")
    fieldsets = (
        (
            None,
            {
                "fields": ("label", "position"),
                "description": (
                    "O Caixa anexa o atalho com um toque à nota da cozinha de um pedido no Gestor, "
                    "e a nota sai no ticket da Cozinha. Escreva instruções curtas."
                ),
            },
        ),
        (
            "Vale para",
            {
                "fields": ("collections", "products"),
                "description": (
                    "O pedido mostra o atalho só se tiver algum produto destas categorias ou "
                    "algum destes produtos. Deixe os dois vazios para valer em todo pedido."
                ),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("collections", "products")

    @display(description="vale para")
    def applies_to(self, obj: KitchenNoteTag) -> str:
        names = [collection.name for collection in obj.collections.all()]
        names += [product.name for product in obj.products.all()]
        return ", ".join(names) if names else "Todos os pedidos"
