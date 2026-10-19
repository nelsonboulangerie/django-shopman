"""Trilha do apply do descritor de Instância, somente leitura.

O apply só insere (``config/instance_descriptors.py``): a linha é evidência de
quem aplicou, quando e o que mudou, e é a base da comparação de três vias do
próximo apply. Editar ou apagar uma linha aqui mudaria o que o próximo apply
considera "mudado por fora", então o Admin só mostra.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import InstanceApplyRecord


@admin.register(InstanceApplyRecord)
class InstanceApplyRecordAdmin(ModelAdmin):
    list_display = (
        "applied_at",
        "instance_ref",
        "schema_version",
        "descriptor_short_hash",
        "on_drift",
        "change_count",
        "actor",
    )
    list_filter = ("instance_ref", "on_drift", "applied_at")
    search_fields = ("instance_ref", "actor", "descriptor_sha256")
    ordering = ("-applied_at", "-pk")
    date_hierarchy = "applied_at"
    actions = ()
    list_per_page = 50
    show_full_result_count = False
    readonly_fields = (
        "instance_ref",
        "schema_version",
        "descriptor_sha256",
        "actor",
        "on_drift",
        "applied_at",
        "changes",
        "descriptor",
    )
    fieldsets = (
        ("Aplicação", {"fields": ("instance_ref", "applied_at", "actor", "on_drift")}),
        ("Descritor", {"fields": ("schema_version", "descriptor_sha256", "descriptor")}),
        ("Mudanças", {"fields": ("changes",)}),
    )

    @display(description="hash", ordering="descriptor_sha256")
    def descriptor_short_hash(self, obj):
        return obj.descriptor_sha256[:12]

    @display(description="mudanças")
    def change_count(self, obj):
        return len(obj.changes or [])

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
