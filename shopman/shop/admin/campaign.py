"""Admin de campanha — CRUD de regras e modelos, leitura dos announcements.

Divisão de papéis (feedback_admin_crud_config_only): o Admin configura
(regras, modelos de announcement); a revisão e a publicação são operação e vivem nas
superfícies de operador. Por isso ``Announcement`` entra aqui só para
auditoria, sem criação nem edição.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
)


@admin.register(AnnouncementTemplate)
class AnnouncementTemplateAdmin(ModelAdmin):
    list_display = ("name", "image_source", "use_ai_generation", "is_active")
    list_filter = ("is_active", "use_ai_generation", "image_source")
    search_fields = ("name", "body")
    list_editable = ("is_active",)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("conteúdo", {"fields": ("body", "variables", "platform_variants", "image_source")}),
        ("inteligência artificial", {"fields": ("use_ai_generation", "ai_prompt")}),
    )


@admin.register(Campaign)
class CampaignAdmin(ModelAdmin):
    list_display = (
        "name", "trigger_display", "next_occurrence_display", "template",
        "requires_approval", "is_active",
    )
    list_filter = ("is_active", "trigger", "requires_approval")
    search_fields = ("name",)
    list_editable = ("is_active",)
    autocomplete_fields = ("template",)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("gatilho", {"fields": ("trigger", "trigger_filter")}),
        ("conteúdo", {"fields": ("template", "platforms")}),
        ("audiência", {"fields": ("audience_rules",)}),
        (
            "publicação",
            {"fields": ("requires_approval", "expires_after_minutes", "notify_users", "schedule")},
        ),
    )

    @display(description="gatilho")
    def trigger_display(self, obj):
        return obj.get_trigger_display()

    @display(description="próxima ocasião")
    def next_occurrence_display(self, obj):
        """Quando esta campanha dispara sozinha — em português, na lista.

        Uma campanha agendada que nunca dispara é indistinguível de uma que ainda não
        disparou. Mostrar a data resolve isso sem o gestor abrir o JSON.
        """
        from shopman.shop.services import campaign_schedule as sched

        if not sched.fires_on_its_own(obj.schedule):
            return "—"
        if sched.next_occurrence(obj.schedule) is None:
            return "não dispara mais"
        return sched.describe_occurrence(obj.schedule)


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = (
        "created_at", "status_display", "rule", "audience_total",
        "rejection_display", "published_at",
    )
    list_filter = ("status", "rule")
    # O motivo entra na busca porque a pergunta útil raramente é "quantos" — é "por quê",
    # e ela se responde procurando "foto" ou "acabou" e vendo o padrão aparecer.
    search_fields = ("content", "rejected_reason")
    readonly_fields = (
        "rule", "template", "status", "content", "platform_content", "platforms",
        "audience", "platform_results", "trigger_context", "approved_by",
        "approved_at", "rejected_by", "rejected_at", "rejected_reason",
        "published_at", "expires_at", "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False  # announcements nascem de eventos, nunca da mão do gestor no Admin

    def has_change_permission(self, request, obj=None):
        return False

    @display(
        description="situação",
        label={
            "aguardando aprovação": "warning",
            "publicado": "success",
            "falhou": "danger",
            # Recusa é decisão, não falha: cinza, não vermelho. Pintar de vermelho o
            # gesto correto do gestor treina ele a evitar o botão.
            "recusado": "info",
            "expirado": "danger",
        },
    )
    def status_display(self, obj):
        return obj.get_status_display()

    @display(description="audiência")
    def audience_total(self, obj):
        return (obj.audience or {}).get("total", 0)

    @display(description="recusa")
    def rejection_display(self, obj):
        """Quem recusou e por quê, numa coluna — sem tabela de agregação nenhuma.

        É assim que o Admin responde "quantos anúncios o gestor recusou, e por quê":
        filtro por situação + esta coluna. A [ADR-020] fecha a porta para um quinto
        contador no painel, e ela está certa: contagem sem motivo não muda decisão.
        """
        if obj.status != AnnouncementStatus.REJECTED:
            return "—"
        who = obj.rejected_by
        name = (who.get_full_name() or who.username) if who else "sem autor"
        return f"{name}: {obj.rejected_reason}" if obj.rejected_reason else name
