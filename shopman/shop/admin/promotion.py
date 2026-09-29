"""Promotion + Coupon admin — storefront discount management."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from shopman.shop.models import Coupon, Promotion


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
        return f"R$ {obj.value / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
