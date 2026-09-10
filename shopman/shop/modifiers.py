"""
Shop — Custom order modifiers.

Modifiers follow the Orderman Modifier protocol:
- code: str — unique identifier
- order: int — execution order (lower = first)
- apply(*, channel, session, ctx) -> None — mutates session in-place

Execution order:
  10  pricing.item          — base price from backend (qty-aware)
  20  shop.discount         — promotions + coupons (maior desconto ganha)
  50  pricing.session_total — recalculate total
  60  shop.employee_discount
  70  shop.delivery_fee     — taxa de entrega por zona (só delivery)
  80  shop.loyalty_redeem   — loyalty points redemption (post-pricing)
  85  shop.manual_discount  — desconto manual (POS)

Rule-driven discount modifiers (availability / time-window) are generic and
configured per deployment through ``RuleConfig`` rows — enabled state, params and
channel scope all live in the DB. They are registered unconditionally; execution
is gated by ``get_channel_rule_params`` so a disabled rule means no discount.

Discount policy — "maior desconto ganha":
  Per item, only ONE discount applies (the best one).
  Employee discount is post-pricing.
"""
from __future__ import annotations

import logging
from datetime import time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone
from shopman.utils.monetary import monetary_div, monetary_mult

logger = logging.getLogger(__name__)

# ── Configurable defaults ──────────────────────────────────────────
DEFAULT_EMPLOYEE_DISCOUNT_PERCENT = 20
DEFAULT_AVAILABILITY_DISCOUNT_PERCENT = 50
DEFAULT_TIME_WINDOW_DISCOUNT_PERCENT = 25
DEFAULT_TIME_WINDOW_START = "17:30"
DEFAULT_TIME_WINDOW_END = "18:00"


def _is_non_merchandise_line(item: dict) -> bool:
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") in {"delivery_fee"}


def _discount_label(copy_key: str, fallback: str) -> str:
    """Resolve a customer-facing discount label from OmotenashiCopy.

    The label is moment/audience-agnostic, so the wildcard cascade resolves the
    deployment override (if any) or the generic code default. ``fallback`` is the
    last resort if the key is unknown.
    """
    from shopman.shop.omotenashi.copy import WILDCARD, resolve_copy

    entry = resolve_copy(copy_key, moment=WILDCARD, audience=WILDCARD)
    return entry.title or entry.message or fallback


def _parse_time(raw: str | None, fallback: str) -> time:
    """Parse a ``"HH:MM"`` string into a ``time``, falling back on bad input."""
    value = raw or fallback
    try:
        h, m = map(int, value.split(":"))
        return time(h, m)
    except (ValueError, AttributeError):
        h, m = map(int, fallback.split(":"))
        return time(h, m)


# ── "Maior desconto ganha" — árbitro por-linha ─────────────────────────────
# ``modifiers_applied`` NÃO sobrevive ao ``Session._normalize_items`` (só ``meta``
# e ``unit_price_q`` persistem). Então o desconto vencedor da linha é registrado em
# ``meta["_disc"]`` (fonte durável entre modifiers), e o preço de lista pré-desconto
# em ``meta["_list_q"]`` (carimbado pelo ItemPricingModifier). Descontos flat
# (funcionário, happy hour) calculam sobre a LISTA e só substituem quando batem o
# desconto atual — nunca compõem sobre um preço já reduzido.


def _stamp_disc(
    item: dict,
    disc_type: str,
    amount_q: int,
    label: str,
    *,
    order_amount_q: int | None = None,
) -> None:
    """Registra o desconto vencedor da linha em ``meta`` (``amount_q`` por unidade).

    ``order_amount_q`` marca a linha como fatia de um desconto de PEDIDO (cupom/promo
    de valor fixo, rateado): guarda quanto DESTA linha veio daquele registro
    order-level, para ``_reverse_prior_pricing`` saber o que abater se um desconto
    flat vencer a linha depois.
    """
    meta = item.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        item["meta"] = meta
    disc: dict[str, Any] = {"type": disc_type, "amount_q": int(amount_q), "label": label}
    if order_amount_q is not None:
        disc["scope"] = "order"
        disc["line_amount_q"] = int(order_amount_q)
    meta["_disc"] = disc


def _qty_decimal(item: dict) -> Decimal:
    """A quantidade da linha como Decimal — sem truncar.

    Era ``int(item.get("qty", 1)) or 1``, e ele erra nos DOIS sentidos no dia em
    que a Nelson vender pão a quilo: meio quilo vira ``int(0.5) == 0``, o ``or 1``
    o promove a 1, e o cliente paga o dobro; um quilo e meio vira 1, e a loja
    perde a metade. Hoje nada é vendido por peso, então o defeito é inócuo — mas
    é inócuo por acidente do catálogo, não por desenho, e some junto com o
    catálogo no dia da balança.

    O zero continua virando 1: linha sem quantidade é linha de uma unidade, que
    é o que o resto do carrinho assume.
    """
    bruto = item.get("qty", 1)
    try:
        qty = Decimal(str(bruto))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("1")
    return qty if qty > 0 else Decimal("1")


def _list_price_q(item: dict) -> int:
    """Preço de lista (pré-desconto) carimbado; cai no preço atual se ausente."""
    meta = item.get("meta") or {}
    listed = meta.get("_list_q")
    return int(listed if listed is not None else (item.get("unit_price_q", 0) or 0))


def _current_disc_q(item: dict) -> int:
    """Desconto por unidade já na linha (lista − preço corrente)."""
    return max(0, _list_price_q(item) - int(item.get("unit_price_q", 0) or 0))


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


def _line_qty(item: dict) -> Decimal:
    """Quantidade da linha como ``Decimal`` (o campo é decimal: venda por peso)."""
    try:
        qty = Decimal(str(item.get("qty", 1)))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("1")
    return qty if qty > 0 else Decimal("1")


def _spread_order_discount(
    lines: list[dict], amount_q: int, *, at_least: bool = False
) -> list[tuple[dict, int, int]]:
    """Rateia ``amount_q`` entre ``lines`` reduzindo o PREÇO UNITÁRIO e recalculando
    o total da linha a partir dele — nunca o contrário.

    ``at_least=True`` permite estourar o alvo no mínimo possível quando ele não é
    representável (promoção/cupom de valor fixo: a casa PROMETEU "R$ 5 de desconto",
    então entrega pelo menos isso). ``at_least=False`` fica abaixo (resgate de pontos
    e desconto manual: nunca debitar mais pontos do que o cliente pediu, nem dar mais
    do que o operador autorizou).

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
        qty = _line_qty(item)
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

    # Passo 3 — sobrou e ninguém comporta (linha única de 6 unidades × cupom de
    # R$ 5,00). Quem prometeu paga o centavo a mais; quem debita fica abaixo.
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


def _reverse_prior_pricing(pricing: dict, item: dict) -> None:
    """Remove da transparência (``session.pricing``) a contribuição do desconto que
    a linha carrega hoje, antes do vencedor 'maior ganha' substituí-lo. O tipo vem
    de ``meta["_disc"]`` (``modifiers_applied`` não persiste)."""
    prior = (item.get("meta") or {}).get("_disc")
    if not prior:
        return
    t = prior.get("type")
    sku = item.get("sku", "")
    qty = int(item.get("qty", 1)) or 1
    if t in ("promotion", "coupon", "manual"):
        disc = pricing.get("discount") or {}
        if prior.get("scope") == "order":
            # Desconto de PEDIDO (valor fixo) rateado: o registro é um só, com
            # ``sku=""``, e esta linha é uma fatia dele. Abater a fatia — e só ela,
            # senão o desconto das OUTRAS linhas rateadas sumiria da transparência
            # sem sumir do preço. O registro morre quando a última fatia é abatida.
            kept = _reverse_order_level_share(
                disc.get("items") or [],
                disc_type=t,
                share_q=int(prior.get("line_amount_q") or 0),
            )
        else:
            # ⚠️ POR LINHA, não por produto. O filtro casava `(sku, type)`, e com
            # duas linhas do mesmo SKU — que o balcão agora produz o tempo todo,
            # bastando o cliente pedir mais um depois de o primeiro ir à cozinha
            # — reverter UMA apagava o registro das DUAS. A irmã seguia com a
            # cortesia no preço e sem registro na transparência: o
            # `original_price_q` sumia, a projection devolvia o preço JÁ
            # descontado como preço de lista, e a gravação seguinte aplicava a
            # cortesia de novo, por cima. Desconto composto a cada reprice.
            #
            # O `sku` continua atendendo o registro sem `line_id` (order-level e
            # o que vier de outra origem).
            line_id = str(item.get("line_id") or "")
            kept = [
                d
                for d in (disc.get("items") or [])
                if not (
                    d.get("type") == t
                    and (
                        d.get("line_id") == line_id
                        if line_id and d.get("line_id")
                        else d.get("sku") == sku
                    )
                )
            ]
        disc["items"] = kept
        disc["total_discount_q"] = sum(int(d.get("discount_q", 0)) * int(d.get("qty", 1)) for d in kept)
        pricing["discount"] = disc
        if t == "coupon" and pricing.get("coupon"):
            pricing["coupon"]["discount_q"] = sum(
                int(d.get("discount_q", 0)) * int(d.get("qty", 1)) for d in kept if d.get("type") == "coupon"
            )
    elif t in ("lot_discount", "employee_discount", "happy_hour"):
        entry = pricing.get(t)
        if entry:
            new_total = int(entry.get("total_discount_q", 0)) - int(prior.get("amount_q", 0)) * qty
            if new_total > 0:
                entry["total_discount_q"] = new_total
            else:
                pricing.pop(t, None)


def _reverse_order_level_share(entries: list[dict], *, disc_type: str, share_q: int) -> list[dict]:
    """Abate ``share_q`` do registro order-level (``sku=""``) de ``disc_type``.

    Existe porque o desconto de valor fixo é UM registro para N linhas rateadas: o
    filtro por ``sku`` (que serve aos descontos por-linha) ou não acharia nada — e o
    valor fantasma sobreviveria à substituição — ou apagaria o registro inteiro,
    zerando o desconto das linhas que ainda o carregam.
    """
    kept: list[dict] = []
    left_to_reverse = max(0, int(share_q))
    for entry in entries:
        if left_to_reverse and entry.get("sku") == "" and entry.get("type") == disc_type:
            remainder = int(entry.get("discount_q", 0)) - left_to_reverse
            left_to_reverse = 0
            if remainder <= 0:
                continue
            entry = {**entry, "discount_q": remainder}
        kept.append(entry)
    return kept


def _apply_flat_best_wins(session, *, percent, disc_type, label, pricing_key) -> bool:
    """Aplica um % flat sobre o preço de LISTA sob 'maior desconto ganha': vence a
    linha só quando bate o desconto atual (sem composição) e reconcilia a
    transparência do desconto substituído."""
    items = session.items or []
    pricing = session.pricing or {}
    won_total_q = 0
    modified = False
    for item in items:
        if _is_non_merchandise_line(item):
            continue
        list_q = _list_price_q(item)
        if list_q <= 0:
            continue
        my_disc = monetary_div(list_q * percent, 100)
        if my_disc <= _current_disc_q(item):
            continue  # o desconto já na linha vence ou empata — sem composição
        _reverse_prior_pricing(pricing, item)
        qty = _qty_decimal(item)
        item["unit_price_q"] = list_q - my_disc
        item["line_total_q"] = monetary_mult(qty, item["unit_price_q"])
        _stamp_disc(item, disc_type, my_disc, label)
        won_total_q += monetary_mult(qty, my_disc)
        modified = True
    if modified:
        session.update_items(items)
    if won_total_q > 0:
        pricing[pricing_key] = {"total_discount_q": won_total_q, "label": label}
    else:
        pricing.pop(pricing_key, None)
    session.pricing = pricing
    session.save(update_fields=["pricing"])
    return modified


def _lot_label() -> str:
    """Para o cliente é "Liquidação".

    Reusa a chave de copy existente de propósito: o vocabulário do cliente não
    muda porque a mecânica interna mudou, e chave nova sem tela vira órfã no
    gate de copy.
    """
    return _discount_label("CART_DISCOUNT_LABEL_AVAILABILITY", "Liquidação")


class LotDiscountModifier:
    """Desconto do LOTE que a linha reservou (ADR-017 / D1-RETIREMENT-PLAN).

    O percentual vem do ``Batch`` (congelado na inspeção da fornada), então pão
    de um dia e queijo de vinte passam pelo mesmo caminho — a diferença é a
    validade do lote, não um balde chamado "ontem".

    Por linha, porque cada linha pode ter reservado um lote diferente: a mesma
    fornada produz um lote a preço cheio e outro com desconto. É por isso que
    não dá para reusar ``_apply_flat_best_wins``, que aplica um percentual único
    à sacola inteira.

    "Maior desconto ganha": aplica sobre o preço de LISTA e só vence a linha
    quando bate o desconto já aplicado (promo, funcionário) — nunca compõe.
    """

    code = "shop.lot_discount"
    order = 15

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.shop.services import lot_pricing

        items = session.items or []
        if not items:
            return

        pricing = session.pricing or {}
        won_total_q = 0
        modified = False
        for item in items:
            if _is_non_merchandise_line(item):
                continue
            batch_ref = (item.get("meta") or {}).get("batch_ref") or ""
            if not batch_ref:
                continue
            percent = lot_pricing.percent_for_lot(batch_ref)
            if percent <= 0:
                continue
            list_q = _list_price_q(item)
            if list_q <= 0:
                continue
            my_disc = monetary_div(list_q * percent, 100)
            if my_disc <= _current_disc_q(item):
                continue  # o desconto já na linha vence ou empata
            _reverse_prior_pricing(pricing, item)
            qty = _qty_decimal(item)
            item["unit_price_q"] = list_q - my_disc
            item["line_total_q"] = monetary_mult(qty, item["unit_price_q"])
            _stamp_disc(item, "lot_discount", my_disc, _lot_label())
            won_total_q += monetary_mult(qty, my_disc)
            modified = True

        if modified:
            session.update_items(items)
        if won_total_q > 0:
            pricing["lot_discount"] = {
                "total_discount_q": won_total_q,
                "label": _lot_label(),
            }
        elif pricing.pop("lot_discount", None) is None and not modified:
            return
        session.pricing = pricing
        session.save(update_fields=["pricing"])


class TimeWindowDiscountModifier:
    """Discount applied during a configured time window (e.g. end-of-day clearance).

    Generic form of the "happy hour" discount: within ``[start, end)`` every
    eligible line gets a percentage off. Rule-driven — params, the window and
    channel scope come from the ``happy_hour`` RuleConfig. Restricting the rule
    to specific channels is how a deployment keeps the discount off a surface
    (e.g. the online storefront, where listed prices would otherwise diverge).

    "Maior desconto ganha": aplica sobre o preço de LISTA e só vence a linha quando
    bate o desconto já aplicado (promo, funcionário) — nunca compõe.
    """

    code = "shop.happy_hour"
    order = 65

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.shop.rules.engine import get_channel_rule_params

        params = get_channel_rule_params("happy_hour", getattr(channel, "ref", None))
        if params is None:
            return

        discount_percent = params.get("discount_percent", DEFAULT_TIME_WINDOW_DISCOUNT_PERCENT)
        start = _parse_time(params.get("start"), DEFAULT_TIME_WINDOW_START)
        end = _parse_time(params.get("end"), DEFAULT_TIME_WINDOW_END)

        now = timezone.localtime().time()
        if not (start <= now < end):
            # Fora da janela: limpa transparência residual de uma passagem anterior.
            pricing = session.pricing or {}
            if pricing.pop("happy_hour", None) is not None:
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            return

        _apply_flat_best_wins(
            session,
            percent=discount_percent,
            disc_type="happy_hour",
            label=_discount_label("CART_DISCOUNT_LABEL_TIME_WINDOW", "Happy Hour"),
            pricing_key="happy_hour",
        )


class DiscountModifier:
    """
    Desconto unificado — promoções automáticas + cupom.

    Política: "maior desconto ganha" por item.
    Para cada item elegível, coleta candidatos (promoções ativas + cupom),
    calcula o desconto de cada sobre o preço BASE, e aplica apenas o maior.

    Promoções com ``fulfillment_types`` só se aplicam depois que o cliente escolhe o tipo
    de entrega no checkout. Sem ``fulfillment_type`` na sessão → desconto não aplica.
    """

    code = "shop.discount"
    order = 20

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:

        # Inject fulfillment_type from session data into ctx for matching
        fulfillment_type = (session.data or {}).get("fulfillment_type", "")
        if fulfillment_type:
            ctx.setdefault("fulfillment_type", fulfillment_type)

        # Customer-derived pricing context (tier, RFM segment, birthday) needed
        # for ``customer_segments``-gated and ``birthday_only`` promotions/coupons.
        # Resolved from the session's linked customer so it survives EVERY reprice
        # (each cart mutation re-runs this modifier); a value the caller already
        # put in ``ctx`` still wins. The POS writes ``customer.price_tier`` straight to
        # the session; the storefront links the customer (ref + tier) when a
        # segment-gated coupon is applied, and the RFM segment resolves from the
        # customer's ``insight``.
        self._resolve_customer_ctx(session, ctx)

        now = timezone.now()

        from shopman.shop.services import promotions as promotion_service

        # A promoção é escopada por canal (`Promotion.channels`, vazio = todos), e o
        # modifier sabe o canal — então o escopo é honrado aqui, no único lugar que
        # decide desconto. Campo de escopo sem leitor é escopo decorativo.
        channel_ref = getattr(channel, "ref", "") or ""
        promotions = promotion_service.get_active_promotions(now, channel_ref=channel_ref)

        coupon_code = (session.data or {}).get("coupon_code")
        coupon_promo = None
        if coupon_code:
            coupon_promo = promotion_service.get_coupon_promotion(
                coupon_code, now, channel_ref=channel_ref
            )

        # ⚠️ O DESCONTO DO OPERADOR NÃO DEPENDE DE HAVER PROMOÇÃO NO AR. Esta
        # saída antecipada existe para limpar pricing velho quando não há nada
        # automático a aplicar — e ela estava passando por cima do desconto
        # manual de linha, que é avaliado no laço LOGO ABAIXO. Numa padaria sem
        # campanha ativa (o caso comum), o operador dava 50% de cortesia num
        # item, a linha guardava o desconto em `meta.manual_discount`, e o
        # pedido cobrava o preço cheio. Cortesia prometida ao cliente, caixa
        # cobrando integral, e nenhum erro em lugar nenhum.
        manual_lines = any(
            ((item.get("meta") or {}).get("manual_discount") or {}).get("value")
            for item in (session.items or [])
        )
        if not promotions and not coupon_promo and not manual_lines:
            if not session.pricing:
                session.pricing = {}
            session.pricing.pop("coupon", None)
            session.pricing.pop("discount", None)
            return

        items = session.items or []
        # Coleções por SKU — necessário para promoções por coleção. Usa o MESMO
        # helper canônico do menu (catalog_context) para os dois motores lerem a
        # mesma fonte (D4: evita o menu ver a coleção e o carrinho não).
        # ⚠️ A ida ao banco é da PROMOÇÃO, não da cortesia. `sku_collections` só
        # alimenta o `_matches`, que só roda para promoção e cupom — uma comanda
        # que tem apenas desconto do operador (o caso que passou a chegar até
        # aqui) pagaria uma consulta que não serve a ninguém, a cada reprice, e
        # o reprice acontece a cada toque no carrinho.
        if (promotions or coupon_promo) and items and not ctx.get("sku_collections"):
            line_skus = [i.get("sku") for i in items if i.get("sku") and not _is_non_merchandise_line(i)]
            try:
                from shopman.shop.projections import catalog_context

                ctx["sku_collections"] = catalog_context.collection_refs_by_sku(line_skus)
            except Exception:
                # Fail-closed: sem coleções, promo por coleção NÃO aplica (nunca
                # cobra a mais). WARNING (não debug) para a divergência ficar visível.
                ctx["sku_collections"] = {}
                logger.warning(
                    "discount_modifier: collection lookup failed for skus=%s",
                    line_skus,
                    exc_info=True,
                )

        session_total = sum(item.get("line_total_q", 0) for item in items if not _is_non_merchandise_line(item))
        modified = False
        total_coupon_discount_q = 0
        discounts_applied = []  # Persisted in session.pricing

        # ``pricing`` é o mesmo objeto de ``session.pricing`` para que
        # ``_reverse_prior_pricing`` (best-wins) reconcilie a transparência do
        # desconto substituído — ex.: um % promo/cupom que vença o desconto de
        # LOTE precisa tirar a contribuição do lote de ``pricing["lot_discount"]``.
        pricing = session.pricing or {}
        session.pricing = pricing

        for item in items:
            if _is_non_merchandise_line(item):
                continue
            sku = item.get("sku", "")
            # Percentuais competem sobre o preço de LISTA e vencem a linha em
            # "maior desconto ganha", NUNCA compondo sobre um desconto já aplicado
            # (ex.: LotDiscountModifier, order 15, roda antes). Ler ``unit_price_q``
            # aqui empilharia o % sobre o preço já reduzido pelo lote — cobrança a
            # menor silenciosa que o guard de total não pega (tela e cobrança usam
            # o mesmo ``line_total_q`` furado). Ver DISCOUNT-AUDIT / lot best-wins.
            list_q = _list_price_q(item)
            if list_q <= 0:
                continue
            current_disc_q = _current_disc_q(item)
            price_q = list_q

            manual = (item.get("meta") or {}).get("manual_discount") or {}
            manual_allowed = bool(manual.get("value"))

            # Find best discount candidate
            best_discount_q = 0
            best_source = None  # (type, name)

            # Only PERCENT discounts compete per-line: a percentage is intrinsically
            # per-unit. FIXED discounts are order-level and applied once, after this
            # loop (see the order-level fixed step below).
            # Evaluate auto-promotions
            for promo in promotions:
                if promo.type != "percent":
                    continue
                if promo.min_order_q and session_total < promo.min_order_q:
                    continue
                if not self._matches(promo, sku, ctx):
                    continue
                discount_q = self._calc_discount(promo, price_q)
                if discount_q > best_discount_q:
                    best_discount_q = discount_q
                    best_source = ("promotion", promo.name, promo.pk)

            # Evaluate coupon
            if coupon_promo and coupon_promo.type == "percent":
                if not (coupon_promo.min_order_q and session_total < coupon_promo.min_order_q):
                    if self._matches(coupon_promo, sku, ctx):
                        coupon_discount_q = self._calc_discount(coupon_promo, price_q)
                        if coupon_discount_q >= best_discount_q:
                            best_discount_q = coupon_discount_q
                            best_source = ("coupon", coupon_code, None)

            # Evaluate operator manual per-line discount (percent), best wins.
            if manual_allowed:
                manual_discount_q = self._calc_manual(manual, price_q)
                if manual_discount_q > best_discount_q:
                    best_discount_q = manual_discount_q
                    best_source = ("manual", manual.get("reason") or "manual", None)

            # Apply winner — só quando bate o desconto já na linha (best-wins, sem
            # composição). Reconcilia a transparência do desconto substituído
            # (ex.: lote) antes de gravar o novo vencedor.
            if best_source and best_discount_q > current_disc_q:
                _reverse_prior_pricing(pricing, item)
                item["unit_price_q"] = list_q - best_discount_q
                item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))

                source_type, source_name, source_id = best_source
                # Fonte durável do desconto vencedor da linha: ``meta._disc`` (para o
                # árbitro flat reconciliar em "maior ganha") + ``discounts_applied``
                # (abaixo) que vira ``pricing["discount"]``. ``modifiers_applied`` foi
                # removido — não persistia e criava guards cegos (ver DISCOUNT-AUDIT).
                _stamp_disc(item, source_type, best_discount_q, source_name or source_type)
                modified = True

                qty = int(item.get("qty", 1))
                discounts_applied.append({
                    # A LINHA que ganhou o desconto, ao lado do SKU. O registro é
                    # a única fonte que sobrevive ao save (a linha perde campos
                    # extras no ``update_items``), e quem o relê é a comanda do
                    # PDV para restaurar o preço PRÉ-desconto. Identificado só
                    # pelo SKU, o registro de uma linha respondia pela outra do
                    # mesmo produto — a cortesia dada num café aparecia nos dois.
                    "line_id": item.get("line_id", ""),
                    "sku": sku,
                    "type": source_type,
                    "name": source_name,
                    "original_price_q": price_q,
                    "discount_q": best_discount_q,
                    "qty": qty,
                })
                if source_type == "coupon":
                    total_coupon_discount_q += best_discount_q * qty

        # Order-level FIXED discount (fixed promo / fixed coupon). A fixed value
        # like "R$5 off" is a single per-ORDER discount, never per unit — 6 units
        # of a R$5 coupon is R$5 off the order, not R$30. Applied once to the
        # eligible merchandise subtotal, distributed across lines that don't
        # already carry a per-line discount (no stacking on the same line).
        fixed = self._best_fixed_discount(promotions, coupon_promo, coupon_code, session_total)
        if fixed is not None:
            fixed_value, fixed_source, fixed_promo = fixed
            eligible = [
                item
                for item in items
                if not _is_non_merchandise_line(item)
                # Linha sem desconto por-linha (durável em ``meta._disc``): um fixo
                # de pedido não empilha sobre promo/cupom/manual já aplicados.
                and not (item.get("meta") or {}).get("_disc")
                and int(item.get("line_total_q", 0)) > 0
                and self._matches(fixed_promo, item.get("sku", ""), ctx)
            ]
            eligible_subtotal = sum(int(item.get("line_total_q", 0)) for item in eligible)
            target_q = min(fixed_value, eligible_subtotal)
            src_type, src_name = fixed_source
            # O registrado é o desconto REALMENTE aplicado, nunca o nominal: um
            # cupom de R$ 5,00 sobre uma linha de 6 unidades não é representável em
            # centavos por unidade (5,00/6 = 0,8333…), então o rateio entrega o
            # mínimo acima do prometido e a tela mostra ESSE valor. Registrar o
            # nominal era a origem do desconto fantasma no recibo.
            applied_q = (
                self._distribute_order_discount(
                    eligible, target_q, disc_type=src_type, label=src_name or src_type
                )
                if target_q > 0
                else 0
            )
            if applied_q > 0:
                modified = True
                # sku=""/line_id="" — an order-level record: it aggregates into the
                # cart's discount total/line but matches no line (no strikethrough).
                discounts_applied.append({
                    "line_id": "",
                    "sku": "",
                    "type": src_type,
                    "name": src_name,
                    "original_price_q": 0,
                    "discount_q": applied_q,
                    "qty": 1,
                })
                if src_type == "coupon":
                    total_coupon_discount_q += applied_q

        if modified:
            session.update_items(items)

        # Persist discount info in session.pricing (items lose extra fields on save)
        if not session.pricing:
            session.pricing = {}
        session.pricing["discount"] = {
            "total_discount_q": sum(d["discount_q"] * d["qty"] for d in discounts_applied),
            "items": discounts_applied,
        }
        if coupon_code:
            session.pricing["coupon"] = {
                "code": coupon_code,
                "discount_q": total_coupon_discount_q,
            }
        else:
            session.pricing.pop("coupon", None)

    @staticmethod
    def _resolve_customer_ctx(session: Any, ctx: dict) -> None:
        """Populate ``price_tier``, ``customer_segment`` and ``is_birthday``
        in ``ctx`` from the session's linked customer, without overriding values
        the caller already supplied.

        ``customer.price_tier`` persisted on the session (POS) is authoritative for the
        tier. Everything else (segment, birthday, and the tier when only the ref
        is on the session) resolves from the ``Customer`` row, so the discount is
        recomputed correctly on every reprice, not just the moment the coupon is
        applied.
        """
        from django.core.exceptions import ObjectDoesNotExist

        customer_data = (session.data or {}).get("customer") or {}

        needs_tier = not ctx.get("price_tier")
        if needs_tier and customer_data.get("price_tier"):
            ctx["price_tier"] = customer_data["price_tier"]
            needs_tier = False

        needs_segment = not ctx.get("customer_segment")
        needs_birthday = "is_birthday" not in ctx
        customer_ref = customer_data.get("ref")
        if not customer_ref or not (needs_tier or needs_segment or needs_birthday):
            return

        try:
            from shopman.guestman.models import Customer

            customer = (
                Customer.objects.filter(ref=customer_ref)
                .select_related("price_tier", "insight")
                .first()
            )
        except Exception:
            logger.debug(
                "discount_modifier: customer lookup failed for customer=%s",
                customer_ref,
                exc_info=True,
            )
            return
        if customer is None:
            return

        if needs_tier and customer.price_tier_id:
            ctx["price_tier"] = customer.price_tier.ref

        if needs_segment:
            try:
                ctx["customer_segment"] = customer.insight.rfm_segment or ""
            except ObjectDoesNotExist:
                # Insight (OneToOne) not computed yet — the customer still matches
                # by tier; the segment stays empty. Degrade quietly, no traceback.
                logger.debug(
                    "discount_modifier: no insight for customer=%s", customer_ref
                )

        if needs_birthday and customer.birthday:
            today = timezone.localdate()
            ctx["is_birthday"] = (
                customer.birthday.month == today.month
                and customer.birthday.day == today.day
            )

    @staticmethod
    def _matches(promo: Any, sku: str, ctx: dict) -> bool:
        if promo.fulfillment_types:
            fulfillment_type = (ctx.get("fulfillment_type") or "").strip()
            if fulfillment_type:
                if fulfillment_type not in promo.fulfillment_types:
                    return False
            else:
                # fulfillment_type not chosen yet — don't pre-apply fulfillment-restricted promos
                return False
        if promo.skus and sku not in promo.skus:
            return False
        if promo.collections:
            item_collections = ctx.get("sku_collections", {}).get(sku, [])
            if not any(c in promo.collections for c in item_collections):
                return False
        if promo.customer_segments:
            customer_segment = ctx.get("customer_segment", "")
            price_tier = ctx.get("price_tier", "")
            if customer_segment not in promo.customer_segments and price_tier not in promo.customer_segments:
                return False
        if getattr(promo, "birthday_only", False):
            if not ctx.get("is_birthday"):
                return False
        return True

    @staticmethod
    def _calc_discount(promo: Any, price_q: int) -> int:
        if promo.type == "percent":
            # Clamp 0-100: percentual digitado errado no admin (ex.: 150)
            # jamais pode produzir preço negativo.
            value = min(max(int(promo.value or 0), 0), 100)
            return monetary_div(price_q * value, 100)
        return max(0, min(promo.value, price_q))

    @staticmethod
    def _best_fixed_discount(
        promotions: list[Any], coupon_promo: Any, coupon_code: str | None, session_total: int
    ) -> tuple[int, tuple[str, str], Any] | None:
        """Largest applicable FIXED discount, as a single order-level candidate.

        Fixed promotions and the fixed coupon compete on value (best wins, no
        stacking of two fixed discounts). ``min_order_q`` is gated against the
        gross order subtotal; SKU/collection scope is enforced later when picking
        the eligible lines. Returns ``(value_q, source, promo)`` where ``source``
        is ``("promotion", name)`` or ``("coupon", code)``, or ``None``.
        """
        best: tuple[int, tuple[str, str], Any] | None = None
        for promo in promotions:
            if promo.type != "fixed":
                continue
            if promo.min_order_q and session_total < promo.min_order_q:
                continue
            value = max(0, int(promo.value or 0))
            if value > 0 and (best is None or value > best[0]):
                best = (value, ("promotion", promo.name), promo)
        if coupon_promo is not None and coupon_promo.type == "fixed":
            if not (coupon_promo.min_order_q and session_total < coupon_promo.min_order_q):
                value = max(0, int(coupon_promo.value or 0))
                if value > 0 and (best is None or value >= best[0]):
                    best = (value, ("coupon", coupon_code or ""), coupon_promo)
        return best

    @staticmethod
    def _distribute_order_discount(
        eligible: list[dict], amount_q: int, *, disc_type: str, label: str
    ) -> int:
        """Rateia um desconto de PEDIDO entre as linhas elegíveis e devolve o valor
        efetivamente aplicado.

        Duas coisas que a versão anterior não fazia, e cada uma custava dinheiro:

        1. **Carimbava ``meta["_disc"]``** — não carimbava. Os outros descontos
           passam todos por ``_stamp_disc``, e é dali que ``_reverse_prior_pricing``
           descobre o que abater quando um desconto flat (funcionário, happy hour)
           vence a linha depois. Sem o carimbo, o flat vencia, o preço da linha caía
           de novo e o fixo continuava inteiro em ``pricing["discount"]`` e em
           ``pricing["coupon"]``: a tela dizia "Cupom aplicado, desconto de R$ 5,00"
           e "de R$ 94,00 por R$ 71,20" num pedido de lista R$ 89,00. O cliente
           pagava o certo e **queimava um cupom de uso único que não lhe deu nada**
           (``pricing["coupon"]["discount_q"] > 0`` faz o lifecycle consumir o
           cupom), e o snapshot levava o desconto fantasma para recibo e B.I.
        2. **Preservava ``qty × unit_price_q == line_total_q``** — não preservava
           (ver ``_spread_order_discount``).
        """
        touched = _spread_order_discount(eligible, amount_q, at_least=True)
        applied_q = 0
        for item, per_unit_q, line_amount_q in touched:
            applied_q += line_amount_q
            _stamp_disc(item, disc_type, per_unit_q, label, order_amount_q=line_amount_q)
        return applied_q

    @staticmethod
    def _calc_manual(manual: dict, price_q: int) -> int:
        """Desconto POR UNIDADE do manual de linha — em % ou em R$.

        O R$ é por unidade de propósito: é assim que ele compete com o automático
        no "maior desconto ganha", que mede tudo por unidade contra o preço de
        etiqueta. Rateio de um valor pela linha inteira existe para o desconto de
        PEDIDO (``ManualDiscountModifier``), que não disputa linha com ninguém.

        ``value`` segue a convenção do desconto do pedido: percentual em
        ``percent``, REAIS em ``fixed``.
        """
        try:
            value = float(manual.get("value") or 0)
        except (TypeError, ValueError):
            return 0
        if value <= 0:
            return 0
        if str(manual.get("type") or "percent").strip().lower() == "fixed":
            return min(int(round(value * 100)), price_q)
        return min(monetary_div(int(round(price_q * value)), 100), price_q)



class EmployeeDiscountModifier:
    """
    Discount for employees (the customer's price tier is "staff").

    Percentage is configurable via channel config rules.employee_discount_percent
    or SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT setting (default 20).

    "Maior desconto ganha": aplica sobre o preço de LISTA e só vence a linha quando
    bate o desconto já aplicado (promo) — nunca compõe.
    """

    code = "shop.employee_discount"
    order = 60  # After canonical pricing (10, 50), before session total recalc

    def __init__(
        self,
        *,
        discount_percent: int = DEFAULT_EMPLOYEE_DISCOUNT_PERCENT,
        pickup_only: bool = True,
    ):
        self.discount_percent = discount_percent
        # Fallback quando não há RuleConfig; a regra no admin é a fonte real.
        self.pickup_only = pickup_only

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.shop.rules.engine import get_rule_params

        rule_params = get_rule_params("employee_discount")

        data = session.data or {}
        price_tier = data.get("customer", {}).get("price_tier", "")
        # Benefício, não canal: com entrega o preço de funcionário viajaria para
        # qualquer endereço, sem ninguém ver. Retirando, alguém entrega na mão.
        pickup_only = rule_params.get("pickup_only", self.pickup_only)
        delivering = pickup_only and data.get("fulfillment_type") == "delivery"

        # QUAL tier marca funcionário é decisão da regra no admin, não um
        # literal daqui — era "staff" cravado e o parâmetro ficava decorativo
        # (achado da faxina 2026-08-13: one question, one owner).
        employee_tier = rule_params.get("price_tier", "staff")

        if price_tier != employee_tier or delivering:
            # Deixou de ser o tier de funcionário (ou trocou para entrega):
            # limpa transparência residual de uma passagem anterior.
            pricing = session.pricing or {}
            if pricing.pop("employee_discount", None) is not None:
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            return

        config = getattr(channel, "config", None) or {}
        channel_rules = config.get("rules", {})
        if "employee_discount_percent" in channel_rules:
            percent = channel_rules["employee_discount_percent"]
        else:
            percent = rule_params.get("discount_percent", self.discount_percent)

        _apply_flat_best_wins(
            session,
            percent=percent,
            disc_type="employee_discount",
            label="Desconto funcionário",
            pricing_key="employee_discount",
        )


_ZONE_MODE_EXCLUDE = "exclude"


def _address_text(addr: dict) -> str:
    """Texto do endereço p/ geocode: prefere o formatado; senão compõe dos campos."""
    formatted = (addr.get("formatted_address") or "").strip()
    if formatted:
        return formatted
    street = " ".join(
        p for p in [(addr.get("route") or "").strip(), (addr.get("street_number") or "").strip()] if p
    )
    parts = [
        street,
        (addr.get("neighborhood") or "").strip(),
        (addr.get("city") or "").strip(),
        (addr.get("state_code") or "").strip(),
        (addr.get("postal_code") or "").strip(),
    ]
    return ", ".join(p for p in parts if p)


class DeliveryFeeModifier:
    """
    Taxa de entrega: faixa de DISTÂNCIA (motor) + zona CEP/bairro (exceção).

    Só se aplica quando fulfillment_type == "delivery". Lê o endereço estruturado
    de session.data["delivery_address_structured"] (postal_code, neighborhood,
    latitude, longitude).

    Ordem de resolução (WP-11):
      1. Zona ``exclude`` casa → fora da área (``delivery_zone_error``).
      2. Zona ``override`` casa → taxa fixa da zona (sobrepõe a distância).
      3. Senão, distância loja→endereço casa uma ``DeliveryDistanceBand`` → taxa da faixa.
      4. Senão (sem faixa/cobertura, ou sem coordenada e sem zona) → fora da área.

    Grava ``delivery_fee_q`` (taxa efetiva) ou ``delivery_zone_error``, e
    ``delivery_distance_km`` quando a distância foi calculada (transparência no
    checkout). Frete grátis: se ``shop.defaults.rules.free_delivery_above_q`` > 0
    e o subtotal atingir o limiar, a taxa efetiva vira 0. Como depende do subtotal,
    é reavaliada a cada passagem dos modifiers (sem cache).
    """

    code = "shop.delivery_fee"
    order = 70

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        data = session.data or {}
        if data.get("fulfillment_type", "") != "delivery":
            # Mudou para retirada: taxa e linha de uma passagem anterior saem.
            new_data = dict(data)
            new_data.pop("delivery_fee_q", None)
            new_data.pop("delivery_zone_error", None)
            new_data.pop("delivery_distance_km", None)
            if new_data != data:
                session.data = new_data
                session.save(update_fields=["data"])
            self._sync_fee_line(session, None)
            return

        addr = data.get("delivery_address_structured") or {}
        postal_code = (addr.get("postal_code") or "").strip()
        neighborhood = (addr.get("neighborhood") or "").strip()
        lat, lng = addr.get("latitude"), addr.get("longitude")

        if not postal_code and not neighborhood and lat in (None, "") and lng in (None, ""):
            # Endereço ainda não preenchido (pré-checkout) — não calcular taxa.
            self._sync_fee_line(session, None)
            return

        base_fee_q, distance_km, blocked = self._resolve(
            postal_code, neighborhood, lat, lng, address_text=_address_text(addr)
        )

        new_data = dict(data)
        if distance_km is not None:
            new_data["delivery_distance_km"] = round(distance_km, 1)
        else:
            new_data.pop("delivery_distance_km", None)

        fee_q: int | None
        if blocked:
            new_data["delivery_zone_error"] = True
            new_data.pop("delivery_fee_q", None)
            fee_q = None
        else:
            fee_q = self._effective_fee_q(base_fee_q, session, channel=channel)
            new_data["delivery_fee_q"] = fee_q
            new_data.pop("delivery_zone_error", None)

        if new_data != data:  # evita save redundante a cada passagem dos modifiers
            session.data = new_data
            session.save(update_fields=["data"])

        self._sync_fee_line(session, fee_q)

    # Marca de propriedade da linha de taxa criada por este modifier. Uma linha
    # de taxa SEM esta marca (ex.: POS, taxa manual do operador) nunca é tocada.
    FEE_LINE_SOURCE = "shop.delivery_fee"

    @classmethod
    def _sync_fee_line(cls, session: Any, fee_q: int | None) -> None:
        """Mantém a linha ``__DELIVERY_FEE__`` em sincronia com a taxa resolvida.

        ``Order.total_q`` é a soma das linhas — só o que vira linha é cobrado
        (PIX/cartão/fiscal/caixa). A taxa em ``session.data`` é exibição; a
        linha é a cobrança.
        """
        items = list(session.items or [])
        manual = [
            i for i in items
            if _is_non_merchandise_line(i)
            and (i.get("meta") or {}).get("source") != cls.FEE_LINE_SOURCE
        ]
        if manual:
            return  # taxa manual (POS) tem precedência total

        ours = [
            i for i in items
            if (i.get("meta") or {}).get("source") == cls.FEE_LINE_SOURCE
        ]
        others = [i for i in items if i not in ours]
        has_merchandise = any(not _is_non_merchandise_line(i) for i in others)

        if not fee_q or fee_q <= 0 or not has_merchandise:
            if ours:
                session.update_items(others)
            return

        if len(ours) == 1 and int(ours[0].get("unit_price_q", 0)) == int(fee_q):
            return  # já em sincronia

        line = {
            "sku": "__DELIVERY_FEE__",
            "name": "Taxa de entrega",
            "qty": 1,
            "unit_price_q": int(fee_q),
            "meta": {"type": "delivery_fee", "non_production": True, "source": cls.FEE_LINE_SOURCE},
        }
        if ours:
            line["line_id"] = ours[0].get("line_id")
        session.update_items(others + [line])

    @staticmethod
    def _resolve(
        postal_code: str, neighborhood: str, lat, lng, address_text: str = ""
    ) -> tuple[int, float | None, bool]:
        """Resolve (taxa_base_q, distância_km, bloqueado) pela ordem zona → faixa → fallback.

        Caminho feliz: a distância vem de coordenadas. Places já as captura; quando o
        endereço chega SEM coordenada (ViaCEP/manual), geocodifica o TEXTO do endereço
        aqui (cached) — assim um endereço válido quase sempre entra no cálculo por faixa.

        Só bloqueia quando a distância é CONHECIDA e cai fora de toda faixa (longe demais).
        Se mesmo o geocode não resolver (raro), NÃO rejeita um endereço válido: cobra a
        taxa-padrão (``default_delivery_fee_q``) — fallback de último recurso, não regra.
        """
        from shopman.shop.projections.cart import shop_rule_q
        from shopman.shop.services import delivery_distance
        from shopman.shop.services import promotions as promotion_service

        distance_km = delivery_distance.store_distance_km(lat, lng)

        # Zona (exceção) primeiro: é lookup barato e curto-circuita o geocode.
        zone = promotion_service.match_delivery_zone(postal_code, neighborhood)
        if zone is not None:
            if getattr(zone, "mode", "") == _ZONE_MODE_EXCLUDE:
                return (0, distance_km, True)  # zona de exclusão: não entregamos aqui
            return (zone.fee_q, distance_km, False)  # override: taxa fixa da zona

        # Sem zona e sem coordenada → geocodifica o TEXTO do endereço (caminho feliz p/
        # ViaCEP/manual). Só aqui, e cached: o custo de rede é uma vez por endereço.
        if distance_km is None and address_text:
            from shopman.shop.services.geocoding import forward_geocode

            coords = forward_geocode(address_text)
            if coords is not None:
                distance_km = delivery_distance.store_distance_km(coords[0], coords[1])

        if distance_km is not None:
            band = promotion_service.match_distance_band(distance_km)
            if band is not None:
                return (band.fee_q, distance_km, False)
            # Distância conhecida e além de toda faixa → genuinamente fora de área.
            return (0, distance_km, True)

        # Nem zona, nem coordenada, nem geocode: fallback de último recurso (taxa-padrão).
        return (shop_rule_q("default_delivery_fee_q"), None, False)

    @staticmethod
    def _effective_fee_q(base_fee_q: int, session: Any, *, channel: Any = None) -> int:
        """A taxa efetiva: a renúncia que renuncia MAIS, entre duas políticas.

        Duas políticas, **um dono**. O limiar permanente (`free_delivery_above_q`, de
        `Shop.defaults`) e a promoção `free_delivery` ativa. Isto não é segundo dono da
        taxa — é um dono lendo duas políticas, e vence a que renuncia mais, na mesma
        convenção best-wins que o projeto já usa para desconto.

        Entrega grátis é renúncia AQUI, nunca linha de desconto: a linha
        `__DELIVERY_FEE__` é blindada contra desconto em dez pontos deste arquivo, e é
        essa invariante que mantém a taxa com um dono. E o resultado sai certo de
        graça — taxa zerada REMOVE a linha em vez de gerar uma de R$ 0,00.
        """
        if base_fee_q <= 0:
            return base_fee_q

        subtotal_q = sum(
            item.get("line_total_q", 0)
            for item in (session.items or [])
            if item.get("sku") != "__DELIVERY_FEE__"
            and (item.get("meta") or {}).get("type") != "delivery_fee"
        )

        # Cupom promocional NÃO conta pros thresholds de frete grátis: aplicar uma
        # cortesia não pode tirar a elegibilidade do cliente. Mesma base que a
        # projeção do carrinho (``threshold_base_q``, cart.py) e o gate de mínimo
        # de entrega (validation.py) — senão a tela diz "frete grátis" e o modifier
        # cobra a taxa. O preço por lote continua contando (é venda real).
        coupon_discount_q = int(((session.pricing or {}).get("coupon") or {}).get("discount_q") or 0)
        threshold_base_q = subtotal_q + coupon_discount_q

        candidates = [base_fee_q]

        # Política 1: o limiar permanente da loja.
        from shopman.shop.projections.cart import shop_rule_q

        free_above_q = shop_rule_q("free_delivery_above_q")
        if free_above_q and threshold_base_q >= free_above_q:
            candidates.append(0)

        # Política 2: promoção de entrega grátis (automática ou por cupom). O
        # encanamento já existia: este modifier roda em order=70, cinquenta slots
        # depois do desconto (order=20), então o cupom já está resolvido em
        # `session.data` quando a taxa é calculada.
        waived = DeliveryFeeModifier._promotional_fee_q(
            base_fee_q, session, channel=channel, subtotal_q=threshold_base_q
        )
        if waived is not None:
            candidates.append(waived)

        return min(candidates)

    @staticmethod
    def _promotional_fee_q(base_fee_q: int, session: Any, *, channel, subtotal_q: int):
        """A taxa que sobra depois da promoção de entrega grátis, ou ``None``.

        ``value`` é o TETO da renúncia: `0` isenta o frete todo, `> 0` isenta até
        aquele valor e o cliente paga a diferença — "entrega grátis até R$ 8,00".
        """
        from django.utils import timezone as tz

        from shopman.shop.models import Promotion
        from shopman.shop.services import promotions as promotion_service

        channel_ref = getattr(channel, "ref", "") or ""
        now = tz.now()

        found = [
            promo
            for promo in promotion_service.get_active_promotions(now, channel_ref=channel_ref)
            if promo.type == Promotion.FREE_DELIVERY
        ]
        coupon_code = (session.data or {}).get("coupon_code")
        if coupon_code:
            promo = promotion_service.get_coupon_promotion(
                coupon_code, now, channel_ref=channel_ref
            )
            if promo is not None and promo.type == Promotion.FREE_DELIVERY:
                found.append(promo)

        best = None
        for promo in found:
            if not DeliveryFeeModifier._promotion_covers_order(promo, session, subtotal_q):
                continue
            cap_q = int(promo.value or 0)
            remaining = 0 if cap_q <= 0 else max(0, base_fee_q - cap_q)
            best = remaining if best is None else min(best, remaining)
        return best

    @staticmethod
    def _promotion_covers_order(promo, session: Any, subtotal_q: int) -> bool:
        """Os eixos de elegibilidade que fazem sentido para uma renúncia de frete.

        `skus`/`collections` NÃO entram: renúncia de frete é do pedido, não do item —
        "frete grátis se levar croissant" seria outra feature, e inventá-la aqui é
        inventar pedido que não houve.
        """
        from shopman.shop.services.cart import customer_eligible_for_promotion

        if int(promo.min_order_q or 0) > subtotal_q:
            return False

        types = [str(t).strip() for t in (promo.fulfillment_types or []) if str(t).strip()]
        if types and "delivery" not in types:
            return False

        if promo.customer_segments or promo.birthday_only:
            from shopman.guestman.models import Customer

            ref = ((session.data or {}).get("customer") or {}).get("ref") or ""
            customer = Customer.objects.filter(ref=ref).first() if ref else None
            if not customer_eligible_for_promotion(customer, promo):
                return False

        return True


class LoyaltyRedeemModifier:
    """
    Apply loyalty points redemption as a discount.

    Reads session.data["loyalty"]["redeem_points_q"] (centavos to redeem).
    Clamps to min(balance, subtotal) to never make total negative.
    Writes discount summary to session.pricing["loyalty_redeem"].
    """

    code = "shop.loyalty_redeem"
    order = 80  # After all other discounts and delivery fee

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        loyalty_data = (session.data or {}).get("loyalty", {})
        redeem_q = int(loyalty_data.get("redeem_points_q", 0))
        if redeem_q <= 0:
            pricing = session.pricing or {}
            if "loyalty_redeem" in pricing:
                pricing.pop("loyalty_redeem", None)
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            self._record_applied(session, 0)
            return

        items = session.items or []
        subtotal_q = sum(
            item.get("line_total_q", 0)
            for item in items
            if not _is_non_merchandise_line(item)
        )

        # Clamp: never redeem more than the order total
        redeem_q = min(redeem_q, subtotal_q)
        if redeem_q <= 0:
            self._record_applied(session, 0)
            return

        # O rateio preserva ``qty × unit_price_q == line_total_q`` em cada linha
        # (ver ``_spread_order_discount``); antes o unitário levava o piso e o total
        # o valor exato, e os dois campos discordavam. ``at_least=False``: resgate
        # nunca pode debitar mais pontos do que o cliente pediu, então o que não é
        # representável em centavos por unidade fica de fora.
        #
        # ⚠️ Passe só as linhas ELEGÍVEIS, nunca ``items``: a linha
        # ``__DELIVERY_FEE__`` não é mercadoria e resgatar pontos contra ela daria
        # desconto na taxa (e o resíduo cairia numa linha que ninguém desconta).
        eligible = [
            item for item in items
            if not _is_non_merchandise_line(item)
            and item.get("line_total_q", 0) > 0
        ]
        touched = _spread_order_discount(eligible, redeem_q, at_least=False)
        modified = bool(touched)

        if modified:
            session.update_items(items)

        # Débito e transparência seguem o desconto REALMENTE aplicado, nunca o
        # saldo pedido — invariante: pontos debitados == desconto dado.
        applied_q = sum(line_amount_q for _item, _per_unit, line_amount_q in touched)

        pricing = session.pricing or {}
        pricing["loyalty_redeem"] = {
            "total_discount_q": applied_q,
            "label": "Resgate de pontos",
        }
        session.pricing = pricing
        session.save(update_fields=["pricing"])

        self._record_applied(session, applied_q)

    @staticmethod
    def _record_applied(session: Any, applied_q: int) -> None:
        data = session.data or {}
        loyalty_data = data.get("loyalty") or {}
        if int(loyalty_data.get("applied_discount_q") or 0) == applied_q:
            return
        new_loyalty = dict(loyalty_data)
        if applied_q > 0:
            new_loyalty["applied_discount_q"] = applied_q
        else:
            new_loyalty.pop("applied_discount_q", None)
        new_data = dict(data)
        new_data["loyalty"] = new_loyalty
        session.data = new_data
        session.save(update_fields=["data"])


class ManualDiscountModifier:
    """
    Desconto manual aplicado pelo operador no POS.

    Lê session.data["manual_discount"]["discount_q"] (centavos) e
    session.data["manual_discount"]["reason"] (motivo).
    Aplica proporcionalmentenos itens e persiste em session.pricing["manual_discount"].

    Ordem 85: após loyalty (80), só POS usa este modifier.
    """

    code = "shop.manual_discount"
    order = 85

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        manual = (session.data or {}).get("manual_discount") or {}
        discount_q = int(manual.get("discount_q", 0))
        reason = str(manual.get("reason", "") or "")

        pricing = session.pricing or {}

        if discount_q <= 0:
            if "manual_discount" in pricing:
                pricing.pop("manual_discount", None)
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            return

        items = session.items or []
        subtotal_q = sum(
            item.get("line_total_q", 0)
            for item in items
            if not _is_non_merchandise_line(item)
        )
        discount_q = min(discount_q, subtotal_q)
        if discount_q <= 0:
            return

        # Mesmo rateio do LoyaltyRedeemModifier: preserva
        # ``qty × unit_price_q == line_total_q`` em cada linha (ver
        # ``_spread_order_discount``). ``at_least=False``: o operador autorizou um
        # TETO, então o rateio nunca passa dele.
        eligible = [
            item for item in items
            if not _is_non_merchandise_line(item)
            and item.get("line_total_q", 0) > 0
        ]
        touched = _spread_order_discount(eligible, discount_q, at_least=False)
        modified = bool(touched)

        if modified:
            session.update_items(items)

        # O desconto REALMENTE aplicado — invariante: total cobrado cai exatamente
        # pelo valor registrado em pricing.
        applied_q = sum(line_amount_q for _item, _per_unit, line_amount_q in touched)
        pricing["manual_discount"] = {
            "total_discount_q": applied_q,
            "label": f"Desconto ({reason})" if reason else "Desconto manual",
        }
        session.pricing = pricing
        session.save(update_fields=["pricing"])
