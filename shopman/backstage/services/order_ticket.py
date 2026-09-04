"""A filipeta do pedido remoto: uma, ou a semana inteira na bobina.

A padaria trabalha com um painel de parede. O pedido remoto — entrega, retirada
ou encomenda agendada — chega pela tela e some dela; o que a casa quer é
**enxergar a semana pendurada**, e para isso o pedido precisa virar papel antes
de virar dinheiro. Esta é a diferença entre a filipeta e o recibo: o recibo é a
projeção do que já foi vendido e pago, a filipeta é a projeção do que foi
COMBINADO.

Duas coisas moram aqui, e só duas:

1. **Que pedidos entram no lote** (:func:`orders_for_period`) — e a resposta é
   pela DATA COMBINADA, nunca pela data da venda. A encomenda feita hoje para
   sábado é filipeta de sábado.
2. **A janela do lote** (:func:`parse_period`), na forma canônica de
   ``date_from``/``date_to`` desta casa.

A composição dos bytes é do :mod:`shopman.backstage.services.receipt_escpos`
(``order_ticket``) — um dono só para o leiaute do papel, como manda a docstring
de lá.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

#: Sete dias, como no relatório de produção. O lote existe para a pergunta
#: "quero as filipetas da semana"; um mês na bobina é papel no chão.
DEFAULT_WINDOW_DAYS = 7

#: Teto duro do lote. Não é gosto: é a bobina. Passar disto quase sempre é
#: intervalo digitado errado, e o custo do engano é o rolo inteiro no chão — a
#: tela avisa antes, e aqui a porta fecha.
MAX_BATCH = 200

#: Pedido morto não vai para o painel. Mesma exclusão do fechamento do dia
#: (``backstage.services.closing``), pelo mesmo motivo: cancelado e devolvido
#: não são compromisso da casa com ninguém.
EXCLUDED_STATUSES = ("cancelled", "returned")


class BatchTooLarge(Exception):
    """O intervalo pedido rende mais filipetas do que o teto do lote."""

    def __init__(self, count: int):
        self.count = count
        super().__init__(
            f"O intervalo tem {count} pedidos e o lote imprime no máximo {MAX_BATCH}. "
            "Escolha um intervalo menor."
        )


def parse_period(raw_from, raw_to, *, today: date | None = None) -> tuple[date, date]:
    """A janela do lote, na forma canônica de ``date_from``/``date_to``.

    Mesma régua de ``backstage.api._production_filters.report_filters``: data
    ilegível cai no padrão em vez de estourar, e intervalo invertido é TROCADO
    em vez de recusado — quem digitou as duas datas ao contrário quis o mesmo
    intervalo, e um 400 aqui só faria a tela pedir de novo.

    ⚠️ O padrão é a semana QUE VEM, e essa é a única divergência deliberada do
    relatório de produção (que olha 7 dias para trás). O relatório pergunta o
    que aconteceu; o painel de filipetas pergunta o que a casa prometeu. Abrir
    a tela mostrando a semana passada seria oferecer o lote errado por padrão.
    """
    from django.utils import timezone

    hoje = today or timezone.localdate()
    date_from = _coerce_iso_date(raw_from, fallback=hoje)
    date_to = _coerce_iso_date(raw_to, fallback=hoje + timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _coerce_iso_date(raw, *, fallback: date) -> date:
    try:
        return date.fromisoformat(str(raw or "").strip())
    except ValueError:
        return fallback


def commitment_of(order) -> date:
    """A data que o pedido representa no painel.

    ``delivery_date`` quando existe; senão o dia em que o pedido foi feito. É a
    MESMA leitura do fechamento do dia (``closing._sold_vs_available``), e
    manter as duas iguais é o que impede a encomenda de sábado de aparecer no
    painel de hoje numa tela e no de sábado noutra.
    """
    from django.utils import timezone

    from shopman.shop.services.order_helpers import get_commitment_date

    return get_commitment_date(order) or timezone.localtime(order.created_at).date()


def _window_sort_key(order):
    """Ordem do painel: dia, hora combinada, e a hora do pedido para desempatar.

    O pedido sem janela combinada vai para o FIM do dia dele (``time.max``), não
    para o começo: ausência de hora é "não combinado", e pôr o não combinado
    antes das 07h faria o painel abrir o dia com o pedido que ninguém marcou.
    """
    from datetime import time

    from shopman.shop.services.fulfillment_window import window_start_time

    inicio = window_start_time((order.data or {}).get("delivery_time_slot"))
    return (commitment_of(order), inicio or time.max, order.created_at)


def orders_for_period(date_from: date, date_to: date) -> list:
    """Os pedidos com compromisso no intervalo, na ordem em que vão para a parede.

    A consulta é a do fechamento do dia, esticada para um intervalo: ou o pedido
    foi FEITO na janela, ou ele foi COMBINADO para a janela
    (``data__delivery_date``). O SQL é o filtro grosso — quem decide de verdade
    é :func:`commitment_of` em Python, porque a data combinada é uma leitura
    (chave ausente ⇒ vale a data da venda) e não uma coluna.
    """
    from django.db.models import Q
    from shopman.orderman.models import Order

    # ⚠️ UM filtro com dois ``Q``, não a união de dois querysets: `|` entre
    # querysets pede `.distinct()`, e `.distinct()` num model com ordenação
    # default arrasta a coluna de ordenação para o SELECT e deixa de deduplicar
    # o que se esperava. A forma abaixo é a do fechamento do dia.
    candidatos = (
        Order.objects.filter(
            Q(
                data__delivery_date__gte=date_from.isoformat(),
                data__delivery_date__lte=date_to.isoformat(),
            )
            | Q(created_at__date__gte=date_from, created_at__date__lte=date_to)
        )
        .exclude(status__in=EXCLUDED_STATUSES)
        .prefetch_related("items")
    )

    dentro = [o for o in candidatos if date_from <= commitment_of(o) <= date_to]
    return sorted(dentro, key=_window_sort_key)


def shop_display_name() -> str:
    """O nome que sai no alto do papel — o mesmo que o recibo de venda usa."""
    from shopman.shop.models import Shop

    shop = Shop.objects.first()
    if shop is None:
        return ""
    return str(getattr(shop, "brand_name", "") or getattr(shop, "name", "") or "")


def ticket_bytes(order, *, shop_name: str = "", reprint: bool = False) -> bytes:
    """Os bytes de UMA filipeta, com o QR do acompanhamento já resolvido.

    O QR aponta para o acompanhamento do pedido na LOJA e não para uma tela de
    operador: a filipeta pode acompanhar a sacola, e no pedido de link em aberto
    o acompanhamento é a MESMA página onde se paga (ver
    ``shop.services.notification`` — PAYMENT-TRACKING-MERGE). Deployment sem base
    de loja configurada imprime sem QR, nunca com um QR mudo.
    """
    from shopman.backstage.services.receipt_escpos import order_ticket
    from shopman.shop.services.storefront_links import order_tracking_url, storefront_base_url

    tracking_url = order_tracking_url(order.ref) if storefront_base_url() else ""
    return order_ticket(
        order,
        shop_name=shop_name or shop_display_name(),
        tracking_url=tracking_url,
        reprint=reprint,
    )


def preview_rows(orders: list) -> list[dict]:
    """A lista que a tela mostra ANTES de mandar imprimir.

    Ninguém quer descobrir que pediu 200 filipetas depois de a bobina começar a
    andar. Estas linhas existem para a conferência do intervalo — quem, quando,
    entrega ou retirada — e por isso NÃO carimbam nada: olhar não é imprimir.
    """
    from shopman.shop.services.fulfillment_window import window_label
    from shopman.shop.services.order_helpers import get_fulfillment_type

    linhas = []
    for order in orders:
        data = order.data or {}
        customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
        is_delivery = get_fulfillment_type(order) == "delivery"
        linhas.append({
            "ref": order.ref,
            "customer_name": str(customer.get("name") or "").strip(),
            "commitment_date": commitment_of(order).isoformat(),
            "window_label": window_label(data.get("delivery_time_slot")),
            "fulfillment_type": "delivery" if is_delivery else "pickup",
            "fulfillment_label": "Entrega" if is_delivery else "Retirada",
            "status": order.status,
            "already_printed": bool(data.get("ticket_printed_at")),
        })
    return linhas
