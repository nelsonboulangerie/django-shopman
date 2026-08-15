"""DayClosing admin — readonly day-closing records."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from shopman.utils import unfold_badge_numeric, unfold_link
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import DayClosing


@admin.register(DayClosing)
class DayClosingAdmin(ModelAdmin):
    list_display = ("date", "closed_by", "closed_at", "items_count_display", "errors_count_display", "operation_link_display")
    list_filter = ("closed_by",)
    date_hierarchy = "date"
    # ``closed_by`` é FK para User — buscar nele direto quebra a busca global
    # inteira com FieldError (icontains em relação). Atravesse até o texto.
    search_fields = ("closed_by__username", "closed_by__first_name", "closed_by__last_name")
    readonly_fields = ("date", "closed_by", "closed_at", "notes", "data")
    compressed_fields = True
    list_fullwidth = True

    @display(description="itens")
    def items_count_display(self, obj):
        data = obj.data if isinstance(obj.data, dict) else {"items": obj.data or []}
        return unfold_badge_numeric(str(len(data.get("items") or [])), "base")

    @display(description="discrepâncias")
    def errors_count_display(self, obj):
        data = obj.data if isinstance(obj.data, dict) else {}
        count = len(data.get("reconciliation_errors") or [])
        return unfold_badge_numeric(str(count), "red" if count else "green")

    @display(description="operação")
    def operation_link_display(self, obj):
        # Relatórios vivem no /reports do Produção (WP-ADM-7d); sem base URL
        # configurada não há link morto.
        base = (getattr(settings, "SHOPMAN_PRODUCTION_BASE_URL", "") or "").rstrip("/")
        if not base:
            return "-"
        url = f"{base}/reports?date_from={obj.date.isoformat()}&date_to={obj.date.isoformat()}"
        return unfold_link(url, "Relatório", icon="table_chart")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.perform_closing")
