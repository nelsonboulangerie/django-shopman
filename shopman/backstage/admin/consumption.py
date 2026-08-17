"""Etiquetas que ensinam a cesta a dizer quem sentou e quem levou.

Config, não operação: ninguém no balcão passa por aqui. O gestor etiqueta o
cardápio uma vez, e a inferência do modo de consumo passa a valer — inclusive
para trás, sobre o histórico externo.

⚠️ **Etiqueta é decisão de negócio, não detalhe técnico.** Mudar o papel de um
produto muda números já publicados, inclusive de meses passados. Por isso o
campo de observação existe: quando o nome do produto engana (o "Hambúrguer 100g"
é o **pão**, não o sanduíche), quem etiquetou escreve o porquê e quem revisar
daqui a um ano não desfaz sem saber.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag


@admin.register(ConsumptionRole)
class ConsumptionRoleAdmin(ModelAdmin):
    list_display = ("label", "ref", "hint", "reading_display", "ordering", "is_active")
    list_editable = ("ordering", "is_active")
    ordering = ("ordering",)
    fields = ("ref", "label", "hint", "anchors_dine_in", "travels", "ordering", "is_active")

    def get_readonly_fields(self, request, obj=None):
        # Etiquetas gravadas apontam para o ref; o rótulo edita à vontade.
        return ("ref",) if obj else ()

    @display(
        description="o que a cesta passa a dizer",
        label={
            "ancora consumo local": "success",
            "item de levar": "info",
            "neutro": "warning",
        },
    )
    def reading_display(self, obj):
        if obj.anchors_dine_in:
            return "ancora consumo local"
        if obj.travels:
            return "item de levar"
        return "neutro"

    def has_delete_permission(self, request, obj=None):
        # Apagar um papel em uso deixaria produtos sem classificação e mudaria
        # a leitura do passado sem aviso. Sai de circulação desativando.
        return False


@admin.register(ProductConsumptionTag)
class ProductConsumptionTagAdmin(ModelAdmin):
    list_display = ("sku", "role", "note", "updated_at")
    list_filter = ("role",)
    search_fields = ("sku", "note")
    autocomplete_fields = ()
    ordering = ("sku",)
    fields = ("sku", "role", "note")
    list_per_page = 100
