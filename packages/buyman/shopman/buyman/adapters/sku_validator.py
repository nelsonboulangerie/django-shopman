"""
Buyman SkuValidator — resolve insumos (Material) via Stockman's SkuValidator protocol.

An ingredient is a `Material`, not a sellable Product. This adapter lets stock
queries resolve an ingredient sku to its unit/shelf-life. It reports
``is_sellable=False`` (insumo não é vendável) with ``availability_policy=planned_ok``
(insumo pode ser planejado/segurado para produção).

Composed with Offerman's validator in the orchestrator (Offerman p/ vendáveis +
Buyman p/ insumos). Imports of Stockman protocols are lazy (ADR-001).
"""

from __future__ import annotations

import threading


class MaterialSkuValidator:
    """SkuValidator implementation backed by Buyman's Material master."""

    def validate_sku(self, sku: str):
        from shopman.buyman.models import Material
        from shopman.stockman.protocols.sku import SkuValidationResult

        material = Material.objects.filter(sku=sku).first()
        if material is None:
            return SkuValidationResult(valid=False, sku=sku, error_code="not_found")
        return SkuValidationResult(
            valid=True,
            sku=sku,
            product_name=material.name,
            is_published=material.is_active,
            is_sellable=False,
        )

    def validate_skus(self, skus: list[str]) -> dict:
        from shopman.buyman.models import Material
        from shopman.stockman.protocols.sku import SkuValidationResult

        found = {m.sku: m for m in Material.objects.filter(sku__in=skus)}
        result = {}
        for sku in skus:
            material = found.get(sku)
            if material is None:
                result[sku] = SkuValidationResult(valid=False, sku=sku, error_code="not_found")
            else:
                result[sku] = SkuValidationResult(
                    valid=True,
                    sku=sku,
                    product_name=material.name,
                    is_published=material.is_active,
                    is_sellable=False,
                )
        return result

    def _to_sku_info(self, material):
        """Um insumo, visto pelo contrato de SKU do Stockman.

        Fonte única dos dez campos: `get_sku_info`, `get_sku_infos` e
        `search_skus` respondem pela MESMA construção, então não existe o dia em
        que alguém atualiza duas cópias e esquece a terceira.
        """
        from shopman.stockman.protocols.sku import SkuInfo

        return SkuInfo(
            sku=material.sku,
            name=material.name,
            description=None,
            is_published=material.is_active,
            is_sellable=False,
            unit=material.unit,
            category="insumo",
            base_price_q=None,
            availability_policy="planned_ok",
            shelflife_days=material.shelf_life_days,
            metadata=material.metadata or None,
        )

    def get_sku_info(self, sku: str):
        from shopman.buyman.models import Material

        material = Material.objects.filter(sku=sku).first()
        if material is None:
            return None
        return self._to_sku_info(material)

    def get_sku_infos(self, skus: list[str]) -> dict:
        from shopman.buyman.models import Material

        found = {m.sku: m for m in Material.objects.filter(sku__in=skus)}
        return {
            sku: (self._to_sku_info(found[sku]) if sku in found else None)
            for sku in skus
        }

    def search_skus(self, query: str, limit: int = 20, include_inactive: bool = False) -> list:
        from django.db.models import Q
        from shopman.buyman.models import Material

        qs = Material.objects.filter(Q(sku__icontains=query) | Q(name__icontains=query))
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return [self._to_sku_info(m) for m in qs[:limit]]


_lock = threading.Lock()
_instance: MaterialSkuValidator | None = None


def get_material_sku_validator() -> MaterialSkuValidator:
    """Return the singleton MaterialSkuValidator."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = MaterialSkuValidator()
    return _instance
