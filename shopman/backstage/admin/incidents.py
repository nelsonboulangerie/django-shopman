"""Incidentes: a credencial da ponte (conferir e revogar) e o placar dos remédios."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.backstage.models import IncidentAction, IncidentReaderCredential


@admin.register(IncidentReaderCredential)
class IncidentReaderCredentialAdmin(ModelAdmin):
    list_display = ("label", "token_hint", "is_active", "expires_at", "last_seen_at")
    list_filter = ("is_active",)
    fields = ("ref", "label", "token_hint", "is_active", "expires_at", "last_seen_at", "created_at")
    readonly_fields = ("ref", "label", "token_hint", "expires_at", "last_seen_at", "created_at")

    def has_add_permission(self, request):
        # O segredo aparece uma vez só: emissão por issue_incident_reader_credential.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IncidentAction)
class IncidentActionAdmin(ModelAdmin):
    """O placar: o que o sistema fez sozinho, o que deixou para gente, e por quê."""

    list_display = ("created_at", "alert_type", "target", "remedy", "outcome", "decided_by", "confidence", "detail")
    list_filter = ("outcome", "remedy", "alert_type", "mode", "decided_by")
    search_fields = ("target", "alert_type", "detail")
    date_hierarchy = "created_at"
    readonly_fields = [field.name for field in IncidentAction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
