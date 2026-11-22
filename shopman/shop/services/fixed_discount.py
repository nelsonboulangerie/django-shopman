"""A competição do desconto de valor fixo de pedido (#3233).

Os descontos não se somam e o maior ganha, também para o desconto de valor fixo: a
promoção fixa e o cupom fixo competem entre si pelas linhas sem desconto
(``best_fixed_discount``), e o CUPOM fixo ainda compete com o desconto por item que as
linhas já têm (``swap_in_fixed_coupon``): se valer mais, entra no lugar dele. A promoção
automática fixa não desloca o desconto por item, porque o tile do PDV mostra o preço por
item e nunca o fixo de pedido.

Saiu de ``shopman.shop.modifiers`` (``DiscountModifier``), que estava no teto de linhas.
"""

from __future__ import annotations

from typing import Any

from shopman.utils.monetary import monetary_mult

from shopman.shop.policies.promotion import promotion_minimum_eligible


def best_fixed_discount(
    promotions: list[Any],
    coupon_promo: Any,
    coupon_code: str | None,
    session_total: int,
    *,
    group_refs: set[str] = frozenset(),
    group_meta=None,
    applicable_q=None,
) -> tuple[int, tuple[str, str, str | None, str], Any] | None:
    """Largest applicable FIXED discount, as a single order-level candidate.

    Fixed promotions and the fixed coupon compete on value (best wins, no
    stacking of two fixed discounts). min_order_q is gated against the gross
    order subtotal. Compete o que aplica, ``min(valor, applicable_q(promo))`` (subtotal que o
    escopo alcança): fixo sem linha não vence o cupom (beta SMS-04). A fixed discount of the
    customer's own group carries its (discount_kind, group_ref) per the WINNING group, not the
    primary one. Returns (value_q, source, promo), source = (type, name, discount_kind, group_ref), or None.
    """
    best: tuple[int, tuple[str, str, str | None, str], Any] | None = None
    for promo in promotions:
        if promo.type != "fixed":
            continue
        if not promotion_minimum_eligible(
            min_order_q=promo.min_order_q,
            merchandise_subtotal_q=session_total,
        ):
            continue
        value = min(max(0, int(promo.value or 0)), applicable_q(promo) if applicable_q else 1 << 62)
        if value > 0 and (best is None or value > best[0]):
            kind, group_ref = None, ""
            if getattr(promo, "ref", "") in group_refs and group_meta is not None:
                group_ref, kind, _step = group_meta(promo)
            best = (value, ("promotion", promo.name, kind, group_ref), promo)
    if coupon_promo is not None and coupon_promo.type == "fixed":
        if promotion_minimum_eligible(
            min_order_q=coupon_promo.min_order_q,
            merchandise_subtotal_q=session_total,
        ):
            value = min(max(0, int(coupon_promo.value or 0)), applicable_q(coupon_promo) if applicable_q else 1 << 62)
            if value > 0 and (best is None or value > best[0]):  # empate não gasta o cupom
                best = (value, ("coupon", coupon_code or "", None, ""), coupon_promo)
    return best


def swap_in_fixed_coupon(
    items: list[dict],
    pricing: dict,
    coupon_promo: Any,
    coupon_code: str | None,
    session_total: int,
    *,
    standing_fixed_q: int,
    reaches,
) -> tuple[int, list[dict]] | None:
    """O cupom de valor fixo entra no lugar do desconto por-linha que vale hoje?

    Os descontos não se somam e o maior ganha, também para o cupom de valor fixo:
    R$ 5,00 contra os 10% de aniversário de 3 Croissants (R$ 3,90) é o cupom.
    Sem a troca, ``_fixed_eligible_lines`` deixa de fora toda linha que já tem
    desconto, e o cupom valia zero por maior que fosse.

    A troca alcança as linhas que o cupom alcança, COM ou sem desconto. Ela vale
    ``min(valor do cupom, subtotal de LISTA dessas linhas)`` e desloca o desconto
    por-linha que elas têm hoje (``meta._disc``). Entra só quando o desconto total
    depois dela é ESTRITAMENTE maior do que sem ela: o deslocado mais o fixo que já
    venceria nas linhas sem desconto (``standing_fixed_q``). No empate fica o que
    já valia, e o cupom não é gasto à toa (a mesma régua do percentual).

    Quando entra, cada linha deslocada volta ao preço de lista pelo mesmo caminho
    do vencedor percentual (``_reverse_prior_pricing`` reconcilia a transparência
    do desconto deslocado, como o lote) e perde o ``_disc``. Devolve
    ``(valor da troca, linhas deslocadas)``; o rateio e o registro do cupom ficam
    com o passo de valor fixo, igual a qualquer desconto de pedido. ``None`` quando
    não há troca.
    """
    from shopman.shop.modifiers import _is_non_merchandise_line, _list_price_q, _qty_decimal, _reverse_prior_pricing

    if coupon_promo is None or coupon_promo.type != "fixed":
        return None
    if not promotion_minimum_eligible(
        min_order_q=coupon_promo.min_order_q,
        merchandise_subtotal_q=session_total,
    ):
        return None
    reached = [
        item
        for item in items
        if not _is_non_merchandise_line(item)
        and int(item.get("line_total_q", 0) or 0) > 0
        and reaches(item)
    ]
    displaced = [item for item in reached if (item.get("meta") or {}).get("_disc")]
    if not displaced:
        return None  # nada a deslocar: o passo de valor fixo já cuida do cupom

    def _displaced_q(item: dict) -> int:
        disc = item["meta"]["_disc"]
        if disc.get("scope") == "order":
            return int(disc.get("line_amount_q") or 0)
        return monetary_mult(_qty_decimal(item), int(disc.get("amount_q") or 0))

    list_subtotal_q = sum(monetary_mult(_qty_decimal(item), _list_price_q(item)) for item in reached)
    swap_value_q = min(max(0, int(coupon_promo.value or 0)), list_subtotal_q)
    standing_q = sum(_displaced_q(item) for item in displaced) + max(0, int(standing_fixed_q))
    if swap_value_q <= standing_q:
        return None

    for item in displaced:
        _reverse_prior_pricing(pricing, item)
        list_q = _list_price_q(item)
        item["unit_price_q"] = list_q
        item["line_total_q"] = monetary_mult(_qty_decimal(item), list_q)
        item["meta"].pop("_disc", None)
    return swap_value_q, displaced


def swap_fixed_coupon(
    items: list[dict],
    pricing: dict,
    coupon_promo: Any,
    coupon_code: str | None,
    session_total: int,
    *,
    fixed,
    reaches,
    discounts_applied: list[dict],
):
    """Aplica a troca do cupom fixo no passe do ``DiscountModifier``.

    Devolve ``(fixed, devolvido_do_cupom_q, trocou)``: o candidato fixo que o passo de
    valor fixo vai ratear (o cupom, quando a troca entra), quanto sai do total de cupom
    deste passe (o registro de cupom por item que a troca deslocou) e se houve troca. Os
    registros que este mesmo passe já fez para as linhas deslocadas saem de
    ``discounts_applied``, achados pela linha (``line_id``, ou o SKU quando a linha não
    tem id), o mesmo critério de ``_reverse_prior_pricing``. O registro de pedido
    (``sku=""``) nunca é de uma linha e fica.
    """
    from shopman.shop.modifiers import _record_total_q

    swapped = swap_in_fixed_coupon(
        items,
        pricing,
        coupon_promo,
        coupon_code,
        session_total,
        standing_fixed_q=fixed[0] if fixed is not None else 0,
        reaches=reaches,
    )
    if swapped is None:
        return fixed, 0, False
    swap_value_q, displaced = swapped
    coupon_back_q = 0
    for item in displaced:
        line_id = str(item.get("line_id") or "")
        sku = item.get("sku", "")
        for record in [
            r for r in discounts_applied
            if r.get("sku") and (r.get("line_id") == line_id if line_id and r.get("line_id") else r.get("sku") == sku)
        ]:
            discounts_applied.remove(record)
            if record.get("type") == "coupon":
                coupon_back_q += _record_total_q(record)
    return (swap_value_q, ("coupon", coupon_code or "", None, ""), coupon_promo), coupon_back_q, True
