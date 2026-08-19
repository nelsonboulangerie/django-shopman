"""Alarmes do B.I. — a régua é do gestor, o disparo é trilha.

A regra se edita (métrica, percentual, cadência, severidade, silêncio após
disparar); o que a última avaliação viu fica à vista na lista, para que "o
alarme não disparou" e "o alarme não tinha amostra para opinar" sejam coisas
distintas na tela. Os disparos são somente leitura: o que o sistema mediu num
instante não se reescreve.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import BIAlertEvent, BIAlertRule


@admin.register(BIAlertRule)
class BIAlertRuleAdmin(ModelAdmin):
    list_display = ("label", "metric", "active_display", "severity", "cooldown_minutes", "reading_display", "last_fired_at")
    list_filter = ("metric", "is_active", "severity")
    search_fields = ("ref", "label")
    ordering = ("label",)
    fieldsets = (
        (None, {"fields": ("ref", "label", "metric", "is_active", "severity", "cooldown_minutes")}),
        ("Importação esperada não chegou", {"fields": ("source", "expected_every_days")}),
        ("Faturamento abaixo do esperado", {"fields": ("threshold_percent", "baseline_weeks")}),
        ("Última avaliação", {"fields": ("last_evaluated_at", "last_fired_at", "last_reading")}),
    )
    readonly_fields = ("last_evaluated_at", "last_fired_at", "last_reading")

    def get_readonly_fields(self, request, obj=None):
        # A ref é a identidade do alarme nos disparos já gravados.
        return self.readonly_fields + (("ref",) if obj else ())

    @display(description="estado", label={"ativo": "success", "desligado": "base"})
    def active_display(self, obj):
        return "ativo" if obj.is_active else "desligado"

    @display(description="última leitura")
    def reading_display(self, obj):
        reading = obj.last_reading or {}
        if not reading:
            return "ainda não avaliado"
        prefix = "DISPAROU · " if reading.get("fired") else ""
        return f"{prefix}{reading.get('message', '')}"

    def has_delete_permission(self, request, obj=None):
        # Disparos apontam para a regra (PROTECT). Sai de circulação desligando.
        return False


@admin.register(BIAlertEvent)
class BIAlertEventAdmin(ModelAdmin):
    list_display = ("fired_at", "rule", "severity", "value", "baseline", "message")
    list_filter = ("rule", "severity")
    date_hierarchy = "fired_at"
    ordering = ("-fired_at",)
    fields = ("rule", "fired_at", "severity", "value", "baseline", "message", "operator_alert")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
