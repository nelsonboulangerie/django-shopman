"""O "Separado" da Preparação, no Admin: somente leitura.

Quem marca é quem separa, no tablet, com o PIN (WP-F09a). Aqui o gestor confere o
que aconteceu: o item, o dia, a quantidade separada, quem fez o último gesto e a
história de cada marca. Nada se cria, se edita ou se apaga pela tela: uma marca
editada no Admin seria uma conferência que ninguém fez na bancada.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import PrepChecklistMark


@admin.register(PrepChecklistMark)
class PrepChecklistMarkAdmin(ModelAdmin):
    list_display = ("prep_date", "item_ref", "quantity", "checked_display", "marked_by_name", "marked_at")
    list_filter = ("checked", "prep_date")
    search_fields = ("item_ref", "marked_by_name")
    readonly_fields = (
        "prep_date",
        "item_ref",
        "quantity",
        "checked",
        "marked_by",
        "marked_by_name",
        "marked_at",
        "history",
    )
    date_hierarchy = "prep_date"
    ordering = ("-prep_date", "item_ref")
    list_per_page = 50
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="separado", label={"separado": "success", "desmarcado": "warning"})
    def checked_display(self, obj):
        return "separado" if obj.checked else "desmarcado"
