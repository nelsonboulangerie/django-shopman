"""O corte do atendimento — até quando o pedido remoto precisa estar pago.

O link de pagamento vale ``min(agora + janela do canal, corte do atendimento)``
(``adapters/_payment_link``). A janela é configuração; o corte é o que a casa
já sabe do PEDIDO, e por isso mora aqui, ao lado de ``order_helpers``, e não no
adapter — o adapter recebe o instante pronto (``config["link_expires_by"]``) e
não precisa conhecer pedido nem calendário.

O corte é o momento em que a casa precisa do dinheiro para cumprir:

1. **a janela combinada**, quando existe — o início do slot de retirada ou da
   janela de entrega (``Order.data["delivery_time_slot"]``, nos dois
   vocabulários: o canônico ``"slot-09"`` da encomenda e a meia hora
   ``"14:00-14:30"`` do pedido de hoje);
2. senão, **o fechamento da loja no dia do compromisso**
   (``Order.data["delivery_date"]`` + ``Shop.opening_hours``);
3. sem compromisso nenhum (retirada "agora"), **o fechamento de hoje**.

Sem expediente conhecido para o dia (loja sem horário cadastrado, dia sem
escala) não há corte: vale só a janela do canal. Não se inventa fechamento.

Corte já passado ou a menos de 30 min (venda de link às 17h50 para retirar às
18h) NÃO é tratado aqui: o adapter prende o instante ao piso de 30 min do
Stripe, e a casa aceita esse caso raro em vez de recusar a venda com o cliente
ao telefone.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from shopman.shop.services.order_helpers import get_commitment_date

logger = logging.getLogger(__name__)


def service_cutoff(order, *, now: datetime | None = None, shop=None) -> datetime | None:
    """O instante (tz-aware) em que o pedido precisa estar pago, ou ``None``.

    Nunca levanta: um calendário quebrado não pode derrubar a venda. Na dúvida
    devolve ``None`` — e aí o link vale a janela do canal, que já é curta.
    """
    try:
        return _service_cutoff(order, now=now, shop=shop)
    except Exception:
        logger.warning("payment_deadline: could not resolve the service cutoff", exc_info=True)
        return None


def _service_cutoff(order, *, now: datetime | None, shop) -> datetime | None:
    from shopman.shop.services import business_calendar

    shop = _load_shop(shop)
    tz = _shop_timezone(shop)
    local_now = timezone.localtime(now or timezone.now(), timezone=tz)
    data = getattr(order, "data", None) or {}

    day = get_commitment_date(data) or local_now.date()

    starts_at = _window_start_for(str(data.get("delivery_time_slot") or "").strip())
    if starts_at is not None:
        return _at(day, starts_at, tz)

    window = business_calendar.selling_hours_for(day, shop=shop)
    if window is None:
        return None
    _opens_at, closes_at = window
    return _at(day, closes_at, tz)


def _window_start_for(slot_ref: str) -> time | None:
    """A hora em que a janela combinada COMEÇA, nos dois vocabulários do slot.

    O canônico (``"slot-09"``) não carrega hora no nome: quem sabe que ele
    começa às 09:00 é a configuração da casa (``canonical_slots``). A meia hora
    (``"14:00-14:30"``) se lê sozinha — inclusive num pedido antigo, depois de
    a casa mudar o expediente.
    """
    if not slot_ref:
        return None
    from shopman.shop.services.fulfillment_window import _window_start, canonical_slots

    known = next((slot for slot in canonical_slots() if slot.get("ref") == slot_ref), None)
    return _window_start(known or {"ref": slot_ref})


def _at(day: date, clock: time, tz) -> datetime:
    return datetime.combine(day, clock, tzinfo=tz)


def _load_shop(shop):
    if shop is not None:
        return shop
    from shopman.shop.models import Shop

    return Shop.load()


def _shop_timezone(shop):
    tz_name = getattr(shop, "timezone", "") or timezone.get_current_timezone_name()
    try:
        return ZoneInfo(str(tz_name))
    except (ValueError, ZoneInfoNotFoundError):
        return timezone.get_current_timezone()
