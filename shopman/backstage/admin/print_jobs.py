"""Canonical Unfold audit surfaces for server-owned print delivery."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from shopman.backstage.models import PrintAgentCredential, PrintAttempt, PrintJob


class PrintAttemptInline(TabularInline):
    model = PrintAttempt
    extra = 0
    can_delete = False
    fields = (
        "sequence",
        "status",
        "credential",
        "claimed_at",
        "acknowledged_at",
        "spooler_job_id",
        "agent_build",
        "queue_name",
        "detail",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PrintJob)
class PrintJobAdmin(ModelAdmin):
    list_display = (
        "ref",
        "kind",
        "transport",
        "status",
        "target_terminal",
        "requested_by_ref",
        "label_count",
        "copy_number",
        "created_at",
    )
    list_filter = ("kind", "status", "target_terminal", "created_at")
    search_fields = ("=ref", "requested_by_ref", "requested_station_ref", "=document_sha256", "=payload_sha256")
    readonly_fields = (
        "ref",
        "kind",
        "transport",
        "status",
        "target_terminal",
        "requested_by",
        "requested_by_ref",
        "requested_station_ref",
        "source_revision",
        "document_sha256",
        "renderer_version",
        "payload_sha256",
        "payload_size",
        "label_count",
        "series_ref",
        "copy_number",
        "reprint_of",
        "confirmation",
        "confirmation_detail",
        "confirmed_by",
        "confirmed_by_ref",
        "confirmed_at",
        "expires_at",
        "created_at",
        "updated_at",
    )
    exclude = ("document", "payload")
    inlines = (PrintAttemptInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PrintAgentCredential)
class PrintAgentCredentialAdmin(ModelAdmin):
    list_display = ("terminal", "label", "token_hint", "is_active", "last_seen_at", "last_build")
    list_filter = ("is_active", "terminal")
    search_fields = ("terminal__ref", "label", "token_hint")
    fields = (
        "ref",
        "terminal",
        "label",
        "token_hint",
        "is_active",
        "last_seen_at",
        "last_build",
        "last_remote_addr",
        "created_at",
        "rotated_at",
        "revoked_at",
    )
    readonly_fields = (
        "ref",
        "terminal",
        "label",
        "token_hint",
        "last_seen_at",
        "last_build",
        "last_remote_addr",
        "created_at",
        "rotated_at",
        "revoked_at",
    )

    def has_add_permission(self, request):
        # Issuance must return the raw secret exactly once.  A normal ModelAdmin
        # save cannot do that safely; use issue_print_agent_credential.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
