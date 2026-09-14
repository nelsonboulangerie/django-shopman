"""Reconciliação pura de um snapshot Catalog v2, sem confirmar vínculos.

Fonte: https://developer.ifood.com.br/en-US/docs/references (catalog-v2,
GetCategoryDto/GetItemDto). O chamador fornece uma leitura completa de
categories?includeItems=true do merchant/catalog/context indicado. Este módulo
não comprova a origem nem a completude da leitura e não consulta ORM ou rede.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class CanonicalProduct(Protocol):
    """Recorte de ProductInfo: identidade SKU canônica e nome para exibição."""

    sku: str
    name: str


@dataclass(frozen=True)
class ReconciliationItem:
    """Uma ocorrência remota; nenhuma sugestão equivale a vínculo confirmado."""

    merchant_id: str
    catalog_id: str
    context: str
    item_id: str
    product_id: str
    category_id: str
    category_name: str
    name: str
    external_code: str
    root_external_code: str
    status: str
    candidate_skus: tuple[str, ...]
    notice: str


@dataclass(frozen=True)
class ReconciliationSummary:
    total_items: int
    suggested: int
    ambiguous: int
    invalid_identity: int
    invalid_context: int
    unmatched: int
    pending: int


@dataclass(frozen=True)
class ReconciliationResult:
    items: tuple[ReconciliationItem, ...]
    summary: ReconciliationSummary


def _text(value: object) -> str:
    # Não converter números/códigos em strings nem normalizar caixa/espaços.
    return value if isinstance(value, str) else ""


def _effective_code(item: Mapping, context: str) -> tuple[str, bool]:
    """ItemContextModifierDto sobrescreve apenas o contexto correspondente.

    GetItemDto também expõe SimpleItemContextModifierDto sem externalCode:
    a ausência do campo não é uma sobrescrita. Nulo não é string no contrato;
    nunca voltar ao código raiz diante de uma sobrescrita inválida.
    """
    code = _text(item.get("externalCode"))
    if "contextModifiers" not in item:
        return code, True
    modifiers = item["contextModifiers"]
    if not isinstance(modifiers, list):
        return "", False
    seen = set()
    for modifier in modifiers:
        if not isinstance(modifier, Mapping):
            return "", False
        target = modifier.get("catalogContext")
        if not isinstance(target, str) or not target.strip() or target in seen:
            return "", False
        seen.add(target)
        if "externalCode" in modifier and not isinstance(modifier["externalCode"], str):
            return "", False
        if target == context and "externalCode" in modifier:
            code = modifier["externalCode"]
    return code, True


def reconcile_ifood_inventory(
    *,
    merchant_id: str,
    catalog_id: str,
    context: str,
    categories: Sequence[Mapping],
    products: Sequence[CanonicalProduct],
) -> ReconciliationResult:
    """Sugere apenas SKU/externalCode exato e único em ambos os lados.

    Cada chamada representa exatamente um merchant, catálogo e contexto. Nunca
    misture snapshots de escopos distintos. IDs remotos existentes são mantidos;
    nomes e códigos de categoria/produto/complemento não substituem externalCode
    do item. Categorias vazias são válidas; formato incompleto levanta ValueError
    para não apresentar inventário parcial como reconciliação bem-sucedida.
    """
    if any(not isinstance(value, str) or not value.strip()
           for value in (merchant_id, catalog_id, context)):
        raise ValueError("Informe loja, catálogo e contexto do inventário.")
    if not isinstance(categories, (list, tuple)):
        raise ValueError("O inventário deve ser uma lista de categorias.")
    local: dict[str, list[CanonicalProduct]] = defaultdict(list)
    for product in products:
        if not isinstance(product.sku, str) or not product.sku.strip():
            raise ValueError("Produto canônico sem SKU válido.")
        local[product.sku].append(product)

    rows = []
    for category in categories:
        if not isinstance(category, Mapping) or not isinstance(category.get("items"), list):
            raise ValueError("Categoria sem lista de itens; leia com includeItems=true.")
        for item in category["items"]:
            if not isinstance(item, Mapping):
                raise ValueError("Item inválido no inventário.")
            rows.append((category, item))
    effective_codes = [_effective_code(item, context) for _, item in rows]
    codes = Counter(code for code, valid in effective_codes if valid)
    identities = Counter(_text(item.get("id")) for _, item in rows)
    result = []
    for (category, item), (code, valid_context) in zip(rows, effective_codes, strict=True):
        item_id = _text(item.get("id"))
        product_id = _text(item.get("productId"))
        category_id = _text(category.get("id"))
        candidates = tuple(sorted({p.sku for p in local.get(code, [])}))
        if "categoryId" in item and item["categoryId"] != category_id:
            raise ValueError("Categoria do item diverge da categoria do inventário.")
        if not valid_context:
            candidates = ()
            status, notice = "invalid_context", "Modificadores de contexto inválidos; confira o inventário."
        elif not all(value.strip() for value in (item_id, product_id, category_id)):
            status, notice = "invalid_identity", "Identidade remota incompleta; confira o inventário."
        elif identities[item_id] > 1:
            status, notice = "duplicate_identity", "Item remoto repetido no inventário; confira as ocorrências."
        elif not code.strip():
            status, notice = "missing_code", "Item sem código externo; selecione o produto canônico."
        elif codes[code] > 1 or len(local.get(code, [])) > 1:
            status, notice = "ambiguous_code", "Código repetido; revise cada anúncio antes de vincular."
        elif candidates:
            status, notice = "suggested", "Código exato e único; confirme o vínculo explicitamente."
        else:
            status, notice = "unmatched_code", "Código sem SKU correspondente; selecione o produto canônico."
        result.append(ReconciliationItem(
            merchant_id=merchant_id, catalog_id=catalog_id, context=context,
            item_id=item_id, product_id=product_id, category_id=category_id,
            category_name=_text(category.get("name")), name=_text(item.get("name")),
            external_code=code, root_external_code=_text(item.get("externalCode")),
            status=status, candidate_skus=candidates, notice=notice,
        ))
    counts = Counter(row.status for row in result)
    return ReconciliationResult(
        items=tuple(result),
        summary=ReconciliationSummary(
            total_items=len(result), suggested=counts["suggested"],
            ambiguous=counts["ambiguous_code"] + counts["duplicate_identity"],
            invalid_identity=counts["invalid_identity"], invalid_context=counts["invalid_context"],
            unmatched=counts["missing_code"] + counts["unmatched_code"],
            pending=len(result),
        ),
    )
