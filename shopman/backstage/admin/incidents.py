"""Credenciais da ponte de incidentes: conferir uso e revogar."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from shopman.backstage.models import IncidentReaderCredential


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
