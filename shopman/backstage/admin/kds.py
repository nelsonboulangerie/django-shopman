"""KDSInstance admin — kitchen display station configuration."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html
from shopman.utils import unfold_badge, unfold_link
from unfold.admin import ModelAdmin
from unfold.decorators import display

from shopman.backstage.models import KDSInstance


@admin.register(KDSInstance)
class KDSInstanceAdmin(ModelAdmin):
    list_display = ["name", "ref", "type_badge", "target_time_minutes", "sound_enabled", "is_active_badge", "open_display"]
    list_filter = ["type", "is_active"]
    search_fields = ["name", "ref"]
    ordering = ["name"]
    prepopulated_fields = {"ref": ("name",)}
    filter_horizontal = ["collections"]
    # ``print_terminal`` fica no select padrão do Unfold (lista fechada dos
    # terminais cadastrados), e não em autocomplete: o autocomplete pede
    # permissão de ver Terminais, que quem configura o KDS pode não ter. O
    # gestor escolhe a impressora e nunca digita um endereço — quem sabe o IP é
    # a fila do agente daquele terminal (CUPS ``socket://IP:9100``).
    readonly_fields = ["print_destination_display"]
    compressed_fields = True
    warn_unsaved_form = True
    fieldsets = [
        (None, {"fields": ("name", "ref", "type")}),
        ("Coleções", {
            "fields": ("collections",),
            "description": "Categorias de produto que esta estação processa. Vazio = processa todas as categorias.",
        }),
        ("Impressora do posto", {
            "fields": ("print_terminal", "print_destination_display"),
            "description": (
                "Para a estação que não tem tela: cada pedido que cai aqui sai impresso na impressora "
                "escolhida (Via Cozinha). Imprimir não conclui o pedido: quem dá o pronto é a Saída, "
                "o PDV ou o leitor de código na bancada, que lê o QR do papel."
            ),
        }),
        ("Configuração", {"fields": ("target_time_minutes", "sound_enabled", "is_active", "config")}),
    ]

    @display(description="tipo")
    def type_badge(self, obj):
        colors = {"prep": "yellow", "picking": "blue", "expedition": "green"}
        return unfold_badge(obj.get_type_display(), colors.get(obj.type, "base"))

    @display(description="ativa")
    def is_active_badge(self, obj):
        if obj.is_active:
            return unfold_badge("ativa", "green")
        return unfold_badge("inativa", "base")

    @display(description="impressora agora")
    def print_destination_display(self, obj):
        """A saúde da impressora escolhida, com a MESMA régua do relay.

        Escolher a impressora e só descobrir no primeiro pedido que o agente
        dela não está pareado é o buraco de sempre: aqui o gestor lê o que o
        servidor vai encontrar (``print_jobs._destination_health``).
        """
        terminal = getattr(obj, "print_terminal", None) if obj is not None else None
        if terminal is None:
            return unfold_badge("sem impressora — o posto usa a tela", "base")
        if not terminal.is_active:
            return format_html(
                "{} {}",
                unfold_badge("terminal desativado", "red"),
                "Reative o terminal em Terminais do PDV ou escolha outra impressora.",
            )
        from shopman.backstage.services.print_jobs import _destination_health

        health = _destination_health(terminal)
        color = "green" if health.status_label == "Pronta" else ("yellow" if health.available else "red")
        detail = health.problem or health.label
        return format_html("{} {}", unfold_badge(health.status_label, color), detail)

    @display(description="operação")
    def open_display(self, obj):
        # KDS é app Nuxt dedicado (kds.) — sem rota Django. Link só quando a base
        # URL do deployment está configurada (estação fica em /<ref>).
        base = (getattr(settings, "SHOPMAN_KDS_BASE_URL", "") or "").rstrip("/")
        if not base:
            return "—"
        return unfold_link(f"{base}/{obj.ref}", "Abrir", icon="open_in_new", new_tab=True)

    def has_add_permission(self, request):
        return request.user.has_perm("backstage.operate_kds")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("backstage.operate_kds")
