"""Prepara revisão local; snapshot remoto e cadastro exemplo nunca são fundidos."""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime

from shopman.shop.services.ifood_catalog_reconciliation import reconcile_ifood_inventory


def _identity(value):
    return isinstance(value, str) and bool(value.strip())


def _indexed(rows, label):
    if not isinstance(rows, list):
        raise ValueError(f"{label}: informe uma lista.")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not _identity(row.get("id")) or row["id"] in result:
            raise ValueError(f"{label}: identidade ausente ou repetida.")
        result[row["id"]] = row
    return result


def validate_review_snapshot(snapshot):
    """Valida cobertura interna declarada, sem atestar origem ou atualidade.

    O envelope é nosso contrato de arquivo, não um payload de escrita iFood.
    category_items conserva as respostas GetCategoryItemsDto completas.
    Campos opcionais ausentes continuam ausentes: não usar cadastro como fallback.
    """
    if not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        raise ValueError("Snapshot exige schema_version 1.")
    if any(not _identity(snapshot.get(key)) for key in ("merchant_id", "catalog_id", "context")):
        raise ValueError("Informe loja, catálogo e contexto de origem.")
    if snapshot.get("source") not in ("imported_file", "api_capture"):
        raise ValueError("Origem de snapshot desconhecida.")
    try:
        captured = datetime.fromisoformat(snapshot["captured_at"].replace("Z", "+00:00"))
        if captured.tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("Informe captured_at com data, hora e fuso da coleta.") from None
    categories = _indexed(snapshot.get("categories"), "Categorias")
    responses = snapshot.get("category_items")
    if not isinstance(responses, list):
        raise ValueError("Informe category_items com as respostas completas por categoria.")
    details = {}
    for response in responses:
        if not isinstance(response, dict) or not _identity(response.get("categoryId")):
            raise ValueError("Resposta completa sem categoryId.")
        ref = response["categoryId"]
        if ref in details:
            raise ValueError("Resposta de categoria repetida.")
        details[ref] = response
    if set(categories) != set(details):
        raise ValueError("Faltam respostas de categorias ou há categorias fora do snapshot.")
    projected_categories = []
    seen = set()
    for ref, category in categories.items():
        brief = _indexed(category.get("items"), "Itens resumidos")
        detail = details[ref]
        items = _indexed(detail.get("items"), "Itens completos")
        if set(brief) != set(items):
            raise ValueError("Itens resumidos e completos divergem; refaça a coleta.")
        products = _indexed(detail.get("products", []), "Produtos remotos")
        for key in ("optionGroups", "options"):
            if key in detail and not isinstance(detail[key], list):
                raise ValueError("Complementos remotos devem ser listas quando presentes.")
        projected = []
        for item_id, item in items.items():
            if item_id in seen:
                raise ValueError("Item repetido entre categorias; refaça a coleta.")
            seen.add(item_id)
            if "categoryId" in item and item["categoryId"] != ref:
                raise ValueError("Categoria do item diverge da resposta.")
            if not _identity(item.get("productId")):
                raise ValueError("Item completo sem productId.")
            if brief[item_id].get("productId") != item["productId"]:
                raise ValueError("Produto do item mudou durante a coleta.")
            product = products.get(item["productId"])
            projected.append({**item, "name": (product or {}).get("name", "")})
        projected_categories.append({**category, "items": projected})
    return projected_categories


def build_ifood_catalog_review(*, snapshot, products, local_details):
    """Sugestões não confirmam vínculos nem aprovam alterações locais/remotas."""
    categories = validate_review_snapshot(snapshot)
    reconciliation = reconcile_ifood_inventory(
        merchant_id=snapshot["merchant_id"], catalog_id=snapshot["catalog_id"],
        context=snapshot["context"], categories=categories, products=products,
    )
    responses = {row["categoryId"]: row for row in snapshot["category_items"]}
    rows = []
    for result in reconciliation.items:
        response = responses[result.category_id]
        item = next(row for row in response["items"] if row["id"] == result.item_id)
        product = next((row for row in response.get("products", []) if row["id"] == result.product_id), None)
        modifiers = item.get("contextModifiers", [])
        # Não resolver defaults quando os modificadores forem inválidos.
        effective = None
        if result.status != "invalid_context":
            modifier = next((row for row in modifiers if row["catalogContext"] == snapshot["context"]), {})
            effective = {key: deepcopy(modifier[key] if key in modifier else item[key])
                         for key in ("price", "status", "externalCode") if key in modifier or key in item}
            effective["itemContextId"] = modifier.get("itemContextId")
        rows.append({
            "identity": asdict(result),
            "review_status": "pending", "binding_confirmed": False,
            "remote": {"item": deepcopy(item), "product": deepcopy(product), "effective_context": effective},
            "local_candidates": [deepcopy(local_details[sku]) for sku in result.candidate_skus if sku in local_details],
            "notices": ["Dados locais ainda precisam de revisão; salvar este relatório não altera cadastros."]
                + (["Dados do produto remoto ausentes; não foram preenchidos com dados locais."] if product is None else []),
        })
    return {
        "schema_version": 1, "purpose": "local_review_only", "write_authorized": False,
        "scope": {key: snapshot[key] for key in ("merchant_id", "catalog_id", "context", "captured_at", "source")},
        "coverage": {"category_count": len(categories), "item_count": len(rows),
                     "internally_consistent": True, "origin_verified": False,
                     "notice": "Cobertura confere dentro do arquivo; origem, completude na plataforma e atualidade não foram verificadas."},
        "summary": asdict(reconciliation.summary), "items": rows,
        "remote_snapshot": deepcopy(snapshot),
    }
