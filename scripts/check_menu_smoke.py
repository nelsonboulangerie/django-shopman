#!/usr/bin/env python3
"""Technical menu smoke from the canonical catalog, independent of curation volume."""
import json
import os
import sys


def check_menu(data, *, minimum_skus=30):
    items = data.get("catalog", {}).get("items")
    if not isinstance(items, list):
        raise ValueError("contrato inválido: catalog.items ausente")
    products = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("sku"), str) or not item["sku"]:
            raise ValueError("contrato inválido: item sem SKU")
        if item.get("availability") not in {"available", "low_stock", "planned_ok", "unavailable"}:
            raise ValueError("contrato inválido: disponibilidade desconhecida")
        products[item["sku"]] = item
    paused = {sku for sku, item in products.items() if item.get("is_paused") is True}
    available = {sku for sku, item in products.items() if sku not in paused
                 and item["availability"] in {"available", "low_stock", "planned_ok"}
                 and item.get("can_add_to_cart") is True}
    result = {"skus": len(products), "paused": len(paused),
              "active": len(products) - len(paused), "available": len(available)}
    if len(products) < minimum_skus:
        raise ValueError(f"cardápio abaixo do piso configurado: {result}; piso={minimum_skus}")
    if not result["active"]:
        raise ValueError(f"cardápio totalmente pausado; conferir curadoria: {result}")
    if not available:
        raise ValueError(f"nenhum item ativo pode ser comprado; conferir disponibilidade: {result}")
    return result


def main():
    try:
        with open(sys.argv[1], encoding="utf-8") as source:
            result = check_menu(json.load(source), minimum_skus=max(1, int(os.environ.get("MENU_MIN_SKUS", "30"))))
    except (OSError, ValueError, IndexError, AttributeError) as exc:
        print(f"menu smoke: FAIL — {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
