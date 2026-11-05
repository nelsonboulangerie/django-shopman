"""Promotion + Coupon admin — storefront discount management."""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from shopman.utils.contrib.admin_unfold.money import MoneyReaisField, parse_reais
from shopman.utils.monetary import format_money
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminTextInputWidget

from shopman.shop.models import Coupon, Promotion


class PromotionAdminForm(forms.ModelForm):
    """Dinheiro em reais na tela; o modelo continua em centavos.

    ``value`` muda de grandeza com o tipo: percentual é número de 1 a 100; valor
    fixo e teto do frete são dinheiro. Com o inteiro cru, o gestor digitava
    centavos de cabeça (beta test 05/11/2026, ADM-09).
    """

    value = forms.CharField(
        label="valor",
        widget=UnfoldAdminTextInputWidget(attrs={"inputmode": "decimal"}),
        help_text=(
            "Percentual: de 1 a 100. Valor fixo: o desconto em reais, como 15,00. "
            "Entrega grátis: o teto do frete em reais, ou 0 para o frete inteiro."
        ),
    )
    min_order_q = MoneyReaisField(
        label="pedido mínimo",
        required=False,
        help_text="Em reais. Em branco ou 0,00: sem mínimo.",
    )

    class Meta:
        model = Promotion
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance.pk and instance.value is not None and instance.type != Promotion.PERCENT:
            self.initial["value"] = format_money(instance.value)

    def clean(self):
        cleaned = super().clean()
        raw = str(cleaned.get("value") or "").strip()
        if raw:
            if cleaned.get("type") == Promotion.PERCENT:
                if not raw.isdigit():
                    self.add_error("value", "Percentual é um número inteiro de 1 a 100.")
                else:
                    cleaned["value"] = int(raw)
            else:
                try:
                    cleaned["value"] = parse_reais(raw)
                except ValueError:
                    self.add_error("value", "Informe o valor em reais, como 15,00.")
        if cleaned.get("min_order_q") is None:
            cleaned["min_order_q"] = 0
        return cleaned


class CouponInline(TabularInline):
    """Inline do Unfold, não o do Django: com `admin.TabularInline` os campos saem
    com os widgets do Admin antigo (`AdminTextInputWidget`) dentro de uma tela
    Unfold."""

    model = Coupon
    extra = 1
    fields = ("code", "max_uses", "uses_count", "is_active")
    readonly_fields = ("uses_count",)


def _set_active(model_admin, request, queryset, *, active: bool) -> int:
    """Liga ou desliga `is_active` só nas linhas que mudam, e registra cada uma.

    É a chave de desligar do go-live: precisa ser auditável. O `update()` vai só nas
    linhas cujo valor muda (pausar o que já está pausado não conta como pausa), e
    cada uma ganha um `LogEntry` no histórico do objeto.
    """
    changed = list(queryset.exclude(is_active=active))
    if not changed:
        return 0
    change_message = "Reativação em lote." if active else "Pausa em lote."
    with transaction.atomic():
        queryset.model.objects.filter(pk__in=[obj.pk for obj in changed]).update(is_active=active)
        for obj in changed:
            obj.is_active = active
            model_admin.log_change(request, obj, change_message)
    return len(changed)


class PromotionStatusFilter(admin.SimpleListFilter):
    title = "situação"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [
            ("ativa", "Ativa agora"),
            ("futura", "Futura"),
            ("expirada", "Expirada"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "ativa":
            return queryset.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
        if self.value() == "futura":
            return queryset.filter(is_active=True, valid_from__gt=now)
        if self.value() == "expirada":
            return queryset.filter(valid_until__lt=now)
        return queryset


@admin.register(Promotion)
class PromotionAdmin(ModelAdmin):
    form = PromotionAdminForm
    list_display = (
        "name", "value_display", "valid_from", "valid_until",
        "birthday_only", "status_badge",
    )
    list_filter = (PromotionStatusFilter, "is_active", "type", "birthday_only")
    search_fields = ("name",)
    ordering = ("-valid_from",)
    inlines = [CouponInline]
    actions = ["pause_selected", "reactivate_selected"]

    # Pausar a promoção NÃO mexe nos cupons dela: não precisa. `get_coupon_promotion`
    # exige `promotion.is_active`, então promoção pausada já não dá desconto por
    # código nenhum, e os cupons voltam a valer sozinhos quando ela for reativada.
    @admin.action(description="Pausar promoções selecionadas", permissions=["change"])
    def pause_selected(self, request, queryset):
        count = _set_active(self, request, queryset, active=False)
        if count == 0:
            self.message_user(
                request,
                "Nenhuma promoção mudou: as selecionadas já estavam pausadas.",
                level=messages.WARNING,
            )
        elif count == 1:
            self.message_user(
                request,
                "1 promoção pausada. Nenhum desconto dela vale até reativar, nem por cupom.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"{count} promoções pausadas. Nenhum desconto delas vale até reativar, nem por cupom.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Reativar promoções selecionadas", permissions=["change"])
    def reactivate_selected(self, request, queryset):
        count = _set_active(self, request, queryset, active=True)
        if count == 0:
            self.message_user(
                request,
                "Nenhuma promoção mudou: as selecionadas já estavam ativas.",
                level=messages.WARNING,
            )
        elif count == 1:
            self.message_user(
                request,
                "1 promoção reativada. Volta a valer dentro do prazo de validade.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"{count} promoções reativadas. Voltam a valer dentro do prazo de validade.",
                level=messages.SUCCESS,
            )

    @admin.display(description="desconto", ordering="value")
    def value_display(self, obj):
        if obj.type == Promotion.PERCENT:
            return f"{obj.value}%"
        return f"R$ {format_money(obj.value)}"

    @display(
        description="situação",
        label={"Ativa": "success", "Futura": "info", "Expirada": "danger", "Inativa": "warning"},
    )
    def status_badge(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return "Inativa"
        if obj.valid_from > now:
            return "Futura"
        if obj.valid_until < now:
            return "Expirada"
        return "Ativa"


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = (
        "code", "promotion", "usage_display", "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "promotion__name")
    ordering = ("code",)
    readonly_fields = ("uses_count",)
    actions = ["reset_usage", "pause_selected", "reactivate_selected"]

    @admin.action(description="Zerar contador de usos")
    def reset_usage(self, request, queryset):
        updated = queryset.update(uses_count=0)
        self.message_user(request, f"{updated} cupom(ns) com contador zerado.")

    # Pausar o cupom NÃO mexe na promoção dele: promoção com cupom só é resolvida
    # pelo código (`get_active_promotions` exclui as que têm cupom), então pausar o
    # cupom já basta para parar o desconto que vem por ele. Pausar a promoção
    # derrubaria também os outros cupons dela, que não foram selecionados.
    @admin.action(description="Pausar cupons selecionados", permissions=["change"])
    def pause_selected(self, request, queryset):
        count = _set_active(self, request, queryset, active=False)
        if count == 0:
            self.message_user(
                request,
                "Nenhum cupom mudou: os selecionados já estavam pausados.",
                level=messages.WARNING,
            )
        elif count == 1:
            self.message_user(
                request,
                "1 cupom pausado. O código dele não dá desconto até reativar.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"{count} cupons pausados. Os códigos deles não dão desconto até reativar.",
                level=messages.SUCCESS,
            )

    @admin.action(description="Reativar cupons selecionados", permissions=["change"])
    def reactivate_selected(self, request, queryset):
        count = _set_active(self, request, queryset, active=True)
        if count == 0:
            self.message_user(
                request,
                "Nenhum cupom mudou: os selecionados já estavam ativos.",
                level=messages.WARNING,
            )
        elif count == 1:
            self.message_user(
                request,
                "1 cupom reativado. O código volta a dar desconto se a promoção dele estiver ativa e no prazo.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"{count} cupons reativados. Os códigos voltam a dar desconto se a promoção de cada um estiver ativa e no prazo.",
                level=messages.SUCCESS,
            )

    @admin.display(description="uso")
    def usage_display(self, obj):
        if obj.max_uses == 0:
            return f"{obj.uses_count} (ilimitado)"
        return f"{obj.uses_count}/{obj.max_uses}"
