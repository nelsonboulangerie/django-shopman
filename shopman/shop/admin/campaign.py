"""Auditoria de Marketing no Admin; toda operação fica no cockpit Nuxt.

O corte de ownership de G-H07 é deliberadamente estreito: campanha, modelo,
aprovação, disparo e recuperação têm um único dono, o Marketing Nuxt. O Admin
Unfold só oferece evidência agregada e sem PII para quem possui
``shop.audit_marketing``. Membership e alvos de entrega não são registrados.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    AudienceSnapshot,
    Campaign,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingPlatformAuditEvent,
    MarketingSecurityEvent,
)

_PLATFORM_LABELS = {
    "facebook": "Facebook",
    "google_business": "Perfil da Empresa no Google",
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
}

_SECURITY_EVENT_LABELS = {
    "authorization_denied": "autorização negada",
    "confirmation_consumed": "confirmação utilizada",
    "confirmation_issued": "confirmação preparada",
    "dual_control_approved": "dupla aprovação concluída",
    "freeze_activated": "Marketing congelado",
    "freeze_deactivated": "Marketing descongelado",
    "step_up_succeeded": "verificação adicional concluída",
}


def _actor_label(actor, actor_ref: str = "") -> str:
    if actor is not None:
        return actor.get_full_name() or actor.get_username()
    return actor_ref or "sistema"


def _admin_link(obj, label: str):
    if obj is None:
        return "—"
    opts = obj._meta
    url = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
    return format_html('<a href="{}">{}</a>', url, label)


def _datetime_label(value) -> str:
    if value is None:
        return "—"
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return formats.date_format(value, "DATETIME_FORMAT")


class MarketingReadOnlyAdmin(ModelAdmin):
    """Porta única da auditoria: capability explícita e nenhuma mutação."""

    actions = ()
    list_per_page = 50
    show_full_result_count = False

    def get_readonly_fields(self, request, obj=None):
        if self.readonly_fields:
            return self.readonly_fields
        return tuple(field.name for field in self.model._meta.fields)

    def has_module_permission(self, request):
        return request.user.has_perm("shop.audit_marketing")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("shop.audit_marketing")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="criado em", ordering="created_at")
    def created_at_display(self, obj):
        return _datetime_label(obj.created_at)

    @display(description="ocorrido em", ordering="occurred_at")
    def occurred_at_display(self, obj):
        return _datetime_label(obj.occurred_at)

    @display(description="recurso", ordering="resource_ref")
    def resource_ref_display(self, obj):
        return obj.resource_ref or "—"

    @display(description="versão anterior")
    def base_version_display(self, obj):
        return obj.base_version

    @display(description="versão resultante")
    def resulting_version_display(self, obj):
        return obj.resulting_version or "—"

    @display(description="identificador da requisição")
    def request_id_display(self, obj):
        return obj.request_id or "—"

    @display(description="código do motivo")
    def reason_code_display(self, obj):
        return obj.reason_code or "—"

    @display(description="fatos registrados")
    def facts_display(self, obj):
        return obj.facts or "Nenhum fato adicional."

    @display(description="concluído em")
    def completed_at_display(self, obj):
        return _datetime_label(obj.completed_at)

    @display(description="retido até")
    def retention_until_display(self, obj):
        return _datetime_label(obj.retention_until)


@admin.register(AnnouncementTemplate)
class AnnouncementTemplateAdmin(MarketingReadOnlyAdmin):
    """Defesa em profundidade; a curadoria oculta esta configuração do Admin."""

    list_display = ("name", "image_source", "use_ai_generation", "is_active")
    list_filter = ("is_active", "use_ai_generation", "image_source")
    search_fields = ("name", "body")
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("conteúdo", {"fields": ("body", "variables", "platform_variants", "image_source")}),
        ("inteligência artificial", {"fields": ("use_ai_generation", "ai_prompt")}),
    )


@admin.register(Campaign)
class CampaignAdmin(MarketingReadOnlyAdmin):
    """Defesa em profundidade; campanhas são editadas somente no Nuxt."""

    list_display = (
        "name",
        "trigger_display",
        "next_occurrence_display",
        "template",
        "requires_approval",
        "is_active",
    )
    list_filter = ("is_active", "trigger", "requires_approval")
    search_fields = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("gatilho", {"fields": ("trigger", "trigger_filter")}),
        ("conteúdo", {"fields": ("template", "platforms", "promotion_ref")}),
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
        from shopman.shop.services import campaign_schedule as sched

        if not sched.fires_on_its_own(obj.schedule):
            return "—"
        if sched.next_occurrence(obj.schedule) is None:
            return "Não dispara mais"
        return sched.describe_occurrence(obj.schedule)


@admin.register(Announcement)
class AnnouncementAdmin(MarketingReadOnlyAdmin):
    list_display = (
        "created_at_display",
        "status_display",
        "delivery_state_display",
        "rule",
        "audience_total",
        "platforms_display",
        "published_at",
        "open_in_marketing",
    )
    list_filter = ("status", "delivery_state", "rule")
    search_fields = ("=id", "rule__name", "rejected_reason")
    list_select_related = ("rule", "template", "approved_by", "rejected_by")
    readonly_fields = (
        "announcement_ref",
        "version",
        "rule",
        "template",
        "status_display",
        "delivery_state_display",
        "body_display",
        "platforms_display",
        "audience_summary",
        "delivery_summary",
        "approved_by",
        "approved_at",
        "rejection_display",
        "rejected_at",
        "publish_at",
        "published_at",
        "expires_at",
        "created_at_display",
        "open_in_marketing",
    )
    fieldsets = (
        ("Identificação", {"fields": ("announcement_ref", "version", "rule", "template")}),
        (
            "Decisão",
            {
                "fields": (
                    "status_display",
                    "body_display",
                    "platforms_display",
                    "audience_summary",
                    "approved_by",
                    "approved_at",
                    "rejection_display",
                    "rejected_at",
                )
            },
        ),
        (
            "Entrega agregada",
            {
                "fields": (
                    "delivery_state_display",
                    "delivery_summary",
                    "publish_at",
                    "published_at",
                    "expires_at",
                )
            },
        ),
        ("Acesso operacional", {"fields": ("open_in_marketing", "created_at_display")}),
    )
    date_hierarchy = "created_at"

    @display(description="anúncio")
    def announcement_ref(self, obj):
        return f"#{obj.pk}"

    @display(
        description="situação",
        label={
            "aguardando aprovação": "warning",
            "publicado": "success",
            "falhou": "danger",
            "recusado": "info",
            "expirado": "danger",
        },
    )
    def status_display(self, obj):
        return obj.get_status_display()

    @display(description="entrega")
    def delivery_state_display(self, obj):
        return obj.get_delivery_state_display()

    @display(description="texto aprovado")
    def body_display(self, obj):
        return obj.body or "—"

    @display(description="plataformas")
    def platforms_display(self, obj):
        return ", ".join(_PLATFORM_LABELS.get(item, item) for item in (obj.platforms or [])) or "—"

    @display(description="audiência")
    def audience_total(self, obj):
        return (obj.audience or {}).get("total", 0)

    @display(description="resumo do público")
    def audience_summary(self, obj):
        return obj.audience or {"total": 0}

    @display(description="resultado por plataforma")
    def delivery_summary(self, obj):
        return obj.platform_results or "Ainda sem resultado de entrega."

    @display(description="recusa")
    def rejection_display(self, obj):
        if obj.status != AnnouncementStatus.REJECTED:
            return "—"
        who = obj.rejected_by
        name = (who.get_full_name() or who.username) if who else "sem autor"
        return f"{name}: {obj.rejected_reason}" if obj.rejected_reason else name

    @display(description="continuar no Marketing")
    def open_in_marketing(self, obj):
        base_url = (getattr(settings, "SHOPMAN_MARKETING_BASE_URL", "") or "").rstrip("/")
        if not base_url:
            return "Aplicativo não configurado neste ambiente."
        return format_html('<a href="{}/announcements/{}">Abrir anúncio no Marketing</a>', base_url, obj.pk)


@admin.register(MarketingCommandReceipt)
class MarketingCommandReceiptAdmin(MarketingReadOnlyAdmin):
    list_display = (
        "created_at_display",
        "kind_display",
        "state_display",
        "resource_ref_display",
        "actor_display",
        "version_change",
        "announcement_link",
    )
    list_filter = ("kind", "state", "created_at")
    search_fields = ("=ref", "=request_id", "=resource_ref", "actor_ref", "actor__username")
    list_select_related = ("announcement", "actor")
    readonly_fields = (
        "receipt_ref",
        "kind_display",
        "state_display",
        "resource_ref_display",
        "actor_display",
        "announcement_link",
        "base_version_display",
        "resulting_version_display",
        "outcome_display",
        "request_id_display",
        "payload_hash_display",
        "idempotency_key_hash_display",
        "created_at_display",
        "completed_at_display",
        "retention_until_display",
    )
    fieldsets = (
        ("Comando", {"fields": ("receipt_ref", "kind_display", "state_display", "resource_ref_display")}),
        ("Responsabilidade", {"fields": ("actor_display", "announcement_link")}),
        (
            "Resultado",
            {
                "fields": (
                    "base_version_display",
                    "resulting_version_display",
                    "outcome_display",
                    "request_id_display",
                )
            },
        ),
        (
            "Prova técnica",
            {
                "fields": (
                    "payload_hash_display",
                    "idempotency_key_hash_display",
                    "created_at_display",
                    "completed_at_display",
                    "retention_until_display",
                )
            },
        ),
    )
    date_hierarchy = "created_at"

    @display(description="comprovante")
    def receipt_ref(self, obj):
        return obj.ref

    @display(description="ação")
    def kind_display(self, obj):
        return obj.get_kind_display()

    @display(description="situação")
    def state_display(self, obj):
        return obj.get_state_display()

    @display(description="responsável")
    def actor_display(self, obj):
        return _actor_label(obj.actor, obj.actor_ref)

    @display(description="versão")
    def version_change(self, obj):
        return f"{obj.base_version} → {obj.resulting_version or '—'}"

    @display(description="anúncio")
    def announcement_link(self, obj):
        if obj.announcement is None:
            return "—"
        return _admin_link(obj.announcement, f"Anúncio #{obj.announcement_id}")

    @display(description="resultado registrado")
    def outcome_display(self, obj):
        return obj.outcome or "Nenhum detalhe adicional."

    @display(description="assinatura do comando")
    def payload_hash_display(self, obj):
        return obj.payload_hash

    @display(description="assinatura de idempotência")
    def idempotency_key_hash_display(self, obj):
        return obj.idempotency_key_hash


@admin.register(AudienceSnapshot)
class AudienceSnapshotAdmin(MarketingReadOnlyAdmin):
    list_display = (
        "sealed_at_display",
        "snapshot_ref",
        "announcement_link",
        "version_display",
        "audience_total",
        "policy_version_display",
        "expires_at_display",
    )
    list_filter = ("policy_version", "sealed_at")
    search_fields = ("=ref", "=announcement__id", "=cohort_hash", "=rule_hash")
    list_select_related = ("announcement",)
    readonly_fields = (
        "snapshot_ref",
        "announcement_link",
        "version_display",
        "audience_summary",
        "rule_summary_display",
        "rule_hash_display",
        "cohort_hash_display",
        "policy_version_display",
        "calculated_at_display",
        "expires_at_display",
        "sealed_at_display",
        "retention_until_display",
    )
    fieldsets = (
        ("Público selado", {"fields": ("snapshot_ref", "announcement_link", "version_display")}),
        ("Resumo sem dados pessoais", {"fields": ("audience_summary", "rule_summary_display")}),
        (
            "Prova técnica",
            {"fields": ("rule_hash_display", "cohort_hash_display", "policy_version_display")},
        ),
        (
            "Validade e retenção",
            {
                "fields": (
                    "calculated_at_display",
                    "expires_at_display",
                    "sealed_at_display",
                    "retention_until_display",
                )
            },
        ),
    )
    date_hierarchy = "sealed_at"

    @display(description="selado em", ordering="sealed_at")
    def sealed_at_display(self, obj):
        return _datetime_label(obj.sealed_at)

    @display(description="versão")
    def version_display(self, obj):
        return obj.version

    @display(description="versão da política")
    def policy_version_display(self, obj):
        return obj.policy_version

    @display(description="assinatura das regras")
    def rule_hash_display(self, obj):
        return obj.rule_hash

    @display(description="assinatura do público")
    def cohort_hash_display(self, obj):
        return obj.cohort_hash

    @display(description="calculado em")
    def calculated_at_display(self, obj):
        return _datetime_label(obj.calculated_at)

    @display(description="válido até")
    def expires_at_display(self, obj):
        return _datetime_label(obj.expires_at)

    @display(description="público selado")
    def snapshot_ref(self, obj):
        return obj.ref

    @display(description="anúncio")
    def announcement_link(self, obj):
        if obj.announcement is None:
            return "—"
        return _admin_link(obj.announcement, f"Anúncio #{obj.announcement_id}")

    @display(description="pessoas")
    def audience_total(self, obj):
        return (obj.summary or {}).get("total", 0)

    @display(description="resumo do público")
    def audience_summary(self, obj):
        return obj.summary or {"total": 0}

    @display(description="regras aplicadas")
    def rule_summary_display(self, obj):
        return obj.rule_summary or "Nenhuma regra adicional."


class _EventAdmin(MarketingReadOnlyAdmin):
    """Apresentação compartilhada pelos ledgers append-only."""

    @display(description="evento")
    def event_ref(self, obj):
        return obj.ref

    @display(description="responsável")
    def actor_display(self, obj):
        return _actor_label(obj.actor, obj.actor_ref)

    @display(description="comprovante")
    def command_link(self, obj):
        return _admin_link(obj.command, str(obj.command.ref))

    @display(description="versão")
    def version_change(self, obj):
        return f"{obj.base_version} → {obj.resulting_version}"


@admin.register(MarketingAuditEvent)
class MarketingAuditEventAdmin(_EventAdmin):
    list_display = (
        "occurred_at_display",
        "event_type_display",
        "announcement_link",
        "actor_display",
        "version_change",
        "command_link",
    )
    list_filter = ("event_type", "occurred_at")
    search_fields = ("=ref", "=announcement__id", "actor_ref", "reason_code", "request_id")
    list_select_related = ("announcement", "actor", "command")
    readonly_fields = (
        "event_ref",
        "event_type_display",
        "announcement_link",
        "actor_display",
        "command_link",
        "base_version_display",
        "resulting_version_display",
        "reason_code_display",
        "decision_reason_display",
        "facts_display",
        "request_id_display",
        "occurred_at_display",
        "created_at_display",
        "retention_until_display",
    )
    fieldsets = (
        (
            "Decisão",
            {"fields": ("event_ref", "event_type_display", "announcement_link", "actor_display", "command_link")},
        ),
        (
            "Contexto",
            {
                "fields": (
                    "base_version_display",
                    "resulting_version_display",
                    "reason_code_display",
                    "decision_reason_display",
                    "facts_display",
                    "request_id_display",
                )
            },
        ),
        (
            "Tempo e retenção",
            {
                "fields": (
                    "occurred_at_display",
                    "created_at_display",
                    "retention_until_display",
                )
            },
        ),
    )
    date_hierarchy = "occurred_at"

    @display(description="tipo")
    def event_type_display(self, obj):
        return obj.get_event_type_display()

    @display(description="anúncio")
    def announcement_link(self, obj):
        return _admin_link(obj.announcement, f"Anúncio #{obj.announcement_id}")

    @display(description="justificativa da decisão")
    def decision_reason_display(self, obj):
        return obj.decision_reason or "—"


@admin.register(MarketingPlatformAuditEvent)
class MarketingPlatformAuditEventAdmin(_EventAdmin):
    list_display = (
        "occurred_at_display",
        "event_type_display",
        "platform_display",
        "actor_display",
        "version_change",
        "command_link",
    )
    list_filter = ("platform", "event_type", "occurred_at")
    search_fields = ("=ref", "actor_ref", "previous_flow_ref", "resulting_flow_ref", "request_id")
    list_select_related = ("actor", "command")
    readonly_fields = (
        "event_ref",
        "event_type_display",
        "platform_display",
        "actor_display",
        "command_link",
        "base_version_display",
        "resulting_version_display",
        "previous_flow_ref_display",
        "resulting_flow_ref_display",
        "catalog_hash_display",
        "catalog_as_of_display",
        "request_id_display",
        "occurred_at_display",
        "created_at_display",
        "retention_until_display",
    )
    fieldsets = (
        (
            "Configuração",
            {"fields": ("event_ref", "event_type_display", "platform_display", "actor_display", "command_link")},
        ),
        (
            "Alteração",
            {
                "fields": (
                    "base_version_display",
                    "resulting_version_display",
                    "previous_flow_ref_display",
                    "resulting_flow_ref_display",
                    "catalog_hash_display",
                    "catalog_as_of_display",
                    "request_id_display",
                )
            },
        ),
        (
            "Tempo e retenção",
            {
                "fields": (
                    "occurred_at_display",
                    "created_at_display",
                    "retention_until_display",
                )
            },
        ),
    )
    date_hierarchy = "occurred_at"

    @display(description="tipo")
    def event_type_display(self, obj):
        return obj.get_event_type_display()

    @display(description="plataforma")
    def platform_display(self, obj):
        return _PLATFORM_LABELS.get(obj.platform, obj.platform)

    @display(description="configuração anterior")
    def previous_flow_ref_display(self, obj):
        return obj.previous_flow_ref or "—"

    @display(description="configuração resultante")
    def resulting_flow_ref_display(self, obj):
        return obj.resulting_flow_ref or "—"

    @display(description="assinatura do catálogo")
    def catalog_hash_display(self, obj):
        return obj.catalog_hash

    @display(description="catálogo conferido em")
    def catalog_as_of_display(self, obj):
        return _datetime_label(obj.catalog_as_of)


@admin.register(MarketingSecurityEvent)
class MarketingSecurityEventAdmin(MarketingReadOnlyAdmin):
    list_display = (
        "occurred_at_display",
        "event_type_display",
        "action_display",
        "resource_ref_display",
        "actor_display",
        "second_actor_display",
    )
    list_filter = ("event_type", "action", "occurred_at")
    search_fields = ("=ref", "=resource_ref", "event_type", "action", "reason_code")
    list_select_related = ("actor", "second_actor")
    readonly_fields = (
        "event_ref",
        "event_type_display",
        "action_display",
        "resource_ref_display",
        "actor_display",
        "second_actor_display",
        "reason_code_display",
        "facts_display",
        "occurred_at_display",
        "retention_until_display",
    )
    fieldsets = (
        (
            "Evento de segurança",
            {
                "fields": (
                    "event_ref",
                    "event_type_display",
                    "action_display",
                    "resource_ref_display",
                    "actor_display",
                    "second_actor_display",
                    "reason_code_display",
                    "facts_display",
                )
            },
        ),
        (
            "Tempo e retenção",
            {"fields": ("occurred_at_display", "retention_until_display")},
        ),
    )
    date_hierarchy = "occurred_at"

    @display(description="evento")
    def event_ref(self, obj):
        return obj.ref

    @display(description="tipo")
    def event_type_display(self, obj):
        return _SECURITY_EVENT_LABELS.get(obj.event_type, obj.event_type)

    @display(description="ação")
    def action_display(self, obj):
        return obj.action or "—"

    @display(description="responsável")
    def actor_display(self, obj):
        return _actor_label(obj.actor)

    @display(description="segundo responsável")
    def second_actor_display(self, obj):
        return _actor_label(obj.second_actor) if obj.second_actor else "não exigido"
