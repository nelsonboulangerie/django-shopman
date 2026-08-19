"""
Unfold-themed admin for Buyman (item master de insumo + fornecedores + custo).

CRUD admins for Material, Supplier, MaterialConversion and
SupplierMaterialCost. Registered when 'shopman.buyman.contrib.admin_unfold' is
in INSTALLED_APPS. Buyman has no core admin, so there is nothing to unregister.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from shopman.buyman.models import (
    Material,
    MaterialConversion,
    Supplier,
    SupplierMaterialCost,
)
from shopman.utils.contrib.admin_unfold.badges import unfold_badge
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin, BaseTabularInline
from shopman.utils.monetary import format_money
from unfold.decorators import display


class CostOnSupplierInline(BaseTabularInline):
    """Custos dos insumos fornecidos por este fornecedor."""

    model = SupplierMaterialCost
    extra = 0
    fields = ("material", "conversion", "cost_q", "is_preferred")
    autocomplete_fields = ("material", "conversion")


class CostOnMaterialInline(BaseTabularInline):
    """Custos deste insumo por fornecedor."""

    model = SupplierMaterialCost
    extra = 0
    fields = ("supplier", "conversion", "cost_q", "is_preferred")
    autocomplete_fields = ("supplier", "conversion")


class ConversionOnMaterialInline(BaseTabularInline):
    """Conversões declaradas deste insumo — o que se compra e o que se conta."""

    model = MaterialConversion
    extra = 0
    fields = ("label", "to_base_factor", "kind", "supplier", "is_active")
    autocomplete_fields = ("supplier",)


@admin.register(Material)
class MaterialAdmin(BaseModelAdmin):
    list_display = ("sku", "name", "unit", "shelf_life_display", "is_active")
    list_filter = ("unit", "is_active")
    search_fields = ("sku", "name")
    ordering = ("sku",)
    inlines = (ConversionOnMaterialInline, CostOnMaterialInline)

    @display(description=_("Validade"))
    def shelf_life_display(self, obj: Material):
        if obj.shelf_life_days is None:
            return unfold_badge(_("Não perecível"), "blue")
        return unfold_badge(_("%(d)d dias") % {"d": obj.shelf_life_days}, "orange")


@admin.register(Supplier)
class SupplierAdmin(BaseModelAdmin):
    list_display = ("ref", "name", "document", "is_active")
    list_filter = ("is_active",)
    search_fields = ("ref", "name", "document")
    ordering = ("name",)
    inlines = (CostOnSupplierInline,)


@admin.register(SupplierMaterialCost)
class SupplierMaterialCostAdmin(BaseModelAdmin):
    list_display = (
        "material", "supplier", "cost_display", "base_cost_display", "preferred_display",
    )
    list_filter = ("is_preferred",)
    search_fields = ("material__sku", "material__name", "supplier__ref", "supplier__name")
    autocomplete_fields = ("material", "supplier", "conversion")
    ordering = ("material", "supplier")

    @display(description=_("Custo da compra"))
    def cost_display(self, obj: SupplierMaterialCost):
        """O número da nota, com a unidade em que ele foi digitado."""
        return f"{format_money(obj.cost_q)} / {obj.purchase_unit_label}".strip(" /")

    @display(description=_("Por unidade-base"))
    def base_cost_display(self, obj: SupplierMaterialCost):
        """A divisão que o operador não precisa fazer — e o "≈" quando é estimada."""
        prefix = "≈ " if obj.is_approximate else ""
        unit = obj.material.unit if obj.material_id else ""
        return f"{prefix}{format_money(obj.cost_per_base_unit_q)} / {unit}".strip(" /")

    @display(description=_("Preferencial"))
    def preferred_display(self, obj: SupplierMaterialCost):
        if obj.is_preferred:
            return unfold_badge(_("Preferencial"), "green")
        return unfold_badge(_("Alternativo"), "base")


@admin.register(MaterialConversion)
class MaterialConversionAdmin(BaseModelAdmin):
    list_display = ("material", "label", "factor_display", "scope_display", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("material__sku", "material__name", "label", "supplier__name")
    autocomplete_fields = ("material", "supplier")
    ordering = ("material", "label")

    @display(description=_("Fator"))
    def factor_display(self, obj: MaterialConversion):
        # O "≈" é o carimbo da regra R3: número que veio de equivalência
        # aproximada não circula liso, nem na lista do Admin.
        prefix = "≈ " if obj.is_approximate else ""
        unit = obj.material.unit if obj.material_id else ""
        return f"{prefix}{obj.to_base_factor.normalize():f} {unit}".strip()

    @display(description=_("Escopo"))
    def scope_display(self, obj: MaterialConversion):
        if obj.supplier_id:
            return unfold_badge(obj.supplier.name or obj.supplier.ref, "orange")
        return unfold_badge(_("Qualquer fornecedor"), "base")
