"""``CommerceReadPort`` sobre o Shopman: catálogo, promessa, cotação, pedido, cliente, política (N4).

Garantias da porta (v2 5.4, ``spec/03-ports.md`` do framework), e como o Shopman as cumpre:

- **fato com fonte e validade**: todo valor sai como ``Known`` com ``source`` (Offerman,
  Stockman, Orderman, Shop) e ``valid_until`` (a validade do turno, P14 do perfil);
- **fonte que falha vira ``Unknown``**, nunca o valor velho (K04): erro de leitura é
  ``Unknown(source_failed)``, item que não existe é ``Unknown(not_found)``;
- **autorização por objeto**: carrinho, cliente e pedido só do sujeito do contexto
  confiável, pela ``Ownership`` que o chamador injeta; o resto é ``object_forbidden``;
- **consulta não é reserva**, e **"pode prometer" não é "há unidade separada"** (K27): a
  promessa devolve as quatro leituras do Stockman separadas (o pronto agora, o esperado, o
  planejado e o que se pode prometer), sem reduzir a "disponível".

Só leitura: nada aqui escreve no comércio (a execução é o N6).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from conversational_commerce.contracts import Known, Quantity, TermsDocument, Unknown, seal
from conversational_commerce.contracts.common import Unavailable
from conversational_commerce.ports import Capabilities, ItemSummary, PortError, PromiseReading, TrustedContext
from conversational_commerce.ports.commerce_read import OPERATIONS

logger = logging.getLogger(__name__)

PORT = "commerce_read"
CURRENCY = "BRL"
FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
# P14 do perfil da Nice: o fato vale para o turno. O turno da Concierge tem posse por 120 s.
FACT_VALIDITY_SECONDS = 120
PRODUCER_NAME = "shopman-commerce-read"
# Operações declaradas que o Shopman ainda não responde: ``knowledge`` (o FAQ promovido da
# equipe chega com o N7) e ``scarcity`` (nenhuma previsão no D1). Devolvem vazio e
# ``Unavailable``, nunca um valor inventado.
UNSUPPORTED = ("knowledge", "scarcity")


def instant(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(UTC)
    return moment.astimezone(UTC).strftime(FORMAT)


class Ownership(Protocol):
    """Quem diz o que é do sujeito do contexto confiável. Mora com a superfície (a Concierge)."""

    def cart(self, ctx: TrustedContext) -> str | None: ...

    def new_cart(self, ctx: TrustedContext) -> str | None:
        """A sacola que o sujeito ainda vai ter (sem nenhuma aberta), ou ``None``. Ela nasce no efeito."""
        ...

    def customer(self, ctx: TrustedContext) -> str | None: ...

    def owns_order(self, ctx: TrustedContext, order_ref: str) -> bool: ...


class DenyAll:
    """Sem superfície que resolva o sujeito: nada pessoal se lê (o padrão seguro)."""

    def cart(self, ctx: TrustedContext) -> str | None:
        return None

    def new_cart(self, ctx: TrustedContext) -> str | None:
        return None

    def customer(self, ctx: TrustedContext) -> str | None:
        return None

    def owns_order(self, ctx: TrustedContext, order_ref: str) -> bool:
        return False


@dataclass
class ShopmanCommerceRead:
    """A porta de leitura do comércio, no canal de venda ``channel_ref``."""

    channel_ref: str
    ownership: Ownership = None  # type: ignore[assignment]
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    fact_validity_seconds: int = FACT_VALIDITY_SECONDS
    new_id: Callable[[str], str] | None = None

    PORT = PORT

    def __post_init__(self) -> None:
        if self.ownership is None:
            self.ownership = DenyAll()
        self._sequence = 0

    # ── comum ────────────────────────────────────────────────────────────────
    def capabilities(self) -> Capabilities:
        return Capabilities(port=PORT, operations=OPERATIONS, unsupported=UNSUPPORTED, guarantees={
            "fact_validity_seconds": self.fact_validity_seconds, "object_authorization": True,
            "promise_is_not_reservation": True, "source_failure_is_unknown": True})

    def _id(self, prefix: str) -> str:
        if self.new_id is not None:
            return self.new_id(prefix)
        self._sequence += 1
        return f"{prefix}-{int(self.now().timestamp() * 1_000_000)}-{self._sequence}"

    def _known(self, value: Any, source: str, *, version: str | None = None) -> Known:
        now = self.now()
        return Known(value=value, source=source, observed_at=instant(now),
                     valid_until=instant(now + timedelta(seconds=self.fact_validity_seconds)), source_version=version)

    def _channel(self):
        from shopman.shop.models import Channel

        return Channel.objects.filter(ref=self.channel_ref).first()

    def _price_q(self, product) -> int:
        from shopman.shop.services.display_prices import resolve_prices

        channel = self._channel()
        if channel is None:
            raise LookupError(f"canal {self.channel_ref} não existe")
        return int(resolve_prices(channel, [product])[product.sku])

    # ── catálogo ─────────────────────────────────────────────────────────────
    def search_catalog(self, ctx: TrustedContext, query: str) -> tuple[ItemSummary, ...]:
        """Os itens publicados e vendáveis cujo nome ou SKU contém ``query``, com o preço do canal."""
        from django.db.models import Q
        from shopman.offerman.models import Product

        try:
            needle = (query or "").strip()
            products = Product.objects.filter(is_published=True, is_sellable=True)
            if needle:
                products = products.filter(Q(name__icontains=needle) | Q(sku__icontains=needle))
            return tuple(ItemSummary(ref=p.sku, name=p.name, unit=p.unit or "unit",
                                     price={"amount_minor": self._price_q(p), "currency": CURRENCY})
                         for p in products.order_by("sku")[:50])
        except Exception as error:  # noqa: BLE001 - a fonte falhou: a porta diz, não inventa
            logger.warning("conversational.search_catalog: fonte falhou", exc_info=True)
            raise PortError("provider_unavailable", f"catálogo fora: {type(error).__name__}") from error

    def read_item(self, ctx: TrustedContext, ref: str):
        from shopman.offerman.models import Product

        try:
            product = Product.objects.filter(sku=ref).first()
            if product is None or not product.is_published:
                return Unknown(reason="not_found")
            value = {"ref": product.sku, "name": product.name, "unit": product.unit or "unit",
                     "price_minor": self._price_q(product), "currency": CURRENCY,
                     "sellable": bool(product.is_sellable)}
        except Exception:  # noqa: BLE001 - K04: a fonte que falha vira Unknown, nunca o valor velho
            logger.warning("conversational.read_item: fonte falhou", exc_info=True)
            return Unknown(reason="source_failed")
        return self._known(value, f"offerman:{self.channel_ref}")

    # ── promessa ─────────────────────────────────────────────────────────────
    def promise(self, ctx: TrustedContext, ref: str, quantity: Quantity, when: str) -> PromiseReading:
        """As quatro leituras do Stockman, separadas. ``promisable`` é a decisão do orquestrador."""
        from shopman.shop.services import availability

        target = _date_of(when)
        failed = Unknown(reason="source_failed")
        try:
            decision = availability.decide(ref, Decimal(quantity.value), channel_ref=self.channel_ref,
                                           target_date=target)
        except Exception:  # noqa: BLE001
            logger.warning("conversational.promise: fonte falhou", exc_info=True)
            return PromiseReading(ref=ref, quantity=quantity, factual=failed, expected=failed, planned=failed,
                                  promisable=failed)
        source = f"stockman:{decision.get('source', 'promise')}"
        promisable = self._known({"approved": bool(decision.get("approved")),
                                  "reason": decision.get("reason_code") or None,
                                  "orderable_ceiling": _text(decision.get("orderable_ceiling"))}, source)
        factual = expected = planned = Unknown(reason="not_supported")
        if decision.get("source") == "stock.promise_decision":
            reading = self._stock_reading(ref, quantity, decision.get("target_date") or target)
            if reading is None:
                factual = expected = planned = failed
            elif reading.available_qty is None:
                # Sem ledger no Stockman: "não se sabe", nunca "ilimitado" (PromiseDecision).
                factual = expected = planned = Unknown(reason="not_supported")
            else:
                factual = self._known(_text(reading.available), "stockman:ready")
                expected = self._known(_text(reading.expected), "stockman:expected")
                planned = self._known(_text(reading.planned), "stockman:planned")
        return PromiseReading(ref=ref, quantity=quantity, factual=factual, expected=expected, planned=planned,
                              promisable=promisable)

    def _stock_reading(self, ref: str, quantity: Quantity, target):
        """A ``PromiseDecision`` inteira, com o esperado e o planejado que o dict de ``decide`` não leva."""
        try:
            from shopman.stockman.services.availability import decision_from_availability

            from shopman.shop.adapters import get_adapter
            from shopman.shop.services.availability import availability_kwargs

            adapter = get_adapter("stock")
            scope = adapter.get_channel_scope(self.channel_ref)
            info = adapter.get_availability(ref, target_date=target, **availability_kwargs(scope, target))
            return decision_from_availability(ref, Decimal(quantity.value), info, target_date=target)
        except Exception:  # noqa: BLE001
            logger.warning("conversational.promise: leitura do estoque falhou", exc_info=True)
            return None

    # ── cotação ──────────────────────────────────────────────────────────────
    def quote(self, ctx: TrustedContext, cart_ref: str) -> TermsDocument:
        """Os termos da sacola do sujeito, selados. Só a sacola dele (autorização por objeto)."""
        from shopman.orderman.models import Session

        if not cart_ref or self.ownership.cart(ctx) != cart_ref:
            raise PortError("object_forbidden", "sacola inexistente ou de outro sujeito")
        session = Session.objects.filter(session_key=cart_ref, channel_ref=self.channel_ref).first()
        if session is None:
            raise PortError("object_forbidden", "sacola inexistente ou de outro sujeito")
        items = []
        for line in session.items or []:
            items.append({"ref": str(line.get("sku")), "quantity": {"value": _text(line.get("qty")), "unit": "unit"},
                          "unit_price": {"amount_minor": int(line.get("unit_price_q") or 0), "currency": CURRENCY},
                          "line_total": {"amount_minor": int(line.get("line_total_q") or 0), "currency": CURRENCY}})
        if not items:
            raise PortError("fact_unavailable", "sacola vazia: não há termos a cotar")
        data = session.data or {}
        adjustments = []
        fee = int(data.get("delivery_fee_q") or 0)
        if fee:
            adjustments.append({"code": "delivery_fee", "amount": {"amount_minor": fee, "currency": CURRENCY}})
        total = sum(item["line_total"]["amount_minor"] for item in items) + fee
        now = self.now()
        return seal(TermsDocument(
            id=self._id("terms"), tenant=ctx.tenant, environment=ctx.environment, trace_id=self._id("trace"),
            occurred_at=instant(now), producer={"name": PRODUCER_NAME, "version": "1"},
            terms_id=f"{cart_ref}-r{session.rev}", version=max(1, int(session.rev or 0)), items=items,
            adjustments=adjustments, total={"amount_minor": total, "currency": CURRENCY},
            recipient={"subject_ref": ctx.subject or "unknown-subject"},
            fulfillment=_fulfillment(data), conditions=_fulfillment_conditions(data, self.channel_ref),
            valid_until=instant(now + timedelta(minutes=self._hold_minutes())),
        ))

    def requirements(self, ctx: TrustedContext, cart_ref: str):
        """O que os termos da sacola ainda exigem do cliente, e as opções do canal para cada condição.

        Hoje, a forma de pagamento: falta quando o canal oferece mais de uma e a sacola não tem
        nenhuma escolhida (a MESMA regra do ``review_order`` da casa, que grava o pedido). As opções
        são as do canal sem dinheiro (D-003, a mesma lista do fechamento de hoje). Vale também para
        a sacola que o sujeito ainda vai ter: "2 croissants, pago no pix" no primeiro pedido.
        """
        from shopman.orderman.models import Session

        if not cart_ref or cart_ref not in {self.ownership.cart(ctx), self.ownership.new_cart(ctx)}:
            raise PortError("object_forbidden", "sacola inexistente ou de outro sujeito")
        try:
            methods = conversation_payment_methods(self.channel_ref)
            session = Session.objects.filter(session_key=cart_ref, channel_ref=self.channel_ref).first()
        except Exception:  # noqa: BLE001 - K04: a fonte que falha vira Unknown, nunca o valor velho
            logger.warning("conversational.requirements: fonte falhou", exc_info=True)
            return Unknown(reason="source_failed")
        chosen = str((((session.data if session is not None else None) or {}).get("payment") or {}).get("method") or "")
        missing = [] if chosen in methods or len(methods) <= 1 else ["payment_method"]
        return self._known({"missing": missing, "payment_method": methods}, "shop:channel_config")

    def _hold_minutes(self) -> int:
        """Os termos valem enquanto valem as reservas da sacola (``stock.hold_ttl_minutes`` do canal).

        É a mesma conta que as reservas fazem (``availability._channel_hold_ttl_minutes``,
        com o padrão seguro que o ``ChannelConfig`` declara para ``None``). Sem substituto
        aqui: configuração do canal que não se lê levanta, e a cotação falha fechada
        (trava ``test_instance_runtime_config``).
        """
        from shopman.shop.services.availability import _channel_hold_ttl_minutes

        return max(1, _channel_hold_ttl_minutes(self.channel_ref))

    # ── pedido, cliente, política ────────────────────────────────────────────
    def read_order(self, ctx: TrustedContext, ref: str):
        from shopman.orderman.models import Order

        if not self.ownership.owns_order(ctx, ref):
            raise PortError("object_forbidden", "pedido de outro sujeito")
        try:
            order = Order.objects.filter(ref=ref).first()
        except Exception:  # noqa: BLE001 - K04: a fonte que falha vira Unknown, nunca o valor velho
            logger.warning("conversational.read_order: fonte falhou", exc_info=True)
            return Unknown(reason="source_failed")
        if order is None:
            return Unknown(reason="not_found")
        return self._known({"ref": order.ref, "status": order.status,
                            "total": {"price_minor": int(order.total_q), "currency": CURRENCY}}, "orderman")

    def read_customer(self, ctx: TrustedContext, ref: str):
        """Só a referência do próprio cliente. Nome, telefone e endereço não saem (P17)."""
        if not ref or self.ownership.customer(ctx) != ref:
            raise PortError("object_forbidden", "cliente que não é o sujeito do contexto")
        return self._known({"ref": ref}, "guestman")

    def read_policy(self, ctx: TrustedContext, policy_id: str):
        """A política da casa que o Shopman sabe dizer: hoje, o horário (``hours``)."""
        if policy_id != "hours":
            return Unknown(reason="not_found")
        try:
            from shopman.shop.services.business_calendar import current_business_state

            state = current_business_state()
            value = {"open": bool(state.is_open), "opens": state.opens_at, "closes": state.closes_at}
        except Exception:  # noqa: BLE001 - K04: a fonte que falha vira Unknown, nunca o valor velho
            logger.warning("conversational.read_policy: fonte falhou", exc_info=True)
            return Unknown(reason="source_failed")
        return self._known(value, "shop:business_calendar")

    def knowledge(self, ctx: TrustedContext, query: str) -> tuple:
        return ()

    def scarcity(self, ctx: TrustedContext, ref: str):
        return Unavailable(reason="not_supported")


def _fulfillment(data: dict) -> dict:
    """O recebimento da sacola: o modo e, quando há janela combinada, o começo (e o fim) dela."""
    from django.utils import timezone

    from shopman.shop.services.fulfillment_window import _hour_pair, _window_start

    found: dict = {"mode": str(data.get("fulfillment_type") or "pickup")}
    day, slot = _date_or_none(data.get("delivery_date")), str(data.get("delivery_time_slot") or "")
    start = _window_start({"ref": slot}) if day and slot else None
    if start is not None:
        zone = timezone.get_current_timezone()
        found["window_start"] = instant(datetime.combine(day, start, tzinfo=zone))
        pair = _hour_pair(slot)
        if pair is not None and pair[1] > start:
            found["window_end"] = instant(datetime.combine(day, pair[1], tzinfo=zone))
    return found


def conversation_payment_methods(channel_ref: str) -> list[str]:
    """As formas de pagamento que a conversa oferece: as do canal, sem dinheiro (D-003).

    Régua ÚNICA: o ``requirements`` conta por ela o que falta, as condições dos termos mostram por
    ela a forma única, e o fechamento de hoje (``order_closing._methods``) lista por ela as opções.
    """
    from shopman.shop.config import ChannelConfig

    return [m for m in ChannelConfig.for_channel(channel_ref).payment.available_methods if m != "cash"]


def _fulfillment_conditions(data: dict, channel_ref: str = "") -> list[dict]:
    """O dia e a janela como a casa os guarda (a resposta mostra o rótulo da janela, não a hora crua)."""
    found = []
    day = _date_or_none(data.get("delivery_date"))
    if day:
        found.append({"code": "fulfillment_date", "value": day.isoformat()})
        slot = str(data.get("delivery_time_slot") or "")
        if slot:
            found.append({"code": "fulfillment_window", "value": slot})
    method = str(((data.get("payment") or {}).get("method")) or "")
    if not method and channel_ref:
        # Sem escolha, vale a única forma que a conversa oferece: a MESMA régua do ``requirements``
        # (``conversation_payment_methods``), para que "não falta" e "esta é a forma" nunca discordem.
        methods = conversation_payment_methods(channel_ref)
        method = methods[0] if len(methods) == 1 else ""
    if method:
        # A forma de pagamento escolhida é condição dos termos: o cliente vê como paga antes do "sim".
        found.append({"code": "payment_method", "value": method})
    return found


def _date_or_none(value: Any):
    from datetime import date

    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    number = Decimal(str(value))
    return format(number.normalize(), "f") if number != number.to_integral_value() else str(int(number))


def _date_of(when: str):
    try:
        return datetime.strptime(when, FORMAT).replace(tzinfo=UTC).date()
    except (TypeError, ValueError):
        return None
