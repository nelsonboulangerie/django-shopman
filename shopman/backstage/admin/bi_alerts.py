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

from shopman.backstage.models import BIAlertEvent, BIAlertRule, BIScenarioReport
from shopman.backstage.permissions import can_audit_cash


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
        if obj.metric in BIAlertRule.AUDIT_ONLY_METRICS and not can_audit_cash(self._request_user):
            # Apuração de caixa: quem opera vê que houve disparo, não quem nem quanto.
            return f"{prefix}apuração de caixa — detalhe só para quem audita"
        return f"{prefix}{reading.get('message', '')}"

    _request_user = None

    def changelist_view(self, request, extra_context=None):
        self._request_user = request.user
        return super().changelist_view(request, extra_context)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None and obj.metric in BIAlertRule.AUDIT_ONLY_METRICS and not can_audit_cash(request.user):
            # Sem o bloco "Última avaliação": a leitura traz nome e valor.
            return tuple(fs for fs in fieldsets if fs[0] != "Última avaliação")
        return fieldsets

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

    def get_queryset(self, request):
        # Disparo de apuração de caixa traz nome e valor: só para quem audita.
        queryset = super().get_queryset(request)
        if can_audit_cash(request.user):
            return queryset
        return queryset.exclude(rule__metric__in=BIAlertRule.AUDIT_ONLY_METRICS)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BIScenarioReport)
class BIScenarioReportAdmin(ModelAdmin):
    """O que a IA viu e o que propôs, versionado. Só leitura: relatório que muda depois de lido não vale."""

    list_display = ("generated_at", "focus", "status", "requested_by", "model", "duration_ms", "scenarios_display")
    list_filter = ("focus", "status")
    date_hierarchy = "generated_at"
    ordering = ("-generated_at",)
    fields = (
        "generated_at", "requested_by", "focus", "window_from", "window_to", "model", "status",
        "duration_ms", "inputs_hash", "scenarios", "error", "raw_text", "inputs",
    )
    readonly_fields = fields

    @display(description="cenários")
    def scenarios_display(self, obj):
        return f"{len(obj.scenarios or [])} cenário(s)" if obj.status == "done" else (obj.error[:80] or "falhou")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
