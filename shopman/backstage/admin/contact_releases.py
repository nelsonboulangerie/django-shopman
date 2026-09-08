"""A trilha dos contatos LIBERADOS no balcão.

Liberar um contato preso num cadastro desativado apaga o ``ContactPoint`` (ou o
``CustomerIdentifier``) para que o UNIQUE global pare de recusar a venda. É a
saída certa, e ela é destrutiva: não tem desfazer.

A tela do PDV promete, na reconfirmação, que "fica registrado e dá para refazer
o cadastro depois". Esta é a tela onde essa promessa se cumpre — e é por isso
que ela existe. A mesma lição do desfazer da unificação: registro que ninguém
alcança é o mesmo que registro nenhum. Antes disto o rastro só existiria para
quem tivesse um shell do Django, o que no balcão significa ninguém.

Somente leitura. O rastro nasce do service (`release_pos_customer_contact`) e
editá-lo à mão seria apagar exatamente o que ele guarda. Refazer o contato é
gesto no cadastro do cliente, não nesta trilha.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils import timezone
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.shop.models import ContactRelease


def _quando(momento) -> str:
    return timezone.localtime(momento).strftime("%d/%m/%Y às %H:%M")


@admin.register(ContactRelease)
class ContactReleaseAdmin(ModelAdmin):
    """O que foi solto, de qual ficha, por quem e quando."""

    list_display = (
        "released_display",
        "from_display",
        "actor_display",
        "released_at_display",
        "merge_badge",
    )
    list_filter = ("kind",)
    search_fields = ("value", "released_from_ref", "released_from_name", "actor")
    ordering = ("-released_at",)
    list_per_page = 50
    list_fullwidth = True
    compressed_fields = True
    readonly_fields = (
        "kind",
        "value",
        "released_from_ref",
        "released_from_name",
        "released_pk",
        "was_primary",
        "merge_audit_id",
        "actor",
        "released_at",
    )
    fieldsets = (
        (
            "O que foi liberado",
            {
                "fields": ("kind", "value", "was_primary"),
                "description": (
                    "O contato saiu de um cadastro DESATIVADO para destravar uma venda. "
                    "Recriá-lo é gesto no cadastro do cliente; aqui fica o registro de "
                    "que ele existia e de onde veio."
                ),
            },
        ),
        ("De onde saiu", {"fields": ("released_from_ref", "released_from_name", "released_pk")}),
        ("Quem e quando", {"fields": ("actor", "released_at")}),
        (
            "Unificação afetada",
            {
                "fields": ("merge_audit_id",),
                "description": (
                    "Quando preenchido, este contato tinha sido movido por uma unificação: "
                    "o desfazer dela NÃO o devolve, porque devolve por PK e o PK foi "
                    "apagado. O diálogo de desfazer avisa quem for desfazer."
                ),
            },
        ),
    )

    def has_add_permission(self, request) -> bool:
        # A liberação nasce no balcão, nunca digitada aqui.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Apagar o rastro do apagamento seria o pior dos dois mundos.
        return False

    # ── Colunas ──────────────────────────────────────────────────────────────

    @display(description="Contato liberado")
    def released_display(self, obj) -> str:
        return f"{obj.get_kind_display()} {obj.value}"

    @display(description="Saiu de")
    def from_display(self, obj) -> str:
        nome = obj.released_from_name or "—"
        return f"{nome} ({obj.released_from_ref})"

    @display(description="Quem liberou")
    def actor_display(self, obj) -> str:
        return obj.actor or "—"

    @display(description="Quando")
    def released_at_display(self, obj) -> str:
        return _quando(obj.released_at)

    @display(description="Unificação")
    def merge_badge(self, obj):
        """A linha grita quando a liberação deixou um desfazer incompleto."""
        if not obj.merge_audit_id:
            return unfold_badge("—", "base")
        return unfold_badge("desfazer incompleto", "orange")
