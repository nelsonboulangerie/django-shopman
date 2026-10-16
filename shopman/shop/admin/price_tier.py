"""Grupo de clientes com desconto automático (decisão do dono, 14/10/2026).

O caso real: alunos da Aliança Francesa consumindo no balcão. Em vez de cupom no
PDV, o GRUPO tem um desconto, e o PDV o aplica sozinho quando o cliente é
identificado.

Nada novo no motor. O grupo é a ``PriceTier`` do guestman (uma por cliente, e ela
já é segmento de promoção: ``Promotion.customer_segments`` casa a faixa), e o
desconto é uma ``Promotion`` comum, que o ``DiscountModifier`` aplica no reprice
com a régua de sempre: escopo por canal, "maior desconto ganha", registro em
``pricing.discount`` do pedido. O que esta tela faz é deixar o gestor cadastrar
tudo num lugar só: o grupo, o desconto e os canais onde ele vale.

A promoção do grupo tem ``ref`` derivado do grupo (``grupo-<ref>``) e não tem
prazo: vale enquanto estiver ligada aqui. Tirar o desconto PAUSA a promoção (não
apaga), e o histórico dos pedidos segue apontando para ela.
"""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db import transaction
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Concat
from shopman.guestman.contrib.admin_unfold.admin import (
    PriceTierAdmin as _GuestmanPriceTierAdmin,
)
from shopman.guestman.contrib.admin_unfold.admin import (
    PriceTierAdvantageInline,
)
from shopman.guestman.models import PriceTier
from shopman.utils.monetary import format_money
from unfold.decorators import display
from unfold.widgets import (
    UnfoldAdminCheckboxSelectMultipleWidget,
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminRadioSelectWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanSwitchWidget,
)

from shopman.shop.models import Channel, Promotion
from shopman.shop.services import customer_groups as customer_group_service
from shopman.shop.services import promotions as promotion_service

#: Sem data de fim: o desconto do grupo vale enquanto estiver ligado. O campo do
#: modelo é obrigatório, então "sem prazo" é o último dia que o banco guarda bem.
NO_DISCOUNT = ""
DISCOUNT_TYPE_CHOICES = [
    (NO_DISCOUNT, "Sem desconto"),
    (Promotion.PERCENT, "Percentual em cada item"),
    (Promotion.FIXED, "Valor em reais por pedido"),
]


def _pos_channel_ref() -> str:
    return getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")


def _group_promotion(tier_ref: str) -> Promotion | None:
    return customer_group_service.group_promotion(tier_ref)


class PriceTierGroupDiscountForm(forms.ModelForm):
    group_discount_type = forms.ChoiceField(
        label="Desconto do grupo",
        choices=DISCOUNT_TYPE_CHOICES,
        required=False,
        widget=UnfoldAdminRadioSelectWidget,
    )
    group_discount_value = forms.DecimalField(
        label="Valor do desconto",
        required=False,
        min_value=Decimal("0"),
        max_digits=8,
        decimal_places=2,
        # "2,50" como o gestor escreve: sem ``localize`` o campo só aceita "2.50".
        localize=True,
        widget=UnfoldAdminDecimalFieldWidget,
        help_text="Percentual: 10 é 10% em cada item. Valor por pedido: 2,00 é R$ 2,00 a menos na venda.",
    )
    group_discount_channels = forms.ModelMultipleChoiceField(
        label="Onde vale",
        queryset=Channel.objects.all().order_by("name"),
        required=False,
        widget=UnfoldAdminCheckboxSelectMultipleWidget,
        help_text="Nenhum marcado: vale em todos os canais.",
    )
    group_pickup_only = forms.BooleanField(
        label="Só na retirada",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text="Com entrega, o desconto do grupo não vale. É o guarda do benefício da Equipe.",
    )
    group_discount_kind = forms.CharField(
        label="Tipo do desconto",
        required=False,
        max_length=40,
        widget=UnfoldAdminTextInputWidget,
        help_text="Para o B.I. medir desconto por tipo. Ex: equipe, parceiro.",
    )
    group_rounding = forms.BooleanField(
        label="Arredondar o preço final",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text="Arredonda o preço de cada item para o R$ 0,00 ou R$ 0,50 mais próximo.",
    )
    group_savings_message = forms.CharField(
        label="Mensagem de economia",
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
        help_text='Texto do checkout e do comprovante. Use {amount} para o valor e {group} para o nome do grupo. Ex: "Hoje você economizou {amount} por ser {group}".',
    )

    class Meta:
        model = PriceTier
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        promo = _group_promotion(getattr(self.instance, "ref", "") if self.instance.pk else "")
        metadata = (getattr(self.instance, "metadata", None) or {}) if self.instance.pk else {}
        self.fields["group_discount_kind"].initial = metadata.get("discount_kind", "")
        self.fields["group_rounding"].initial = int(metadata.get("rounding", 50) or 0) > 0
        self.fields["group_savings_message"].initial = metadata.get("savings_message", "")
        self.fields["group_pickup_only"].initial = bool(
            promo is not None and list(promo.fulfillment_types or []) == ["pickup"]
        )
        if promo is not None and promo.is_active:
            self.fields["group_discount_type"].initial = promo.type
            self.fields["group_discount_value"].initial = (
                Decimal(promo.value) if promo.type == Promotion.PERCENT else Decimal(promo.value) / 100
            )
            self.fields["group_discount_channels"].initial = list(promo.channels.all())
        else:
            self.fields["group_discount_type"].initial = NO_DISCOUNT
            # O padrão é o balcão: é onde o grupo é identificado (telefone ou CPF).
            self.fields["group_discount_channels"].initial = list(
                Channel.objects.filter(ref=_pos_channel_ref())
            )

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("group_discount_type") or NO_DISCOUNT
        value = cleaned.get("group_discount_value")
        if kind == NO_DISCOUNT or "group_discount_value" in self.errors:
            return cleaned
        if value is None or value <= 0:
            self.add_error("group_discount_value", "Informe o valor do desconto.")
        elif kind == Promotion.PERCENT and (value > 100 or value != value.to_integral_value()):
            self.add_error("group_discount_value", "Percentual inteiro, de 1 a 100.")
        return cleaned

    def group_discount_value_q(self) -> int:
        """O ``Promotion.value``: percentual inteiro, ou centavos no valor por pedido."""
        value = self.cleaned_data.get("group_discount_value") or Decimal("0")
        return customer_group_service.discount_value_q(
            self.cleaned_data.get("group_discount_type") or NO_DISCOUNT,
            value,
        )


def _metadata_with_group_settings(metadata: dict, form: PriceTierGroupDiscountForm) -> dict:
    """Aplica as chaves do grupo (B.I., arredondamento e economia) ao metadata.

    O campo ``metadata`` cru do form continua sendo a base; estas três chaves são
    o atalho editável e têm dono único aqui. Chave vazia sai do metadata para o
    padrão do motor voltar a valer (nada de ``""`` fingindo configuração).
    """
    return customer_group_service.metadata_with_group_settings(
        metadata,
        discount_kind=form.cleaned_data.get("group_discount_kind") or "",
        rounding=bool(form.cleaned_data.get("group_rounding")),
        savings_message=form.cleaned_data.get("group_savings_message") or "",
    )


def sync_group_discount(tier: PriceTier, form: PriceTierGroupDiscountForm, *, previous_ref: str = "") -> Promotion | None:
    """Grava a promoção do grupo a partir do formulário. Devolve a promoção (ou None)."""
    return customer_group_service.sync_group_discount(
        tier,
        discount_type=form.cleaned_data.get("group_discount_type") or NO_DISCOUNT,
        discount_value_q=form.group_discount_value_q(),
        channel_refs=[channel.ref for channel in (form.cleaned_data.get("group_discount_channels") or [])],
        pickup_only=bool(form.cleaned_data.get("group_pickup_only")),
        previous_ref=previous_ref,
    )


admin.site.unregister(PriceTier)


@admin.register(PriceTier)
class PriceTierAdmin(_GuestmanPriceTierAdmin):
    """A faixa de preço do guestman, com o desconto automático do grupo."""

    form = PriceTierGroupDiscountForm
    inlines = [PriceTierAdvantageInline]
    list_display = [*_GuestmanPriceTierAdmin.list_display, "group_discount_display"]
    fieldsets = [
        (None, {"fields": ("name", "ref", "description", "listing_ref", "is_default", "priority", "metadata")}),
        (
            "Desconto automático",
            {
                "fields": (
                    "group_discount_type",
                    "group_discount_value",
                    "group_discount_channels",
                    "group_pickup_only",
                    "group_discount_kind",
                    "group_rounding",
                    "group_savings_message",
                ),
                "description": (
                    "Quem é deste grupo ganha o desconto sozinho quando é identificado na venda. "
                    "Ele disputa com os outros descontos automáticos da linha e o maior ganha: não soma."
                ),
            },
        ),
    ]

    def save_model(self, request, obj, form, change):
        previous_ref = form.initial.get("ref", "") if change else ""
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            merged = _metadata_with_group_settings(obj.metadata or {}, form)
            if merged != (obj.metadata or {}):
                obj.metadata = merged
                obj.save(update_fields=["metadata"])
            sync_group_discount(obj, form, previous_ref=previous_ref)

    def get_queryset(self, request):
        # O desconto de cada grupo num único JOIN (não uma consulta por linha).
        group_promo = Promotion.objects.filter(
            ref=Concat(Value(promotion_service.GROUP_DISCOUNT_REF_PREFIX), OuterRef("ref")),
            is_active=True,
        )
        return super().get_queryset(request).annotate(
            _group_discount_type=Subquery(group_promo.values("type")[:1]),
            _group_discount_value=Subquery(group_promo.values("value")[:1]),
        )

    @display(description="Desconto")
    def group_discount_display(self, obj):
        kind = getattr(obj, "_group_discount_type", None)
        if not kind:
            return "-"
        value = int(getattr(obj, "_group_discount_value", 0) or 0)
        return f"{value}%" if kind == Promotion.PERCENT else f"R$ {format_money(value)} por pedido"
