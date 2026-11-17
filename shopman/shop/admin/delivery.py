"""Delivery admin — faixas de distância (motor) + zonas CEP/bairro (exceção)."""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from shopman.shop.models import Courier, CourierRate, DeliveryDistanceBand, DeliveryService, DeliveryZone


@admin.register(DeliveryDistanceBand)
class DeliveryDistanceBandAdmin(ModelAdmin):
    # Lista arrastável (Unfold) em vez da coluna numérica de ordem. O motor
    # avalia pela distância (a menor faixa que cobre o pedido vence); o arraste
    # define a ordem de exibição/empate.
    ordering_field = "sort_order"
    hide_ordering_field = True
    list_display = ("max_distance_km", "fee_display", "is_active")
    list_filter = ("is_active", "shop")
    ordering = ("sort_order", "max_distance_km")
    list_editable = ("is_active",)
    fieldsets = (
        (None, {
            "fields": ("shop", "max_distance_km", "fee_q", "sort_order", "is_active"),
            "description": (
                "Motor da entrega: a taxa é a primeira faixa cuja distância "
                "(loja → endereço) cobre o pedido. Endereços além da maior faixa "
                "ficam fora da área. Exceções por bairro/CEP ficam em "
                "“Zonas de entrega”."
            ),
        }),
    )

    @admin.display(description="taxa")
    def fee_display(self, obj):
        if obj.fee_q == 0:
            return "grátis"
        return f"R$ {obj.fee_q / 100:.2f}".replace(".", ",")


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(ModelAdmin):
    # Prioridade manual → lista arrastável (Unfold ordering_field) em vez de
    # uma coluna numérica de ordem. Menor sort_order = maior prioridade.
    ordering_field = "sort_order"
    hide_ordering_field = True
    list_display = ("name", "mode_badge", "zone_type_badge", "match_value", "fee_display", "is_active")
    list_filter = ("mode", "zone_type", "is_active", "shop")
    search_fields = ("name", "match_value")
    ordering = ("sort_order", "name")
    list_editable = ("is_active",)

    @display(
        description="Modo",
        label={"Sobrepor taxa (fixa)": "info", "Não entregar (bloquear)": "danger"},
    )
    def mode_badge(self, obj):
        return obj.get_mode_display()

    @display(
        description="Tipo",
        label={"Prefixo de CEP": "info", "Bairro": "warning"},
    )
    def zone_type_badge(self, obj):
        return obj.get_zone_type_display()

    fieldsets = (
        (None, {
            "fields": ("shop", "name", "zone_type", "match_value", "mode", "fee_q", "sort_order", "is_active"),
            "description": (
                "Exceções à taxa por distância. “Sobrepor taxa” fixa um valor para "
                "um bairro/CEP (0 = grátis); “Não entregar” bloqueia o checkout "
                "naquela região. Prefixo de CEP tem prioridade sobre bairro."
            ),
        }),
    )

    @admin.display(description="taxa")
    def fee_display(self, obj):
        if obj.mode == DeliveryZone.MODE_EXCLUDE:
            return "—"
        if obj.fee_q == 0:
            return "grátis"
        return f"R$ {obj.fee_q / 100:.2f}".replace(".", ",")


# ── Quem leva a entrega (DEV-2026-030, frente M0 do DELIVERY-MULTI-SERVICE-PLAN) ──


def _brl(value_q: int) -> str:
    return f"R$ {value_q / 100:.2f}".replace(".", ",")


@admin.register(DeliveryService)
class DeliveryServiceAdmin(ModelAdmin):
    ordering_field = "sort_order"
    hide_ordering_field = True
    list_display = ("name", "kind_badge", "is_default", "is_active")
    list_filter = ("kind", "is_active")
    ordering = ("sort_order", "name")
    list_editable = ("is_active",)
    prepopulated_fields = {"ref": ("name",)}
    fieldsets = (
        (None, {
            "fields": ("name", "ref", "kind", "is_default", "is_active", "sort_order"),
            "description": (
                "Quem pode levar as entregas da casa. O serviço padrão vem marcado ao chamar o "
                "entregador e é o que o despacho automático usa; os entregadores da casa livres "
                "aparecem como opção no mesmo gesto. O cliente nunca vê o nome do serviço."
            ),
        }),
    )

    @display(
        description="Tipo",
        label={"Central de entregas por API (TaOn)": "info", "Entregadores da casa": "success"},
    )
    def kind_badge(self, obj):
        return obj.get_kind_display()

    def get_readonly_fields(self, request, obj=None):
        # O tipo e o identificador são a identidade do serviço: trocar depois de criado
        # deixaria as corridas gravadas apontando para outra coisa.
        return ("ref", "kind") if obj else ()

    def get_prepopulated_fields(self, request, obj=None):
        # Na edição o identificador é só leitura: não há o que preencher a partir do nome.
        return {} if obj else {"ref": ("name",)}


class CourierRateInline(TabularInline):
    model = CourierRate
    fk_name = "courier"
    extra = 0
    fields = ("max_km", "value_q", "extra_stop_q", "return_q")
    verbose_name = "valor combinado"
    verbose_name_plural = "Valores combinados com este entregador (substituem a tabela da casa para ele)"


@admin.register(Courier)
class CourierAdmin(ModelAdmin):
    list_display = ("name", "phone", "vehicle", "service", "is_active")
    list_filter = ("is_active", "service")
    search_fields = ("name", "phone", "vehicle")
    list_editable = ("is_active",)
    prepopulated_fields = {"ref": ("name",)}
    inlines = (CourierRateInline,)
    fieldsets = (
        (None, {
            "fields": ("service", "name", "ref", "phone", "vehicle", "is_active", "on_shift_on"),
            "description": (
                "O entregador recebe o link da corrida pelo WhatsApp. O veículo aparece na Saída "
                "para o balcão conferir antes de entregar as sacolas. Sem valor combinado, vale a "
                "tabela da casa."
            ),
        }),
    )

    def save_formset(self, request, form, formset, change):
        # A linha combinada herda o serviço do entregador: o operador não escolhe duas vezes.
        for inline_form in formset.forms:
            instance = getattr(inline_form, "instance", None)
            if isinstance(instance, CourierRate) and not instance.service_id:
                instance.service_id = form.instance.service_id
        super().save_formset(request, form, formset, change)


@admin.register(CourierRate)
class CourierRateAdmin(ModelAdmin):
    list_display = ("who", "reach", "value_display", "extra_stop_display", "return_display")
    list_filter = ("service", "courier")
    ordering = ("service", "courier", "max_km")
    fieldsets = (
        (None, {
            "fields": ("service", "courier", "max_km", "value_q", "extra_stop_q", "return_q"),
            "description": (
                "A tabela da casa são as linhas sem entregador: vale a de menor distância que "
                "alcança a rota inteira (com a volta, quando houver); a linha sem distância vale "
                "para qualquer distância. Linhas com entregador são o valor combinado com ele e "
                "substituem a tabela da casa só para ele. É custo da casa: o frete do cliente não muda."
            ),
        }),
    )

    @admin.display(description="De quem")
    def who(self, obj):
        return obj.courier.name if obj.courier_id else "Tabela da casa"

    @admin.display(description="Até")
    def reach(self, obj):
        return f"{obj.max_km} km".replace(".", ",") if obj.max_km is not None else "Qualquer distância"

    @admin.display(description="Valor")
    def value_display(self, obj):
        return _brl(obj.value_q)

    @admin.display(description="Parada a mais")
    def extra_stop_display(self, obj):
        return _brl(obj.extra_stop_q)

    @admin.display(description="Com volta")
    def return_display(self, obj):
        return _brl(obj.return_q)
