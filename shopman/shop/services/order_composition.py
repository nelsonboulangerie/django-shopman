"""Pedido + ajustes: UMA leitura composta, e todo mundo lê ela.

Por que existe
-------------

``Order.snapshot`` e ``Order.total_q`` são ``SEALED_FIELDS`` do Core: qualquer
``save()`` que os altere levanta ``ImmutabilityError``. Quando o cliente altera
um pedido depois de ele existir — hoje só o ``ORDER_PATCHED`` do iFood —, a
alteração **não tem onde ser escrita por cima**. Ela vive ao lado, em
``order.data["adjustment"]``, e é aqui que pedido e ajuste voltam a ser uma
coisa só.

A alternativa era cada tela somar o ajuste por conta própria. Isso é divergência
garantida: bastaria a cozinha somar e o B.I. não somar para que o pão feito e o
pão faturado deixassem de bater — e ninguém descobriria pelo sistema, só pelo
prejuízo. Por isso a regra é dura: **quem lê item ou total de pedido lê daqui.**

O que o ajuste é, e o que ele NÃO é
-----------------------------------

O ajuste é **estado final absoluto**, nunca delta: a lista inteira de itens e o
total inteiro, relidos da fonte (no iFood, ``ifood_orders.fetch_order``). Delta
é frágil contra reentrega e evento fora de ordem, e este módulo já paga esse
preço em outros lugares. Guardar o estado final faz de uma reentrega um no-op
natural.

O ajuste **não apaga o pedido original**. As linhas de ``OrderItem`` e o
``total_q`` selado continuam lá, intactos, e é o que permite dizer ao operador
"era R$ 25,50, virou R$ 41,00" sem inventar o antes.

Interface
---------

- :func:`effective_items` — os itens que valem AGORA (``EffectiveItem``, mesmos
  nomes de atributo de ``OrderItem``, para o consumidor não precisar mudar nada
  além da linha que busca os itens).
- :func:`effective_total_q` — o total que vale agora, em centavos.
- :func:`effective_items_by_order_id` — a versão em lote, para quem lê muitos
  pedidos de uma vez (fila do Gestor, B.I.) sem N+1.
- :func:`record` — o ÚNICO escritor da chave. Quem reconcilia chama aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

#: A chave em ``Order.data``. Registrada em ``docs/reference/data-schemas.md``.
KEY = "adjustment"


@dataclass(frozen=True)
class EffectiveItem:
    """Um item do pedido depois do ajuste.

    Os nomes dos atributos são os de ``OrderItem`` de propósito: trocar
    ``order.items.all()`` por ``effective_items(order)`` num consumidor é uma
    linha, e nada abaixo dela precisa saber que o ajuste existe.

    Não é um ``OrderItem`` — é um objeto de leitura, sem ``save()``. Um item
    ajustado não tem linha no banco (o pedido é selado), e devolver instância de
    modelo não salva convidaria alguém a gravá-la um dia.
    """

    line_id: str
    sku: str
    name: str
    qty: Decimal
    unit_price_q: int
    line_total_q: int
    meta: dict


def _to_decimal(value) -> Decimal:
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return quantity if quantity.is_finite() else Decimal("0")


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _item_from_payload(payload: dict) -> EffectiveItem:
    return EffectiveItem(
        line_id=str(payload.get("line_id") or ""),
        sku=str(payload.get("sku") or ""),
        name=str(payload.get("name") or ""),
        qty=_to_decimal(payload.get("qty")),
        unit_price_q=_to_int(payload.get("unit_price_q")),
        line_total_q=_to_int(payload.get("line_total_q")),
        meta=payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
    )


def _item_from_row(row) -> EffectiveItem:
    return EffectiveItem(
        line_id=str(row.line_id or ""),
        sku=str(row.sku or ""),
        name=str(row.name or ""),
        qty=_to_decimal(row.qty),
        unit_price_q=_to_int(row.unit_price_q),
        line_total_q=_to_int(row.line_total_q),
        meta=row.meta if isinstance(row.meta, dict) else {},
    )


def as_payload(item: EffectiveItem) -> dict:
    """``EffectiveItem`` → o dict canônico gravado no ajuste e no ingest."""
    from shopman.shop.services.order_helpers import json_quantity

    return {
        "line_id": item.line_id,
        "sku": item.sku,
        "name": item.name,
        "qty": json_quantity(item.qty),
        "unit_price_q": item.unit_price_q,
        "line_total_q": item.line_total_q,
        "meta": item.meta,
    }


# ── Leitura ───────────────────────────────────────────────────────────────────


def adjustment(order) -> dict | None:
    """O ajuste vigente do pedido, ou ``None`` quando ele nunca foi alterado."""
    record = (getattr(order, "data", None) or {}).get(KEY)
    return record if isinstance(record, dict) and record.get("items") is not None else None


def is_adjusted(order) -> bool:
    return adjustment(order) is not None


def original_items(order) -> list[EffectiveItem]:
    """As linhas como o pedido nasceu — o "antes" do aviso ao operador."""
    return [_item_from_row(row) for row in order.items.all()]


def effective_items(order) -> list[EffectiveItem]:
    """Os itens que valem agora: o pedido, com o ajuste aplicado por cima."""
    record = adjustment(order)
    if record is None:
        return original_items(order)
    return [_item_from_payload(payload) for payload in record["items"] if isinstance(payload, dict)]


def effective_total_q(order) -> int:
    """O total que vale agora, em centavos.

    Sem ajuste é o ``Order.total_q`` selado. Com ajuste é o total da fonte —
    no iFood, o ``orderAmount`` do pedido relido, que é o que a plataforma paga.
    """
    record = adjustment(order)
    if record is None or record.get("total_q") is None:
        return _to_int(getattr(order, "total_q", 0))
    return _to_int(record["total_q"])


def effective_items_by_order_id(order_ids) -> dict[int, list[EffectiveItem]]:
    """Itens vigentes de muitos pedidos, em duas consultas.

    Para quem lê pedido em lote (fila do Gestor, B.I.) e não pode pagar um
    ``order.items.all()`` por linha. Pedido sem ajuste vem das linhas; pedido
    com ajuste vem do ajuste, e as linhas dele nem são lidas.
    """
    from shopman.orderman.models import Order, OrderItem

    ids = [int(pk) for pk in order_ids]
    if not ids:
        return {}

    adjusted: dict[int, list[EffectiveItem]] = {}
    for pk, data in _adjusted_rows(Order.objects.filter(pk__in=ids)):
        record = (data or {}).get(KEY)
        if isinstance(record, dict) and isinstance(record.get("items"), list):
            adjusted[pk] = [
                _item_from_payload(payload) for payload in record["items"] if isinstance(payload, dict)
            ]

    by_order: dict[int, list[EffectiveItem]] = {pk: [] for pk in ids}
    by_order.update(adjusted)
    plain = [pk for pk in ids if pk not in adjusted]
    if plain:
        for row in OrderItem.objects.filter(order_id__in=plain):
            by_order[row.order_id].append(_item_from_row(row))
    return by_order


def adjusted_order_ids(order_ids) -> set[int]:
    """Quais destes pedidos têm ajuste — para o lote decidir o que reler."""
    from shopman.orderman.models import Order

    ids = [int(pk) for pk in order_ids]
    if not ids:
        return set()
    return {pk for pk, _data in _adjusted_rows(Order.objects.filter(pk__in=ids))}


def _adjusted_rows(queryset):
    """``(pk, data)`` só dos pedidos que TÊM ajuste, filtrados no banco.

    O filtro é ``data__has_key`` de propósito. Trazer ``data`` de todo pedido da
    janela para depois olhar uma chave em Python custaria alguns KB de JSON por
    pedido no B.I., para descobrir que quase nenhum tem ajuste — ajuste é a
    exceção, e a consulta tem de tratá-lo como exceção.
    """
    return queryset.filter(data__has_key=KEY).values_list("pk", "data")


# ── Diferença, em português de tela ───────────────────────────────────────────


def diff(before: list[EffectiveItem], after: list[EffectiveItem]) -> dict:
    """O que mudou entre duas listas, por ``line_id``.

    Devolve ``{"added": [...], "removed": [...], "changed": [...]}``, cada
    entrada com ``{line_id, sku, name, qty, previous_qty}``. É o que o aviso ao
    operador e a via do pedido usam para dizer o que mexeu, em vez de mandar
    conferir tudo de novo.
    """
    before_by_line = {item.line_id: item for item in before}
    after_by_line = {item.line_id: item for item in after}

    def entry(item: EffectiveItem, previous: EffectiveItem | None) -> dict:
        from shopman.shop.services.order_helpers import json_quantity

        return {
            "line_id": item.line_id,
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": json_quantity(item.qty),
            "previous_qty": None if previous is None else json_quantity(previous.qty),
        }

    added = [entry(item, None) for line_id, item in after_by_line.items() if line_id not in before_by_line]
    removed = [
        entry(item, item) for line_id, item in before_by_line.items() if line_id not in after_by_line
    ]
    changed = [
        entry(item, before_by_line[line_id])
        for line_id, item in after_by_line.items()
        if line_id in before_by_line and before_by_line[line_id].qty != item.qty
    ]
    return {"added": added, "removed": removed, "changed": changed}


def describe(difference: dict) -> str:
    """Uma frase inequívoca sobre a diferença, para o operador.

    Inequívoco antes de curto: diz o verbo, o item e a quantidade, e na troca
    de quantidade diz de quanto para quanto — "2 para 1" e "1 para 2" não podem
    ler igual.
    """
    parts: list[str] = []
    if difference.get("added"):
        parts.append("entrou " + ", ".join(f"{e['qty']}× {e['name']}" for e in difference["added"]))
    if difference.get("removed"):
        parts.append("saiu " + ", ".join(f"{e['qty']}× {e['name']}" for e in difference["removed"]))
    if difference.get("changed"):
        parts.append(
            "mudou "
            + ", ".join(
                f"{e['name']} de {e['previous_qty']} para {e['qty']}" for e in difference["changed"]
            )
        )
    return "; ".join(parts)


def is_empty(difference: dict) -> bool:
    return not any(difference.get(key) for key in ("added", "removed", "changed"))


# ── Escrita ───────────────────────────────────────────────────────────────────


def record(order, *, items: list[dict], total_q: int | None, source: str, event_id: str) -> dict:
    """Grava o ajuste vigente. ÚNICO escritor de ``order.data["adjustment"]``.

    ``items`` é a lista FINAL (não delta), no dict canônico do ingest. O
    registro substitui o anterior, porque estado final substitui estado final;
    ``revision`` conta quantas vezes o pedido foi alterado, e a lista original
    nunca é tocada — ela continua nas linhas de ``OrderItem`` e no
    ``total_q`` selado.

    Não salva o pedido: devolve o registro para o chamador gravar na MESMA
    transação em que reconcilia estoque e cozinha.
    """
    from django.utils import timezone

    previous = adjustment(order) or {}
    return {
        "source": source,
        "event_id": event_id,
        "revision": int(previous.get("revision") or 0) + 1,
        "applied_at": timezone.now().isoformat(),
        "items": items,
        "total_q": None if total_q is None else int(total_q),
        "sealed_total_q": _to_int(getattr(order, "total_q", 0)),
    }


__all__ = [
    "KEY",
    "EffectiveItem",
    "adjusted_order_ids",
    "adjustment",
    "as_payload",
    "describe",
    "diff",
    "effective_items",
    "effective_items_by_order_id",
    "effective_total_q",
    "is_adjusted",
    "is_empty",
    "original_items",
    "record",
]
