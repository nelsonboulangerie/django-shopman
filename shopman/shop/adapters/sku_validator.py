"""
Composed SkuValidator — Offerman (vendáveis) + Buyman (insumos) + neutro.

Resolves a sku as a sellable Product (Offerman) first, then as an ingredient
Material (Buyman). Implements Stockman's SkuValidator protocol.

Ligado em STOCKMAN["SKU_VALIDATOR"] (config/settings.py) — é este validador que
responde disponibilidade e shelf-life de todo sku do sistema.

⚠️ Produto e insumo dividem um namespace de SKU só, sem unicidade cruzada no
banco, e aqui a precedência é do produto. Diferente do catálogo composto, este
caminho é QUENTE (disponibilidade da loja), então ele não paga uma consulta extra
por resolução para detectar colisão: quem impede a colisão de nascer é o porteiro
em shopman/shop/services/sku_namespace.py (pre_save nos dois modelos), e quem
denuncia a colisão preexistente é o system check SHOPMAN_W015.
"""

from __future__ import annotations

import threading


class ComposedSkuValidator:
    """SkuValidator chaining Offerman (products) then Buyman (materials)."""

    def __init__(self):
        from shopman.buyman.adapters.sku_validator import MaterialSkuValidator
        from shopman.offerman.adapters.sku_validator import SkuValidator as OffermanSkuValidator

        self._offerman = OffermanSkuValidator()
        self._buyman = MaterialSkuValidator()

    def validate_sku(self, sku: str):
        result = self._offerman.validate_sku(sku)
        if result.valid:
            return result
        material = self._buyman.validate_sku(sku)
        return material if material.valid else result

    def validate_skus(self, skus: list[str]) -> dict:
        merged = self._offerman.validate_skus(skus)
        missing = [sku for sku, r in merged.items() if not r.valid]
        if missing:
            for sku, r in self._buyman.validate_skus(missing).items():
                if r.valid:
                    merged[sku] = r
        return merged

    def get_sku_info(self, sku: str):
        return self._offerman.get_sku_info(sku) or self._buyman.get_sku_info(sku)

    def get_sku_infos(self, skus: list[str]) -> dict:
        merged = self._offerman.get_sku_infos(skus)
        missing = [sku for sku, info in merged.items() if info is None]
        if missing:
            for sku, info in self._buyman.get_sku_infos(missing).items():
                if info is not None:
                    merged[sku] = info
        return merged

    def search_skus(self, query: str, limit: int = 20, include_inactive: bool = False) -> list:
        results = list(self._offerman.search_skus(query, limit=limit, include_inactive=include_inactive))
        seen = {info.sku for info in results}
        for info in self._buyman.search_skus(query, limit=limit, include_inactive=include_inactive):
            if info.sku not in seen and len(results) < limit:
                results.append(info)
                seen.add(info.sku)
        return results


_lock = threading.Lock()
_instance: ComposedSkuValidator | None = None


def get_composed_sku_validator() -> ComposedSkuValidator:
    """Return the singleton ComposedSkuValidator."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ComposedSkuValidator()
    return _instance


def reset_composed_sku_validator() -> None:
    """Reset the singleton (for tests)."""
    global _instance
    _instance = None
