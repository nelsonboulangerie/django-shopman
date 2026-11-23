"""Rateio de desconto de PEDIDO entre as linhas da sacola.

O desconto de pedido de valor fixo (cupom, promoção), o resgate de pontos e o
desconto manual do PDV saem do PREÇO UNITÁRIO de cada linha, em centavos inteiros,
e o total da linha sai do unitário: ``line_total_q == qty × unit_price_q``. Quando
sobra centavo que nenhuma linha comporta, a linha se parte em duas (#3240), e a
parte volta à linha de origem no começo do próximo preço (``SplitLineMergeModifier``).
"""

from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
from typing import Any

from shopman.utils.monetary import monetary_div, monetary_mult


def qty_json(qty: Decimal) -> int | float:
    """Quantidade para o registro de transparência (JSON): inteira ou fração de kg."""
    return int(qty) if qty == qty.to_integral_value() else float(qty)


# ── Rateio de desconto de PEDIDO entre as linhas ──────────────────────────
# Invariante que o rateio precisa preservar: ``line_total_q == qty × unit_price_q``.
# É o ``ItemPricingModifier`` (ordem 10) quem a estabelece, e os três rateios de
# pedido (cupom/promo de valor fixo, resgate de pontos, desconto manual do PDV) a
# quebravam do mesmo jeito: piso no unitário (``share // qty``) e valor EXATO no
# total (``line_total - share``). Com ``share % qty != 0`` os dois campos discordam,
# a sacola imprime "3 × R$ 6,34" com total "R$ 19,00" (quem multiplica acha 19,02),
# e é a única conta que o cliente confere sozinho. Os dois campos também descem para
# o payload fiscal, onde a incoerência hoje precisa de tratamento especial
# (``fiscal_focusnfe`` deriva ``vUnCom`` de ``vProd/qCom`` com 10 casas para não ser
# rejeitado pela SEFAZ).
#
# Como o preço unitário é INTEIRO em centavos, o desconto de uma linha só pode ser
# um múltiplo inteiro de ``qty``. Um valor que não é múltiplo de nenhuma combinação
# de ``qty`` das linhas elegíveis é aritmeticamente irrepresentável sem quebrar a
# linha em duas. Em vez de mentir num dos campos, o rateio coloca o resíduo na linha
# que o comporta e, quando nenhuma comporta, arredonda para o lado de quem é dono do
# dinheiro — e o chamador registra o valor REALMENTE aplicado, nunca o nominal.


def line_qty(item: dict) -> Decimal:
    """Quantidade da linha como ``Decimal`` (o campo é decimal: venda por peso)."""
    try:
        qty = Decimal(str(item.get("qty", 1)))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("1")
    return qty if qty > 0 else Decimal("1")


#: Marca da parte de uma linha partida pelo rateio (#3240): guarda a ``line_id``
#: da linha de origem, para onde as unidades voltam no próximo preço.
SPLIT_OF = "_split_of"


def split_line_id(line_id: str) -> str:
    """A ``line_id`` estável da parte partida: o mesmo rateio regrava a mesma linha."""
    return f"{line_id}~r"


def split_siblings(items: list[dict], line_id: str) -> list[dict]:
    """As partes partidas de ``line_id`` na sacola."""
    return [i for i in items if (i.get("meta") or {}).get(SPLIT_OF) == line_id]


def spread_order_discount(
    lines: list[dict], amount_q: int, *, at_least: bool = False, split: bool = False
) -> list[tuple[dict, int, int]]:
    """Rateia ``amount_q`` entre ``lines`` reduzindo o PREÇO UNITÁRIO e recalculando
    o total da linha a partir dele — nunca o contrário.

    ``at_least=True`` permite estourar o alvo no mínimo possível quando ele não é
    representável (promoção/cupom de valor fixo: a casa PROMETEU "R$ 5 de desconto",
    então entrega pelo menos isso). ``at_least=False`` fica abaixo (resgate de pontos
    e desconto manual: nunca debitar mais pontos do que o cliente pediu, nem dar mais
    do que o operador autorizou).

    ``split=True`` parte a linha em duas quando sobra centavo que nenhuma linha
    comporta, e o desconto fecha exato (#3240). A parte nova volta em ``touched``
    com ``meta[SPLIT_OF]``, e o chamador a insere logo depois da linha de origem.

    Devolve ``[(linha, desconto_por_unidade_q, desconto_da_linha_q)]`` só das linhas
    tocadas; o chamador soma ``desconto_da_linha_q`` para registrar o desconto de
    verdade em ``session.pricing``.
    """
    eligible = [i for i in lines if int(i.get("line_total_q", 0) or 0) > 0]
    subtotal = sum(int(i.get("line_total_q", 0) or 0) for i in eligible)
    if not eligible or subtotal <= 0 or amount_q <= 0:
        return []
    amount_q = min(int(amount_q), subtotal)

    # [linha, qty, unit_q, line_total_q, per_unit]
    plan: list[list[Any]] = []

    def _cost(entry: list[Any], per_unit: int) -> int:
        """Quanto a linha cai com este desconto por unidade, medido no total."""
        _, qty, unit_q, line_total_q, _ = entry
        return line_total_q - monetary_mult(qty, unit_q - per_unit)

    # Passo 1 — cota proporcional de cada linha, com o resto na última (a soma das
    # cotas é exatamente ``amount_q``), convertida no maior desconto por unidade que
    # cabe na cota.
    remaining_share = amount_q
    last = len(eligible) - 1
    for idx, item in enumerate(eligible):
        line_total_q = int(item.get("line_total_q", 0) or 0)
        qty = line_qty(item)
        unit_q = int(item.get("unit_price_q", 0) or 0)
        share = remaining_share if idx == last else monetary_div(amount_q * line_total_q, subtotal)
        share = max(0, min(share, line_total_q, remaining_share))
        remaining_share -= share

        entry: list[Any] = [item, qty, unit_q, line_total_q, 0]
        per_unit = max(0, min(unit_q, int(Decimal(share) / qty)))
        while per_unit > 0 and _cost(entry, per_unit) > share:
            per_unit -= 1
        while per_unit < unit_q and _cost(entry, per_unit + 1) <= share:
            per_unit += 1
        entry[4] = per_unit
        plan.append(entry)

    applied = sum(_cost(e, e[4]) for e in plan)
    remaining = amount_q - applied

    def _step(entry: list[Any]) -> int:
        """Custo de dar mais um centavo de desconto por unidade nesta linha."""
        return _cost(entry, entry[4] + 1) - _cost(entry, entry[4])

    # Passo 2 — o resíduo (< soma dos ``qty``) vai para as linhas que o comportam,
    # do menor passo para o maior, para caber no maior número de casos. Um carrinho
    # com qualquer linha de 1 unidade absorve qualquer resíduo.
    progress = True
    while remaining > 0 and progress:
        progress = False
        for entry in sorted((e for e in plan if e[4] < e[2]), key=_step):
            step = _step(entry)
            if 0 < step <= remaining:
                entry[4] += 1
                remaining -= step
                applied += step
                progress = True
                break

    # Passo 3 — sobrou e ninguém comporta (linha única de 3 Croissants × cupom de
    # R$ 5,00). Com ``split``, a linha se parte em duas (#3240): ``remaining``
    # unidades levam um centavo a mais de desconto e as outras ficam como estão,
    # e o total fecha exato (2 a R$ 11,33 e 1 a R$ 11,34 = R$ 34,00). Cada parte
    # segue com ``line_total_q == qty × unit_price_q``. A parte nova é irmã da
    # linha (``meta[SPLIT_OF]``) e volta a ela no começo do próximo preço
    # (``SplitLineMergeModifier``).
    if remaining > 0 and split:
        for entry in plan:
            item, qty, unit_q, _, per_unit = entry
            whole = qty == qty.to_integral_value()
            if not whole or qty <= remaining or per_unit + 1 > unit_q:
                continue
            rest_qty = qty - remaining
            sibling = copy.deepcopy(item)
            sibling["line_id"] = split_line_id(str(item.get("line_id") or ""))
            sibling["qty"] = qty_json(rest_qty)
            sibling.setdefault("meta", {})[SPLIT_OF] = str(item.get("line_id") or "")
            item["qty"] = qty_json(Decimal(remaining))
            entry[1] = Decimal(remaining)
            entry[3] = monetary_mult(entry[1], unit_q)
            entry[4] = per_unit + 1
            plan.append([sibling, rest_qty, unit_q, monetary_mult(rest_qty, unit_q), per_unit])
            remaining = 0
            break

    # Sem ``split`` (ou sem linha que se parta), quem prometeu paga o centavo a
    # mais; quem debita fica abaixo.
    if remaining > 0 and at_least:
        candidates = [e for e in plan if e[4] < e[2] and _step(e) > 0]
        if candidates:
            entry = min(candidates, key=_step)
            applied += _step(entry)
            entry[4] += 1

    touched: list[tuple[dict, int, int]] = []
    for entry in plan:
        item, qty, unit_q, line_total_q, per_unit = entry
        if per_unit <= 0:
            continue
        new_unit_q = unit_q - per_unit
        # O total sai do unitário (mesma conta do ``ItemPricingModifier`` e do
        # ``Session._normalize_items``), então a linha NÃO PODE ficar incoerente.
        new_line_total_q = monetary_mult(qty, new_unit_q)
        item["unit_price_q"] = new_unit_q
        item["line_total_q"] = new_line_total_q
        touched.append((item, per_unit, line_total_q - new_line_total_q))
    return touched


class SplitLineMergeModifier:
    """Junta de volta a linha que o rateio partiu (#3240), antes do preço.

    O rateio do desconto de pedido parte uma linha em duas quando sobra centavo
    (``spread_order_discount(split=True)``). A partição é do PREÇO, não da compra:
    no próximo preço as unidades voltam à linha de origem, o ``ItemPricingModifier``
    precifica a quantidade inteira (a faixa por quantidade enxerga as 3 unidades, e
    não 2 e 1) e o rateio parte de novo só se ainda sobrar centavo.

    Soma, não substitui: a tela mostra as duas linhas, e mudar a quantidade de
    qualquer uma (pela ``line_id``) muda o total do produto nessa medida. A parte
    cuja linha de origem saiu da sacola fica como linha comum.
    """

    code = "pricing.unsplit"
    order = 8

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        items = session.items or []
        if not any((i.get("meta") or {}).get(SPLIT_OF) for i in items):
            return
        by_id = {i.get("line_id"): i for i in items}
        kept: list[dict] = []
        for item in items:
            meta = item.get("meta") or {}
            origin = meta.get(SPLIT_OF)
            if not origin:
                kept.append(item)
                continue
            target = by_id.get(origin)
            if target is None or target is item or (target.get("meta") or {}).get(SPLIT_OF):
                meta.pop(SPLIT_OF, None)
                kept.append(item)
                continue
            qty = line_qty(target) + line_qty(item)
            target["qty"] = qty_json(qty)
            target["line_total_q"] = monetary_mult(qty, int(target.get("unit_price_q", 0) or 0))
        session.update_items(kept)


def merged_for_display(items: list[dict]) -> list[dict]:
    """As linhas como a cliente as comprou: cada parte partida volta à de origem.

    A partição é do preço gravado (pedido, NFC-e, Gestor), não da compra. Na tela da
    loja o desconto de pedido aparece como linha própria e a linha a preço de lista,
    então as duas partes seriam o mesmo produto duas vezes, sem razão à vista. Não
    muda nada: devolve cópias.
    """
    if not any((i.get("meta") or {}).get(SPLIT_OF) for i in items):
        return items
    merged = [dict(i) for i in items]
    by_id = {i.get("line_id"): i for i in merged}
    out: list[dict] = []
    for item in merged:
        origin = (item.get("meta") or {}).get(SPLIT_OF)
        target = by_id.get(origin) if origin else None
        if target is None or target is item:
            out.append(item)
            continue
        target["qty"] = qty_json(line_qty(target) + line_qty(item))
        target["line_total_q"] = int(target.get("line_total_q", 0) or 0) + int(item.get("line_total_q", 0) or 0)
    return out
