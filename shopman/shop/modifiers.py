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
  70  shop.delivery_fee     — taxa de entrega por zona (só delivery)
  80  shop.loyalty_redeem   — loyalty points redemption (post-pricing)
  85  shop.manual_discount  — desconto manual (POS)

Rule-driven discount modifiers (availability / time-window) are generic and
configured per deployment through ``RuleConfig`` rows — enabled state, params and
channel scope all live in the DB. They are registered unconditionally; execution
is gated by ``get_channel_rule_params`` so a disabled rule means no discount.

O relógio da precificação: todo modifier que lê a hora (Happy Hour, promoções,
cupom, aniversário, frete promocional) lê ``pricing_now(ctx)``. É ``now()``, salvo
quando quem precifica diz outra hora em ``ctx["priced_at"]`` (a venda feita sem
conexão no PDV, precificada na hora em que foi cobrada).

Discount policy — "maior desconto ganha":
  Per item, only ONE discount applies (the best one).
  Employee discount is post-pricing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone
from shopman.utils.monetary import monetary_div, monetary_mult

from shopman.shop.policies.promotion import (
    PromotionContext,
    Shopper,
    promotion_matches,
    promotion_minimum_eligible,
)

logger = logging.getLogger(__name__)

# ── Configurable defaults ──────────────────────────────────────────
DEFAULT_TIME_WINDOW_DISCOUNT_PERCENT = 25
DEFAULT_TIME_WINDOW_START = "17:30"
DEFAULT_TIME_WINDOW_END = "18:00"


#: A chave do ``ctx`` dos modifiers que diz QUANDO a sessão está sendo precificada.
#: Ausente, é agora. A venda que o PDV fez sem conexão chega depois com a hora da
#: cobrança (``order.data.pos.offline.captured_at``) e é precificada naquela hora:
#: o Happy Hour que começou durante a queda não vale para a venda das 15h, e a
#: promoção que venceu durante a queda vale para a venda feita antes (decisão do
#: dono, 10/10/2026, WP-PDV-SEM-CONEXAO §3.3).
PRICED_AT_CTX_KEY = "priced_at"


def pricing_now(ctx: dict | None) -> datetime:
    """O "agora" da precificação: ``ctx["priced_at"]`` quando presente, senão ``timezone.now()``.

    Todo modifier que lê o relógio lê por aqui. Instante sem fuso não vale (seria
    lido como outra hora em silêncio) e cai no relógio do servidor.
    """
    value = (ctx or {}).get(PRICED_AT_CTX_KEY)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value
    return timezone.now()


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


def in_time_window(start: time, end: time, now: time) -> bool:
    """``now`` cai em ``[start, end)``; janela com ``start > end`` atravessa a meia-noite.

    Um Happy Hour 23:00–01:00 vale das 23:00 à 00:59. Sem o ramo da virada, a
    comparação simples nunca é verdadeira e a regra some em silêncio.
    """
    if start <= end:
        return start <= now < end
    return now >= start or now < end


@dataclass(frozen=True)
class TimeWindowOffer:
    """A janela de desconto por horário (Happy Hour, "Hora da Xepa") vista num instante.

    UMA leitura para quem cobra (``TimeWindowDiscountModifier``) e para quem mostra
    (a grade do PDV): mesma regra, mesmo canal, mesmo relógio. ``next_change_at()``
    é quando a janela abre (se está fechada) ou fecha (se está aberta), para a
    tela trocar o preço na hora certa sem recarregar.
    """

    active: bool
    discount_percent: int | float
    label: str
    start: time
    end: time
    #: O instante local em que a janela foi lida.
    seen_at: datetime

    def next_change_at(self) -> datetime:
        """Quando a janela abre (fechada) ou fecha (aberta), a partir de ``seen_at``."""
        from datetime import timedelta

        boundary = self.end if self.active else self.start
        change = self.seen_at.replace(hour=boundary.hour, minute=boundary.minute, second=0, microsecond=0)
        if change <= self.seen_at:
            change += timedelta(days=1)
        return change

    def price_q(self, list_q: int) -> int:
        """O preço que a janela dá sobre a etiqueta, pela mesma conta do modifier."""
        if not self.active or list_q <= 0:
            return list_q
        return list_q - monetary_div(list_q * self.discount_percent, 100)


def time_window_offer(channel_ref: str | None, *, now: datetime | None = None) -> TimeWindowOffer | None:
    """A janela de horário que vale para o canal, ou ``None`` sem regra ligada para ele."""
    from shopman.shop.rules.engine import get_channel_rule_params

    params = get_channel_rule_params("happy_hour", channel_ref)
    if params is None:
        return None
    start = _parse_time(params.get("start"), DEFAULT_TIME_WINDOW_START)
    end = _parse_time(params.get("end"), DEFAULT_TIME_WINDOW_END)
    local_now = timezone.localtime(now or timezone.now())
    return TimeWindowOffer(
        active=in_time_window(start, end, local_now.time()),
        discount_percent=params.get("discount_percent", DEFAULT_TIME_WINDOW_DISCOUNT_PERCENT),
        label=_discount_label("CART_DISCOUNT_LABEL_TIME_WINDOW", "Happy Hour"),
        start=start,
        end=end,
        seen_at=local_now,
    )


# ── "Maior desconto ganha" — árbitro por-linha ─────────────────────────────
# ``modifiers_applied`` NÃO sobrevive ao ``Session._normalize_items`` (só ``meta``
# e ``unit_price_q`` persistem). Então o desconto vencedor da linha é registrado em
# ``meta["_disc"]`` (fonte durável entre modifiers), e o preço de lista pré-desconto
# em ``meta["_list_q"]`` (carimbado pelo ItemPricingModifier). Descontos flat
# (happy hour) calculam sobre a LISTA e só substituem quando batem o
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


def _qty_json(qty: Decimal) -> int | float:
    """Quantidade para o registro de transparência (JSON): inteira ou fração de kg."""
    return int(qty) if qty == qty.to_integral_value() else float(qty)


def _record_total_q(record: dict) -> int:
    """Quanto um registro de desconto tira no total: por unidade × quantidade.

    Com a venda por peso a quantidade pode ser 0,312 kg; ``int(qty)`` fazia o
    desconto do queijo sumir da transparência (0 × desconto).
    """
    try:
        qty = Decimal(str(record.get("qty", 1)))
    except (InvalidOperation, TypeError, ValueError):
        qty = Decimal("1")
    return monetary_mult(qty, int(record.get("discount_q", 0) or 0))


def _list_price_q(item: dict) -> int:
    """Preço de lista (pré-desconto) carimbado; cai no preço atual se ausente."""
    meta = item.get("meta") or {}
    listed = meta.get("_list_q")
    return int(listed if listed is not None else (item.get("unit_price_q", 0) or 0))


def _current_disc_q(item: dict) -> int:
    """Desconto por unidade já na linha (lista − preço corrente)."""
    return max(0, _list_price_q(item) - int(item.get("unit_price_q", 0) or 0))


def _round_to_step_q(price_q: int, step_q: int) -> int:
    """Arredonda price_q ao múltiplo de step_q mais próximo (half-up).

    O passo de 50 centavos é a régua da casa: o preço final do grupo cai no
    R$ X,00 ou R$ X,50 mais perto, podendo subir ou descer até R$ 0,25.
    """
    if step_q <= 1:
        return price_q
    from decimal import ROUND_HALF_UP

    steps = (Decimal(int(price_q)) / Decimal(int(step_q))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(steps) * int(step_q)


def _savings_message(template: str, *, amount_q: int, group: str) -> str:
    """Renderiza a mensagem de economia do grupo ({amount} e {group}).

    Texto do grupo quando configurado no Admin; vazio cai no copy global
    CHECKOUT_GROUP_SAVINGS.
    """
    from shopman.utils.monetary import format_money

    text = (template or "").strip()
    if not text:
        from shopman.shop.omotenashi.copy import WILDCARD, resolve_copy

        entry = resolve_copy("CHECKOUT_GROUP_SAVINGS", moment=WILDCARD, audience=WILDCARD)
        text = (entry.message or entry.title or "").strip()
    if not text:
        text = "Hoje você economizou {amount} por ser {group}"
    return (
        text.replace("{amount}", f"R$ {format_money(amount_q)}")
        .replace("{group}", group)
        .strip()
    )


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
    qty = _qty_decimal(item)
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
        disc["total_discount_q"] = sum(_record_total_q(d) for d in kept)
        pricing["discount"] = disc
        if t == "coupon" and pricing.get("coupon"):
            pricing["coupon"]["discount_q"] = sum(_record_total_q(d) for d in kept if d.get("type") == "coupon")
    elif t in ("lot_discount", "happy_hour"):
        entry = pricing.get(t)
        if entry:
            new_total = int(entry.get("total_discount_q", 0)) - monetary_mult(qty, int(prior.get("amount_q", 0)))
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


class CustomerPricingModifier:
    """Resolve o cliente da sessão UMA vez e deixa o contexto de preço pronto.

    Ordem 5, antes do ``ItemPricingModifier`` (10). A sessão é a fonte em TODO
    canal: a loja online grava ``customer.ref`` (e a faixa) a cada mexida na
    sacola, e o PDV grava ``customer.ref``/``price_tier`` no atendimento. Sem
    isto, ``ctx["customer"]`` nunca existia e a cascata "faixa do cliente ->
    listing do offerman" de ``shop/handlers/pricing.py`` não mudava preço nenhum.

    Uma consulta resolve o cadastro (com faixa e insight juntos) e abastece
    ``customer``, ``price_tier``, ``price_tier_name``, ``price_tier_metadata``,
    ``customer_segment`` e ``is_birthday``. O ``DiscountModifier`` reusa o
    contexto em vez de reler a mesma linha; o ``ItemPricingModifier`` passa o
    cliente ao backend, que resolve todas as linhas em lote.
    """

    code = "pricing.customer"
    order = 5

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        if ctx.get("customer") is not None:
            self._publish_profile(ctx, ctx["customer"])
            self._publish_groups(ctx, self._customer_tiers(ctx["customer"]))
            return

        session_customer = (session.data or {}).get("customer") or {}
        customer_ref = str(session_customer.get("ref") or "").strip()
        session_refs = self._session_group_refs(session_customer)
        if not customer_ref and not session_refs:
            return

        customer = None
        if customer_ref:
            try:
                from shopman.guestman.models import Customer

                customer = (
                    Customer.objects.prefetch_related("price_tiers")
                    .select_related("insight")
                    .filter(ref=customer_ref)
                    .first()
                )
            except Exception:  # silêncio-deliberado: sem cadastro os grupos da sessão ainda resolvem o preço
                logger.debug(
                    "pricing.customer: customer lookup failed for ref=%s",
                    customer_ref,
                    exc_info=True,
                )
        if customer is not None:
            ctx["customer"] = customer
            self._publish_groups(ctx, self._customer_tiers(customer), fallback_refs=session_refs)
        elif session_refs:
            self._publish_groups(ctx, self._load_tiers(session_refs), fallback_refs=session_refs)
        if customer is not None:
            self._publish_profile(ctx, customer)
        elif "customer_segment" not in ctx:
            ctx["customer_segment"] = ""
            ctx.setdefault("is_birthday", False)

    @staticmethod
    def _session_group_refs(session_customer: dict) -> list[str]:
        from shopman.shop.services import promotions

        refs = session_customer.get("price_tiers") or session_customer.get("price_tier")
        return promotions._tier_refs(refs)

    @staticmethod
    def _customer_tiers(customer: Any) -> list[Any]:
        tiers = getattr(customer, "price_tiers", None)
        if tiers is None:
            return []
        try:
            return list(tiers.all())
        except Exception:  # silêncio-deliberado: sem os grupos, o resto do contexto segue
            logger.debug("pricing.customer: tiers lookup failed", exc_info=True)
            return []

    @staticmethod
    def _load_tiers(refs: list[str]) -> list[Any]:
        try:
            from shopman.guestman.models import PriceTier

            by_ref = {tier.ref: tier for tier in PriceTier.objects.filter(ref__in=refs)}
        except Exception:  # silêncio-deliberado: grupo ilegível não derruba a precificação
            logger.debug("pricing.customer: tier lookup failed for refs=%s", refs, exc_info=True)
            return []
        return [by_ref[ref] for ref in refs if ref in by_ref]

    @classmethod
    def _publish_groups(cls, ctx: dict, tiers: list[Any], fallback_refs=()) -> None:
        """Publica a LISTA de grupos do cliente e o mapa de metadados de cada um.

        O motor de desconto usa a lista inteira (melhor por tipo, sem acumular); o
        ``price_tier``/``price_tier_name`` seguem como o grupo PRIMÁRIO, para quem lê
        "o grupo do cliente". Nada é sobrescrito quando o chamador já publicou.
        """
        refs = [getattr(tier, "ref", "") for tier in tiers if getattr(tier, "ref", "")]
        if not refs:
            refs = list(fallback_refs)
        if not refs:
            return
        ctx.setdefault("price_tiers", refs)
        ctx.setdefault("price_tier", refs[0])
        if not tiers:
            return
        metadata_by_ref = {}
        names_by_ref = {}
        for tier in tiers:
            ref = getattr(tier, "ref", "")
            if not ref:
                continue
            names_by_ref[ref] = getattr(tier, "name", "") or ""
            metadata = getattr(tier, "metadata", None)
            metadata_by_ref[ref] = metadata if isinstance(metadata, dict) else {}
        primary = tiers[0]
        ctx.setdefault("price_tier_name", getattr(primary, "name", "") or "")
        ctx.setdefault("price_tier_metadata", metadata_by_ref.get(getattr(primary, "ref", ""), {}))
        ctx.setdefault("price_tier_metadata_by_ref", metadata_by_ref)
        ctx.setdefault("price_tier_names_by_ref", names_by_ref)
        # O PDV pode vincular só os grupos (sem ``ref`` de cliente): o backend precisa
        # do melhor ``listing_ref`` dos grupos para a cascata de preço.
        if ctx.get("customer") is None:
            from types import SimpleNamespace

            best_listing = next(
                (getattr(tier, "listing_ref", "") for tier in tiers if getattr(tier, "listing_ref", "")),
                "",
            )
            ctx["customer"] = SimpleNamespace(listing_ref=best_listing)

    @staticmethod
    def _publish_profile(ctx: dict, customer: Any) -> None:
        if "customer_segment" not in ctx:
            try:
                ctx["customer_segment"] = customer.insight.rfm_segment or ""
            except Exception:  # silêncio-deliberado: Insight (OneToOne) pode não existir; a faixa ainda casa
                logger.debug("pricing.customer: no insight for customer", exc_info=True)
                ctx["customer_segment"] = ""
        if "is_birthday" not in ctx:
            birthday = getattr(customer, "birthday", None)
            if birthday:
                today = timezone.localdate(pricing_now(ctx))
                ctx["is_birthday"] = birthday.month == today.month and birthday.day == today.day
            else:
                ctx["is_birthday"] = False


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
    quando bate o desconto já aplicado (promo, happy hour) — nunca compõe.
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
    bate o desconto já aplicado (promo, lote) — nunca compõe.
    """

    code = "shop.happy_hour"
    order = 65

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        offer = time_window_offer(getattr(channel, "ref", None), now=pricing_now(ctx))
        if offer is None:
            return

        if not offer.active:
            # Fora da janela: limpa transparência residual de uma passagem anterior.
            pricing = session.pricing or {}
            if pricing.pop("happy_hour", None) is not None:
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            return

        _apply_flat_best_wins(
            session,
            percent=offer.discount_percent,
            disc_type="happy_hour",
            label=offer.label,
            pricing_key="happy_hour",
        )


def promotion_context(
    ctx: dict,
    *,
    sku: str,
    merchandise_subtotal_q: int | None = None,
) -> PromotionContext:
    """Os fatos que o contexto de preço já reuniu, no formato da política de promoção.

    O contexto de preço é o dicionário que os modifiers e o preço contextual do
    catálogo compartilham (``customer_segment``, ``price_tier``/``price_tiers``,
    ``is_birthday``, ``fulfillment_type``, ``sku_collections``). Quem decide é
    ``promotion_matches``; aqui só se traduz o dicionário.
    """
    tier_refs = {str(ref) for ref in (ctx.get("price_tiers") or []) if ref}
    if ctx.get("price_tier"):
        tier_refs.add(str(ctx["price_tier"]))
    return PromotionContext(
        shopper=Shopper(
            segment=str(ctx.get("customer_segment") or ""),
            tier_refs=frozenset(tier_refs),
            is_birthday=bool(ctx.get("is_birthday")),
        ),
        sku=sku,
        sku_collections=tuple((ctx.get("sku_collections") or {}).get(sku, []) or ()),
        fulfillment_type=str(ctx.get("fulfillment_type") or ""),
        merchandise_subtotal_q=merchandise_subtotal_q,
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
        # put in ``ctx`` still wins. The POS writes ``customer.primary_price_tier`` straight to
        # the session; the storefront links the customer (ref + tier) when a
        # segment-gated coupon is applied, and the RFM segment resolves from the
        # customer's ``insight``.
        self._resolve_customer_ctx(session, ctx)

        now = pricing_now(ctx)

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
            if not _is_non_merchandise_line(item)
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

        # O desconto do PRÓPRIO grupo do cliente (a promoção grupo-<ref>) é o
        # único que arredonda o preço final, carrega o tipo para o B.I. e produz a
        # mensagem de economia. O cliente pode ter MAIS DE UM grupo: o mapa por ref
        # diz qual metadado vale para o vencedor de cada linha.
        from shopman.shop.services.promotions import group_discount_ref

        tier_refs = list(ctx.get("price_tiers") or [])
        if not tier_refs and ctx.get("price_tier"):
            tier_refs = [str(ctx["price_tier"])]
        group_refs = {group_discount_ref(ref) for ref in tier_refs}
        metadata_by_ref = dict(ctx.get("price_tier_metadata_by_ref") or {})
        if not metadata_by_ref and ctx.get("price_tier_metadata") and tier_refs:
            metadata_by_ref = {tier_refs[0]: ctx["price_tier_metadata"]}

        def _winning_group_meta(promo):
            """(ref do grupo vencedor, discount_kind, passo do arredondamento)."""
            for ref in tier_refs:
                if group_discount_ref(ref) == getattr(promo, "ref", ""):
                    meta = metadata_by_ref.get(ref) or {}
                    kind = str(meta.get("discount_kind") or "").strip() or None
                    try:
                        step = int(meta.get("rounding", 50) or 0)
                    except (TypeError, ValueError):
                        step = 50
                    return ref, kind, step
            return "", None, 0

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
            line_ctx = promotion_context(ctx, sku=sku, merchandise_subtotal_q=session_total)

            # Find best discount candidate
            best_discount_q = 0
            best_source = None  # (type, name, promo, discount_kind)

            # Only PERCENT discounts compete per-line: a percentage is intrinsically
            # per-unit. FIXED discounts are order-level and applied once, after this
            # loop (see the order-level fixed step below).
            # Evaluate auto-promotions
            for promo in promotions:
                if promo.type != "percent":
                    continue
                if not promotion_matches(promo, line_ctx):
                    continue
                discount_q = self._calc_discount(promo, price_q)
                promo_kind = None
                promo_group_ref = ""
                if getattr(promo, "ref", "") in group_refs:
                    promo_group_ref, promo_kind, rounding_step = _winning_group_meta(promo)
                    if rounding_step > 0:
                        rounded = _round_to_step_q(max(0, price_q - discount_q), rounding_step)
                        discount_q = max(0, price_q - rounded)
                if discount_q > best_discount_q:
                    best_discount_q = discount_q
                    best_source = ("promotion", promo.name, promo, promo_kind, promo_group_ref)

            # Evaluate coupon
            if coupon_promo and coupon_promo.type == "percent":
                if promotion_matches(coupon_promo, line_ctx):
                    coupon_discount_q = self._calc_discount(coupon_promo, price_q)
                    if coupon_discount_q >= best_discount_q:
                        best_discount_q = coupon_discount_q
                        best_source = ("coupon", coupon_code, coupon_promo, None, "")

            # Evaluate operator manual per-line discount (percent), best wins.
            if manual_allowed:
                manual_discount_q = self._calc_manual(manual, price_q)
                if manual_discount_q > best_discount_q:
                    best_discount_q = manual_discount_q
                    best_source = ("manual", manual.get("reason") or "manual", None, None, "")

            # Apply winner — só quando bate o desconto já na linha (best-wins, sem
            # composição). Reconcilia a transparência do desconto substituído
            # (ex.: lote) antes de gravar o novo vencedor.
            if best_source and best_discount_q > current_disc_q:
                _reverse_prior_pricing(pricing, item)
                item["unit_price_q"] = list_q - best_discount_q
                item["line_total_q"] = monetary_mult(_qty_decimal(item), item["unit_price_q"])

                source_type, source_name, source_promo, source_kind, source_group = best_source
                # Fonte durável do desconto vencedor da linha: ``meta._disc`` (para o
                # árbitro flat reconciliar em "maior ganha") + ``discounts_applied``
                # (abaixo) que vira ``pricing["discount"]``. ``modifiers_applied`` foi
                # removido — não persistia e criava guards cegos (ver DISCOUNT-AUDIT).
                _stamp_disc(item, source_type, best_discount_q, source_name or source_type)
                modified = True

                qty = _qty_decimal(item)
                record = {
                    # A LINHA que ganhou o desconto, ao lado do SKU. O registro é
                    # a única fonte que sobrevive ao save (a linha perde campos
                    # extras no update_items), e quem o relê é a comanda do PDV
                    # para restaurar o preço PRÉ-desconto. Identificado só pelo
                    # SKU, o registro de uma linha respondia pela outra do mesmo
                    # produto — a cortesia dada num café aparecia nos dois.
                    "line_id": item.get("line_id", ""),
                    "sku": sku,
                    "type": source_type,
                    "name": source_name,
                    "original_price_q": price_q,
                    "discount_q": best_discount_q,
                    "qty": _qty_json(qty),
                    "fulfillment_types": list(getattr(source_promo, "fulfillment_types", None) or []),
                }
                if source_kind:
                    record["discount_kind"] = source_kind
                if source_group:
                    record["discount_group"] = source_group
                discounts_applied.append(record)
                if source_type == "coupon":
                    total_coupon_discount_q += monetary_mult(qty, best_discount_q)

        # Order-level FIXED discount (fixed promo / fixed coupon). A fixed value
        # like "R$5 off" is a single per-ORDER discount, never per unit — 6 units
        # of a R$5 coupon is R$5 off the order, not R$30. Applied once to the
        # eligible merchandise subtotal, distributed across lines that don't
        # already carry a per-line discount (no stacking on the same line).
        fixed = self._best_fixed_discount(
            promotions,
            coupon_promo,
            coupon_code,
            session_total,
            group_refs=group_refs,
            group_meta=_winning_group_meta,
        )
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
                and promotion_matches(fixed_promo, promotion_context(ctx, sku=item.get("sku", "")))
            ]
            eligible_subtotal = sum(int(item.get("line_total_q", 0)) for item in eligible)
            target_q = min(fixed_value, eligible_subtotal)
            src_type, src_name, src_kind, src_group = fixed_source
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
                order_record = {
                    "line_id": "",
                    "sku": "",
                    "type": src_type,
                    "name": src_name,
                    "original_price_q": 0,
                    "discount_q": applied_q,
                    "qty": 1,
                    "fulfillment_types": list(getattr(fixed_promo, "fulfillment_types", None) or []),
                }
                if src_kind:
                    order_record["discount_kind"] = src_kind
                if src_group:
                    order_record["discount_group"] = src_group
                discounts_applied.append(order_record)
                if src_type == "coupon":
                    total_coupon_discount_q += applied_q

        if modified:
            session.update_items(items)

        # Persist discount info in session.pricing (items lose extra fields on save)
        if not session.pricing:
            session.pricing = {}
        discount_block = {
            "total_discount_q": sum(_record_total_q(d) for d in discounts_applied),
            "items": discounts_applied,
        }
        group_savings_q = sum(
            _record_total_q(d) for d in discounts_applied if d.get("discount_kind")
        )
        if group_savings_q > 0:
            winner = next(d for d in discounts_applied if d.get("discount_kind"))
            group_name = str(winner.get("name") or "")
            winner_meta = metadata_by_ref.get(str(winner.get("discount_group") or "")) or {}
            discount_block["savings"] = {
                "amount_q": group_savings_q,
                "group": group_name,
                "kind": str(winner.get("discount_kind") or ""),
                "message": _savings_message(
                    str(winner_meta.get("savings_message") or ""),
                    amount_q=group_savings_q,
                    group=group_name,
                ),
            }
        session.pricing["discount"] = discount_block
        if coupon_code:
            session.pricing["coupon"] = {
                "code": coupon_code,
                "discount_q": total_coupon_discount_q,
            }
        else:
            session.pricing.pop("coupon", None)

    @staticmethod
    def _resolve_customer_ctx(session: Any, ctx: dict) -> None:
        """Populate ``price_tiers``, ``customer_segment`` and ``is_birthday``
        in ``ctx`` from the session's linked customer, without overriding values
        the caller already supplied.

        ``customer.price_tiers`` persisted on the session (POS) is authoritative for the
        groups. Everything else (segment, birthday, and the groups when only the ref
        is on the session) resolves from the ``Customer`` row, so the discount is
        recomputed correctly on every reprice, not just the moment the coupon is
        applied.
        """
        from django.core.exceptions import ObjectDoesNotExist

        from shopman.shop.services import promotions

        customer_data = (session.data or {}).get("customer") or {}

        # Pertencimento, não valor: o ``CustomerPricingModifier`` (ordem 5) já
        # abasteceu o contexto e uma chave presente (mesmo vazia) dispensa a
        # releitura. Só quem chama o modifier direto (testes) paga a consulta.
        needs_groups = "price_tiers" not in ctx and "price_tier" not in ctx
        if needs_groups:
            session_refs = promotions._tier_refs(
                customer_data.get("price_tiers") or customer_data.get("price_tier")
            )
            if session_refs:
                ctx["price_tiers"] = session_refs
                ctx["price_tier"] = session_refs[0]
                needs_groups = False

        needs_segment = "customer_segment" not in ctx
        needs_birthday = "is_birthday" not in ctx
        customer_ref = customer_data.get("ref")
        if not customer_ref or not (needs_groups or needs_segment or needs_birthday):
            return

        try:
            from shopman.guestman.models import Customer

            customer = (
                Customer.objects.filter(ref=customer_ref)
                .prefetch_related("price_tiers").select_related("insight")
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

        if needs_groups:
            tiers = list(customer.price_tiers.all())
            if tiers:
                CustomerPricingModifier._publish_groups(ctx, tiers)

        if needs_segment:
            try:
                ctx["customer_segment"] = customer.insight.rfm_segment or ""
            except ObjectDoesNotExist:  # silêncio-deliberado: cliente novo ainda sem Insight (RFM roda em lote); casa pela faixa, segmento vazio
                # Insight (OneToOne) not computed yet — the customer still matches
                # by tier; the segment stays empty. Degrade quietly, no traceback.
                logger.debug(
                    "discount_modifier: no insight for customer=%s", customer_ref
                )

        if needs_birthday and customer.birthday:
            # O aniversário é o do DIA DA VENDA: a venda das 23h50 enviada depois
            # da meia-noite ainda é do dia do aniversário (e a do dia seguinte não).
            ctx["is_birthday"] = Shopper.birthday_on(
                customer.birthday, timezone.localdate(pricing_now(ctx))
            )

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
        promotions: list[Any],
        coupon_promo: Any,
        coupon_code: str | None,
        session_total: int,
        *,
        group_refs: set[str] = frozenset(),
        group_meta=None,
    ) -> tuple[int, tuple[str, str, str | None, str], Any] | None:
        """Largest applicable FIXED discount, as a single order-level candidate.

        Fixed promotions and the fixed coupon compete on value (best wins, no
        stacking of two fixed discounts). min_order_q is gated against the gross
        order subtotal; SKU/collection scope is enforced later when picking the
        eligible lines. A fixed discount of the customer's own group carries its
        (discount_kind, group_ref) per the WINNING group, not the primary one.
        Returns (value_q, source, promo) where source is
        (type, name, discount_kind, group_ref), or None.
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
            value = max(0, int(promo.value or 0))
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
                value = max(0, int(coupon_promo.value or 0))
                if value > 0 and (best is None or value >= best[0]):
                    best = (value, ("coupon", coupon_code or "", None, ""), coupon_promo)
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
           descobre o que abater quando um desconto flat (happy hour) vence a
           linha depois. Sem o carimbo, o flat vencia, o preço da linha caía
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


def operator_agreed_delivery_fee_q(data: dict) -> int | None:
    """A taxa que um operador do PDV assumiu com nome e hora, ou ``None``.

    Só vale com as DUAS marcas que o PDV grava juntas: o valor
    (``delivery_fee_override_q``) e quem/quando (``pos.delivery_fee_agreed``).
    Uma chave solta na sessão, sem assinatura, não desliga a área de entrega.
    """
    override = data.get("delivery_fee_override_q")
    agreed = (data.get("pos") or {}).get("delivery_fee_agreed") if isinstance(data.get("pos"), dict) else None
    if override in (None, "") or not isinstance(agreed, dict) or not agreed.get("by"):
        return None
    try:
        return max(0, int(override))
    except (TypeError, ValueError):
        return None


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

        agreed_fee_q = operator_agreed_delivery_fee_q(data)
        if agreed_fee_q is not None:
            # A taxa que o operador do balcão ASSUMIU (combinado de porta, cortesia,
            # endereço fora da área): é a taxa, e o motor não tem segunda opinião.
            # Fora da área deixa de ser recusa no commit porque a exceção foi feita
            # com nome e hora (`pos.delivery_fee_agreed`); quem cobra é a linha
            # manual que o PDV pôs no pedido (zero = nenhuma linha).
            new_data = dict(data)
            new_data["delivery_fee_q"] = agreed_fee_q
            new_data.pop("delivery_zone_error", None)
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
            fee_q = self._effective_fee_q(base_fee_q, session, channel=channel, now=pricing_now(ctx))
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
    def _effective_fee_q(base_fee_q: int, session: Any, *, channel: Any = None, now: datetime | None = None) -> int:
        """A taxa efetiva da sessão: ``resolve_delivery_fee_waiver`` sobre o carrinho.

        Entrega grátis é renúncia AQUI, nunca linha de desconto: a linha
        `__DELIVERY_FEE__` é blindada contra desconto em dez pontos deste arquivo, e é
        essa invariante que mantém a taxa com um dono. E o resultado sai certo de
        graça: taxa zerada REMOVE a linha em vez de gerar uma de R$ 0,00.
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
        # de entrega (validation.py), senão a tela diz "frete grátis" e o modifier
        # cobra a taxa. O preço por lote continua contando (é venda real).
        coupon_discount_q = int(((session.pricing or {}).get("coupon") or {}).get("discount_q") or 0)
        data = session.data or {}
        # O cupom já está resolvido em `session.data` quando a taxa é calculada:
        # este modifier roda em order=70, cinquenta slots depois do desconto (20).
        return resolve_delivery_fee_waiver(
            base_fee_q,
            merchandise_q=subtotal_q + coupon_discount_q,
            channel_ref=getattr(channel, "ref", "") or "",
            customer_ref=(data.get("customer") or {}).get("ref") or "",
            coupon_code=data.get("coupon_code") or "",
            now=now,
        ).fee_q


@dataclass(frozen=True)
class DeliveryFeeWaiver:
    """A taxa que sobra depois da renúncia, e QUAL política renunciou.

    ``reason``: ``""`` (nada renunciou) · ``"threshold"`` (o limiar permanente
    da loja, ``threshold_q``) · ``"promotion"`` (a promoção ``promotion_name``).
    """

    fee_q: int
    base_fee_q: int = 0
    reason: str = ""
    promotion_name: str = ""
    threshold_q: int = 0


def resolve_delivery_fee_waiver(
    base_fee_q: int,
    *,
    merchandise_q: int,
    channel_ref: str,
    customer_ref: str = "",
    coupon_code: str = "",
    now: datetime | None = None,
) -> DeliveryFeeWaiver:
    """A renúncia de frete que renuncia MAIS, entre duas políticas. Um motor, todo canal.

    Duas políticas, **um dono**. O limiar permanente (`free_delivery_above_q`, de
    `Shop.defaults`) e a promoção `free_delivery` ativa NO CANAL (automática ou por
    cupom). Vence a que renuncia mais, na convenção best-wins do desconto. É a
    mesma função para a sessão da loja (``DeliveryFeeModifier``) e para a revisão
    do PDV (``pos._compute_engine_delivery_fee``): o PDV não tem sessão até fechar,
    e uma cópia da regra lá seria a segunda opinião sobre o frete (P2-21).

    ``channel_ref`` é obrigatório de propósito: vazio, ``get_active_promotions``
    não filtra, e a promoção só da loja online valeria em todo canal.
    """
    if base_fee_q <= 0:
        return DeliveryFeeWaiver(fee_q=base_fee_q, base_fee_q=base_fee_q)

    best = DeliveryFeeWaiver(fee_q=base_fee_q, base_fee_q=base_fee_q)

    # Política 1: o limiar permanente da loja.
    from shopman.shop.projections.cart import shop_rule_q

    free_above_q = shop_rule_q("free_delivery_above_q")
    if free_above_q and merchandise_q >= free_above_q:
        best = DeliveryFeeWaiver(fee_q=0, base_fee_q=base_fee_q, reason="threshold", threshold_q=free_above_q)

    # Política 2: promoção de entrega grátis. No empate, a promoção nomeia a
    # renúncia: é ela que o operador procura quando o frete sai grátis.
    if channel_ref:
        promoted = _best_free_delivery_promotion(
            base_fee_q, channel_ref=channel_ref, merchandise_q=merchandise_q,
            customer_ref=customer_ref, coupon_code=coupon_code, now=now,
        )
        if promoted is not None and promoted[0] <= best.fee_q:
            remaining, promo = promoted
            best = DeliveryFeeWaiver(
                fee_q=remaining, base_fee_q=base_fee_q, reason="promotion",
                promotion_name=str(getattr(promo, "name", "") or ""),
            )
    return best


def _best_free_delivery_promotion(
    base_fee_q: int, *, channel_ref: str, merchandise_q: int, customer_ref: str, coupon_code: str,
    now: datetime | None,
):
    """``(taxa que sobra, promoção)`` da promoção de entrega grátis que mais renuncia, ou ``None``.

    ``value`` é o TETO da renúncia: `0` isenta o frete todo, `> 0` isenta até
    aquele valor e o cliente paga a diferença ("entrega grátis até R$ 8,00").
    """
    from django.utils import timezone as tz

    from shopman.shop.models import Promotion
    from shopman.shop.services import promotions as promotion_service

    now = now or tz.now()
    found = [
        promo
        for promo in promotion_service.get_active_promotions(now, channel_ref=channel_ref)
        if promo.type == Promotion.FREE_DELIVERY
    ]
    if coupon_code:
        promo = promotion_service.get_coupon_promotion(coupon_code, now, channel_ref=channel_ref)
        if promo is not None and promo.type == Promotion.FREE_DELIVERY:
            found.append(promo)

    best = None
    for promo in found:
        if not _free_delivery_covers_order(promo, customer_ref=customer_ref, merchandise_q=merchandise_q):
            continue
        cap_q = int(promo.value or 0)
        remaining = 0 if cap_q <= 0 else max(0, base_fee_q - cap_q)
        if best is None or remaining < best[0]:
            best = (remaining, promo)
    return best


def _free_delivery_covers_order(promo, *, customer_ref: str, merchandise_q: int) -> bool:
    """Os eixos de elegibilidade que fazem sentido para uma renúncia de frete.

    `skus`/`collections` NÃO entram (a pergunta não traz item): renúncia de frete é
    do pedido, não do item. "Frete grátis se levar croissant" seria outra feature, e
    inventá-la aqui é inventar pedido que não houve. O cliente só é buscado quando a
    promoção tem alvo por cliente (o visitante anônimo não a satisfaz).
    """
    from shopman.shop.services.cart import promotion_shopper

    order_ctx = PromotionContext(fulfillment_type="delivery", merchandise_subtotal_q=merchandise_q)
    if promotion_matches(promo, order_ctx):
        return True
    if not customer_ref or promotion_matches(promo, PromotionContext()):
        return False  # falhou por mínimo/atendimento, ou exige um cliente que não há

    from shopman.guestman.models import Customer

    customer = Customer.objects.filter(ref=customer_ref).first()
    if customer is None:
        return False
    return promotion_matches(promo, replace(order_ctx, shopper=promotion_shopper(customer)))


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
