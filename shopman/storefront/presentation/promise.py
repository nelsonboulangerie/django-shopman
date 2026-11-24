"""A promessa de quando: UM fato, escrito no servidor, para toda tela da loja.

Antes, cinco telas respondiam "quando fica pronto?" cada uma do seu jeito: o
cardápio só com o selo "Lista de espera", o produto com uma frase montada no
aparelho a partir do estado da loja em cache (que dizia "Disponível hoje" com a
casa fechada), a sacola com "Previsto para amanhã" só quando havia fornada
futura, o checkout com "sai amanhã" calculado no aparelho e "sai às 15:00" de
outro serviço (plano EXCELENCIA-STOREFRONT, seção 4.1, P1-01, P1-02, P2-12).

Aqui existe uma função só, :func:`promise_for`, e o card do cardápio, o detalhe
do produto e a linha da sacola leem dela. O dia e a hora vêm de
``shop/projections/ready_promise`` (:func:`ready_window`), que lê os mesmos
serviços que o checkout e o envio do pedido conferem: o dia da fornada
(``waitlist``), a hora de pronto (``product_readiness``) e a grade de horários
(``fulfillment_window``). O que a tela promete é o que o checkout oferece, e é o
mesmo dia que vai ao Google no ``pickupSla`` de cada item. Aqui só se escreve a
frase.

Três tipos (``kind``):

- ``ready`` (pronto): há pronto hoje e um horário hoje já serve. "Disponível
  agora". É o estado padrão, e a tela do produto não o diz: só fala quando
  difere (dono, 24/11/2026).
- ``batch`` (fornada): o item espera uma fornada, hoje mais tarde ou num dia
  planejado. "Disponível a partir das 15h", "Disponível amanhã, terça, a partir
  das 15h".
- ``preorder`` (encomenda): o item seria de hoje, mas hoje já não há horário
  (casa fechada, corte do dia, dia sem expediente), ou o dia da fornada é
  fechado. Fica para o próximo dia com horário, e a frase diz qual.

Sem promessa (``None``): item indisponível ou pausado, prontidão que não pôde
ser apurada (o checkout recusa todo horário nesse caso), fornada que não se
achou, ou nenhum dia com horário na busca. Nunca "hoje" por falta de dado.

Sobre o PRODUTO a loja fala de disponibilidade, nunca de prontidão: "Disponível
amanhã", não "Fica pronto amanhã" (dono, 24/11/2026; ``docs/reference/
suite-vocabulary.md``). "Fica pronto" segue só na frase sobre o PEDIDO.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta

from shopman.utils.formatting import format_clock

from shopman.shop.projections.ready_promise import PromiseFacts, ready_window

KIND_READY = "ready"
KIND_BATCH = "batch"
KIND_PREORDER = "preorder"

_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@dataclass(frozen=True)
class PromiseProjection:
    """Quando o item está disponível, já escrito para a cliente.

    ``date`` é o dia (ISO) do primeiro horário em que a casa entrega o item;
    ``ready_at`` é a hora desse horário (``"HH:MM"``), a mesma que o checkout
    oferece como a mais cedo; ``day_label`` é o dia como a frase o diz ("hoje",
    "amanhã, terça", "quinta, 19/11"), para o botão "Encomendar para amanhã"
    não ter de recalcular; ``text`` é a frase inteira.
    """

    kind: str
    date: str
    ready_at: str
    day_label: str
    text: str


def promise_for(
    sku: str,
    facts: PromiseFacts,
    *,
    orderable: bool,
    planned_for: date | None = None,
    made_to_order: bool = False,
) -> PromiseProjection | None:
    """A promessa de ``sku``, ou ``None`` quando não há o que prometer.

    ``orderable`` é a decisão de venda que a própria tela já tomou (o botão
    Adicionar acende). ``planned_for`` é o dia da fornada que uma linha da
    sacola já reservou: ali a data é fato da reserva, não estimativa.
    """
    window = ready_window(sku, facts, orderable=orderable, planned_for=planned_for)
    if window is None:
        return None
    today = facts.today
    target, day, start, ready_at = window.target, window.day, window.start, window.ready_at

    day_label = _day_label(day, today=today)
    if day == today:
        now_clock = _local_clock(facts.now)
        if target == today and (ready_at is None or ready_at <= now_clock):
            text = "Preparado na hora" if made_to_order else "Disponível agora"
            return PromiseProjection(KIND_READY, day.isoformat(), _clock(start), day_label, text)
        return PromiseProjection(
            KIND_BATCH, day.isoformat(), _clock(start), day_label, f"Disponível a partir das {_hour(start)}"
        )

    kind = KIND_BATCH if day == target and target != today else KIND_PREORDER
    text = f"Disponível {day_label}, a partir das {_hour(start)}"
    return PromiseProjection(kind, day.isoformat(), _clock(start), day_label, text)


def _local_clock(value) -> time:
    from django.utils import timezone

    local = timezone.localtime(value) if timezone.is_aware(value) else value
    return local.time().replace(second=0, microsecond=0)


def _clock(value: time) -> str:
    return value.strftime("%H:%M")  # hora-ok: contrato HH:MM de ready_at, lido por código


def _hour(value: time) -> str:
    """A hora da frase pelo formatador da casa: ``15:00`` → ``15h``; ``15:30`` → ``15h30``."""
    return format_clock(value)


def _day_label(day: date, *, today: date) -> str:
    weekday = _WEEKDAYS[day.weekday()]
    if day == today:
        return "hoje"
    if day == today + timedelta(days=1):
        return f"amanhã, {weekday}"
    return f"{weekday}, {day:%d/%m}"


# ── Dá para pedir? (OC-04) ─────────────────────────────────────────────

ORDERING_NOW = "now"
ORDERING_PREORDER = "preorder"
ORDERING_NONE = "none"


@dataclass(frozen=True)
class OrderingProjection:
    """Se a loja aceita pedido agora, e para quando, lido das promessas do cardápio.

    Não é regra nova: é o resumo das promessas que o card, o produto e a sacola
    já dizem (:func:`promise_for`). A frase da home e da sacola sai daqui, e por
    isso nunca oferece o que nenhum card oferece (U1 do laudo da Etapa II: às
    22h, com 0 de 31 itens podendo ir à sacola, a home dizia "Você já pode
    finalizar o pedido").

    - ``now``: ao menos um item tem horário HOJE (pronto, fornada de hoje, ou
      casa fechada que ainda abre hoje);
    - ``preorder``: há item para pedir, mas o primeiro horário é de outro dia;
      ``next_date`` é esse dia e ``day_label`` é como a frase o diz ("amanhã,
      terça", "quinta, 19/11");
    - ``none``: nenhum item do cardápio tem promessa. Ninguém consegue pôr nada
      na sacola, e a tela não oferece finalização.
    """

    state: str
    next_date: str | None = None
    day_label: str = ""


def ordering_from_promises(promises, *, today: date) -> OrderingProjection:
    """O resumo de um conjunto de promessas: o dia mais cedo em que algo se entrega.

    ``promises`` são as do cardápio inteiro (``None`` para o item sem promessa).
    O estado sai só das datas: o dia mais cedo é hoje (``now``), outro dia
    (``preorder``) ou não há nenhum (``none``).
    """
    days = sorted({p.date for p in promises if p is not None})
    if not days:
        return OrderingProjection(ORDERING_NONE)
    earliest = date.fromisoformat(days[0])
    state = ORDERING_NOW if earliest <= today else ORDERING_PREORDER
    return OrderingProjection(state, earliest.isoformat(), _day_label(earliest, today=today))
