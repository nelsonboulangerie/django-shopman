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
    list_display = (
        "label", "ref", "hint", "reading_display", "beverage_display", "ordering", "is_active",
    )
    list_editable = ("ordering", "is_active")
    ordering = ("ordering",)
    fields = ("ref", "label", "hint", "reading", "beverage", "ordering", "is_active")

    def get_readonly_fields(self, request, obj=None):
        # Etiquetas gravadas apontam para o ref; o rótulo edita à vontade.
        return ("ref",) if obj else ()

    @display(
        description="o que a cesta passa a dizer",
        label={"Consome aqui": "success", "Leva": "info", "Híbrido": "warning"},
    )
    def reading_display(self, obj):
        return obj.get_reading_display()

    @display(description="bebida")
    def beverage_display(self, obj):
        # Bebida é fato à parte da leitura: conta no strike rate e nas bebidas
        # por pedido, e não muda quem sentou.
        return obj.get_beverage_display() if obj.beverage else ""

    def has_delete_permission(self, request, obj=None):
        # Apagar um papel em uso deixaria produtos sem classificação e mudaria
        # a leitura do passado sem aviso. Sai de circulação desativando.
        return False


@admin.register(ProductConsumptionTag)
class ProductConsumptionTagAdmin(ModelAdmin):
    """A curadoria acontece aqui — e a proposta fica visível como proposta.

    `propose_consumption_tags` preenche a lista a partir das coleções do
    catálogo, mas nada do que ele escreve entra como revisado. Filtre por
    "revisada = não" para ver o que ainda espera por gente.
    """

    list_display = ("sku", "role", "review_display", "note", "updated_at")
    list_filter = ("reviewed", "role")
    search_fields = ("sku", "note")
    ordering = ("reviewed", "sku")
    fields = ("sku", "role", "note", "reviewed")
    list_per_page = 100
    actions = ("mark_reviewed",)

    @display(
        description="curadoria",
        label={"revisada": "success", "proposta — revisar": "warning"},
    )
    def review_display(self, obj):
        return "revisada" if obj.reviewed else "proposta — revisar"

    @admin.action(description="Marcar como revisada")
    def mark_reviewed(self, request, queryset):
        updated = queryset.update(reviewed=True)
        self.message_user(request, f"{updated} etiqueta(s) marcada(s) como revisada(s).")
