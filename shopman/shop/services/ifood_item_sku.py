"""Qual produto da casa é o item que chegou num pedido do iFood.

O pedido do iFood traz dois identificadores por item: o ``id`` do item no
cardápio deles e o ``externalCode`` (o "código PDV" que a loja digita no
Portal). Até 13/11/2026 a ingestão usava ``externalCode or id`` como SKU, e
nenhum dos dois é o nosso SKU sem alguém ter feito isso de propósito: no
primeiro pedido real (IFOOD-261112-3417) os dois itens viraram
``stock_unknown_sku``, não baixaram estoque e o ticket caiu na estação
genérica da cozinha.

A ponte entre os dois mundos já existe e é decisão humana: o
``CatalogBinding``, confirmado na revisão de vínculos do canal
(``backstage/services/catalog_bindings.bind_item``). A ordem aqui é:

1. **vínculo confirmado** do canal e da conta, pelo ``id`` do item (o
   ``resource_id`` do vínculo) ou, quando o iFood manda o id do produto, pelo
   ``external_product_ref``;
2. **o ``externalCode`` já é um SKU nosso** (a loja preencheu o código PDV
   com o SKU da casa no Portal);
3. **nada disso**: o item entra como veio. O pedido nunca quebra por isso (o
   cliente já pagou no iFood); o aviso ``stock_unknown_sku`` sai na reserva
   (``services/stock._alert_unknown_sku``) e leva à revisão de vínculos.

Dois vínculos apontando o mesmo item para produtos diferentes não se
desempatam por ordem do banco: o item fica sem resolver e o log diz por quê.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROVIDER = "ifood"

#: Como o SKU da linha foi decidido (``OrderItem.meta.catalog_link.source``).
SOURCE_BINDING = "binding"
SOURCE_EXTERNAL_CODE = "external_code"
SOURCE_UNBOUND = "unbound"
SOURCE_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ItemLink:
    sku: str
    source: str
    remote_sku: str
    remote_item_id: str

    def as_meta(self) -> dict:
        return {
            "source": self.source,
            "remote_sku": self.remote_sku,
            "remote_item_id": self.remote_item_id,
        }


def resolve_items(items: list[dict], *, channel_ref: str, merchant_id: str = "") -> list[dict]:
    """Devolve ``items`` (payload canônico) com o ``sku`` da casa onde houver.

    Não altera a lista recebida. Cada item ganha ``meta.catalog_link`` com o
    código que veio do iFood, para que o B.I., o suporte e a revisão de
    vínculos saibam de onde o SKU saiu.
    """
    remote_ids = {
        str(value)
        for item in items
        for value in (item.get("line_id"), item.get("sku"))
        if value
    }
    bindings = _bindings_by_remote_id(remote_ids, channel_ref=channel_ref, merchant_id=merchant_id)
    local_skus = _existing_skus({str(item.get("sku") or "") for item in items} - {""})

    resolved: list[dict] = []
    for item in items:
        link = _resolve(item, bindings=bindings, local_skus=local_skus)
        meta = dict(item.get("meta") or {})
        meta["catalog_link"] = link.as_meta()
        resolved.append({**item, "sku": link.sku, "meta": meta})
        if link.source in {SOURCE_UNBOUND, SOURCE_AMBIGUOUS}:
            logger.warning(
                "ifood_item_sku.%s channel=%s merchant=%s item_id=%s remote_sku=%s name=%s",
                link.source, channel_ref, merchant_id, link.remote_item_id,
                link.remote_sku, item.get("name", ""),
            )
    return resolved


def _resolve(item: dict, *, bindings: dict[str, set[str]], local_skus: set[str]) -> ItemLink:
    remote_sku = str(item.get("sku") or "")
    remote_item_id = str(item.get("line_id") or "")

    skus: set[str] = set()
    for key in (remote_item_id, remote_sku):
        if key:
            skus |= bindings.get(key, set())
    if len(skus) == 1:
        return ItemLink(skus.pop(), SOURCE_BINDING, remote_sku, remote_item_id)
    if len(skus) > 1:
        return ItemLink(remote_sku, SOURCE_AMBIGUOUS, remote_sku, remote_item_id)
    if remote_sku in local_skus:
        return ItemLink(remote_sku, SOURCE_EXTERNAL_CODE, remote_sku, remote_item_id)
    return ItemLink(remote_sku, SOURCE_UNBOUND, remote_sku, remote_item_id)


def _bindings_by_remote_id(remote_ids: set[str], *, channel_ref: str, merchant_id: str) -> dict[str, set[str]]:
    if not remote_ids or not channel_ref:
        return {}
    from django.db.models import Q

    from shopman.shop.models import CatalogBinding

    rows = CatalogBinding.objects.filter(provider=PROVIDER, channel__ref=channel_ref).filter(
        Q(resource_id__in=remote_ids) | Q(external_product_ref__in=remote_ids)
    )
    # Vínculo de outra conta do iFood não serve a este pedido; sem merchant no
    # payload (simulação de dev), vale o canal.
    if merchant_id:
        rows = rows.filter(account_ref=merchant_id)
    found: dict[str, set[str]] = {}
    for resource_id, product_ref, sku in rows.values_list("resource_id", "external_product_ref", "product__sku"):
        for key in (resource_id, product_ref):
            if key in remote_ids:
                found.setdefault(key, set()).add(sku)
    return found


def _existing_skus(candidates: set[str]) -> set[str]:
    if not candidates:
        return set()
    from shopman.offerman.models import Product

    return set(Product.objects.filter(sku__in=candidates).values_list("sku", flat=True))
