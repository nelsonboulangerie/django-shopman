"""Os read models dos pedidos do operador: o quadro do Gestor e o detalhe.

``build_two_zone_queue`` monta o quadro (Novos, Em preparo, Prontos e a lista
de Encomendas), um ``OrderCardProjection`` por pedido; ``build_operator_order``
monta o detalhe de um pedido, o mesmo contrato para o Gestor e para o PDV.
Projeções imutáveis, prontas para a tela.

Nunca importa de ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple
from urllib.parse import quote

from django.db.models import Q
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem
from shopman.utils.formatting import format_clock, format_local
from shopman.utils.monetary import format_money
from shopman.utils.phone import normalize_phone

from shopman.backstage.presentation.status import (
    order_status_label,
    payment_method_label,
    payment_status_label,
)
from shopman.backstage.projections import ifood as ifood_projection
from shopman.backstage.projections import order_pending, order_pricing, order_promise
from shopman.backstage.projections.ifood_handshake import IFoodNegotiationProjection, negotiations
from shopman.backstage.projections.notification_receipts import (
    NotificationReceiptProjection,
    build_notification_receipts,
)
from shopman.backstage.projections.order_attention import (
    AcceptanceTimer,
    QueueAwarenessProjection,
    acceptance_timer_goal,
    build_queue_awareness,
    card_attention,
)
from shopman.backstage.projections.preorders import CounterOrderProjection
from shopman.backstage.services import order_danfe
from shopman.backstage.services.courier_reminder import REMINDER_STATUSES, CourierReminderProjection, courier_reminder
from shopman.shop.projections.types import (
    Action,
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.shop.protocols import RideState
from shopman.shop.services import operator_orders, order_composition, volume_check
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.kitchen_eta import PrepExpectation, prep_expectation, ready_eta
from shopman.shop.services.order_helpers import get_commitment_date, get_fulfillment_type

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

ACTIVE_STATUSES = ("new", "accepted", "preparing", "ready", "dispatched", "delivered")

_PAYMENT_COMPLETE = frozenset({"captured", "paid"})
_OFFLINE_METHODS = frozenset({"cash", "credit", "debit", "external"})
# Um tender de balcão nasce ``received`` ao ser liquidado no PDV; o dinheiro na
# entrega (COD) nasce ``pending`` e vira ``received`` quando o entregador acerta.
# Ver shop/services/pos.py (status do tender) e operator_orders.settle_delivery_cash.
_SETTLED_TENDER_STATUSES = frozenset({"received", "captured", "paid", ""})

CHANNEL_ICONS: dict[str, str] = {
    "web": "language",
    "whatsapp": "chat",
    "ifood": "fastfood",
    "pos": "storefront",
}
_DEFAULT_CHANNEL_ICON = "shopping_bag"

# Pedido de teste da homologação do iFood: ele entra pelo polling como qualquer
# outro e precisa ser aceito e concluído (é isso que o iFood valida do lado
# dele), mas nada na casa se move por causa dele. Até hoje a única pista na tela
# era o nome do item vir "NÃO ENTREGAR" — defesa humana em horário de movimento.
# O rótulo é do CRACHÁ (cabe na linha de selos do card); o aviso é a frase
# inteira, que diz o que fazer e o que a casa desligou.
TEST_ORDER_LABEL = "Pedido de teste do iFood"
TEST_ORDER_NOTICE = (
    "Pedido de teste do iFood: avance as etapas normalmente, mas não produza "
    "nem entregue nada. Ele não reserva estoque, não vai para a cozinha, não "
    "emite nota fiscal e não avisa o cliente."
)


#: O rótulo do pagamento capturado por SIMULAÇÃO (``payment_mock``, Efí
#: homologação, Stripe em chave de teste). "Pago" ali era rótulo que mente: o
#: operador entregava confiando num dinheiro que nunca entrou.
SIMULATED_PAYMENT_LABEL = "Pagamento simulado, sem dinheiro"


def _order_payment_status_label(order, payment_status: str) -> str:
    """O rótulo do pagamento no card e no detalhe — uma função para os dois."""
    if order.channel_ref == "ifood":
        return {"paid": "Pago online", "pending": "Pagamento pendente", "unknown": "Pagamento não informado"}.get(
            payment_status, "Pagamento não informado"
        )
    from shopman.shop.services.payment_provenance import is_simulated_order_payment

    if payment_status in _PAYMENT_COMPLETE and is_simulated_order_payment(order):
        return SIMULATED_PAYMENT_LABEL
    if _card_capture_failed(order, payment_status):
        return CARD_CAPTURE_FAILED_LABEL
    if payment_status not in _PAYMENT_COMPLETE and payment_svc.awaiting_repayment(order) is not None:
        return AWAITING_REPAYMENT_LABEL
    if (order.data or {}).get("no_show"):
        # Pedido não retirado (WP-G11): só parte do valor volta. "Estornado"
        # sozinho mentiria sobre o que ficou com a loja.
        from shopman.backstage.projections.order_no_show import payment_outcome_label

        outcome = payment_outcome_label(order)
        if outcome:
            return outcome
    return payment_status_label(payment_status)


def _card_capture_failed(order, payment_status: str) -> bool:
    """O cartão está autorizado, mas a cobrança no aceite foi recusada.

    Um estado só (beta 06/11): a pílula, o bloqueio do avanço e o aviso da ficha
    dizem "Cobrança recusada", em vez de "Autorizado" ao lado de "Aguardando
    pagamento · link gerado".
    """
    if str(payment_status or "").lower() != "authorized":
        return False
    return payment_svc.capture_failure(order) is not None


#: Quem registra dinheiro fora da cobrança do pedido: o Pix que caiu numa
#: cobrança já encerrada, e o pagamento digital que chegou depois de o balcão
#: receber (``gateway_data.booked_by``).
_OUTSIDE_CHARGE_BOOKERS = frozenset({"pix_confirmation", "counter_takeover"})


def _money_outside_the_charge_label(order, payment_status: str) -> str:
    """O dinheiro que entrou num intent à parte, quando a cobrança do pedido morreu.

    ``get_payment_status`` lê só ``payment.intent_ref``: com a cobrança cancelada e
    o Pix registrado à parte (e estornado), o detalhe dizia "Pix · Cancelado" para
    um dinheiro que entrou e voltou (beta 06/11, PIXEXP-03). Vazio quando a
    cobrança do pedido responde por si (paga, pendente) ou não há nada à parte.
    """
    if order.channel_ref == "ifood" or payment_status in _PAYMENT_COMPLETE:
        return ""
    from shopman.payman import PaymentService

    intent_ref = str(((order.data or {}).get("payment") or {}).get("intent_ref") or "")
    captured_q = refunded_q = 0
    for intent in PaymentService.get_by_order(order.ref).filter(status__in=("captured", "refunded")):
        if intent.ref == intent_ref or (intent.gateway_data or {}).get("booked_by") not in _OUTSIDE_CHARGE_BOOKERS:
            continue
        captured_q += PaymentService.captured_total(intent.ref)
        refunded_q += PaymentService.refunded_total(intent.ref)
    if captured_q <= 0:
        return ""
    # A tela já põe o meio na frente ("Pix · R$ 22,00 recebido e estornado").
    if refunded_q >= captured_q:
        return f"{_money(captured_q)} recebido e estornado"
    if refunded_q > 0:
        return f"{_money(captured_q)} recebido, {_money(refunded_q)} estornado"
    return f"{_money(captured_q)} recebido fora da cobrança"


def _test_order_label(order) -> str:
    """O crachá de pedido de teste, ou vazio quando o pedido é de verdade."""
    from shopman.shop.services.order_helpers import is_test_order

    return TEST_ORDER_LABEL if is_test_order(order) else ""


def _test_order_notice(order) -> str:
    """A frase inteira do pedido de teste, ou vazia quando o pedido é de verdade."""
    from shopman.shop.services.order_helpers import is_test_order

    return TEST_ORDER_NOTICE if is_test_order(order) else ""


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AwaitingWorkOrderProjection:
    """A compact production dependency shown on order cards and detail."""

    ref: str
    status: str
    status_label: str
    output_sku: str
    recipe_name: str
    planned_qty: str
    finished_qty: str
    progress_pct: int


@dataclass(frozen=True)
class CancelReasonProjection:
    """Um motivo de recusar ou cancelar da lista única (``shop/services/cancel_reasons.py``).

    ``key`` é o que a tela devolve no recusar/cancelar; ``label`` é o que o
    operador escolhe; ``customer_text`` é a frase que o cliente vai ler, mostrada
    na hora da escolha para o operador saber o que sai. ``offered_on_ifood``: o
    motivo aparece no pedido do iFood (o quadro mistura canais e filtra por ele).
    """

    key: str
    label: str
    customer_text: str
    offered_on_ifood: bool


@dataclass(frozen=True)
class EquipmentOptionProjection:
    """Uma maquininha que o entregador pode levar no despacho (ref do canal + rótulo)."""

    ref: str
    label: str
    enabled: bool = True
    reason: str = ""
    # Pedido com o qual a maquininha está na rua (vazio quando livre): o despacho
    # diz onde ela está e oferece "Entregador voltou" daquele pedido.
    order_ref: str = ""


@dataclass(frozen=True)
class EquipmentOutProjection:
    """Onde está a maquininha agora: saiu com o entregador deste pedido e não voltou."""

    ref: str
    label: str
    order_ref: str
    customer_name: str
    out_at: str
    actions: tuple[Action, ...] = ()
    identified: bool = False
    #: Os outros pedidos que levam a MESMA maquininha (corrida ou saída com vários).
    shared_with: tuple[str, ...] = ()


@dataclass(frozen=True)
class RideCandidateProjection:
    """Uma entrega pronta que pode entrar numa corrida da TaOn com outras.

    O que a chamada pergunta dela (``partner_custody_asks``):
    ``change_out_suggested_q`` é o troco sugerido da gaveta (zero: não
    pergunta) e ``needs_machine`` diz que a corrida leva a maquininha.
    """

    ref: str
    change_out_suggested_q: int = 0
    needs_machine: bool = False
    #: "Pedido B12 · Maria": quem é, como o balcão fala.
    label: str = ""
    #: Para onde vai, curto: o bairro (ou o endereço, sem bairro).
    place: str = ""
    #: "Pronto" ou "Em preparo": a corrida pode sair antes do pronto.
    stage: str = ""
    #: "Troco para R$ 100,00": a frase do troco do card, quando há.
    change_label: str = ""


@dataclass(frozen=True)
class UndoProjection:
    """O que o sistema fez (ou o operador tocou) e ainda pode ser desfeito.

    ``kind``: ``"auto_ready"`` (a Cozinha concluiu e o pedido foi a pronto
    sozinho) ou ``"handoff"`` (Entregar/Despachar tocado, gravação na janela).
    ``undo_until_iso`` vazio quando a janela fechou: o fato fica à vista, sem o
    gesto. ``action_ref`` é a ação de ``actions`` que desfaz. ``held_effect``
    diz o que espera a janela, na voz do card; ``already_out`` diz o que NÃO
    espera e já saiu (o ``readyToPickup`` do iFood: ver ``order_undo``), para o
    operador saber que desfazer não alcança aquilo. ``undo_since_iso`` é o
    começo da janela: com ``undo_until_iso``, dá o tamanho dela, para o botão
    Desfazer mostrar quanto ainda resta mesmo montado no meio da janela.
    """

    kind: str
    label: str
    detail: str
    undo_until_iso: str
    action_ref: str
    held_effect: str = ""
    already_out: str = ""
    undo_since_iso: str = ""


#: A porta do toque que fechou a última estação (``auto_ready["via"]``) → o rótulo
#: do pronto e quem o fez, para o detalhe. "Pronto · automático" valia para todo
#: pronto, até o que alguém marcou à mão na Saída (beta 06/11).
_READY_ORIGIN = {
    "station": ("Pronto pela Cozinha", "Cozinha concluiu"),
    "exit": ("Pronto marcado na Saída", "Marcado na Saída"),
    "pos": ("Pronto marcado no PDV", "Marcado no PDV"),
    "scanner": ("Pronto marcado pelo leitor", "Marcado pelo leitor de código"),
}


def _undo_projection(order: Order) -> UndoProjection | None:
    """O bloco "o sistema fez · desfazer" do card e do detalhe, ou ``None``."""
    from shopman.shop.services import order_undo

    pending = order_undo.pending_handoff(order)
    if pending:
        window_open = order_undo.handoff_window_open(order)
        return UndoProjection(
            kind="handoff",
            label=order_undo.handoff_label(pending),
            detail="O aviso ao cliente sai quando o prazo acabar." if window_open else "Gravando a saída.",
            undo_until_iso=str(pending.get("commit_at") or "") if window_open else "",
            action_ref="undo-handoff",
            held_effect="Aviso ao cliente e fim do pedido" if pending.get("to_status") != Order.Status.DISPATCHED else "Aviso ao cliente e saída do pedido",
            undo_since_iso=str(pending.get("requested_at") or "") if window_open else "",
        )
    record = order_undo.auto_ready_record(order)
    if record and order.status == Order.Status.READY:
        hold = order_undo.ready_hold(order)
        clock = order_undo._clock(record.get("at"))
        label, done_by = _READY_ORIGIN.get(str(record.get("via") or "station"), _READY_ORIGIN["station"])
        return UndoProjection(
            kind="auto_ready",
            label=label,
            detail=f"{done_by} às {clock}" if clock else done_by,
            undo_until_iso=str(hold.get("undo_until") or "") if hold else "",
            action_ref="undo-ready",
            held_effect="Aviso de pronto ao cliente" if hold else "",
            already_out="iFood já avisado" if order.channel_ref == "ifood" else "",
            undo_since_iso=str(record.get("at") or "") if hold else "",
        )
    return None


def undo_block_allows_advance(order: Order) -> bool:
    """Com a saída pedida (janela aberta ou gravando), avançar não está à mão."""
    from shopman.shop.services import order_undo

    return not order_undo.pending_handoff(order)


@dataclass(frozen=True)
class KitchenStationProjection:
    """Uma estação da Cozinha neste pedido, vista do Gestor (SUITE-UX §15).

    A mesma régua da Saída da Cozinha (``projections.kds.exit_station_chips``):
    quem falta, o papel da estação sem tela, o "Pronto" que a Saída dava por
    ela e o ticket que volta à cozinha.
    """

    station_ref: str
    station_name: str
    #: A estação recebe o pedido impresso (não tem tela).
    prints: bool
    #: "pending" · "in_progress" · "done"
    state: str
    #: "na fila" · "em preparo" · "pronto"
    state_label: str
    paper_label: str = ""
    paper_failed: bool = False
    #: Itens desta estação retirados do pedido depois do disparo.
    cancelled_items: int = 0
    #: "Pronto de Lanches": a estação sem tela terminou a parte dela.
    can_mark_ready: bool = False
    #: "Voltar para Lanches": o ticket concluído que volta à cozinha.
    recall_ticket_pk: int | None = None
    #: O que foi para esta estação ("2x Croissant"): conferir se chegou onde devia.
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class KitchenProgressProjection:
    """Em que pé a Cozinha está com o pedido: o progresso por estação no cartão."""

    #: Os gestos da estação (``kds/expedition/<pk>/printed-stations/…``) são por pedido.
    order_pk: int
    stations: tuple[KitchenStationProjection, ...]
    #: "Falta Café" · "Faltam Café e Lanches" · "" quando todas terminaram.
    missing_label: str = ""


@dataclass(frozen=True)
class OrderCardProjection:
    """O cartão de um pedido no quadro do Gestor (Painel, Fila, Tabela, Encomendas).

    O contrato leva só o que alguém lê: cada campo tem leitor declarado em
    ``backstage/tests/test_order_card_contract_readers.py``, e campo novo sem
    leitor reprova. O que é só do detalhe mora em ``OperatorOrderProjection``.
    """

    ref: str
    status: str
    actions: tuple[Action, ...]
    status_label: str
    channel_ref: str
    # O nome do canal como a loja o chama ("Loja online", "PDV"): a mesma régua
    # do detalhe (``_channel_name``). A tela não deriva nome de canal.
    channel_name: str
    channel_icon: str
    customer_name: str
    created_at_iso: str
    server_now_iso: str
    elapsed_seconds: int
    timer_class: str  # "timer-ok", "timer-warning", "timer-urgent", "timer-muted"
    items_summary: str
    items_count: int
    total_display: str
    fulfillment_label: str
    fulfillment_type: str  # "delivery" | "pickup" — eixo de triagem no board
    # Para onde vai o pedido. Vazio na retirada. Sem ele o Gestor não tinha
    # endereço em tela nenhuma, e quem despacha ficava sem destino. As instruções
    # de entrega ("portão azul") moram no detalhe.
    delivery_address: str
    can_confirm: bool
    can_advance: bool
    next_status: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    payment_status_label: str
    payment_pending: bool
    # Tom do pill de pagamento. Três estados, não dois: dinheiro/externo não é
    # "pago" nem "devendo" — é cobrança fora do site, e pintá-lo de verde diria
    # que entrou dinheiro que não entrou.
    payment_tone: str  # "warning" (esperando) | "success" (pago) | "neutral" (offline)
    # Por que não dá para avançar agora. O botão sumia quando bloqueado, e o
    # operador ficava sem saber se faltava algo ou se a tela tinha falhado.
    advance_block_label: str
    advance_block_reason: str
    can_settle_delivery_cash: bool
    # A pílula da NFC-e (``_FISCAL_PILL``): o cartão só reage a ``failed``.
    fiscal_status: str
    # A observação do CLIENTE no checkout (``order_notes``). O card só INDICA
    # presença (selo compacto); o conteúdo, e a nota do operador
    # (``kitchen_note``), moram no detalhe, cada nota com seu nome.
    has_customer_note: bool
    # Presente: quem embala precisa saber sem abrir o detalhe. O destinatário é
    # opcional na retirada (gift.py) — o selo distingue "entregar a alguém" de
    # "só embalar", e o nome/recado ficam no detalhe.
    is_gift: bool
    gift_has_recipient: bool
    assigned_operator: str
    awaiting_work_orders: tuple[AwaitingWorkOrderProjection, ...]
    # Prazo da confirmação otimista (só em pedidos NEW com timer agendado). Vazio
    # quando não há timer (confirmação manual, fora de NEW). O gestor renderiza um
    # countdown para o cliente não ficar no escuro sobre o prazo.
    confirmation_deadline_iso: str = ""
    confirmation_action: str = ""  # "confirm" | "cancel" — ação do directive ao vencer
    # Cartão da loja online autorizado e esperando aceite: quando a reserva vence
    # no Stripe (ISO). Vazio fora de NEW ou sem autorização de pé. O card mostra o
    # aviso com Aceitar/Recusar (``services/card_authorization``).
    card_authorization_expires_iso: str = ""
    # Número que o CANAL deu ao pedido (``displayId`` do iFood). Desde que o ref
    # adota esse número (``IFOOD-260919-4994``), o card já o mostra em destaque e
    # este campo fica VAZIO — ele só se preenche quando o ref divergiu: colisão no
    # dia, ou pedido criado antes dessa mudança. Aí o card exibe, e a busca acha.
    channel_display_id: str = ""
    # Corrida externa: o estado dela, na palavra do operador ("Saiu para
    # entrega"). Vazio quando não há corrida registrada no pedido.
    courier_status_label: str = ""
    # Encomenda (WP-D): pedido com data futura. ``commitment_date`` ISO +
    # display curto ("amanhã", "sáb, 19/07") para o badge do card. Um pedido
    # deixa de ser encomenda no dia (mesma régua do lifecycle).
    is_preorder: bool = False
    commitment_date: str = ""
    commitment_date_display: str = ""
    # O combinado, na frase do detalhe (``_schedule``): "Amanhã · A partir das
    # 15h", "Hoje · 14h às 14h30", "Era para ontem · A partir das 15h". Vazio
    # quando não há o que dizer (o pedido de agora, ou o combinado já cumprido).
    # ``schedule_state``: ``future`` | ``today`` | ``overdue`` | "". O cartão, a
    # Fila, a Tabela e o sino leem daqui, e só daqui: aceitar uma encomenda sem
    # ver o dia e a hora era prometer às cegas.
    schedule_label: str = ""
    schedule_state: str = ""
    # A hora da Cozinha (WP-G02). A encomenda do dia espera a hora dela
    # (``lifecycle.preorder_activation_at``: combinado − preparo − antecedência)
    # antes de pedir qualquer gesto. Enquanto espera, ``kitchen_release_at_iso``
    # diz quando chega e ``kitchen_release_label`` é a frase pronta ("Vai para a
    # Cozinha às 16h15"); o "Iniciar preparo" vira "Adiantar", secundário, e o
    # card não entra em ``attention``. Depois que chegou, ``kitchen_released_at_iso``
    # guarda o instante, e é dele que o relógio conta (``clock_since_iso``).
    kitchen_release_at_iso: str = ""
    kitchen_release_label: str = ""
    kitchen_released_at_iso: str = ""
    # De quando o relógio do pedido conta: a chegada à Cozinha, na encomenda; a
    # criação, no pedido de agora. ``elapsed_seconds`` usa a mesma base. Contar a
    # encomenda desde a compra fazia o cartão dizer "há 3d 4h" como tempo de preparo.
    clock_since_iso: str = ""
    # Troco da entrega (WP-9): o que a loja coletou no checkout e o que o livro
    # do caixa diz. ``change_out_suggested_q`` é o troco que a loja sugere levar
    # (com quanto o cliente paga menos o total, enquanto não acertado);
    # ``change_out_q`` é o que de fato saiu da gaveta com o entregador
    # (``courier_out``); ``change_back_pending`` enquanto o acerto não disser
    # quanto voltou. ``change_label`` é a frase pronta para o card/painel (com
    # quanto o cliente paga, o que saiu, o que voltou), vazia sem troco na história.
    change_out_suggested_q: int = 0
    change_out_q: int = 0
    change_back_pending: bool = False
    change_label: str = ""
    # Maquininha que saiu com o entregador: custódia no pedido
    # (``Order.data.dispatch``), não no caixa. ``equipment_options`` é o que o
    # canal permite levar (o despacho pergunta só quando há opção);
    # ``equipment_label`` diz o que saiu; ``equipment_back_pending`` enquanto não voltou.
    equipment_options: tuple[EquipmentOptionProjection, ...] = ()
    equipment_label: str = ""
    equipment_back_pending: bool = False
    # A saída pede maquininha (pagamento com cartão na porta): o botão de saída
    # vira "Saiu com a maquininha" e o sistema escolhe a livre.
    dispatch_needs_machine: bool = False
    # Outros pedidos que saíram junto com este (mesma saída, mesma maquininha).
    trip_with: tuple[str, ...] = ()
    # "Entregador voltou": pedidos que o gesto fecha e o que a mão do operador
    # deve receber ("Maquininha Azul", "R$ 100,00 em dinheiro: ...").
    courier_return_orders: tuple[str, ...] = ()
    courier_return_lines: tuple[str, ...] = ()
    # Fila de espera (WP-P2E): o pedido que espera fornada não está parado por
    # descuido, e o que tem janela de confirmação aberta espera o CLIENTE. Sem o
    # selo os dois se parecem com "pedido travado" no quadro, e alguém cutuca o
    # que não devia.
    # "" | "fermata" | "confirming" | "confirmed" | "released"
    waitlist_state: str = ""
    waitlist_label: str = ""
    ifood_cancellation_notice: str = ""
    # O card NÃO recebe ``payment_summary``/``operation_summary``: eles montam a
    # evidência COMPLETA (bandeira, CEP, responsável pela entrega, três linhas de
    # janela) e são do DETALHE. No card viravam doze linhas para um pedido de dois
    # itens — o dobro da altura do card do PDV, na mesma coluna, e a fila deixava
    # de ser varredura. Ficam só os fatos que decidem algo de relance.
    # "Código do entregador · 6005" na entrega, "Código de retirada · 6005" no
    # balcão: a frase já leva o código.
    ifood_pickup_code_label: str = ""
    # Onde está o entregador do iFood ("Entregador a caminho da loja"), pelo último
    # fato recebido. Ocupa o lugar do "Pronto" nos pedidos com entregador do iFood.
    ifood_logistics_label: str = ""
    ifood_schedule_label: str = ""
    # O iFood à frente do estado local (concluiu, ou o entregador dele já retirou):
    # uma linha escrita como instrução. Vazia no caso normal.
    ifood_remote_ahead_label: str = ""
    ifood_negotiations: tuple[IFoodNegotiationProjection, ...] = ()
    # O aceite saiu daqui e não chegou ao iFood (P1-3): o card avisa, mantém o
    # prazo do iFood contando fora de ``new`` e oferece ``ifood-accept-retry``.
    # ``ifood_accept_notice`` é a frase inteira do aviso; vazia no caso normal.
    ifood_accept_failed: bool = False
    ifood_accept_notice: str = ""
    # Homologação do iFood roda contra o ambiente VIVO: o pedido de teste é
    # operável como qualquer outro e por isso tem de dizer, na tela, que é de
    # teste. ``test_order_label`` é o crachá do card; ``test_order_notice`` é a
    # frase inteira. Vazios no pedido de verdade.
    test_order_label: str = ""
    test_order_notice: str = ""
    # A DANFE da NFC-e (services/order_danfe.py). ``danfe_printable``: a nota
    # está autorizada e o Gestor pode imprimi-la (o iFood fica de fora).
    # ``danfe_printed``: já saiu uma vez, e a próxima é REIMPRESSÃO.
    # ``danfe_state``: ``printed`` · ``sending`` (na fila da impressora do
    # despacho) · ``not_printed`` · ``on_dispatch`` (entrega ainda na casa: sai
    # sozinha na saída) · ``available`` (retirada: à mão, se o cliente pedir).
    # ``danfe_problem``: por que não saiu e o que fazer, só em ``not_printed``.
    danfe_printable: bool = False
    danfe_printed: bool = False
    danfe_state: str = ""
    danfe_problem: str = ""
    # "O sistema fez · desfazer" (SUITE-UX §5.1): pronto automático ou saída
    # tocada ainda na janela. Ver ``UndoProjection``.
    undo: UndoProjection | None = None
    # A Cozinha neste pedido (SUITE-UX §15: a Saída mora no Gestor): no Preparo,
    # quem falta e o "Pronto" da estação sem tela; no pronto, o "Voltar para…".
    # ``None`` quando o pedido não passou pela Cozinha.
    kitchen: KitchenProgressProjection | None = None
    # Volumes (sacolas, caixas) declarados por quem embalou (``Order.data["volumes"]``).
    # 0 = ninguém declarou: o cartão mostra a contagem de itens, nunca um volume
    # deduzido.
    volumes: int = 0
    # Conferência das sacolas no despacho (``shop.services.volume_check``): quantas
    # o leitor da Saída já bipou, valendo para o total atual (declarado, ou 1).
    # 0 = ninguém conferiu (o cartão não fala da conferência).
    volumes_checked: int = 0
    volumes_to_check: int = 0
    # Quando o pedido ficou PRONTO desta vez (a última entrada em READY no log de
    # eventos; ``Order.ready_at`` guarda só a primeira, e o pronto desfeito volta).
    # Vazio fora de READY. É o "pronto há N min" do cartão e da Fila.
    ready_at_iso: str = ""
    # Quando saiu para a entrega (``Order.dispatched_at``), em DISPATCHED/DELIVERED:
    # o "na rua há N min".
    dispatched_at_iso: str = ""
    # A Fila "Precisa de você" (V4-G4, ``order_attention``): o fato humano que o
    # pedido espera (``""`` = nada, está em andamento), desde quando o relógio da
    # etapa conta e a meta dela ("meta 30 min", "no balcão").
    attention: str = ""
    attention_since_iso: str = ""
    goal_minutes: int = 0
    goal_label: str = ""
    # Na Cozinha (aceito ou em preparo): quando deve ficar pronto, pelo início real e
    # pelo tempo que os preparos estão levando agora (G10, ``kitchen_eta.ready_eta``).
    ready_eta_iso: str = ""
    # Lembrete TEMPORÁRIO de chamar o entregador (``services.courier_reminder``):
    # entrega da casa em preparo sem corrida pedida. A tela mostra o aviso quando o
    # relógio passa de ``due_at_iso``. ``None`` quando não cabe.
    courier_reminder: CourierReminderProjection | None = None
    # A cobrança digital venceu sem pagamento ("Pix expirado"): o avanço nunca vai
    # destravar sozinho, e a tela oferece o próximo passo pronto (cancelar com o
    # motivo "Pagamento não confirmado" já marcado), em vez de um botão morto.
    payment_lapsed: bool = False
    # O WhatsApp do cliente, SÓ no pedido que pede ação (a cobrança venceu, ou a
    # promessa está em risco) e só quando o pedido tem telefone que não é o relé do
    # iFood (decisão do dono, #2434, "1:b"): o cartão e a Tabela levam "Chamar no
    # WhatsApp" direto, sem escrever o número. Nos outros pedidos fica vazio: o
    # contato do cliente não mora no cartão.
    customer_whatsapp_url: str = ""
    # O bloqueio anda sozinho, sem ninguém da casa agir ("Aguardando Pix", "Aguardando
    # o dia da encomenda", "Esperando o lote"): a tela não o pinta de vermelho
    # (``WAITING_BLOCK_LABELS``; decisão da coordenação com o mandato do dono, 21/11).
    advance_block_waits: bool = False
    # A promessa do pedido (WP-G08, ``projections/order_promise``): ``None`` quando
    # a reserva está como deve estar. ``state`` ``at_risk`` é "Promessa em risco"
    # (algum item ficou sem lastro, ou o lote dele atrasou), com o item, quanto
    # falta, o porquê e as saídas ao lado (``actions``: avisar o cliente, remarcar
    # no PDV, cancelar; no cartão as três levam ao detalhe ou ao PDV).
    # ``waiting_batch`` é "Esperando o lote": a reserva está inteira e o lote de
    # hoje ainda não ficou pronto; o preparo fica barrado (``blocks_start``) e o
    # selo não depende mais do estado da fila de espera.
    promise: order_promise.OrderPromiseProjection | None = None


@dataclass(frozen=True)
class CustomerProfileProjection:
    """Quem é este cliente, para o operador decidir como tratá-lo.

    Só APRESENTA o que já está materializado — ``CustomerInsight``
    (guestman/contrib/insights) e o cadastro do Guestman. Este bloco não
    calcula segmento, ticket nem favorito: o cálculo já existe e tem dono.

    Duas armadilhas moldam o formato:

    1. **Insight é estado OPCIONAL.** Ele nasce no ``customer.ensure`` de cada
       pedido — quem nunca comprou (cliente importado, semeado, criado à mão no
       cadastro) simplesmente não tem insight, e nenhuma varredura o cria: sem
       pedido, os scores RFM sairiam ``1/1/1`` e o carimbo seria "Perdido", que
       é sobre quem foi embora, não sobre quem nunca chegou. Sem ele os campos
       derivados saem VAZIOS, nunca zero: "R$ 0,00" em ticket médio afirmaria
       que o cliente não gasta nada, que é o oposto de "ainda não sabemos".
    2. **"Última compra" não é ESTE pedido.** O insight guarda ``last_order_at``,
       que depois do ``ensure`` deste pedido é este mesmo pedido — dizer
       "última compra hoje" no detalhe dele é ruído. A recência vem do pedido
       ANTERIOR, e é ela também que decide ``is_first_order``: sem pedido
       anterior é primeira compra, com ou sem insight.
    """

    # Recorrência. ``orders_label`` já vem pronto ("Primeira compra",
    # "12 pedidos") e é vazio quando não há contagem confiável.
    is_first_order: bool
    total_orders: int
    orders_label: str
    # "há 12 dias" / "ontem" / "há 4 meses" — do pedido anterior, nunca deste.
    last_order_display: str
    average_ticket_display: str
    favorite_product: str
    # Selo de segmento RFM só quando ele muda o atendimento: fiel/campeão
    # (``success``) e em risco/perdido (``warning``). "Regular" e "recente" não
    # ganham selo — badge que aparece sempre não informa nada.
    segment: str
    segment_label: str
    segment_tone: str  # "success" | "warning"
    # Cadastro: o que o PDV já mostra ao balcão e muda o atendimento.
    notes: str
    dietary_restrictions: str
    birthday_display: str
    is_birthday_today: bool


@dataclass(frozen=True)
class ContactRequestProjection:
    """Ouvidoria aberta: o cliente pediu para falar com o responsável.

    ``origin``: ``rating`` (avaliou mal; ``rating`` e ``comment`` dizem como) ou
    ``cancellation`` (quis cancelar com o preparo já começado; ``rating`` é 0).
    Só existe enquanto o caso está aberto; o "Resolvido" (com a nota do que foi
    feito) o fecha. Ver ``shop/services/customer_contact.py``.
    """

    rating: int
    comment: str
    requested_at_display: str
    origin: str


@dataclass(frozen=True)
class OperatorOrderProjection:
    """O detalhe de um pedido — o MESMO contrato para o Gestor e o PDV (``context``)."""

    ref: str
    status: str
    actions: tuple[Action, ...]
    revisions: dict[str, str]
    status_label: str
    customer_name: str
    # Contato do cliente que fez ESTE pedido. O dado sempre esteve em
    # ``Order.data["customer"]``; a projection é que não o publicava, e o
    # operador que abria o detalhe para resolver um problema não tinha como
    # falar com a pessoa — nem o telefone na tela. (A ironia é que o telefone do
    # PRESENTEADO já aparecia, em ``gift_recipient_phone``.)
    #
    # ``customer_phone`` é para ler em voz alta; ``customer_phone_uri`` e
    # ``customer_whatsapp_url`` são para clicar. Vazios quando o pedido não tem
    # telefone — a tela some com o bloco em vez de oferecer botão que não liga
    # para lugar nenhum.
    customer_phone: str
    customer_phone_uri: str
    customer_whatsapp_url: str
    # Pedido de marketplace: o iFood não entrega o telefone do cliente, entrega o
    # 0800 da central dele + um localizador com validade. É por onde se fala com a
    # pessoa POR VOZ, discando os dois. Vazios quando o telefone é do cliente.
    customer_relay_phone: str
    customer_relay_code: str
    customer_relay_expires_at: str
    customer_email: str
    # Ref do Customer no cadastro, quando o pedido está ligado a um. É o que
    # deixa a tela oferecer "abrir cadastro" no Admin — hoje o único lugar onde
    # se busca, edita e cria cliente.
    customer_ref: str
    channel_ref: str
    channel_icon: str
    fulfillment_label: str
    fulfillment_type: str  # "delivery" | "pickup"
    # Idem ao cartão: quem abre o detalhe para despachar precisa do endereço.
    delivery_address: str
    delivery_instructions: str
    total_display: str
    # Os itens a preço de tabela; o desconto (cupom com o código, promoção, grupo)
    # vem em ``discount_lines``, uma linha por origem, com o valor negativo pronto.
    items: tuple[OrderItemProjection, ...]
    discount_lines: tuple[order_pricing.OrderDiscountLineProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    kitchen_note: str
    # Observação do CLIENTE (``order_notes``, escrita no checkout). Dona
    # diferente da ``kitchen_note`` (do operador): o Gestor mostra as duas, e
    # só a da cozinha é editável.
    customer_note: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    payment_status_label: str
    # As MESMAS respostas que o board usa, calculadas pelo mesmo serviço. O
    # detalhe não as tinha e a tela chutava: a guarda do "Avançar" era
    # ``can_settle_delivery_cash !== undefined``, que é sempre verdadeira, e o
    # "Aceitar" não tinha guarda nenhuma. O operador via os dois botões cheios
    # num pedido `new` e levava 400 do servidor. Com o board e o detalhe lendo a
    # mesma fonte, os dois não podem mais discordar sobre o que é possível.
    can_confirm: bool
    can_advance: bool
    # Cancelar tem três camadas e a tela precisa das três numa resposta só:
    # `can_cancel` já é régua + política + permissão deste usuário, e
    # `cancel_requires_approval` avisa que virá o desafio de gerente ANTES do
    # operador digitar o motivo. Ver `OrderCancelView`.
    can_cancel: bool
    cancel_requires_approval: bool
    cancel_block_label: str
    advance_block_label: str
    advance_block_reason: str
    can_settle_delivery_cash: bool
    fiscal_status_label: str
    fiscal_status: str
    fiscal_state: str
    fiscal_links: tuple[dict[str, str], ...]
    awaiting_work_orders: tuple[AwaitingWorkOrderProjection, ...]
    is_gift: bool
    gift_recipient_name: str
    gift_recipient_phone: str
    gift_message: str
    gift_hide_values: bool
    # Os motivos de RECUSAR e de CANCELAR: a lista única, com chave estável e a
    # frase que o cliente lê (``services/cancel_reasons``).
    cancel_reasons: tuple[CancelReasonProjection, ...]
    kitchen_note_tags: tuple[str, ...]
    # Quem é este cliente (WP-360): recorrência, recência, ticket, favorito e o
    # que o cadastro sabe. ``None`` quando o pedido não tem cliente identificado
    # (venda de balcão anônima) ou o cadastro sumiu — a tela omite o bloco em
    # vez de desenhar um perfil vazio.
    customer_profile: CustomerProfileProjection | None
    # Corrida de entrega na logística externa (Machine). None quando não se
    # aplica (retirada, ou canal sem adapter courier e sem corrida registrada).
    courier: dict | None = None
    # Troco da entrega (WP-9): o que a loja coletou no checkout e o que o livro
    # do caixa diz. ``change_out_suggested_q`` é o troco que a loja sugere levar
    # (com quanto o cliente paga menos o total, enquanto não acertado);
    # ``change_out_q`` é o que de fato saiu da gaveta com o entregador
    # (``courier_out``); ``change_back_pending`` enquanto o acerto não disser
    # quanto voltou. ``change_label`` é a frase pronta para o card/painel (com
    # quanto o cliente paga, o que saiu, o que voltou), vazia sem troco na história.
    change_out_suggested_q: int = 0
    change_out_q: int = 0
    change_back_pending: bool = False
    change_label: str = ""
    # Maquininha que saiu com o entregador: custódia no pedido
    # (``Order.data.dispatch``), não no caixa. ``equipment_options`` é o que o
    # canal permite levar (o despacho pergunta só quando há opção);
    # ``equipment_label`` diz o que saiu; ``equipment_back_pending`` enquanto não voltou.
    equipment_options: tuple[EquipmentOptionProjection, ...] = ()
    equipment_label: str = ""
    equipment_back_pending: bool = False
    # A saída pede maquininha (pagamento com cartão na porta): o botão de saída
    # vira "Saiu com a maquininha" e o sistema escolhe a livre.
    dispatch_needs_machine: bool = False
    # Outros pedidos que saíram junto com este (mesma saída, mesma maquininha).
    trip_with: tuple[str, ...] = ()
    # "Entregador voltou": pedidos que o gesto fecha e o que a mão do operador
    # deve receber ("Maquininha Azul", "R$ 100,00 em dinheiro: ...").
    courier_return_orders: tuple[str, ...] = ()
    courier_return_lines: tuple[str, ...] = ()
    # Link de pagamento do pedido remoto (WP-PAGAMENTO, frente 5). O botão
    # "Reenviar link" só existe quando o servidor vai aceitar o gesto
    # (``notification.payment_link_resend_refusal``): forma ``link`` com URL,
    # pedido vivo, não pago, link não vencido. A cadência (cedo demais, envio
    # em andamento) é recusa da hora do clique, com toast — não esconde botão.
    # ``payment_link_notice`` descreve a evidência, lida da última Directive do
    # aviso: "Enviando…", "Link enviado às 14h32" ou "falhou — reenvie".
    can_resend_payment_link: bool = False
    payment_link_notice: str = ""
    # "O sistema fez · desfazer": o mesmo bloco do card (``UndoProjection``).
    undo: UndoProjection | None = None
    # Comprovante de entrega de cada aviso ao cliente (D3): canal, hora,
    # identificador do provedor e o estado final. "Entregue" só com
    # comprovante. Ver ``docs/reference/comprovante-de-entrega.md``.
    notification_receipts: tuple[NotificationReceiptProjection, ...] = ()
    # Quem pode dar a segunda assinatura (nome + ``username``, nada além) — a MESMA
    # lista do PDV (``pos._manager_cards``). Sem ela o diálogo canônico caía no
    # campo livre e o gerente tinha de DIGITAR o próprio nome no meio de um
    # cancelamento com o relógio do iFood correndo; nome digitado erra, e o
    # servidor resolve a assinatura por ``username``. Quem opera vem em primeiro
    # e assina com o próprio PIN (dono, 28/10/2026).
    managers: tuple[dict[str, str], ...] = ()
    contact_request: ContactRequestProjection | None = None
    ifood_cancellation_notice: str = ""
    ifood_payment_summary: tuple[str, ...] = ()
    ifood_operation_summary: tuple[str, ...] = ()
    # O mesmo selo do card: onde está o entregador do iFood.
    ifood_logistics_label: str = ""
    # A mesma frase do card (WP-G02): "Vai para a Cozinha às 16h15", enquanto a
    # encomenda do dia espera a hora dela. Vazia depois que chega.
    kitchen_release_label: str = ""
    ifood_negotiations: tuple[IFoodNegotiationProjection, ...] = ()
    # O mesmo aviso do card (P1-3): o aceite não chegou ao iFood.
    ifood_accept_failed: bool = False
    ifood_accept_notice: str = ""
    # Homologação do iFood roda contra o ambiente VIVO: o pedido de teste é
    # operável como qualquer outro e por isso tem de dizer, na tela, que é de
    # teste. ``test_order_label`` é o crachá do card; ``test_order_notice`` é a
    # frase inteira. Vazios no pedido de verdade.
    test_order_label: str = ""
    test_order_notice: str = ""
    # O DETALHE DO PEDIDO É UM SÓ (decisão do dono, 28/09/2026): o Gestor e o PDV
    # leem este mesmo contrato, e o que muda entre eles é o CONTEXTO — ``"orders"``
    # (Gestor) ou ``"pos"`` (balcão). O contexto decide as AÇÕES, aqui no servidor:
    # no balcão ``actions`` só traz o que o balcão faz a partir desta tela (comentar
    # no histórico), os ``can_*`` do fluxo do Gestor vêm desligados, e os gestos do
    # balcão moram em ``counter``. Ver :func:`build_operator_order`.
    context: str = "orders"
    # Quando o combinado acontece — "Sáb, 27/09 · 08h às 10h" —, só para pedido com
    # data ou janela combinada. Vazio no pedido de agora.
    schedule_label: str = ""
    # Só no contexto ``"pos"``: a encomenda como o balcão a lê (situação, saldo) e
    # os gestos do balcão com a régua de cada um (entregar, editar, reagendar,
    # cancelar). ``None`` no Gestor.
    counter: CounterOrderProjection | None = None
    # O cabeçalho do detalhe (G14): o nome do canal ("Loja online", não "web") e a
    # linha de abertura ("aberto às 21:47"), lidos uma vez no servidor.
    channel_name: str = ""
    opened_line: str = ""
    # O prazo do pedido novo, o MESMO do cartão ("Confirma sozinho em 4:32", G15).
    confirmation_deadline_iso: str = ""
    confirmation_action: str = ""
    # O vencimento da autorização do cartão, o MESMO do card do quadro.
    card_authorization_expires_iso: str = ""
    # Onde fica a loja (G18, "fora da loja: mostrando o que pede decisão"): o celular
    # que consentiu compara a própria posição com esta, no dispositivo; a posição de
    # quem opera nunca vem ao servidor. ``None`` sem coordenadas no cadastro da loja.
    store_location: dict[str, float] | None = None
    # O que o cancelamento faz com o dinheiro, ANTES de confirmar: "R$ 5,10 serão
    # estornados no cartão do cliente", "A reserva no cartão será desfeita. Nada
    # foi cobrado." O diálogo de cancelar e recusar e o PIN do gerente diziam só
    # o motivo (beta 06/11, F5). Vazio quando não há dinheiro em jogo.
    cancel_money_effect: str = ""
    # O cancelamento fala com o gateway dentro do pedido (estorno ou anulação da
    # reserva): leva alguns segundos, e a tela diz isso enquanto espera (F12).
    cancel_waits_for_gateway: bool = False
    # O RASTRO da comanda do PDV (dono, T1=1, 13/10/2026): "Transferida da comanda #13"
    # quando o pedido nasceu de uma comanda separada de outra. Vazio no resto.
    transferred_from_label: str = ""
    # Igual ao do cartão: a cobrança venceu e o avanço não destrava mais sozinho.
    payment_lapsed: bool = False
    # Igual ao do cartão: o bloqueio anda sozinho, sem ninguém da casa agir.
    advance_block_waits: bool = False
    # "O que falta neste pedido" (WP-G05): as pendências, da que pede alguém agora
    # à que só espera, cada uma com o gesto que já existe para resolvê-la
    # (``projections/order_pending``). Vazia no contexto ``"pos"``: os gestos são
    # do Gestor.
    pending: tuple[order_pending.OrderPendingProjection, ...] = ()
    # O dinheiro do pedido CANCELADO, lido do mesmo ``payment.cancelled_money``
    # que o acompanhamento da loja: estorno pedido, estornado ou estorno que não
    # saiu, com a frase que o cliente lê. ``None`` fora do cancelado digital.
    cancelled_money: order_pending.CancelledMoneyProjection | None = None
    # A DANFE da NFC-e, os MESMOS campos do cartão (``services/order_danfe``): o
    # gesto de imprimir e reimprimir existia só no painel (P1-14).
    danfe_printable: bool = False
    danfe_printed: bool = False
    danfe_state: str = ""
    danfe_problem: str = ""
    # A promessa do pedido, a MESMA do cartão (WP-G08). No detalhe as saídas são
    # as de verdade: a conversa com o cliente, o PDV e o cancelar de ``actions``.
    # ``None`` no contexto ``"pos"`` e quando a reserva está como deve estar.
    promise: order_promise.OrderPromiseProjection | None = None


#: Os contextos que leem o detalhe do pedido (:func:`build_operator_order`).
DETAIL_CONTEXTS = ("orders", "pos")

#: Os campos do fluxo do Gestor que o balcão NÃO executa a partir do detalhe. No
#: contexto ``"pos"`` eles vêm desligados, para a tela nunca oferecer um gesto que
#: não é dela — aceitar, avançar, acertar a entrega e cancelar pelo Gestor têm, no
#: balcão, o seu equivalente em ``counter`` (ou não existem ali).
_ORDERS_FLOW_OFF = {
    "can_confirm": False,
    "can_advance": False,
    "can_cancel": False,
    "cancel_requires_approval": False,
    "cancel_block_label": "",
    "advance_block_label": "",
    "advance_block_reason": "",
    "can_settle_delivery_cash": False,
    "kitchen_note_tags": (),
}

#: As ações do detalhe que o balcão executa (o resto do fluxo é do Gestor).
#: "Entregador voltou" (``courier-back``) também mora no balcão (dono, P=1,
#: 14/10/2026): o MESMO gesto do Gestor, que fecha a saída inteira (entrega,
#: dinheiro, troco e maquininha), com a mesma permissão.
_POS_DETAIL_ACTIONS = frozenset({"comment", "courier-back"})

#: As ações da corrida que o balcão executa: chamar, chamar de novo e cancelar a
#: corrida antes da coleta (dono, P=1, 14/10/2026). Cotar fica no Gestor.
_POS_COURIER_ACTIONS = frozenset({"courier-dispatch", "courier-dispatch-again", "courier-cancel"})


@dataclass(frozen=True)
class TwoZoneQueueProjection:
    """Operator queue grouped by action area: intake, prep and expedition
    (rendered as the Entrada, Preparo and Saída columns)."""

    intake: tuple[OrderCardProjection, ...]
    preparing_count: int
    prep: tuple[OrderCardProjection, ...]
    expedition_pickup: tuple[OrderCardProjection, ...]
    expedition_delivery: tuple[OrderCardProjection, ...]
    expedition_delivery_transit: tuple[OrderCardProjection, ...]
    expedition_delivery_count: int
    expedition_count: int
    total_count: int
    # Relógio operacional canônico da loja. O tablet pode estar em UTC, com
    # timezone errado ou atravessar a meia-noite local em outro instante; som e
    # memória diária devem seguir o dia calculado pelo Django.
    service_day: str
    service_day_ends_at: str
    # A lista "Encomendas", abaixo das colunas: só encomenda JÁ ACEITA e ainda
    # antes da expedição. Primeiro as de hoje que esperam a hora da Cozinha (pela
    # hora em que cada uma chega), depois as de outros dias (pela data combinada).
    # O pedido NOVO nunca mora aqui, qualquer que seja a data: aceitar tem prazo,
    # e ele fica em ``intake`` até o aceite. No dia, o despertador
    # (``preorder.activate``) leva a encomenda de outro dia ao fluxo do dia.
    preorders: tuple[OrderCardProjection, ...] = ()
    preorders_count: int = 0
    # Maquininhas na rua (saíram com o entregador e não voltaram), para o quadro
    # responder "onde está a maquininha" sem procurar card por card.
    equipment_out: tuple[EquipmentOutProjection, ...] = ()
    equipment_available: tuple[EquipmentOptionProjection, ...] = ()
    # Entregas prontas que podem ir juntas numa corrida da TaOn (uma parada por
    # pedido, ``courier.group_refusal``), com o troco e a maquininha que a
    # chamada pergunta. Com duas ou mais, a Saída oferece a corrida.
    ride_candidates: tuple[RideCandidateProjection, ...] = ()
    # Chamar a corrida desses candidatos (``courier-ride``): quem a tela leu e a
    # revisão de cada um (``courier_ride_action``). ``None`` sem candidatos.
    ride_action: Action | None = None
    # Quantas corridas o plano sugere agora (``ride_plan``, o mesmo da página
    # Entregas): o "Montar corridas (2 sugeridas)" do Painel.
    ride_suggestions: int = 0

    ifood_negotiation_orders: tuple[OrderCardProjection, ...] = ()
    # Os motivos de recusar do quadro: a MESMA lista única do detalhe e do cancelar.
    cancel_reasons: tuple[CancelReasonProjection, ...] = ()
    # A coluna ao lado da Fila: o que o sistema fez nos últimos minutos e o estado
    # do cardápio e dos canais (``order_attention.build_queue_awareness``).
    awareness: QueueAwarenessProjection | None = None


# ── Builders ───────────────────────────────────────────────────────────


def _cancel_capability(order: Order, user) -> dict:
    """Régua + política + permissão numa resposta só, para a tela não adivinhar.

    O botão Cancelar vivia sem guarda nenhuma e o servidor respondia
    ``200 {"ok": true}`` sem cancelar. Agora a capability é a mesma que a view
    aplica — e é ela que decide, não a tela.

    ``user`` ausente (projeção fora de request, teste, job) resolve só régua e
    política: sem ator não há o que autorizar, e um ``True`` otimista aqui
    devolveria o botão mentiroso pela porta dos fundos.
    """
    from shopman.shop.services import cancellation as cancellation_service
    from shopman.shop.services.ifood_cancellation import is_pending

    if is_pending(order):
        return {"can_cancel": False, "cancel_requires_approval": False, "cancel_block_label": "Aguardando confirmação de cancelamento do iFood."}
    policy = cancellation_service.operator_cancel_policy(order)
    if not policy.allowed:
        return {
            "can_cancel": False,
            "cancel_requires_approval": False,
            "cancel_block_label": policy.reason,
        }

    if cancellation_service.is_advanced_cancel(order):
        authorized = bool(user and user.has_perm(cancellation_service.ADVANCED_CANCEL_PERMISSION))
        if not authorized:
            return {
                "can_cancel": False,
                "cancel_requires_approval": False,
                "cancel_block_label": f"Cancelar pedido em {order.get_status_display()} é do gerente.",
            }

    return {
        "can_cancel": True,
        "cancel_requires_approval": policy.requires_approval,
        "cancel_block_label": "",
    }


def _approver_options(user) -> tuple[dict[str, str], ...]:
    """A lista do PDV para o diálogo de gerente do Gestor — uma fonte só."""
    from shopman.backstage.projections.pos import _manager_cards

    return _manager_cards(user)


def transferred_from_label(data: dict) -> str:
    """ "Transferida da comanda #13" (dono, 13/10/2026), de ``transferred_from``; "" sem rastro."""
    origin = data.get("transferred_from") or {}
    display = str(origin.get("tab_display") or origin.get("tab_ref") or "").strip()
    if not display:
        return ""
    return f"Transferida da comanda {'#' + display if display.isdigit() else display}"


def build_operator_order(order: Order, *, user=None, context: str = "orders") -> OperatorOrderProjection:
    """O detalhe de UM pedido — o mesmo contrato para o Gestor e para o PDV.

    Pedido + ajustes: o detalhe mostra o pedido que VALE agora. Um pedido que o
    cliente alterou no iFood depois de confirmado tem itens e total novos, e o
    operador não pode conferir a sacola por uma lista velha.

    ``context`` diz QUEM lê (:data:`DETAIL_CONTEXTS`), e com isso quais gestos a
    tela oferece — decisão do servidor, nunca da tela:

    - ``"orders"`` (Gestor): o fluxo inteiro — aceitar, avançar, acertar a
      entrega, entregador, iFood, NFC-e, link de pagamento, nota da cozinha.
    - ``"pos"`` (balcão, seção Encomendas): as mesmas seções de leitura (resumo,
      cliente, nota fiscal, itens, observação, nota da cozinha, histórico), só
      o comentário no histórico em ``actions``, e os gestos do balcão em
      ``counter`` (:func:`preorders.build_counter_block`).
    """
    if context not in DETAIL_CONTEXTS:
        raise ValueError(f"Contexto de detalhe desconhecido: {context!r}")
    # Um relógio por leitura, como no quadro: o combinado e a hora da Cozinha
    # falam do mesmo instante.
    now = timezone.now()
    today = timezone.localtime(now).date()
    # Itens a preço de tabela e o desconto (cupom, promoção) em linha própria:
    # rateado no preço, o cupom sumia para o operador (beta 06/11).
    items, discount_lines = order_pricing.priced_items(order)
    discount_lines = discount_lines + ifood_projection.total_lines(order)

    customer_data = order.data.get("customer", {})
    customer_name = _format_customer_display(
        customer_data.get("name", "")
        or customer_data.get("phone", "")
        or order.data.get("customer_phone", "")
        or _customer_handle(order)
        or ""
    )
    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")
    payment_status = _payment_status(order)
    payment_method_label = _payment_method_label(method, payment_data, order=order)
    fiscal_status, fiscal_status_label, fiscal_state, fiscal_links = _fiscal_status(order)
    recipient = order.data.get("recipient") if isinstance(order.data.get("recipient"), dict) else {}
    is_delivery = _is_delivery(order)
    delivery_address, delivery_instructions = _delivery_address(order)
    # Os avisos abertos do pedido e o dinheiro do cancelado: uma leitura, usada no
    # rótulo do pagamento (as duas telas) e nas pendências (só o Gestor).
    pending_alerts = order_pending.open_alert_types(order)
    cancelled_money = order_pending.cancelled_money(order, alerts=pending_alerts)
    contact = _customer_contact(order, customer_data)

    # O que as duas telas leem igual.
    common = dict(
        ref=order.ref,
        status=order.status,
        revisions={field: operator_orders.operational_revision(order, field=field) for field in ("advance", "kitchen_note", "assignment", "schedule", "edit")},
        status_label=order_status_label(order.status),
        customer_name=customer_name,
        **contact,
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        fulfillment_label=_fulfillment_label(is_delivery),
        fulfillment_type="delivery" if is_delivery else "pickup",
        delivery_address=delivery_address,
        delivery_instructions=delivery_instructions,
        total_display=_money(order_composition.effective_total_q(order)),
        items=items,
        discount_lines=discount_lines,
        timeline=_build_timeline(order),
        notification_receipts=build_notification_receipts(order),
        kitchen_note=order.data.get("kitchen_note", ""),
        customer_note=str(order.data.get("order_notes", "") or ""),
        payment_method=method,
        # No iFood a linha do pagamento é a frase inteira (cobrar ou não); o status
        # sai vazio para a tela não dizer "iFood · Pago online" e repetir abaixo.
        payment_method_label=(
            ifood_projection.payment_headline(order) if order.channel_ref == "ifood" else payment_method_label
        ),
        managers=_approver_options(user),
        contact_request=_contact_request(order),
        ifood_cancellation_notice=ifood_projection.cancellation_notice(order),
        ifood_payment_summary=ifood_projection.payment_summary(order),
        ifood_operation_summary=ifood_projection.operation_summary(order),
        ifood_logistics_label=ifood_projection.logistics_label(order),
        test_order_label=_test_order_label(order),
        test_order_notice=_test_order_notice(order),
        payment_status=payment_status,
        payment_status_label=_detail_payment_status_label(order, payment_status, cancelled_money),
        cancelled_money=cancelled_money,
        fiscal_status=fiscal_status,
        fiscal_status_label=fiscal_status_label,
        fiscal_state=fiscal_state,
        fiscal_links=fiscal_links,
        awaiting_work_orders=_awaiting_work_orders(order),
        is_gift=bool(order.data.get("is_gift")),
        gift_recipient_name=str(recipient.get("name", "") or ""),
        gift_recipient_phone=str(recipient.get("phone", "") or ""),
        gift_message=str(order.data.get("gift_message", "") or ""),
        gift_hide_values=bool(order.data.get("gift_hide_values")),
        customer_profile=_customer_profile(order),
        schedule_label=_schedule_label(order, today=today),
        context=context,
        channel_name=_channel_name(order.channel_ref or ""),
        opened_line=f"aberto às {format_clock(order.created_at)}" if order.created_at else "",
        transferred_from_label=transferred_from_label(order.data or {}),
    )

    if context == "pos":
        from shopman.backstage.projections import preorders

        # A corrida do entregador (TaOn): o MESMO bloco e as MESMAS ações do Gestor,
        # para a encomenda de entrega da casa (decisão do dono, 13/10/2026).
        courier_block = _courier_block(order)
        pos_authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
        return OperatorOrderProjection(
            **common,
            **_ORDERS_FLOW_OFF,
            actions=(
                *(action for action in operator_orders.operational_actions(order, user=user)
                  if action.ref in _POS_DETAIL_ACTIONS),
                *_courier_actions(order, user, courier_block, authorized=pos_authorized, refs=_POS_COURIER_ACTIONS),
            ),
            courier=courier_block,
            **_equipment_fields(order),
            # A prova de envio do link fica (é leitura); o reenvio é do Gestor.
            payment_link_notice=_payment_link_fields(order, method).get("payment_link_notice", ""),
            counter=preorders.build_counter_block(order, user=user),
            # O cancelar do balcão usa os MESMOS motivos do Gestor: a lista é uma
            # só, no backend (``cancel_reasons``).
            cancel_reasons=_cancel_reasons(order.channel_ref or ""),
            # E a MESMA frase do dinheiro (P1-6, EXCELENCIA-PDV WP-E5): quem cancela
            # e o gerente que assina leem quanto volta e por onde, antes do gesto.
            **_cancel_money_effect(order, method, payment_status),
            # A promessa em risco (WP-G08, #2721 item 3): o MESMO fato do Gestor, e
            # a saída é o "Resolver" de lá (uma situação, um gesto).
            promise=_pos_promise(order, pos_authorized),
        )

    advance_block = operator_orders.gestor_advance_block(order)
    next_status = operator_orders.next_status_for(order) if not advance_block else ""
    block_label, block_reason = _advance_block_copy(
        order, advance_block, method, payment_pending=_is_payment_pending(order, method, payment_status)
    )
    # A cobrança que venceu diz isso também no resumo do pagamento (a mesma régua do cartão).
    lapsed_status = _lapsed_payment_status_label(block_label)
    if lapsed_status:
        common["payment_status_label"] = lapsed_status
    # A promessa do pedido (WP-G08), a mesma leitura e o mesmo bloqueio do cartão.
    promise = _promise_of(order)
    waits_batch = _waits_batch(promise, advance_block, next_status)
    pending_block = str(advance_block or "")
    if waits_batch:
        next_status = ""
        pending_block = str(operator_orders.AdvanceBlock.WAITLIST_FERMATA)
        block_label, block_reason = order_promise.BATCH_WAIT_BLOCK_LABEL, order_promise.batch_wait_reason(promise)

    cancel_capability = _cancel_capability(order, user)
    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
    cancel_action = Action(
        ref="cancel", kind="mutation", label="Cancelar pedido", priority="danger",
        enabled=authorized and cancel_capability["can_cancel"],
        reason=cancel_capability["cancel_block_label"] if authorized else "Identifique uma pessoa com permissão para gerenciar pedidos.",
        method="POST", idempotency="required",
        payload_schema={"base_revision": operator_orders.operational_revision(order), "expected_actor_id": getattr(user, "pk", None)},
        confirmation={"required": True, "manager_approval": cancel_capability["cancel_requires_approval"]},
    )
    extra_actions = [cancel_action, *_cash_settlement_actions(order, user, None)]
    # "Não retirado" (WP-G11): só para pedido pronto, de retirada, fora do iFood e
    # do balcão. A régua (quem, a hora, o motivo) é de ``projections/order_no_show``.
    from shopman.backstage.projections.order_no_show import detail_action as no_show_detail_action

    no_show_action = no_show_detail_action(order, user)
    if no_show_action is not None:
        extra_actions.append(no_show_action)
    # "Avisar o cliente" (WP-G07): os três avisos com um toque, no menu do pedido
    # aberto. Quando cabem e o que cada um pede é de ``services/customer_notice``; o
    # diálogo lê as escolhas ao abrir (``customer-notice/preview/``).
    from shopman.shop.services import customer_notice

    if customer_notice.offered(order):
        notice_refusal = customer_notice.order_refusal(order)
        extra_actions.append(Action(
            ref="customer-notice", kind="mutation", label="Avisar o cliente",
            enabled=authorized and not notice_refusal,
            reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else notice_refusal),
            method="POST", idempotency="required",
            payload_schema={"base_revision": customer_notice.notice_revision(order), "expected_actor_id": getattr(user, "pk", None)},
        ))
    # "Tentar o estorno de novo" (WP-G13, #2727): o pedido em "Estorno não saiu",
    # cancelado ou não (devolução, encomenda editada, pagamento que chegou depois do
    # balcão). A régua (quanto, de onde, a base) é de ``services/refund_retry``.
    refund_retry_plan = None
    if (cancelled_money is not None and cancelled_money.state == order_pending.MONEY_REFUND_FAILED) or (
        cancelled_money is None and order_pending.ALERT_REFUND_FAILED in pending_alerts
    ):
        from shopman.backstage.services import refund_retry

        refund_retry_plan = refund_retry.plan(order)
        if refund_retry_plan.failed:
            extra_actions.append(refund_retry.detail_action(order, user, current=refund_retry_plan))
    # "Estornar" (#2727, item 5): a exceção financeira do Gerente. Só aparece a quem
    # tem ``backstage.refund_single_order`` e no pedido com cobrança online paga; a
    # régua (qual cobrança, quanto, a base) é de ``services/order_refund``.
    from shopman.backstage.services import order_refund

    refund_action = order_refund.detail_action(
        order, user, retry_failed=bool(refund_retry_plan is not None and refund_retry_plan.failed),
    )
    if refund_action is not None:
        extra_actions.append(refund_action)
    courier_block = _courier_block(order)
    extra_actions.extend(_courier_actions(order, user, courier_block, authorized=authorized))
    if fiscal_status == "failed":
        from shopman.backstage.services.orders import fiscal_revision

        extra_actions.append(Action(ref="requeue-fiscal", kind="mutation", label="Reprocessar NFC-e", enabled=authorized,
            reason="" if authorized else "Identifique uma pessoa com permissão para gerenciar pedidos.", method="POST", idempotency="required",
            payload_schema={"base_revision": fiscal_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    from shopman.shop.services import ifood_accept_sync

    accept = ifood_accept_sync.state_for(order)
    detail_deadline = _detail_deadline(order, accept)
    extra_actions.extend(_ifood_accept_actions(order, accept, user))
    if method == "link":
        from shopman.shop.services import notification as notification_svc

        refusal = notification_svc.payment_link_resend_refusal(order)
        extra_actions.append(Action(ref="resend-payment-link", kind="mutation", label="Reenviar link de pagamento", enabled=authorized and refusal is None,
            reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else refusal.message if refusal else ""),
            method="POST", idempotency="required",
            payload_schema={"base_revision": notification_svc.payment_link_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    operational = operator_orders.operational_actions(order, user=user)
    # A encomenda que ainda espera a hora da Cozinha (WP-G02): o detalhe dá ao
    # gesto o mesmo nome e o mesmo peso do card.
    kitchen_release_at = _kitchen_clock(order, now)[0]
    waits_kitchen = kitchen_release_at is not None
    if waits_kitchen:
        operational = _early_start_actions(operational)
    if waits_batch:
        operational = _batch_wait_actions(operational, block_reason)
    operational = _lapsed_payment_actions(
        operational, block_label, can_call=bool(contact.get("customer_whatsapp_url")),
    )
    operational = _exit_gesture_actions(order, operational, customer_name=customer_name)
    actions = (*operational, *extra_actions)
    if promise is not None and promise.state == order_promise.STATE_AT_RISK:
        promise = order_promise.with_actions(promise, _promise_actions(user, promise))
    link_fields, link_problem = _payment_link_read(order, method)
    danfe = order_danfe.card_state(order, now=now)
    return OperatorOrderProjection(
        **common,
        kitchen_release_label=_kitchen_release_label(kitchen_release_at),
        actions=actions,
        pending=order_pending.build_pending(
            order,
            actions=actions,
            fiscal_status=fiscal_status,
            block=pending_block,
            block_label=block_label,
            block_reason=block_reason,
            payment_lapsed=block_label in LAPSED_PAYMENT_LABELS,
            link_problem=link_problem,
            cancel_capability=cancel_capability,
            danfe=danfe,
            awaiting_work_orders=common["awaiting_work_orders"],
            money=cancelled_money,
            refund_retry_plan=refund_retry_plan,
            alerts=pending_alerts,
            schedule_label=common["schedule_label"],
            whatsapp_url=contact.get("customer_whatsapp_url", ""),
            promise=promise,
        ),
        promise=promise,
        danfe_printable=danfe.printable,
        danfe_printed=danfe.printed,
        danfe_state=danfe.state,
        danfe_problem=danfe.problem,
        ifood_negotiations=negotiations(order, user=user),
        can_confirm=not operator_orders.confirmation_block_reason(order),
        can_advance=bool(next_status) and undo_block_allows_advance(order),
        **cancel_capability,
        undo=_undo_projection(order),
        advance_block_label=block_label,
        advance_block_reason=block_reason,
        payment_lapsed=block_label in LAPSED_PAYMENT_LABELS,
        advance_block_waits=block_waits(block_label),
        can_settle_delivery_cash=_can_settle_delivery_cash(order, payment_data),
        cancel_reasons=_cancel_reasons(order.channel_ref or ""),
        kitchen_note_tags=_kitchen_note_tags(order),
        courier=courier_block,
        **_courier_change_fields(order),
        **_equipment_fields(order),
        **link_fields,
        **detail_deadline,
        **_ifood_accept_fields(order, accept),
        card_authorization_expires_iso=_card_authorization_expires_iso(
            order, method, payment_status,
            acceptance_deadline=(
                detail_deadline.get("confirmation_deadline_iso", ""),
                detail_deadline.get("confirmation_action", ""),
            ),
        ),
        store_location=_store_location(),
        **_cancel_money_effect(order, method, payment_status),
    )


def _detail_payment_status_label(order: Order, payment_status: str, cancelled_money) -> str:
    """O rótulo do pagamento no resumo do detalhe.

    No cancelado em que dinheiro se moveu, o estado do estorno ("Estorno
    pedido", "Estornado", "Estorno não saiu"), a mesma palavra do histórico
    (P2-25). Duas leituras mais específicas vêm antes e continuam valendo: o
    dinheiro que entrou fora da cobrança, e o "não retirado" que devolveu só uma
    parte (WP-G11).
    """
    if order.channel_ref == "ifood":
        return ""
    outside = _money_outside_the_charge_label(order, payment_status)
    if outside:
        return outside
    refund_label = order_pending.payment_label(cancelled_money)
    if refund_label:
        from shopman.backstage.projections.order_no_show import payment_outcome_label

        return payment_outcome_label(order) or refund_label
    return _order_payment_status_label(order, payment_status)


#: Os meios que o próprio sistema estorna no gateway, e por onde o dinheiro volta.
_GATEWAY_REFUND_DESTINATION = {"pix": "ao Pix do cliente", "card": "no cartão do cliente", "link": "no cartão do cliente"}


def refund_effect(amount_q: int, method: str) -> str:
    """Para onde volta o dinheiro que a casa devolve, na frase que o operador lê.

    Uma frase por caminho, a mesma no cancelar (:func:`_cancel_money_effect`) e
    no "tirar o item" do diálogo "Resolver" (``order_promise_resolution``): o
    gateway estorna sozinho; dinheiro e maquininha ficam a devolver por alguém
    da casa. ``method`` é o meio do pagamento ("pix", "card", "cash", "credit"…).
    """
    from shopman.shop.services.order_edit import CARD_MACHINE_METHODS

    money = _money(amount_q)
    if method in _GATEWAY_REFUND_DESTINATION:
        return f"{money} serão estornados {_GATEWAY_REFUND_DESTINATION[method]}."
    if method == "cash":
        return f"{money} em dinheiro ficam a devolver no caixa."
    if method in CARD_MACHINE_METHODS:
        return f"{money} ficam a estornar na maquininha."
    return f"{money} ficam a devolver ao cliente."


def _cancel_money_effect(order: Order, method: str, payment_status: str) -> dict:
    """O que o cancelamento (ou a recusa) faz com o dinheiro, dito antes do gesto.

    A mesma régua do estorno (``payment.refund``): gateway estorna sozinho;
    dinheiro e maquininha ficam a devolver por alguém da casa; cartão só
    autorizado tem a reserva desfeita, sem cobrança.

    Sem nada recebido, a frase diz isso em QUALQUER meio (WP-G06): o pedido que
    paga na retirada ou na entrega saía sem frase, e quem recusava não sabia se
    o silêncio era "nada a devolver" ou "não sei". "Não sei" continua sendo
    silêncio: ``captured_balance_q`` devolve ``None`` quando um intent não pôde
    ser lido, e ``None`` não é zero. O iFood tem frase própria
    (:func:`_ifood_cancel_money_effect`): quem devolve é ele.
    """
    empty = {"cancel_money_effect": "", "cancel_waits_for_gateway": False}
    if order.status not in {"new", "accepted", "preparing", "ready", "dispatched", "delivered", "completed"}:
        return empty
    if order.channel_ref == "ifood":
        return {**empty, "cancel_money_effect": _ifood_cancel_money_effect(order)}
    # "Não sei" nunca vira zero: o intent do pedido que o Payman não devolve cala a
    # frase. Lido ele, a régua é a do estorno do cancelamento: TODOS os intents do
    # pedido, não só os que ele referencia (um Pix pago no QR anterior também volta, #2710).
    captured_q = payment_svc.captured_balance_q(order)
    if captured_q is not None:
        held_q = payment_svc.held_by_order_q(order)
        captured_q = None if held_q is None else max(captured_q, held_q)
    if captured_q:
        return {
            "cancel_money_effect": refund_effect(captured_q, method),
            "cancel_waits_for_gateway": method in _GATEWAY_REFUND_DESTINATION,
        }
    if method == "card" and str(payment_status).lower() == "authorized":
        total = _money(order_composition.effective_total_q(order))
        return {
            "cancel_money_effect": f"A reserva de {total} no cartão do cliente será desfeita. Nada foi cobrado.",
            "cancel_waits_for_gateway": True,
        }
    if captured_q == 0:
        return {**empty, "cancel_money_effect": "Nada foi cobrado do cliente."}
    return empty


#: Até aqui o entregador ainda não cobrou o que o cliente paga na entrega.
_BEFORE_DISPATCH = frozenset({"new", "accepted", "preparing", "ready"})


def _ifood_cancel_money_effect(order: Order) -> str:
    """O dinheiro do pedido do iFood, dito antes de recusar ou cancelar (#2710, item 5).

    O que o cliente pagou pelo app (``prepaid``) volta pelo iFood, nunca pela casa. O que
    ele paga na entrega (``OFFLINE``) ainda não foi cobrado antes de o pedido sair. Sem a
    informação do iFood (``unknown``), ou depois da saída, a tela não afirma nada.
    """
    data = order.data or {}
    payments = (data.get("ifood") or {}).get("payments") or {}
    try:
        prepaid_q = int(payments.get("prepaid_q") or 0)
    except (TypeError, ValueError):
        return ""
    if prepaid_q > 0:
        return "Quem devolve o dinheiro ao cliente é o iFood."
    status = str((data.get("payment") or {}).get("status") or "")
    if status == "pending" and str(order.status) in _BEFORE_DISPATCH:
        return "Nada foi cobrado do cliente."
    return ""


def _channel_name(ref: str) -> str:
    """O nome do canal como a loja o chama ("Loja online", "PDV").

    Nunca o ref cru (identificador técnico na tela): sem cadastro ou sem nome, o
    rótulo humano das Encomendas (``preorders._fallback_channel_label``).
    """
    if not ref:
        return ""
    from shopman.backstage.projections.preorders import _fallback_channel_label
    from shopman.shop.request_memo import channel_by_ref

    channel = channel_by_ref(ref)
    return str(getattr(channel, "name", "") or "").strip() or _fallback_channel_label(ref)


def _channel_names_for(orders) -> dict[str, str]:
    """O nome de cada canal do quadro, resolvido uma vez por leitura."""
    return {ref: _channel_name(ref) for ref in {order.channel_ref or "" for order in orders}}


#: Até onde ainda é "na loja" (metros do ponto cadastrado): o pátio e a calçada.
STORE_RADIUS_METERS = 300


def _store_location() -> dict[str, float] | None:
    """As coordenadas do ``Shop`` e o raio de "na loja"; ``None`` sem cadastro."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    if shop is None or shop.latitude is None or shop.longitude is None:
        return None
    return {"lat": float(shop.latitude), "lng": float(shop.longitude), "radius_m": float(STORE_RADIUS_METERS)}


def _card_authorization_expires_iso(
    order: Order,
    method: str,
    payment_status: str,
    *,
    acceptance_deadline: tuple[str, str] | None = None,
) -> str:
    """Quando vence a autorização do cartão do pedido novo; vazio sem uma de pé.

    Um prazo só na tela, o que vem primeiro (beta 06/11): se o pedido cancela
    sozinho por falta de aceite antes de a autorização vencer, é esse relógio
    que manda, e "o cartão vence em 6 dias" ao lado de "cancela sozinho em
    15h27" só fazia o operador conciliar dois prazos.
    """
    if order.status != Order.Status.NEW or str(method or "").lower() != "card":
        return ""
    if str(payment_status or "").lower() != "authorized":
        return ""
    from shopman.shop.services import card_authorization

    deadline = card_authorization.expires_at(order)
    if deadline is None:
        return ""
    if acceptance_deadline and acceptance_deadline[1] == "cancel" and acceptance_deadline[0]:
        cancels_at = datetime.fromisoformat(acceptance_deadline[0])
        if timezone.is_naive(cancels_at):
            cancels_at = timezone.make_aware(cancels_at)
        if cancels_at <= deadline:
            return ""
    return deadline.isoformat()


def _courier_actions(order: Order, user, courier_block: dict | None, *, authorized: bool, refs=None) -> list[Action]:
    """As ações da corrida do entregador, as MESMAS no Gestor e no PDV.

    ``refs`` filtra quais (o balcão chama, chama de novo e cancela a corrida;
    cotar fica no Gestor). Sem bloco (retirada, marketplace, sem TaOn), nada.
    """
    if not courier_block:
        return []
    from shopman.shop.services.courier import dispatch_revision

    extra_actions: list[Action] = []
    extra_actions.append(Action(ref="courier-dispatch", kind="mutation", label="Chamar entregador",
        enabled=authorized and courier_block["can_dispatch"],
        reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else
            "" if courier_block["can_dispatch"] else
            courier_block.get("not_today") or "Confira o estado do pedido e da corrida antes de despachar."),
        method="POST", idempotency="required",
        confirmation={"required": True, "description": _courier_dispatch_question(order)},
        payload_schema={"base_revision": dispatch_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    extra_actions.append(Action(ref="courier-dispatch-again", kind="mutation", label="Chamar de novo",
        enabled=authorized and courier_block["can_dispatch_again"],
        reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else
            "" if courier_block["can_dispatch_again"] else
            f"Não há chamada sem resposta da {courier_block['service_name']} neste pedido."),
        method="POST", idempotency="required",
        confirmation={"required": True, "description": courier_dispatch_again_confirmation(courier_block["service_name"])},
        payload_schema={"base_revision": dispatch_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    extra_actions.append(Action(ref="courier-cancel", kind="mutation", label="Cancelar corrida",
        enabled=authorized and courier_block["can_cancel"],
        reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else
            "" if courier_block["can_cancel"] else "Confira o estado da corrida e de solicitações anteriores."),
        method="POST", idempotency="required", confirmation=courier_cancel_confirmation(order),
        payload_schema={"base_revision": dispatch_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    extra_actions.append(Action(ref="courier-custody", kind="mutation", label="Separar de novo",
        enabled=authorized and bool(courier_block.get("custody_to_separate")),
        reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else
            "" if courier_block.get("custody_to_separate") else "Esta corrida não pede o troco nem a maquininha agora."),
        method="POST", idempotency="required",
        payload_schema={"base_revision": dispatch_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    extra_actions.append(Action(ref="courier-quote", kind="mutation", label="Cotar entrega",
        enabled=authorized and courier_block["can_quote"],
        reason=("Identifique uma pessoa com permissão para gerenciar pedidos." if not authorized else
            "" if courier_block["can_quote"] else "Confira o estado do pedido e da corrida antes de cotar."),
        method="POST", idempotency="required",
        payload_schema={"base_revision": dispatch_revision(order), "expected_actor_id": getattr(user, "pk", None)}))
    return [action for action in extra_actions if refs is None or action.ref in refs]


#: Os motivos que a confirmação oferece depois do aceite: cada botão já é o
#: ``motivo_id`` que vai à central (``courier_machine.CANCEL_REASONS_OPERATOR``).
COURIER_CANCEL_REASONS = (
    (12, "O entregador não está vindo"),
    (37, "Está demorando demais"),
    (40, "Não consegui falar com o entregador"),
)


def courier_cancel_state(order: Order) -> dict:
    """O estado do cancelamento da corrida, igual no pedido e na seção Entregas."""
    from shopman.shop.services import courier

    return courier.cancel_state(order)


def courier_can_cancel(order: Order, cancel: dict | None = None) -> bool:
    """Oferecer "Cancelar corrida"? Antes da coleta e sem cancelamento em curso.

    A recusa da central (``failed``) não esconde o botão: a corrida segue
    aberta, e tentar de novo depois que ela muda de fase pode dar certo.
    """
    from shopman.shop.services import courier

    cancel = cancel if cancel is not None else courier.cancel_state(order)
    return courier.ride_cancellable(courier.get_block(order)) and cancel["state"] not in ("pending", "unknown")


def courier_cancel_confirmation(order: Order) -> dict:
    """A confirmação do cancelar: a pergunta e, depois do aceite, os motivos.

    Antes do aceite basta confirmar (a central só aceita um motivo, o 10):
    ``description`` é a pergunta e ``confirm_label`` o botão que confirma.
    Depois do aceite o motivo é o próprio botão: ``reason_question`` e
    ``consequence`` abrem a escolha, ``reasons`` leva ``{id, label}`` e a tela
    manda o ``reason_id`` escolhido.
    """
    from shopman.shop.services import courier

    name = courier.ride_name(order)
    confirmation: dict = {
        "required": True,
        "description": courier.cancel_question(order),
        "confirm_label": f"Cancelar {name}",
    }
    if courier.cancel_asks_reason(order):
        confirmation.update(
            reason_question=f"Por que cancelar {name}?",
            consequence=courier.cancel_consequence(order),
            reasons=[{"id": reason, "label": label} for reason, label in COURIER_CANCEL_REASONS],
        )
    return confirmation


def _detail_deadline(order: Order, accept=None) -> dict[str, str]:
    """O prazo da confirmação, pela mesma régua do cartão (o do iFood segue no aceite que não chegou)."""
    if order.status != Order.Status.NEW:
        external = _external_deadline(order, accept)
        return {"confirmation_deadline_iso": external[0], "confirmation_action": external[1]} if external else {}
    deadline = _confirmation_deadlines([order.ref]).get(order.ref) or _external_deadline(order)
    return {"confirmation_deadline_iso": deadline[0], "confirmation_action": deadline[1]} if deadline else {}


#: Estados em que o combinado ainda está por cumprir: passada a data, o pedido
#: "era para" aquele dia. Concluído, entregue, cancelado ou devolvido já não
#: deve nada ao relógio, e a data volta a ser só a data.
_SCHEDULE_OPEN_STATUSES = frozenset({
    Order.Status.NEW,
    Order.Status.ACCEPTED,
    Order.Status.PREPARING,
    Order.Status.READY,
    Order.Status.DISPATCHED,
})


def _schedule(order: Order, *, today: date | None = None) -> tuple[str, str]:
    """O combinado do pedido, numa frase só, e em que pé está: ``(rótulo, estado)``.

    ``today`` é o dia da leitura: a projeção que monta muitos cartões o lê uma
    vez e o passa adiante (:func:`build_two_zone_queue`); sem ele, vale o de agora.

    A MESMA frase no detalhe, no cartão, na Fila, na Tabela e no sino: uma
    função só, para nenhuma forma dizer o combinado com outras palavras.

    - ``future``: data depois de hoje. "Amanhã · A partir das 15h".
    - ``today``: hoje, COM hora combinada. "Hoje · 14h às 14h30". Hoje sem
      hora não é estado: é o pedido de agora, e o cartão não tem o que dizer.
    - ``overdue``: o dia passou e o pedido segue aberto. O passado tem nome
      próprio, "Era para ontem · A partir das 15h": a data sozinha se lê como
      se ainda fosse cumprir.
    - ``""``: nada combinado (ou já cumprido). O rótulo pode existir mesmo
      assim, para o detalhe (um concluído de sábado continua "Sáb, 14/11 · …").

    A janela sai de ``fulfillment_window.window_label`` e o dia, de
    ``promised_at`` quando há janela (sem data, o dia da venda): as mesmas
    réguas da Fila e da loja. Data sem janela diz "sem horário combinado" por
    extenso, porque o vazio pareceria esquecimento.
    """
    from shopman.shop.services.fulfillment_window import promised_at, window_label

    commitment = get_commitment_date(order)
    window = window_label((order.data or {}).get("delivery_time_slot"))
    if commitment is None and not window:
        return "", ""
    if commitment is None:
        promised = promised_at(order)
        commitment = timezone.localtime(promised).date() if promised is not None else None
    if commitment is None:
        return window, ""
    today = today or timezone.localdate()
    day = str(_commitment_date_display(commitment, today=today))
    if commitment < today and order.status in _SCHEDULE_OPEN_STATUSES:
        label = f"Era para {day}"
        return (f"{label} · {window}" if window else label), "overdue"
    label = f"{day[:1].upper()}{day[1:]} · {window or 'sem horário combinado'}"
    if commitment > today:
        return label, "future"
    if commitment == today and window:
        return label, "today"
    return label, ""


def _schedule_label(order: Order, *, today: date | None = None) -> str:
    """Quando o combinado acontece, para o detalhe: a frase de :func:`_schedule`."""
    return _schedule(order, today=today)[0]


#: Estado da corrida (``RideState``) → frase do operador (fonte única do gestor).
#: A nuance que só a letra de um serviço sabe (``G``, ``S`` da TaOn) vem de
#: :func:`delivery_services.state_detail`; ``REASSIGNING`` fala pela desistência
#: (``COURIER_REOPENED_LABEL``).
COURIER_STATE_LABELS = {
    RideState.SEARCHING: "Procurando entregador",
    RideState.GROUPED: "Junto com outra corrida",
    RideState.ASSIGNED: "Entregador a caminho da loja",
    RideState.AT_STORE: "Entregador na loja",
    RideState.ON_ROUTE: "Saiu para entrega",
    RideState.DONE: "Entregue",
    RideState.NOT_SERVED: "Não atendida",
    RideState.CANCELLED: "Corrida cancelada",
}

#: Onde a corrida já acabou: a tela não mostra mais entregador vivo.
COURIER_ENDED_STATES = frozenset({RideState.DONE, RideState.NOT_SERVED, RideState.CANCELLED})


def _courier_service_ref(order: Order) -> str:
    block = (order.data or {}).get("courier")
    return str(block.get("service") or "") if isinstance(block, dict) else ""


def _courier_service_name(block: dict) -> str:
    from shopman.shop.services import delivery_services

    return delivery_services.service_name(block)


def courier_state_label(block: dict | None) -> str:
    """A frase do estado da corrida: a nuance do serviço, ou a do estado da casa."""
    from shopman.shop.services import delivery_services

    state = delivery_services.ride_state(block)
    if state is None:
        return ""
    return delivery_services.state_detail(block) or COURIER_STATE_LABELS.get(state, "")


#: A corrida voltou a procurar depois de um entregador desistir (``courier.reopen_view``).
COURIER_REOPENED_LABEL = "Procurando outro entregador"


def _courier_dispatch_question(order: Order) -> str:
    """A pergunta do toque de confirmação: quem vem, para qual pedido, quem paga.

    O nome é o do serviço que leva a corrida, como o cadastro diz (M1b-b3, #3139).
    """
    from shopman.shop.services import courier, delivery_services

    who = delivery_services.service_name(courier.get_block(order))
    return (f"Chamar um entregador da {who} para o pedido {operator_orders.short_ref(order.ref)}? "
            "A corrida é cobrada da casa.")


def courier_no_answer_message(service: str) -> str:
    """A última chamada ao serviço ficou sem resposta: não se sabe se a corrida abriu lá."""
    return f"A {service} não respondeu à última chamada. Veja na central se a corrida abriu."


def courier_dispatch_again_confirmation(service: str) -> str:
    """A confirmação do "Chamar de novo", uma frase: o que aconteceu e o que conferir antes."""
    return (f"A {service} não respondeu à última chamada. "
            "Veja na central se a corrida abriu antes de chamar de novo.")


def _courier_block(order: Order) -> dict | None:
    """Read-model da corrida (Order.data['courier']) + ações possíveis.

    None quando entrega externa não se aplica ao pedido. Nunca falha a
    projection: qualquer erro degrada para None com log.
    """
    try:
        if not _is_delivery(order):
            return None

        from shopman.shop.services import delivery_services

        data = order.data or {}
        block = data.get("courier") if isinstance(data.get("courier"), dict) else {}
        adapter_on = delivery_services.courier_backend(block) is not None
        if not block and not adapter_on:
            return None

        from shopman.shop.services.courier import RIDE_ORDER_STATUSES, house_dispatches

        # Entrega do marketplace nunca oferece Chamar/Cotar (falha fechado; o
        # servidor recusa também em ``courier.redispatch``).
        house = house_dispatches(order)
        if not block and not house:
            return None

        ride_status = str(block.get("status") or "")
        state = delivery_services.ride_state(block)
        active = bool(block.get("ride_ref")) and state not in COURIER_ENDED_STATES
        order_can_ride = order.status in RIDE_ORDER_STATUSES

        estimate = block.get("estimate") if isinstance(block.get("estimate"), dict) else {}
        estimate_display = courier_estimate_display(estimate)
        # O nome do serviço da corrida, como o cadastro diz: as frases o usam (#3139).
        service = delivery_services.service_name(block)

        position = None
        if active and block.get("ride_ref"):
            from shopman.backstage.projections.courier_position import courier_position_projection

            point = courier_position_projection(block["ride_ref"], service=service)
            position = asdict(point) if point else None

        from shopman.shop.services.courier import (
            can_quote,
            custody_to_separate,
            failure_message,
            not_today_refusal,
            ride_health,
            unresolved_dispatch,
        )

        # Tudo o que a tela diz da corrida sai da fonte única, a mesma da página
        # Entregas (``courier.ride_health``).
        health = ride_health(order)
        # A encomenda de outro dia: chamar recusa com a frase (a régua do servidor).
        not_today = not_today_refusal(order) if order_can_ride and not active else ""
        # A falha de ABRIR a corrida mora em ``error``; o cancelamento tem o
        # estado dele (``cancel_state``), o mesmo da seção Entregas.
        error = block.get("error") if isinstance(block.get("error"), dict) else None
        cancel = health["cancel"]
        failure = health["last_failure"]
        if error is None and failure is not None:
            # A corrida que ninguém aceitou ou que foi cancelada: o pedido voltou a
            # esperar, e a tela diz por quê (a mesma frase da página Entregas).
            error = {"message": failure_message(failure), "at": failure["at"]}

        unresolved = unresolved_dispatch(order) if health["unresolved"] else None
        if unresolved is not None:
            error = {"message": courier_no_answer_message(service), "at": unresolved.updated_at.isoformat()}
        progress = health["progress"]
        tracking = health["tracking"]
        reopened = health["reopened"] if active else {"at": "", "driver": "", "reason": ""}
        status_label = courier_state_label(block)
        if state == RideState.ASSIGNED and progress["arrived_pickup_at"]:
            status_label = COURIER_STATE_LABELS[RideState.AT_STORE]
        if reopened["at"]:
            status_label = COURIER_REOPENED_LABEL
        return {
            "provider": str(block.get("provider") or ("machine" if adapter_on else "")),
            "status": ride_status,
            # O estado no vocabulário da casa (``RideState``): é o que a tela lê.
            "ride_state": state.value if state else "",
            # O nome do serviço como o cadastro diz, para a frase do operador.
            "service_name": service,
            "status_label": f"Sem resposta da {service}" if unresolved is not None else status_label,
            # O andamento, em instantes ISO; a tela conta os minutos com o relógio dela.
            **progress,
            # O entregador desistiu e a TaOn procura outro para a MESMA corrida:
            # quando, e quem saiu. Vazios fora disso.
            "reopened_at": reopened["at"],
            "reopened_driver": reopened["driver"],
            # ``withdrew`` (o entregador desistiu) ou ``transfer`` (a TaOn trocou o entregador).
            "reopened_reason": reopened["reason"],
            "active": active,
            "driver": _courier_driver(block, active=active),
            # Só o link e o código casados com a parada DESTE pedido (``courier.proven_tracking``).
            "tracking_url": tracking["url"] if active else "",
            "confirmation_code": tracking["code"],
            "estimate_display": estimate_display,
            "final_value_display": (
                _money(int(block["final_value_q"]))
                if block.get("final_value_q") is not None
                else ""
            ),
            "requested_at": str(block.get("requested_at") or ""),
            "dispatched_at": str(block.get("dispatched_at") or ""),
            "finished_at": str(block.get("finished_at") or ""),
            "attempts_count": len(block.get("attempts") or []),
            "position": position,
            "error": error,
            "can_quote": can_quote(order),
            "can_dispatch": adapter_on and house and not active and order_can_ride and unresolved is None and not not_today,
            "not_today": not_today,
            "can_dispatch_again": adapter_on and house and not active and order_can_ride and unresolved is not None,
            "can_cancel": adapter_on and courier_can_cancel(order, cancel),
            # Em que pé está o cancelamento pedido: ``{state, message, at}``
            # (``pending`` · ``unknown`` · ``failed``; vazio sem pedido).
            "cancel_state": cancel,
            # O lembrete temporário de chamar (o mesmo do cartão), ou ``None``.
            "reminder": asdict(reminder) if (reminder := courier_reminder(order)) is not None else None,
            # O que a chamada pergunta: troco da gaveta e maquininha da casa
            # que vão com o entregador da TaOn (``partner_custody_asks``).
            "custody": operator_orders.partner_custody_asks(order),
            # A TaOn retomou a corrida encerrada e o troco e a maquininha tinham
            # voltado para a casa: o que separar de novo (``courier.custody_to_separate``,
            # #2500), ou ``None``. O gesto é ``courier-custody``.
            "custody_to_separate": custody_to_separate(order),
            # O pedido mudou depois da chamada e a observação da corrida (o que
            # cobrar na porta) ficou para trás: ``{sent, current, collected}``.
            "charge_outdated": health["charge_outdated"],
        }
    except Exception:
        logger.debug("orders.courier_block_failed order=%s", order.ref, exc_info=True)
        return None


def _courier_driver(block: dict, *, active: bool) -> dict | None:
    """O entregador da corrida, com a foto enquanto ela vive (#2736).

    A foto é a MESMA da página Entregas: servida pelo servidor
    (``DeliveryDriverPhotoView``), só em cache e só com a corrida viva
    (decisão do dono, LGPD). Sem foto, ``photo_url`` vazio e a tela mostra o ícone.
    """
    from shopman.shop.services import courier

    driver = block.get("driver")
    if not isinstance(driver, dict):
        return None
    ride_id = str(block.get("ride_ref") or "")
    has_photo = active and bool(ride_id) and courier.has_driver_photo(ride_id)
    return {**driver, "photo_url": f"/api/v1/backstage/deliveries/{ride_id}/driver-photo/" if has_photo else ""}


def _cancel_reasons(channel_ref: str = "") -> tuple[CancelReasonProjection, ...]:
    """A lista única; no detalhe de um pedido do iFood, só os motivos que ele oferece."""
    from shopman.shop.policies.ifood_cancel_reasons import offered_on_ifood
    from shopman.shop.services.cancel_reasons import OPERATOR_CANCEL_REASONS

    return tuple(
        CancelReasonProjection(
            key=r.key, label=r.label, customer_text=r.customer_text, offered_on_ifood=offered_on_ifood(r.key),
        )
        for r in OPERATOR_CANCEL_REASONS
        if channel_ref != "ifood" or offered_on_ifood(r.key)
    )


def _kitchen_note_tags(order: Order) -> tuple[str, ...]:
    """Os atalhos da nota da cozinha que valem para este pedido (Admin/Unfold).

    O Caixa anexa um com um toque no Gestor, e a nota sai no ticket da Cozinha. Cada
    atalho diz a que categorias e produtos se aplica; sem nenhum, vale para todos. O
    pedido mostra só os que valem para algum item dele (decisão do dono, 21/11/2026:
    "Sem cebola" num pedido de pão não ajuda ninguém). Nunca derruba a projeção.
    """
    try:
        from shopman.offerman.models import CollectionItem

        from shopman.shop.models import KitchenNoteTag

        skus = {item.sku for item in order.items.all()}
        collection_ids = set(
            CollectionItem.objects.filter(product__sku__in=skus).values_list("collection_id", flat=True)
        )
        out = []
        for tag in KitchenNoteTag.objects.prefetch_related("collections", "products"):
            tag_collections = {collection.pk for collection in tag.collections.all()}
            tag_skus = {product.sku for product in tag.products.all()}
            if not tag_collections and not tag_skus:
                out.append(tag.label)
            elif tag_skus & skus or tag_collections & collection_ids:
                out.append(tag.label)
    except Exception:
        logger.debug("orders.kitchen_note_tags_read_failed", exc_info=True)
        return ()
    return tuple(out)


#: Segmentos RFM que mudam o atendimento, com rótulo e tom já resolvidos.
#:
#: Fora deste mapa (``regular``, ``recent_customer``, sem segmento) não há selo:
#: badge que aparece em todo pedido vira moldura, e o operador para de lê-la. O
#: rótulo vem de ``RFM_SEGMENTS`` no Guestman — o mesmo que o Admin e o público
#: de campanha mostram —, então esta tabela guarda só o TOM.
_SEGMENT_TONES: dict[str, str] = {
    "champion": "success",
    "loyal_customer": "success",
    "at_risk": "warning",
    "lost": "warning",
}


def _customer_profile(order: Order) -> CustomerProfileProjection | None:
    """Quem é este cliente, do que já está materializado (WP-360).

    Uma cliente real fez pedido no alpha e o detalhe do Gestor não sabia dizer se
    ela era nova ou de casa. O dado existia — em ``CustomerInsight``, no cadastro
    e no histórico do Orderman —, só não chegava à tela de quem atende.

    Três leituras, cada uma com seu dono, nenhuma recalcula nada:

    * o **cadastro** (nota, restrição alimentar, aniversário), que é o mesmo que
      o PDV mostra ao balcão;
    * o **insight** (contagem, ticket médio, favorito, segmento RFM), materializado
      pelo ``InsightService`` — e ausente é estado NORMAL, não erro;
    * o **pedido anterior**, que responde "quando comprou pela última vez" sem
      confundir a resposta com o pedido aberto na tela.

    Devolve ``None`` quando não há cliente identificado: a tela omite o bloco em
    vez de desenhar um perfil vazio.
    """
    data = order.data or {}
    customer_ref = str(
        data.get("customer_ref")
        or (data.get("customer") or {}).get("ref")
        or ""
    ).strip()
    if not customer_ref:
        return None

    try:
        from shopman.guestman.models import Customer

        customer = Customer.objects.filter(ref=customer_ref).first()
    except Exception:
        logger.debug("order_queue.customer_profile_read_failed ref=%s", order.ref, exc_info=True)
        return None
    if customer is None:
        return None

    # ``insight`` é OneToOne reverso e opcional: sem insight (ou sem o app
    # contrib instalado) o descritor levanta AttributeError, e o getattr devolve
    # None — o mesmo guard de ``shop.services.audience._profile``.
    insight = getattr(customer, "insight", None)

    previous_at = _previous_order_at(customer_ref, exclude_ref=order.ref)
    total_orders = int(getattr(insight, "total_orders", 0) or 0)
    # "Primeira compra" é afirmação, e as duas fontes precisam concordar antes de
    # fazê-la. O histórico é indexado por ``data.customer_ref`` — o vínculo
    # canônico —, então um pedido que só carregue ``customer.ref`` devolve
    # histórico vazio e faria a tela chamar de novato um cliente de dez anos. O
    # insight desempata: com contagem acima de um, não é a primeira vez, mesmo
    # sem saber QUANDO foi a anterior.
    is_first_order = previous_at is None and total_orders <= 1

    segment = str(getattr(insight, "rfm_segment", "") or "")
    segment_tone = _SEGMENT_TONES.get(segment, "")
    # Na primeira compra o insight só conhece ESTE pedido: o "ticket médio" é o
    # total dele e o "costuma levar" é o que está no carrinho agora. Dizer isso
    # seria afirmar hábito de quem ainda não tem (pedido iFood 3417, 12/11).
    average_ticket_q = 0 if is_first_order else int(getattr(insight, "average_ticket_q", 0) or 0)

    return CustomerProfileProjection(
        is_first_order=is_first_order,
        total_orders=total_orders,
        orders_label=_orders_label(total_orders, is_first_order=is_first_order),
        last_order_display=_elapsed_since_label(previous_at),
        # Vazio, não "R$ 0,00": sem insight ainda não SABEMOS o ticket, e zero
        # afirmaria que o cliente não gasta nada.
        average_ticket_display=_money(average_ticket_q) if average_ticket_q > 0 else "",
        favorite_product="" if is_first_order else _favorite_product(insight),
        segment=segment if segment_tone else "",
        segment_label=_segment_label(segment) if segment_tone else "",
        segment_tone=segment_tone,
        notes=str(getattr(customer, "notes", "") or "").strip(),
        **_customer_registry_fields(customer),
    )


def _customer_registry_fields(customer) -> dict:
    """Restrição alimentar e aniversário, com a MESMA leitura do PDV.

    São as duas coisas do cadastro que mudam o atendimento na hora, e o balcão já
    as lê — reusar os helpers do ``pos`` é o que mantém as duas telas dizendo a
    mesma coisa sobre a mesma pessoa. Import tardio: só o detalhe do pedido paga
    o custo, e nunca há ciclo entre as projections.
    """
    try:
        from shopman.backstage.projections.pos import (
            _birthday_projection,
            _dietary_restrictions,
        )

        birthday = _birthday_projection(customer)
        return {
            "dietary_restrictions": _dietary_restrictions(customer),
            "birthday_display": str(birthday.get("birthday_display") or ""),
            "is_birthday_today": bool(birthday.get("is_birthday_today")),
        }
    except Exception:
        logger.debug("order_queue.customer_registry_read_failed", exc_info=True)
        return {"dietary_restrictions": "", "birthday_display": "", "is_birthday_today": False}


def _previous_order_at(customer_ref: str, *, exclude_ref: str):
    """Quando este cliente comprou ANTES do pedido aberto na tela.

    O ``last_order_at`` do insight não serve aqui: ele é recalculado no
    ``customer.ensure`` deste mesmo pedido, então no detalhe dele diria "última
    compra hoje" — que é verdade sobre o pedido que o operador está lendo, e
    ruído sobre a relação com o cliente. Lê o contrato público de histórico do
    Orderman (o mesmo do PDV) e pula o pedido atual.
    """
    try:
        from shopman.orderman.services import CustomerOrderHistoryService

        recent = CustomerOrderHistoryService.list_customer_orders(customer_ref, limit=3)
    except Exception:
        logger.debug("order_queue.previous_order_read_failed ref=%s", exclude_ref, exc_info=True)
        return None
    for record in recent:
        if record.order_ref != exclude_ref and record.ordered_at:
            return record.ordered_at
    return None


def _orders_label(total_orders: int, *, is_first_order: bool) -> str:
    """"Primeira compra" / "12 pedidos" — vazio quando não há contagem confiável.

    A contagem vem do insight, que pode não existir. Cliente com pedido anterior e
    sem insight cai no vazio de propósito: dizer "primeira compra" seria falso, e
    "0 pedidos" seria pior.
    """
    if is_first_order:
        return "Primeira compra"
    if total_orders > 1:
        return f"{total_orders} pedidos"
    return ""


def _elapsed_since_label(moment) -> str:
    """"hoje" / "ontem" / "há 12 dias" / "há 4 meses" / "há 2 anos"."""
    if not moment:
        return ""
    try:
        days = (timezone.localdate() - timezone.localtime(moment).date()).days
    except Exception:
        logger.debug("order_queue.elapsed_label_failed", exc_info=True)
        return ""
    if days <= 0:
        return "hoje"
    if days == 1:
        return "ontem"
    if days < 60:
        return f"há {days} dias"
    if days < 730:
        months = days // 30
        return f"há {months} meses"
    years = days // 365
    return "há 1 ano" if years == 1 else f"há {years} anos"


def _favorite_product(insight) -> str:
    """Nome do produto mais comprado, do topo de ``CustomerInsight.favorite_products``.

    A lista é ``[{sku, name, qty, last_order_at}]`` (o help_text do campo é o
    contrato). Sem nome, o SKU serve — o operador reconhece os dois.
    """
    products = getattr(insight, "favorite_products", None) or []
    if not isinstance(products, list) or not products:
        return ""
    top = products[0]
    if not isinstance(top, dict):
        return ""
    return str(top.get("name") or top.get("sku") or "").strip()


def _segment_label(segment: str) -> str:
    """Rótulo pt-BR do segmento — de ``RFM_SEGMENTS``, o mesmo do Admin."""
    try:
        from shopman.guestman.contrib.insights.models import RFM_SEGMENTS

        return dict(RFM_SEGMENTS).get(segment, "")
    except (ImportError, RuntimeError):
        return ""


def build_order_card(order: Order, *, user=None) -> OrderCardProjection:
    """O cartão de UM pedido, fora do quadro: lê sozinho o que o quadro lê em lote."""
    return _build_card(order, user=user)


def board_rail_counts() -> dict[str, int]:
    """Os selos do rail do Gestor fora do quadro (G26): pedidos novos e o que está na Saída.

    As MESMAS réguas do quadro (``build_two_zone_queue``): balcão do PDV fica de
    fora, todo pedido novo conta na Entrada (inclusive a encomenda, que tem prazo
    de aceite), e a Saída soma o pronto e o que saiu para entrega. Só contagem, sem montar cartão nenhum.
    """
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    orders = [
        order for order in Order.objects.filter(
            status__in=(Order.Status.NEW, Order.Status.READY, Order.Status.DISPATCHED, Order.Status.DELIVERED),
        )
        if not is_pos_counter_order(order)
    ]
    intake = sum(1 for order in orders if order.status == Order.Status.NEW)
    exit_ = sum(1 for order in orders if order.status != Order.Status.NEW)
    return {"intake": intake, "exit": exit_}


def build_two_zone_queue(*, user=None) -> TwoZoneQueueProjection:
    """Build the operator queue grouped by the next physical action.

    Um relógio por leitura: ``now`` e ``today`` são lidos aqui, uma vez, e
    passados a cada cartão e a cada régua. Lido de novo a cada pergunta, a
    leitura que cruzava a meia-noite via a mesma encomenda "de amanhã" numa
    lista e "de hoje" na outra, e ela saía das duas por um ciclo.
    """
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    now = timezone.now()
    today = timezone.localtime(now).date()

    # Balcão é propriedade do PDV/KDS: nunca cria trabalho para o Gestor. O
    # filtro em Python alcança também o pequeno intervalo do commit em que o
    # modo já está no snapshot, mas ainda não foi carimbado em Order.data.
    all_orders = [
        order
        for order in Order.objects.filter(
            Q(status__in=ACTIVE_STATUSES) | Q(channel_ref="ifood", data__ifood__handshake_pending=True)
        ).order_by("created_at")
        if not is_pos_counter_order(order)
    ]

    # The queue only reads quantity/name/SKU; no full item models or metadata needed.
    # Pedido + ajustes: o pedido alterado tem a lista dele lida do ajuste, não
    # das linhas — somar as duas no card faria o resumo mentir sobre a sacola.
    adjusted = order_composition.adjusted_order_ids([order.pk for order in all_orders])
    items_by_order = defaultdict(list)
    plain = [order.pk for order in all_orders if order.pk not in adjusted]
    for item in OrderItem.objects.filter(order_id__in=plain).values_list("order_id", "qty", "name", "sku", named=True):
        items_by_order[item.order_id].append(item)
    for order in all_orders:
        order._queue_items = (
            order_composition.effective_items(order)
            if order.pk in adjusted
            else items_by_order[order.pk]
        )

    from shopman.shop.services import waitlist

    waitlist_states = waitlist.states_for(all_orders)
    payment_reads = payment_svc.read_payments_for(all_orders)
    # A última tentativa de DANFE de cada pedido e o destino: uma leitura só.
    danfe_reads = order_danfe.read_for(all_orders)
    # A saúde da reserva de cada pedido (WP-G08): uma leitura para o painel inteiro.
    promise_reads = order_promise.read_for(all_orders, now=now)
    from shopman.backstage.models import DeliveryDevice
    from shopman.backstage.services.delivery_devices import PREFIX

    devices = list(DeliveryDevice.objects.select_related("current_order"))
    for order in all_orders:
        order._delivery_devices = devices
    channel_configs = _channel_configs_for(all_orders)
    channel_names = _channel_names_for(all_orders)
    cash_context = _cash_settlement_context(all_orders)
    fiscal_states = _fiscal_states_for(all_orders)
    # Rótulos canônicos resolvidos uma vez por chave nesta leitura, sem cache
    # entre requests: uma edição de copy aparece na próxima projeção.
    status_labels = {status: order_status_label(status) for status in {order.status for order in all_orders}}
    methods = {(order.data.get("payment") or {}).get("method", "") for order in all_orders}
    methods.update(t.get("method", "") for order in all_orders for t in (order.data or {}).get("payment", {}).get("tenders", []))
    method_labels = {method: payment_method_label(method) for method in methods}
    new_orders = [o for o in all_orders if o.status == "new"]
    deadlines = _confirmation_deadlines([o.ref for o in new_orders])
    from shopman.shop.services import ifood_accept_sync

    # O aceite que não chegou ao iFood (P1-3): uma consulta para a tela inteira.
    accept_batch = ifood_accept_sync.latest_directives(
        [o.ref for o in all_orders if o.channel_ref == "ifood" and o.status != "new"]
    )
    # Uma consulta ao livro para todos os cards: o troco que saiu e voltou.
    courier_change = operator_orders.courier_change_by_order([o.ref for o in all_orders if _is_delivery(o)])
    # Todo pedido NOVO mora na Entrada, qualquer que seja a data: aceitar tem prazo
    # (60 min na encomenda, dono 09/11) e sem aceite o pedido se cancela e
    # estorna. Escondê-lo em "Agendados" fazia o operador perder o prazo (beta
    # 09/11). Aceita, a encomenda de data futura sai do dia e vai para "Agendados";
    # o despertador (preorder.activate) a devolve ao fluxo na data (WP-D).
    intake = tuple(
        _build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user, deadline=deadlines.get(o.ref))
        for o in new_orders
    )
    prep_orders = [o for o in all_orders if o.status in ("accepted", "preparing")]
    ready_orders = [o for o in all_orders if o.status == "ready"]
    # A Cozinha em cada pedido do Preparo e da Saída, numa leitura só (SUITE-UX
    # §15: a Saída da Cozinha mora no Gestor, com o progresso por estação).
    from shopman.backstage.projections.kds import kitchen_station_chips

    kitchen = kitchen_station_chips([o for o in (*prep_orders, *ready_orders) if not _is_future_preorder(o, today=today)])
    ready_moments = ready_moments_for(ready_orders)
    expectation = prep_expectation(now=now)
    day_cards = tuple(_build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user, courier_change=courier_change, kitchen_chips=kitchen, expectation=expectation) for o in prep_orders if not _is_future_preorder(o, today=today))
    # A encomenda do dia que ainda espera a hora da Cozinha não é trabalho do quadro
    # (dono, 18/11/2026): mora na lista "Encomendas", abaixo das colunas, com "Vai
    # para a Cozinha às 17h15", e só entra em "Em preparo" quando chega a hora dela.
    prep = tuple(card for card in day_cards if not card.kitchen_release_at_iso)
    waiting_today = sorted(
        (card for card in day_cards if card.kitchen_release_at_iso),
        key=lambda card: card.kitchen_release_at_iso,
    )
    # Só a encomenda já aceita e ainda antes da expedição vira "Agendados" (a nova
    # está na Entrada); ready/dispatched/delivered seguem nas colunas de expedição
    # mesmo que a data combinada seja futura.
    future_preorders = [
        o for o in all_orders
        if o.status in ("accepted", "preparing") and _is_future_preorder(o, today=today)
    ]
    future_cards = tuple(
        _build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user)
        for o in sorted(future_preorders, key=lambda o: (get_commitment_date(o), o.created_at))
    )
    # Hoje primeiro (pela hora em que cada uma chega à Cozinha), depois os próximos dias.
    preorders = (*waiting_today, *future_cards)
    preparing_count = len(prep)

    expedition_pickup = tuple(_build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user, kitchen_chips=kitchen, ready_moments=ready_moments) for o in ready_orders if not _is_delivery(o))
    expedition_delivery = tuple(_build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user, courier_change=courier_change, kitchen_chips=kitchen, ready_moments=ready_moments) for o in ready_orders if _is_delivery(o))
    expedition_delivery_transit = tuple(
        _build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user, courier_change=courier_change)
        for o in all_orders
        if o.status in ("dispatched", "delivered")
    )

    # O dia de serviço é o dia civil da loja (laudo do Gestor, P2-08): a casa que
    # fecha depois da meia-noite vê as encomendas de "amanhã" entrarem no turno em
    # curso à 0h. A régua do dia mora no shop e no Core (o lifecycle, o commit e
    # ``is_preorder`` medem "hoje" pelo dia civil), e mudá-la só aqui faria o
    # Gestor discordar da Cozinha e do PDV. Quando o shop tiver o dia de serviço
    # (a hora de corte da loja), ele entra por ``today``, que é lido uma vez só.
    service_day = today
    service_day_ends_at = timezone.make_aware(
        datetime.combine(service_day + timedelta(days=1), time.min),
        timezone.get_current_timezone(),
    )

    return TwoZoneQueueProjection(
        equipment_out=_equipment_out(user=user, devices=devices),
        ride_candidates=(ride_candidates := _ride_candidates([*ready_orders, *prep_orders], today=today)),
        ride_action=_ride_action_for(ride_candidates, [*ready_orders, *prep_orders], user=user),
        ride_suggestions=len(_plan_for_board()["suggestions"]) if len(ride_candidates) >= 2 else 0,
        equipment_available=tuple(EquipmentOptionProjection(ref=PREFIX + str(device.ref), label=device.label)
                                  for device in devices if device.active and device.current_order_id is None),
        ifood_negotiation_orders=tuple(
            _build_card(o, accept_batch=accept_batch, fiscal_states=fiscal_states, status_labels=status_labels, method_labels=method_labels, cash_context=cash_context, channel_config=channel_configs.get(o.channel_ref), payment_reads=payment_reads, waitlist_states=waitlist_states, danfe_reads=danfe_reads, promise_reads=promise_reads, now=now, channel_names=channel_names, user=user)
            for o in all_orders if o.channel_ref == "ifood" and ((o.data or {}).get("ifood") or {}).get("handshake_pending")
        ),
        intake=intake,
        preparing_count=preparing_count,
        prep=prep,
        expedition_pickup=expedition_pickup,
        expedition_delivery=expedition_delivery,
        expedition_delivery_transit=expedition_delivery_transit,
        expedition_delivery_count=len(expedition_delivery) + len(expedition_delivery_transit),
        expedition_count=len(expedition_pickup)
        + len(expedition_delivery)
        + len(expedition_delivery_transit),
        total_count=len(all_orders),
        service_day=service_day.isoformat(),
        service_day_ends_at=service_day_ends_at.isoformat(),
        preorders=preorders,
        preorders_count=len(preorders),
        awareness=build_queue_awareness(user=user, now=now, expectation=expectation),
        cancel_reasons=_cancel_reasons(),
    )


# ── Internals ──────────────────────────────────────────────────────────


def _channel_display_id(order) -> str:
    """O número do canal, SÓ quando o ref não o carrega — senão seria dizer duas vezes."""
    display_id = str(((order.data or {}).get("ifood") or {}).get("display_id") or "").strip()
    if not display_id:
        return ""
    return "" if str(order.ref or "").upper().endswith(f"-{display_id.upper()}") else display_id


def _external_deadline(order, accept=None) -> tuple[str, str] | None:
    """Prazo do marketplace (ISO, ação) enquanto o iFood ainda espera a confirmação.

    Gravado na ingestão em ``data.ifood.confirm_by``. Vencido, quem cancela é o
    marketplace — daí a ação ser ``cancel``, igual ao timer de ``auto_cancel``.
    Vale em ``new`` e também depois do aceite local enquanto o ``confirm`` não
    chegou ao iFood (``accept.failed``, P1-3): para o iFood o pedido continua sem
    aceite, e o relógio dele continua correndo com a cozinha trabalhando.
    """
    if order.status != "new" and not (accept is not None and accept.failed):
        return None
    confirm_by = str(((order.data or {}).get("ifood") or {}).get("confirm_by") or "").strip()
    return (confirm_by, "cancel") if confirm_by else None


def _ifood_accept_fields(order, sync) -> dict:
    """Os campos do aviso "o iFood ainda não recebeu o aceite" (card e detalhe)."""
    if not sync.failed:
        return {}
    from shopman.shop.services import ifood_accept_sync

    return {"ifood_accept_failed": True, "ifood_accept_notice": ifood_accept_sync.notice_text(order)}


def _ifood_accept_actions(order, sync, user) -> tuple[Action, ...]:
    """``ifood-accept-retry``: reenvia o ``confirm``. Só existe quando o aceite falhou."""
    if not sync.failed:
        return ()
    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
    return (Action(
        ref="ifood-accept-retry", kind="mutation", label="Tentar de novo", priority="primary",
        enabled=authorized,
        reason="" if authorized else "Identifique uma pessoa com permissão para gerenciar pedidos.",
        method="POST", idempotency="required",
        payload_schema={"base_revision": sync.revision, "expected_actor_id": getattr(user, "pk", None)},
    ),)


def _confirmation_deadlines(refs: list[str]) -> dict[str, AcceptanceTimer]:
    """{order_ref: (expires_at_iso, action, timeout_minutes)} dos timers de confirmação pendentes.

    Batch (sem N+1): busca os directives confirmation.timeout queued uma vez e
    filtra em Python (normalmente há poucos pendentes)."""
    if not refs:
        return {}
    from shopman.orderman.models import Directive

    out: dict[str, AcceptanceTimer] = {}
    # Filtra no DB pelos refs em questão (não traz TODOS os timers queued) — casa
    # a query ao conjunto pequeno de pedidos NEW mesmo se a fila acumular.
    directives = (
        Directive.objects.filter(
            topic="confirmation.timeout", status="queued", payload__order_ref__in=list(refs)
        )
        .order_by("available_at", "id")
    )
    for d in directives:
        ref = (d.payload or {}).get("order_ref")
        if ref and ref not in out:
            payload = d.payload or {}
            minutes = payload.get("timeout_minutes")
            out[ref] = AcceptanceTimer(
                str(payload.get("expires_at") or ""),
                str(payload.get("action") or ""),
                minutes if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes > 0 else 0,
            )
    return out


#: O gesto de quem inicia o preparo antes de a encomenda chegar à Cozinha.
EARLY_START_LABEL = "Adiantar"


def _kitchen_clock(order: Order, now: datetime) -> tuple[datetime | None, datetime | None]:
    """A hora da Cozinha da encomenda: ``(vai chegar às, chegou às)``.

    ``chegou às`` é o carimbo que o lifecycle grava quando a encomenda entra no
    fluxo do dia (``Order.data["kitchen_released_at"]``). ``vai chegar às`` só
    existe para o pedido ACEITO que ainda espera HOJE: a régua é a do lifecycle
    (``awaits_kitchen_release`` decide se espera, ``preorder_activation_at`` diz
    até quando), lida sem alterar nada. O nome privado é a régua única de quem
    espera; repeti-la aqui seria uma segunda conta. Encomenda de outro dia não
    recebe a frase: o card dela já diz o dia e a janela (``_schedule``). O
    agendado do iFood fica de fora: ele segue o relógio do próprio iFood.
    """
    from shopman.shop import lifecycle
    from shopman.shop.services import ifood_schedule

    released = _parse_iso((order.data or {}).get(lifecycle.KITCHEN_RELEASED_AT_KEY))
    if released is not None or order.status != Order.Status.ACCEPTED:
        return None, released
    if ifood_schedule.is_scheduled(order):
        # O agendado do iFood tem o relógio dele (``ifood_schedule_label``) e o
        # lifecycle não o adianta (``release_preorder_now`` recusa): prometer
        # "Adiantar" aqui seria oferecer um gesto que não acontece.
        return None, None
    try:
        if not lifecycle.awaits_kitchen_release(order):
            return None, None
        release_at, _target = lifecycle.preorder_activation_at(order)
    except Exception:
        # Ausência de resposta não é resposta: sem a régua, o card não promete hora.
        logger.warning("order_queue.kitchen_clock_failed order=%s", order.ref, exc_info=True)
        return None, None
    if release_at is None or timezone.localtime(release_at).date() != timezone.localtime(now).date():
        return None, None
    return release_at, None


def _kitchen_release_label(release_at: datetime | None) -> str:
    """A frase de quem espera a hora da Cozinha, a mesma no card e no detalhe."""
    return f"Vai para a Cozinha às {format_clock(release_at)}" if release_at else ""


def _early_start_actions(actions) -> tuple:
    """As ações do pedido que ainda espera a hora da Cozinha.

    O gesto de iniciar existe, mas não é o que a tela pede agora: sai do primeiro
    plano e ganha o nome do que faz (antecipa a chegada à Cozinha). Card e
    detalhe passam por aqui, para o mesmo gesto ter um nome só.
    """
    return tuple(
        replace(action, label=EARLY_START_LABEL, priority="secondary")
        if action.ref == "advance" and action.priority == "primary"
        else action
        for action in actions
    )


def _first_name(customer_name: str) -> str:
    """O primeiro nome, quando o "nome" é mesmo um nome (não telefone, não o nome oculto)."""
    clean = str(customer_name or "").strip()
    if not clean or clean == _MASKED_NAME_LABEL or any(char.isdigit() for char in clean):
        return ""
    return clean.split()[0]


def _exit_gesture_actions(order: Order, actions, *, customer_name: str) -> tuple:
    """O gesto da saída com um nome só: "Entregar a Ana", "Despachar M09".

    Entregar ao cliente no balcão e despachar a entrega tinham um nome em cada
    forma do mesmo pedido: "Entregar a Ana" no Painel (a tela trocava o rótulo),
    "Marcar como retirado" na Tabela, "Marcar saída para entrega" no detalhe. O
    nome agora sai daqui, e toda forma lê o rótulo da ação. É o verbo que a
    Saída fala (``suite-vocabulary``: entregar no balcão, despachar a entrega),
    com quem recebe ou com o código do pedido. Cartão e detalhe passam por
    aqui; os outros passos seguem com o rótulo de ``operational_actions``.
    """
    target = operator_orders.next_status_for(order)
    code = operator_orders.short_ref(order.ref)
    if target == Order.Status.DISPATCHED:
        label = f"Despachar {code}"
    elif order.status == Order.Status.READY and target == Order.Status.COMPLETED and not _is_delivery(order):
        name = _first_name(customer_name)
        label = f"Entregar a {name}" if name else f"Entregar {code}"
    else:
        return tuple(actions)
    return tuple(replace(action, label=label) if action.ref == "advance" else action for action in actions)


def _promise_of(order: Order, reads=None) -> order_promise.OrderPromiseProjection | None:
    """A promessa deste pedido: da leitura do painel, ou lida agora para um pedido só."""
    if reads is None:
        reads = order_promise.read_for([order])
    return reads.get(order.ref)


def _waits_batch(promise, advance_block, next_status: str) -> bool:
    """O preparo deste pedido espera o lote ficar pronto?

    Só quando nada mais barra o avanço (o pagamento e o dia da encomenda vêm
    antes, cada um com a sua frase) e o próximo passo é justamente o preparo.
    """
    return bool(
        promise is not None
        and promise.blocks_start
        and not advance_block
        and next_status == Order.Status.PREPARING
    )


def batch_wait_refusal(order: Order) -> str:
    """A frase que recusa o "Iniciar preparo" de quem espera o lote, ou ``""``.

    A mesma régua do cartão e do detalhe (:func:`_waits_batch` sobre a promessa
    do pedido), para o comando de avançar do Gestor recusar o que a tela não
    oferece: sem ela, um POST direto iniciava o preparo de pão que ainda não
    existe (#2721). Mora aqui, e não no gate do ``shop``, porque a promessa é
    leitura do backstage e o ``shop`` nunca a importa.
    """
    advance_block = operator_orders.gestor_advance_block(order)
    next_status = operator_orders.next_status_for(order) if not advance_block else ""
    if next_status != Order.Status.PREPARING:
        return ""
    promise = _promise_of(order)
    if not _waits_batch(promise, advance_block, next_status):
        return ""
    return order_promise.batch_wait_reason(promise)


def _lapsed_payment_actions(actions, block_label: str, *, can_call: bool) -> tuple:
    """O avanço travado pela cobrança vencida diz o fato, não a espera (``LAPSED_ADVANCE_REASONS``).

    ``can_call``: o pedido tem um telefone para chamar. Sem ele, o botão do WhatsApp
    some e a frase manda só cancelar.
    """
    fact = LAPSED_ADVANCE_REASONS.get(block_label)
    if not fact:
        return tuple(actions)
    reason = f"{fact} {LAPSED_NEXT_STEP if can_call else LAPSED_NEXT_STEP_NO_CONTACT}"
    return tuple(
        replace(action, reason=reason) if action.ref == "advance" and not action.enabled else action
        for action in actions
    )


def _batch_wait_actions(actions, reason: str) -> tuple:
    """As ações do pedido que espera o lote: o gesto de iniciar existe, desligado e com o motivo."""
    return tuple(
        replace(action, enabled=False, reason=action.reason or reason) if action.ref == "advance" else action
        for action in actions
    )


_PERMISSION_REASON = "Identifique uma pessoa com permissão para gerenciar pedidos."


def _manages_orders(user) -> bool:
    return bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))


def _open_production_action(promise, user) -> Action | None:
    """ "Abrir a Produção": o plano do dia que ainda pode cobrir o item (sem lote, ou lote curto).

    Só para quem opera a Produção (a mesma pergunta do tile da Central) e com o
    endereço do app configurado. Sem um dos dois a ação não vem: a frase do
    próximo passo ("Peça à Produção para planejar.") segue dizendo o que fazer.
    """
    from urllib.parse import urlencode

    from shopman.backstage.permissions import can_operate_production
    from shopman.backstage.projections.hub import surface_link

    day = order_promise.production_day(promise)
    if not day or user is None or not getattr(user, "is_active", False) or not can_operate_production(user):
        return None
    href = surface_link("production", f"plan?{urlencode({'date': day})}")
    if not href:
        return None
    return Action(
        ref=order_promise.ACTION_OPEN_PRODUCTION, kind="link", label="Abrir a Produção", href=href, idempotency="none",
    )


#: O "Resolver" visto do balcão: a saída é o diálogo do Gestor, aberto no pedido.
POS_RESOLVE_LABEL = "Resolver no Gestor"
POS_RESOLVE_HASH = "#resolve"
_POS_RESOLVE_UNCONFIGURED = "O endereço do Gestor não está configurado."


def _pos_promise(order: Order, authorized: bool) -> order_promise.OrderPromiseProjection | None:
    """A promessa em risco nas Encomendas do PDV, ou ``None`` quando ela está de pé.

    O fato é o mesmo do Gestor (``order_promise.read_for``); a saída é uma só,
    "Resolver no Gestor", que abre o pedido lá com o diálogo das escolhas
    (``#resolve``). Trocar, remarcar e cancelar continuam no balcão, nos gestos
    que ele já tem; o aviso ao cliente e a escolha moram no Resolver.
    """
    from shopman.backstage.projections.hub import surface_link

    promise = _promise_of(order)
    if promise is None or promise.state != order_promise.STATE_AT_RISK:
        return None
    href = surface_link("gestor", f"{quote(order.ref, safe='')}{POS_RESOLVE_HASH}")
    reason = "" if authorized else _PERMISSION_REASON
    if not reason and not href:
        reason = _POS_RESOLVE_UNCONFIGURED
    resolve = Action(
        ref=order_promise.ACTION_RESOLVE, kind="link", label=POS_RESOLVE_LABEL,
        href=href if not reason else "", enabled=not reason, reason=reason, idempotency="none", priority="primary",
    )
    return order_promise.with_actions(promise, (resolve,))


def _promise_actions(user, promise) -> tuple[Action, ...]:
    """As saídas do aviso "Promessa em risco": as mesmas no cartão e no detalhe.

    "Resolver" abre o diálogo onde moram as escolhas (trocar, remarcar, tirar o
    item, cancelar) e a mensagem ao cliente: a ação não leva endereço nem dado
    do cliente (#2434), a tela busca ``orders/<ref>/promise-resolution/`` ao
    abrir. Quem não gerencia pedidos a recebe travada, com o motivo.

    "Abrir a Produção" só vem quando algum item ela ainda resolve e a conta a
    opera. A principal (``priority="primary"``, a primeira) é ela quando TUDO o
    que falta a Produção resolve (``promise.recommended_action``) e a ação veio;
    senão é "Resolver". Sempre há uma principal.
    """
    authorized = _manages_orders(user)
    resolve = Action(
        ref=order_promise.ACTION_RESOLVE, kind="dialog", label="Resolver",
        enabled=authorized, reason="" if authorized else _PERMISSION_REASON, idempotency="none",
    )
    opening = _open_production_action(promise, user)
    if opening is None:
        return (replace(resolve, priority="primary"),)
    if promise.recommended_action == order_promise.ACTION_OPEN_PRODUCTION:
        return (replace(opening, priority="primary"), resolve)
    return (replace(resolve, priority="primary"), opening)


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _is_future_preorder(order: Order, *, today: date | None = None) -> bool:
    """Data combinada depois de hoje: a régua única do shop (#3163).

    ``order_helpers.is_for_a_later_day``. ``today`` é o dia da leitura de quem
    chama (ver lá por quê).
    """
    from shopman.shop.services.order_helpers import is_for_a_later_day

    return is_for_a_later_day(order, today=today)


def _commitment_date_display(commitment, *, today: date | None = None) -> str:
    """Display curto da data combinada para o badge do card do operador."""
    from shopman.backstage.projections.order_attention import commitment_day_label

    return commitment_day_label(commitment, today=today)


_WAITLIST_LABELS = {
    "fermata": "Na fila de espera",
    "confirming": "Aguardando o cliente confirmar",
    "confirmed": "Confirmado pelo cliente",
    "released": "Vaga liberada",
}


def _waitlist_badge(order: Order, *, states: dict[str, str] | None = None) -> tuple[str, str]:
    """Estado da fila de espera para o cartão: ``(estado, rótulo)`` (WP-P2E).

    Pedido esperando fornada não é pedido travado, e a diferença precisa estar
    na tela: sem o selo, os dois se parecem, e quem opera cutuca o que não deve.
    """
    try:
        from shopman.shop.services import waitlist

        state = states[order.ref] if states is not None else waitlist.state_for(order)
    except Exception:
        logger.debug("order_queue._waitlist_badge degraded ref=%s", order.ref, exc_info=True)
        return "", ""
    if state == "none":
        return "", ""
    return state, _WAITLIST_LABELS.get(state, "")


def _declared_volumes(order: Order) -> int:
    value = (order.data or {}).get("volumes")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def ready_moments_for(orders) -> dict[int, datetime]:
    """A última entrada em READY de cada pedido pronto, numa consulta só.

    ``Order.ready_at`` é carimbado uma vez (a primeira) e não volta quando o
    pronto é desfeito ou a Cozinha chama o pedido de volta; o log de eventos
    sabe a vez que vale.
    """
    from django.db.models import Max
    from shopman.orderman.models import OrderEvent

    pks = [order.pk for order in orders if order.status == Order.Status.READY]
    if not pks:
        return {}
    rows = (
        OrderEvent.objects.filter(order_id__in=pks, type="status_changed", payload__new_status=Order.Status.READY)
        .values("order_id")
        .annotate(at=Max("created_at"))
    )
    return {row["order_id"]: row["at"] for row in rows}


def _ready_moment_iso(order: Order, moments: dict[int, datetime] | None) -> str:
    if order.status != Order.Status.READY:
        return ""
    if moments is None:
        moments = ready_moments_for([order])
    moment = moments.get(order.pk) or order.ready_at
    return moment.isoformat() if moment else ""


def _channel_configs_for(orders):
    """Resolve each channel once for this projection; commands read their own config."""
    from shopman.shop.config import ChannelConfig

    configs = {}
    for ref in {order.channel_ref for order in orders}:
        configs[ref] = ChannelConfig.for_channel(ref)
    return configs


def items_summary(items) -> str:
    """"2x Croissant, 1x Baguete, 3x Pão de queijo..." — o resumo de uma linha.

    Uma régua só para toda tela que resume a sacola num card (Gestor, Encomendas
    do PDV): três itens e reticências. ``items`` são os itens EFETIVOS
    (``order_composition``), nunca as linhas cruas de um pedido ajustado.
    """
    head = list(items[:4])
    summary = ", ".join(
        f"{format(it.qty.normalize(), "f")}x {it.name or it.sku}" for it in head[:3]
    )
    if len(head) > 3:
        summary += "..."
    return summary


def unit_count(items) -> int:
    """Quantos itens o pedido tem, em UNIDADES (docs/reference/suite-vocabulary.md).

    "Item = unidade, nunca linha": três croissants e um café são 4 itens. A linha
    vendida por peso (qtd fracionária, ex.: 0,350 kg) conta 1, porque peso não se
    soma com peça num número só.
    """
    total = 0
    for item in items:
        qty = Decimal(str(getattr(item, "qty", 0) or 0))
        total += int(qty) if qty > 0 and qty == qty.to_integral_value() else 1
    return total


def _build_card(
    order: Order,
    deadline: tuple[str, str] | None = None,
    accept_batch: dict | None = None,
    courier_change: dict[str, tuple[int, int | None]] | None = None,
    waitlist_states: dict[str, str] | None = None,
    user=None,
    payment_reads=None,
    channel_config=None,
    cash_context=None,
    status_labels=None,
    method_labels=None,
    fiscal_states=None,
    danfe_reads=None,
    kitchen_chips=None,
    ready_moments=None,
    expectation: PrepExpectation | None = None,
    promise_reads=None,
    now: datetime | None = None,
    channel_names: dict[str, str] | None = None,
) -> OrderCardProjection:
    # Um relógio por leitura: o quadro lê ``now`` uma vez e o passa a cada cartão
    # (``build_two_zone_queue``). O "hoje" sai dele, nunca de uma segunda leitura.
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    kitchen_release_at, kitchen_released_at = _kitchen_clock(order, now)
    clock_since = kitchen_released_at or order.created_at
    elapsed = max(0.0, (now - clock_since).total_seconds())

    timer_class = _timer_class(order.status, *_acceptance_clock(order, deadline, now))

    queue_items = getattr(order, "_queue_items", None)
    if queue_items is None:
        queue_items = order_composition.effective_items(order)
    summary = items_summary(queue_items)
    items_count = unit_count(queue_items)

    is_delivery = _is_delivery(order)
    fulfillment_label = _fulfillment_label(is_delivery)
    delivery_address, _delivery_instructions = _delivery_address(order)

    customer_data = order.data.get("customer", {})
    customer_name = _format_customer_display(
        customer_data.get("name", "")
        or customer_data.get("phone", "")
        or order.data.get("customer_phone", "")
        or _customer_handle(order)
        or ""
    )

    batch_state = waitlist_states.get(order.ref) if waitlist_states is not None else None
    advance_block = operator_orders.gestor_advance_block(order, waitlist_state=batch_state, payment_reads=payment_reads)
    next_status = operator_orders.next_status_for(order) if not advance_block else ""

    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")
    payment_status = (_payment_status(order) if order.channel_ref == "ifood" else (payment_svc.get_payment_status(order, payment_reads=payment_reads) or ""))
    payment_method_label = _payment_method_label(method, payment_data, labels=method_labels, order=order)
    block_label, block_reason = _advance_block_copy(
        order, advance_block, method, payment_pending=_is_payment_pending(order, method, payment_status)
    )
    # A promessa do pedido (WP-G08). Quem espera o lote não inicia o preparo: o
    # pão ainda não existe. Não depende do estado da fila de espera (P1-22).
    promise = _promise_of(order, promise_reads)
    waits_batch = _waits_batch(promise, advance_block, next_status)
    if waits_batch:
        next_status = ""
        block_label, block_reason = order_promise.BATCH_WAIT_BLOCK_LABEL, order_promise.batch_wait_reason(promise)
    fiscal_status, _fiscal_status_label, _fiscal_state, _fiscal_links = _fiscal_status(
        order,
        directive_status=fiscal_states.directive_status.get(order.ref, "") if fiscal_states is not None else None,
        emit_failed_alert=(order.ref in fiscal_states.failed_alert_refs) if fiscal_states is not None else None,
    )
    commitment = get_commitment_date(order)
    # O cartão pergunta "é de outro dia?" (a Cozinha do Gestor não conta a de amanhã):
    # a régua única do shop, a mesma da Central e das Entregas (#3163).
    is_preorder = _is_future_preorder(order, today=today)
    schedule_label, schedule_state = _schedule(order, today=today)
    waitlist_state, waitlist_label = _waitlist_badge(order, states=waitlist_states)
    recipient = order.data.get("recipient") if isinstance(order.data.get("recipient"), dict) else {}
    danfe = order_danfe.card_state(order, reads=danfe_reads, now=now)

    actions = operator_orders.operational_actions(order, user=user, waitlist_state=batch_state, payment_reads=payment_reads, channel_config=channel_config)
    if kitchen_release_at is not None:
        actions = _early_start_actions(actions)
    if waits_batch:
        actions = _batch_wait_actions(actions, block_reason)
    promise_at_risk = promise is not None and promise.state == order_promise.STATE_AT_RISK
    whatsapp_url = (
        _board_whatsapp_url(order) if block_label in LAPSED_PAYMENT_LABELS or promise_at_risk else ""
    )
    if block_label in LAPSED_PAYMENT_LABELS:
        actions = _lapsed_payment_actions(actions, block_label, can_call=bool(whatsapp_url))
    actions = _exit_gesture_actions(order, actions, customer_name=customer_name)
    if promise_at_risk:
        promise = order_promise.with_actions(
            promise, (*_promise_actions(user, promise), *_contact_customer_action(whatsapp_url)),
        )
    from shopman.shop.services import ifood_accept_sync

    accept = ifood_accept_sync.state_for(order, batch=accept_batch)
    external_deadline = _external_deadline(order, accept)
    card = OrderCardProjection(
        ref=order.ref,
        status=order.status,
        actions=(*actions, *_cash_settlement_actions(order, user, cash_context), *_ifood_accept_actions(order, accept, user)),
        status_label=status_labels[order.status] if status_labels is not None else order_status_label(order.status),
        channel_ref=order.channel_ref or "",
        channel_name=(
            channel_names[order.channel_ref or ""]
            if channel_names is not None and (order.channel_ref or "") in channel_names
            else _channel_name(order.channel_ref or "")
        ),
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        created_at_iso=order.created_at.isoformat(),
        server_now_iso=now.isoformat(),
        elapsed_seconds=int(elapsed),
        timer_class=timer_class,
        items_summary=summary,
        items_count=items_count,
        total_display=_money(order_composition.effective_total_q(order)),
        fulfillment_label=fulfillment_label,
        fulfillment_type="delivery" if is_delivery else "pickup",
        delivery_address=delivery_address,
        can_confirm=not operator_orders.confirmation_block_reason(order, payment_reads=payment_reads, channel_config=channel_config, waitlist_state=batch_state),
        can_advance=bool(next_status) and undo_block_allows_advance(order),
        next_status=next_status if undo_block_allows_advance(order) else "",
        undo=_undo_projection(order),
        volumes=_declared_volumes(order),
        volumes_checked=len(volume_check.checked_volumes(order)),
        volumes_to_check=volume_check.declared_total(order),
        ready_at_iso=_ready_moment_iso(order, ready_moments),
        dispatched_at_iso=order.dispatched_at.isoformat() if order.dispatched_at and order.status in ("dispatched", "delivered") else "",
        payment_method=method,
        payment_method_label="iFood" if order.channel_ref == "ifood" else payment_method_label,
        ifood_cancellation_notice=ifood_projection.cancellation_notice(order),
        ifood_pickup_code_label=ifood_projection.pickup_code_label(order),
        ifood_logistics_label=ifood_projection.logistics_label(order),
        ifood_schedule_label=ifood_projection.schedule_label(order),
        ifood_remote_ahead_label=ifood_projection.remote_ahead_label(order),
        ifood_negotiations=negotiations(order, user=user),
        **_ifood_accept_fields(order, accept),
        test_order_label=_test_order_label(order),
        test_order_notice=_test_order_notice(order),
        payment_status=payment_status,
        payment_status_label=(
            _lapsed_payment_status_label(block_label) or _order_payment_status_label(order, payment_status)
        ),
        payment_pending=_is_payment_pending(order, method, payment_status),
        # Cobrança vencida não é espera (ampulheta): não destrava sozinha.
        payment_tone=(
            "danger" if _lapsed_payment_status_label(block_label)
            else _payment_tone(order, method, payment_status, payment_data)
        ),
        advance_block_label=block_label,
        advance_block_reason=block_reason,
        payment_lapsed=block_label in LAPSED_PAYMENT_LABELS,
        customer_whatsapp_url=whatsapp_url,
        advance_block_waits=block_waits(block_label),
        can_settle_delivery_cash=_can_settle_delivery_cash(order, payment_data),
        fiscal_status=fiscal_status,
        has_customer_note=bool(str(order.data.get("order_notes", "") or "").strip()),
        is_gift=bool(order.data.get("is_gift")),
        gift_has_recipient=bool((recipient or {}).get("name")),
        assigned_operator=str((order.data.get("assignment") or {}).get("operator_name") or ""),
        awaiting_work_orders=_awaiting_work_orders(order),
        # Directive agendada (canais da casa) ou prazo do marketplace (iFood): o card
        # conta um prazo só, porque para quem opera a pergunta é uma só — quanto falta.
        confirmation_deadline_iso=(deadline or external_deadline or ("", ""))[0],
        confirmation_action=(deadline or external_deadline or ("", ""))[1],
        card_authorization_expires_iso=_card_authorization_expires_iso(
            order, method, payment_status, acceptance_deadline=deadline or external_deadline,
        ),
        channel_display_id=_channel_display_id(order),
        courier_status_label=_card_courier_label(order),
        is_preorder=is_preorder,
        commitment_date=commitment.isoformat() if commitment else "",
        # A que espera a hora da Cozinha hoje também mora na lista "Encomendas": o
        # grupo dela precisa do nome do dia ("hoje"), como o das de outro dia.
        commitment_date_display=(
            _commitment_date_display(commitment, today=today) if is_preorder or (kitchen_release_at and commitment) else ""
        ),
        schedule_label=schedule_label if schedule_state else "",
        schedule_state=schedule_state,
        kitchen_release_at_iso=kitchen_release_at.isoformat() if kitchen_release_at else "",
        kitchen_release_label=_kitchen_release_label(kitchen_release_at),
        kitchen_released_at_iso=kitchen_released_at.isoformat() if kitchen_released_at else "",
        clock_since_iso=clock_since.isoformat(),
        **_courier_change_fields(order, courier_change),
        **_equipment_fields(order, channel_config=channel_config),
        waitlist_state=waitlist_state,
        waitlist_label=waitlist_label,
        danfe_printable=danfe.printable,
        danfe_printed=danfe.printed,
        danfe_state=danfe.state,
        danfe_problem=danfe.problem,
        kitchen=_kitchen_progress(order, (kitchen_chips or {}).get(order.ref)),
        courier_reminder=courier_reminder(order) if order.status in REMINDER_STATUSES else None,
        promise=promise,
    )
    attention = card_attention(
        order, card, channel_config,
        acceptance_timer=deadline if isinstance(deadline, AcceptanceTimer) else None,
        today=today,
    )
    if expectation is not None:
        eta = ready_eta(order, expectation, now=now)
        if eta is not None:
            attention = {**attention, "ready_eta_iso": eta.isoformat()}
    return replace(card, **attention) if attention else card


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} e {names[-1]}"


def _kitchen_progress(order: Order, chips) -> KitchenProgressProjection | None:
    """O progresso por estação no cartão: "Falta Café", "Pronto de Lanches", "Voltar para…"."""
    if not chips:
        return None
    from shopman.shop.services import order_undo

    # Saída tocada e ainda na janela: o gesto do cartão é desfazer a saída, e
    # devolver à cozinha um pedido que está saindo misturaria os dois.
    leaving = bool(order_undo.pending_handoff(order))
    stations = tuple(
        KitchenStationProjection(
            station_ref=chip.station_ref,
            station_name=chip.station_name,
            prints=chip.prints,
            state=chip.state,
            state_label=chip.state_label,
            paper_label=chip.paper_label,
            paper_failed=chip.paper_failed,
            cancelled_items=chip.cancelled_items,
            can_mark_ready=chip.can_mark_ready,
            recall_ticket_pk=None if leaving else chip.recall_ticket_pk,
            items=chip.items,
        )
        for chip in chips
    )
    missing = [station.station_name for station in stations if station.state != "done"]
    missing_label = f"{'Falta' if len(missing) == 1 else 'Faltam'} {_join_names(missing)}" if missing else ""
    return KitchenProgressProjection(order_pk=order.pk, stations=stations, missing_label=missing_label)


#: Rótulo pt-BR do equipamento (a ref é contrato do canal; o texto é da tela).
EQUIPMENT_LABELS = {"card_machine": "Maquininha"}


def _equipment_label(ref: str) -> str:
    return EQUIPMENT_LABELS.get(ref, ref)


def _equipment_fields(order: Order, *, channel_config=None) -> dict:
    if not _is_delivery(order):
        return {}
    from shopman.backstage.models import DeliveryDevice
    from shopman.backstage.services.delivery_devices import PREFIX

    allowed = operator_orders.equipment_options(order.channel_ref or "", channel_config=channel_config)
    devices = getattr(order, "_delivery_devices", None)
    if devices is None:
        devices = list(DeliveryDevice.objects.select_related("current_order")) if "card_machine" in allowed else []
    options = tuple(EquipmentOptionProjection(ref=ref, label=_equipment_label(ref)) for ref in allowed if ref != "card_machine")
    if "card_machine" in allowed:
        options += tuple(EquipmentOptionProjection(
            ref=PREFIX + str(device.ref), label=device.label,
            enabled=device.active and device.current_order_id is None,
            reason=(f"Na rua com o pedido {operator_orders.short_ref(device.current_order.ref)}" if device.current_order_id else "Inativa" if not device.active else ""),
            order_ref=device.current_order.ref if device.current_order_id else "",
        ) for device in devices if device.active or device.current_order_id)
    custody = operator_orders.equipment_custody(order)
    # O card diz o que saiu, enquanto não voltou; depois, nada (zero não é informação).
    label = ""
    if custody.pending:
        label = f"Saiu com a {machine_phrase((order.data or {}).get('dispatch', {}).get('device_label') or '')}"
    from shopman.shop.adapters.delivery_devices import needs_card_machine

    return {
        "equipment_options": options,
        "equipment_label": label,
        "equipment_back_pending": custody.pending,
        "dispatch_needs_machine": operator_orders.next_status_for(order) == "dispatched" and needs_card_machine(order),
        **_trip_fields(order),
    }


machine_phrase = operator_orders.machine_phrase


def _trip_fields(order: Order) -> dict:
    """A saída deste pedido: com quem saiu junto e o que "Entregador voltou" deve conferir."""
    if not operator_orders.courier_return_members(order):
        return {}
    others = tuple(m.ref for m in operator_orders.trip_members(order) if m.pk != order.pk)
    back = operator_orders.courier_return(order)
    lines: list[str] = []
    if back.machine:
        phrase = machine_phrase(back.machine)
        lines.append(phrase[0].upper() + phrase[1:])
    if back.cash_q:
        many = len(back.orders) > 1
        parts = [f"{_money(q)} do pedido{' ' + operator_orders.short_ref(ref) if many else ''}" for ref, q in back.cash_parts]
        if back.change_q:
            parts.append(f"{_money(back.change_q)} de troco")
        if len(parts) > 1:
            lines.append(f"{_money(back.cash_q)} em dinheiro: {' + '.join(parts)}")
        else:
            lines.append(f"{_money(back.change_q)} de troco" if back.change_q else f"{_money(back.cash_q)} em dinheiro")
    return {"trip_with": others, "courier_return_orders": back.orders, "courier_return_lines": tuple(lines)}


def courier_estimate_display(estimate: dict | None) -> str:
    """"R$ 14,90 · 18 min · 4,2 km · ida e volta": a cotação numa linha ("" sem valor)."""
    estimate = estimate or {}
    if estimate.get("value_q") is None:
        return ""
    parts = [_money(int(estimate["value_q"]))]
    if estimate.get("minutes"):
        parts.append(f"{int(estimate['minutes'])} min")
    if estimate.get("km"):
        parts.append(f"{float(estimate['km']):.1f} km".replace(".", ","))
    if estimate.get("with_return"):
        # A corrida volta à loja (cobrança na porta ou maquininha): o custo é de ida e volta.
        parts.append("ida e volta")
    return " · ".join(parts)


def courier_ride_action(orders, *, user=None) -> Action | None:
    """A ação de chamar UMA corrida para vários destes pedidos (``courier-ride``).

    Uma só para as três telas que juntam entregas (as Entregas, o Painel e o
    detalhe do pedido): ``payload_schema`` traz quem a tela leu
    (``expected_actor_id``) e o que ela leu de cada pedido que pode entrar
    (``base_revisions``: ``{ref: courier.dispatch_revision}``). A tela manda as
    revisões dos pedidos que escolheu; o servidor confere cada uma com o pedido
    travado antes de gravar. ``None`` com menos de dois pedidos: não há corrida
    em grupo a oferecer.
    """
    from shopman.shop.services.courier import dispatch_revision

    orders = list(orders)
    if len(orders) < 2:
        return None
    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
    return Action(
        ref="courier-ride", kind="mutation", label="Chamar corrida", enabled=authorized,
        reason="" if authorized else "Identifique uma pessoa com permissão para gerenciar pedidos.",
        method="POST", idempotency="required",
        payload_schema={"expected_actor_id": getattr(user, "pk", None),
                        "base_revisions": {order.ref: dispatch_revision(order) for order in orders}},
    )


def _ride_candidates(orders, *, today: date | None = None) -> tuple[RideCandidateProjection, ...]:
    """As entregas que podem entrar juntas numa corrida (prontas primeiro, depois em preparo).

    A TaOn se chama também antes do pronto (o lembrete de chamar vem no preparo),
    então a corrida junta pedido pronto e pedido em preparo. Encomenda de outro
    dia fica de fora.
    """
    from shopman.shop.services import delivery_services

    orders = sorted(orders, key=lambda order: order.status != "ready")
    if len(orders) < 2 or delivery_services.courier_backend() is None:
        return ()
    rows = [_ride_candidate(order) for order in orders if _rides_with_others(order, today=today)]
    return tuple(rows) if len(rows) >= 2 else ()


def _ride_action_for(candidates, orders, *, user=None) -> Action | None:
    """A ação ``courier-ride`` dos candidatos do Painel (os mesmos de ``ride_candidates``)."""
    refs = {row.ref for row in candidates}
    return courier_ride_action([order for order in orders if order.ref in refs], user=user) if refs else None


def _rides_with_others(order: Order, *, today: date | None = None) -> bool:
    from shopman.shop.services import courier

    return _is_delivery(order) and not _is_future_preorder(order, today=today) and not courier.group_refusal(order)


def _ride_candidate(order: Order) -> RideCandidateProjection:
    asks = operator_orders.partner_custody_asks(order)
    data = order.data or {}
    customer = str((data.get("customer") or {}).get("name") or "").strip()
    address = data.get("delivery_address_structured") or {}
    place = str(address.get("neighborhood") or data.get("delivery_address") or address.get("formatted_address") or "")
    change = _courier_change_fields(order).get("change_label", "") if asks["change_out_suggested_q"] else ""
    return RideCandidateProjection(
        ref=order.ref, change_out_suggested_q=int(asks["change_out_suggested_q"]),
        needs_machine=bool(asks["needs_machine"]),
        label=" · ".join(part for part in (f"Pedido {operator_orders.short_ref(order.ref)}", customer) if part),
        place=place.strip(), stage="Pronto" if order.status == "ready" else "Em preparo",
        change_label=change,
    )






def _plan_for_board() -> dict:
    """O plano das corridas para as entregas prontas (o mesmo cache da página Entregas)."""
    from shopman.shop.services import ride_plan

    try:
        return ride_plan.ride_plan(ride_plan.waiting_pool())
    except Exception:  # o plano nunca derruba o quadro nem o detalhe
        logger.warning("orders.ride_plan_failed", exc_info=True)
        return {"suggestions": []}




def _equipment_out(*, user=None, devices=None) -> tuple[EquipmentOutProjection, ...]:
    from shopman.backstage.models import DeliveryDevice

    if devices is None:
        devices = list(DeliveryDevice.objects.select_related("current_order"))
    # Physical identity comes only from the exclusive relation. Old generic
    # custody remains returnable, without assigning an invented reader to it.
    entries = [(str(device.ref), device.current_order, device.label, True) for device in devices if device.current_order_id]
    entries += [(ref, order, f"{_equipment_label(ref)} (registro antigo sem identificação)", False) for ref, order in operator_orders.equipment_out()
                if not (order.data or {}).get("dispatch", {}).get("device_ref")]
    rows = []
    for ref, order, label, identified in entries:
        customer = order.data.get("customer", {}) if isinstance(order.data, dict) else {}
        rows.append(EquipmentOutProjection(
            ref=ref, label=label, identified=identified, order_ref=order.ref, customer_name=str(customer.get("name") or ""),
            out_at=operator_orders.equipment_custody(order).out_at,
            actions=tuple(action for action in operator_orders.operational_actions(order, user=user) if action.ref == "equipment-back"),
            shared_with=_machine_shared_with(order) if identified else (),
        ))
    return tuple(rows)


def _machine_shared_with(order: Order) -> tuple[str, ...]:
    """Os pedidos da mesma saída que dividem a maquininha deste e ainda não a devolveram."""
    device_ref = ((order.data or {}).get("dispatch") or {}).get("device_ref")
    return tuple(
        member.ref for member in operator_orders.trip_members(order)
        if member.pk != order.pk and ((member.data or {}).get("dispatch") or {}).get("device_ref") == device_ref
        and operator_orders.equipment_custody(member).pending
    )


def _courier_change_fields(order: Order, by_order: dict[str, tuple[int, int | None]] | None = None) -> dict:
    """Os campos de troco da entrega do card/painel, lidos do pedido e do livro.

    ``by_order`` é o mapa de ``courier_change_by_order`` quando quem chama tem
    muitos cards (uma consulta); sem ele, consulta só este pedido.
    """
    if not _is_delivery(order):
        return {}
    payment = order.data.get("payment") or {}
    # Quem diz que há dinheiro na porta é a parcela em espécie, não o método do
    # topo: no pedido iFood o topo é `external` e a parcela mora na linha.
    if operator_orders.cash_due_on_delivery_q(order) <= 0:
        return {}
    if by_order is None:
        change = operator_orders.courier_change(order)
        out_q, back_q = change.out_q, change.back_q
    else:
        out_q, back_q = by_order.get(order.ref, (0, None))
    change_for_q = operator_orders.change_for_q(order)
    suggested_q = operator_orders.change_out_suggested_q(order)
    pending = out_q > 0 and back_q is None
    return {
        "change_out_suggested_q": suggested_q,
        "change_out_q": out_q,
        "change_back_pending": pending,
        "change_label": _change_label(change_for_q, suggested_q, out_q, back_q, settled=bool(payment.get("cod_settled_at"))),
    }


def _change_label(change_for_q: int, suggested_q: int, out_q: int, back_q: int | None, *, settled: bool) -> str:
    """A frase do troco, na ordem em que a história acontece.

    Antes do despacho: o que o cliente disse ("paga com R$ 50, levar R$ 20").
    Na rua: o que saiu da gaveta. Depois do acerto: o que voltou.
    """
    if back_q is not None:
        return f"Voltou R$ {format_money(back_q)} de troco" if out_q else ""
    if out_q > 0:
        return f"Entregador levou R$ {format_money(out_q)} de troco"
    if settled or not change_for_q:
        return ""
    if suggested_q > 0:
        return f"Cliente paga com R$ {format_money(change_for_q)} · levar R$ {format_money(suggested_q)} de troco"
    return f"Cliente paga com R$ {format_money(change_for_q)}"


def _card_courier_label(order: Order) -> str:
    """"Entregador a caminho" e, na corrida com várias paradas, com quem ela vai:
    "Entregador a caminho · corrida com B12, C03". O card diz a corrida inteira
    sem o operador abrir pedido por pedido."""
    from shopman.shop.services import courier

    label = courier_state_label(courier.get_block(order))
    if not label:
        return ""

    if courier.reopen_view(courier.get_block(order))["at"]:
        # O entregador desistiu e a TaOn redistribui a mesma corrida.
        label = COURIER_REOPENED_LABEL
    others =[operator_orders.short_ref(ref) for ref in courier.ride_orders(order) if ref != order.ref]
    return f"{label} · corrida com {', '.join(others)}" if others else label


def _awaiting_work_orders(order: Order) -> tuple[AwaitingWorkOrderProjection, ...]:
    refs = tuple(dict.fromkeys((order.data or {}).get("awaiting_wo_refs") or ()))
    if not refs:
        return ()

    try:
        from shopman.craftsman.models import WorkOrder

        from shopman.backstage.projections.production import WO_STATUS_LABELS, _qty, _work_order_progress_pct
    except Exception:
        logger.debug("orders.awaiting_work_orders_import_failed order=%s", order.ref, exc_info=True)
        return ()

    work_orders = WorkOrder.objects.filter(ref__in=refs).select_related("recipe").prefetch_related("events")
    by_ref = {wo.ref: wo for wo in work_orders}
    result: list[AwaitingWorkOrderProjection] = []
    for ref in refs:
        wo = by_ref.get(ref)
        if not wo:
            continue
        result.append(
            AwaitingWorkOrderProjection(
                ref=wo.ref,
                status=wo.status,
                status_label=WO_STATUS_LABELS.get(wo.status, wo.status),
                output_sku=wo.output_sku,
                recipe_name=wo.recipe.name or wo.recipe.ref,
                planned_qty=_qty(wo.quantity),
                finished_qty=_qty(wo.finished) if wo.finished is not None else "",
                progress_pct=_work_order_progress_pct(wo),
            )
        )
    return tuple(result)


def _is_payment_pending(order: Order, method: str, payment_status: str) -> bool:
    """True when the order needs payment capture before physical work can start."""
    if order.status not in {"new", "accepted"}:
        return False
    if method in _OFFLINE_METHODS:
        return False
    if order.status == "new" and not ((order.data or {}).get("payment") or {}).get("intent_ref"):
        return False
    return payment_status not in _PAYMENT_COMPLETE


#: De quanto em quanto tempo o mesmo pedido sem forma de pagamento volta a gritar.
_SCREAM_EVERY_SECONDS = 24 * 60 * 60


def _report_order_without_payment(order: Order | None) -> None:
    """Pedido sem forma de pagamento não existe (decisão do dono, 06/11/2026, GES-03).

    Toda porta que cria pedido recusa sem ela (``policies.order_payment.PaymentMethodRule``
    no commit; o seed se confere no fim). Se um aparecer mesmo assim, é defeito de
    porta, e a tela não o maquia com um estado próprio: grita no Sentry com a ref.

    Grita UMA vez por pedido a cada dia, não a cada leitura: o pedido sem forma é
    estado, e a fila é lida a cada poucos segundos. Até 23/11/2026 um só pedido de
    24/09 gerou 1,9 mil eventos e ajudou a esgotar a cota mensal do Sentry
    (SHOPMAN-15); com a cota no fim, o erro novo de verdade deixa de ser registrado.
    """
    from django.core.cache import cache

    ref = getattr(order, "ref", "?")
    try:
        first_today = cache.add(f"order_queue:order_without_payment:{ref}", 1, timeout=_SCREAM_EVERY_SECONDS)
    except Exception:
        first_today = True
    if first_today:
        logger.error("order_queue.order_without_payment order=%s", ref)


def _offline_payment_settled(payment_data: dict) -> bool:
    """True quando um tender de balcão/entrega já foi de fato recebido.

    Venda de balcão liquida no PDV (tender ``received``); dinheiro na entrega
    (COD) nasce ``pending`` e vira ``received`` quando acertado. Pedido web para
    pagar na retirada ainda não tem tender — fica de fora, corretamente.
    """
    tenders = payment_data.get("tenders") or []
    return any(
        int(tender.get("amount_q") or 0) > 0
        and str(tender.get("status") or "") in _SETTLED_TENDER_STATUSES
        for tender in tenders
    )


def _payment_tone(order: Order, method: str, payment_status: str, payment_data: dict) -> str:
    """Tom do pill de pagamento — explícito, em vez de deduzido na superfície.

    Pagamento só ESPERANDO não é falha: é ampulheta (``warning``), não alarme
    (``danger``). Quem não paga a tempo é cancelado por ``PaymentTimeoutHandler``
    (reason ``payment_timeout``) e sai do board (``cancelled`` ∉ ``ACTIVE_STATUSES``),
    então ``danger`` no card seria alarme para um pedido que, se falhar, some sozinho.
    """
    if order.channel_ref == "ifood" and method == "external":
        return "success" if payment_status in _PAYMENT_COMPLETE else "neutral" if payment_status == "pending" else "warning"
    # Pago é pago, em qualquer canal ou meio: verde primeiro. Uma captura
    # registrada (pix/cartão) vale para qualquer canal (web, whatsapp, pdv).
    if payment_status in _PAYMENT_COMPLETE:
        from shopman.shop.services.payment_provenance import is_simulated_order_payment

        # Simulado não é verde: o pill não pode dizer "dinheiro garantido" ao
        # lado de um rótulo que diz "sem dinheiro".
        return "warning" if is_simulated_order_payment(order) else "success"
    # Marketplace / "pago online": o pedido chega pré-pago (iFood comita só o que
    # já foi pago), então o dinheiro está garantido — verde, mesmo sem captura nossa.
    if method == "external":
        return "success"
    if method in _OFFLINE_METHODS:
        # Dinheiro/cartão no balcão: verde SÓ quando de fato liquidado — tender
        # recebido no PDV, ou COD acertado na entrega. Pedido web para pagar na
        # retirada e COD ainda pendente ficam neutros: não afirmamos "pago" sem
        # recebimento. (Decisão do Pablo: "verde ao liquidar no PDV".)
        if _offline_payment_settled(payment_data):
            return "success"
        return "neutral"
    if _card_capture_failed(order, payment_status):
        return "danger"
    if _is_payment_pending(order, method, payment_status):
        return "warning"
    return "neutral"


_ADVANCE_BLOCK_LABELS: dict[operator_orders.AdvanceBlock, str] = {
    operator_orders.AdvanceBlock.IFOOD_SCHEDULE_BLOCKED: "Aguardando horário do iFood…",
    operator_orders.AdvanceBlock.IFOOD_WINDOW_NOT_OPEN: "Aguardando a janela do iFood…",
    operator_orders.AdvanceBlock.IFOOD_WAITING_PICKUP: "Aguardando entregador iFood…",
    operator_orders.AdvanceBlock.IFOOD_DELIVERY_UNKNOWN: "Quem leva ainda não definido",
    operator_orders.AdvanceBlock.IFOOD_CANCELLATION_PENDING: "Aguardando cancelamento pelo iFood…",
    operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED: "Aguardando pagamento…",
    operator_orders.AdvanceBlock.PREORDER_NOT_DUE: "Aguardando o dia da encomenda…",
    operator_orders.AdvanceBlock.WAITLIST_FERMATA: "Esperando o lote…",
}


PIX_LAPSED_LABEL = "Pix expirado"
PAYMENT_LAPSED_LABEL = "Pagamento vencido"
#: A cobrança do cartão autorizado foi recusada no aceite: o dinheiro não entrou
#: e não vai entrar sem alguém da casa agir.
CARD_CAPTURE_FAILED_LABEL = "Cobrança recusada"
CARD_CAPTURE_FAILED_REASON = (
    "O cartão estava autorizado, mas a cobrança foi recusada ao aceitar o pedido, e nada foi cobrado. "
    "Confira no painel do Stripe ou cancele o pedido: a reserva no cartão do cliente é desfeita."
)
#: A cobrança do cartão não passou depois do aceite e o cliente foi chamado a
#: pagar de novo (decisão do dono, 07/11): o pedido espera, sem ir para a
#: cozinha, e segue sozinho quando o pagamento entrar.
AWAITING_REPAYMENT_LABEL = "Aguardando novo pagamento"
#: Os rótulos do bloqueio de pagamento que não destrava sozinho: a cobrança
#: venceu ou foi recusada. A tela oferece cancelar com o motivo já marcado.
LAPSED_PAYMENT_LABELS = frozenset({PIX_LAPSED_LABEL, PAYMENT_LAPSED_LABEL, CARD_CAPTURE_FAILED_LABEL})
#: Por que o avanço não anda quando a cobrança venceu ou foi recusada: o fato, e o
#: que a pessoa faz (a tela traz o "Cancelar pedido"; chamar o cliente está no
#: pedido). A frase genérica do ``shop`` ("O pedido só avança depois que o dinheiro
#: entra") mentia aqui: esse dinheiro não entra mais (coordenação, 21/11/2026).
LAPSED_ADVANCE_REASONS = {
    PIX_LAPSED_LABEL: "O Pix venceu sem pagamento e o pedido não avança mais sozinho.",
    PAYMENT_LAPSED_LABEL: "O link de pagamento venceu sem pagamento e o pedido não avança mais sozinho.",
    CARD_CAPTURE_FAILED_LABEL: "A cobrança do cartão foi recusada e o pedido não avança mais sozinho.",
}
#: O que fazer, conforme há ou não um telefone para chamar (o botão some sem ele).
LAPSED_NEXT_STEP = "Cancele o pedido ou chame o cliente para combinar o pagamento."
LAPSED_NEXT_STEP_NO_CONTACT = "Cancele o pedido."

#: A situação na LINHA do pagamento quando a cobrança venceu. O bloqueio dizia "Pix
#: expirado" e a linha do pagamento do mesmo pedido, "Pix · Aguardando pagamento": o
#: mesmo fato em duas formas, uma delas falsa (ninguém mais espera aquele Pix).
#: Com o meio na frente, a linha lê "Pix · Expirado" e "Link de pagamento · Vencido".
_LAPSED_PAYMENT_STATUS_LABELS = {PIX_LAPSED_LABEL: "Expirado", PAYMENT_LAPSED_LABEL: "Vencido"}


#: Os bloqueios que andam sozinhos, sem ninguém da casa agir: o pagamento que ainda
#: pode cair (ou cancela sozinho no vencimento), o dia da encomenda, o lote que ainda
#: vai ficar pronto e as esperas do iFood. Vermelho é só para o que pede alguém
#: (decisão da coordenação com o mandato do dono, 21/11/2026, #2721 item 9): a
#: cobrança vencida ou recusada e "Quem leva ainda não definido" seguem fora.
WAITING_BLOCK_LABELS = frozenset({
    "Aguardando Pix",
    "Aguardando pagamento",
    AWAITING_REPAYMENT_LABEL,
    *(
        _ADVANCE_BLOCK_LABELS[block].removesuffix("…")
        for block in (
            operator_orders.AdvanceBlock.PREORDER_NOT_DUE,
            operator_orders.AdvanceBlock.WAITLIST_FERMATA,
            operator_orders.AdvanceBlock.IFOOD_SCHEDULE_BLOCKED,
            operator_orders.AdvanceBlock.IFOOD_WINDOW_NOT_OPEN,
            operator_orders.AdvanceBlock.IFOOD_WAITING_PICKUP,
            operator_orders.AdvanceBlock.IFOOD_CANCELLATION_PENDING,
        )
    ),
})


def block_waits(block_label: str) -> bool:
    """O bloqueio do avanço anda sozinho? Lê o nome que :func:`_advance_block_copy` deu."""
    return str(block_label or "").removesuffix("…") in WAITING_BLOCK_LABELS


def _lapsed_payment_status_label(block_label: str) -> str:
    """A situação do pagamento que venceu ("Expirado", "Vencido"), ou ``""``.

    Lê o nome do bloqueio, que já decidiu se a cobrança venceu
    (:func:`_payment_wait_copy`): uma régua só para a pílula e para a linha.
    """
    return _LAPSED_PAYMENT_STATUS_LABELS.get(block_label, "")


def _payment_wait_copy(order: Order, method: str, *, awaiting_acceptance: bool = False) -> tuple[str, str]:
    """O bloqueio do pagamento escrito como na v4 (G06): o rótulo e a frase do item.

    "Aguardando Pix" + "gerado às 21:55 · expira às 22:25 · avança sozinho quando
    cair". As horas são as do intent no Payman (``created_at``/``expires_at``), com o
    vencimento de ``Order.data["payment"]["expires_at"]`` quando o intent não diz.
    Só é lido para o pedido barrado pelo pagamento (poucos por leitura).
    """
    payment = (order.data or {}).get("payment") or {}
    created = expires = None
    intent_ref = str(payment.get("intent_ref") or "")
    if intent_ref:
        from shopman.payman.models import PaymentIntent

        row = PaymentIntent.objects.filter(ref=intent_ref).values("created_at", "expires_at").first()
        if row:
            created, expires = row["created_at"], row["expires_at"]
    if expires is None and payment.get("expires_at"):
        try:
            parsed = datetime.fromisoformat(str(payment["expires_at"]))
            expires = parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
        except ValueError:
            expires = None
    is_pix = method == "pix"
    lapsed = bool(expires and expires <= timezone.now())
    parts = []
    if created:
        parts.append(f"{'gerado' if is_pix else 'link gerado'} às {format_clock(created)}")
    if expires:
        verb = ("expirou" if is_pix else "venceu") if lapsed else ("expira" if is_pix else "vence")
        parts.append(f"{verb} às {format_clock(expires)}")
    if lapsed:
        # Cobrança vencida não "cai" mais: prometer o avanço sozinho seria mentir.
        return (PIX_LAPSED_LABEL if is_pix else PAYMENT_LAPSED_LABEL), " · ".join(parts)
    if awaiting_acceptance:
        # Pedido NOVO: o Pix que cai não aceita o pedido sozinho, mas o que não
        # cai cancela. É isso que o operador precisa saber, com a hora.
        parts.append("sem pagamento até lá, cancela sozinho")
    else:
        parts.append("avança sozinho quando cair" if is_pix else "avança sozinho quando o pagamento entrar")
    return ("Aguardando Pix" if is_pix else "Aguardando pagamento"), " · ".join(parts)


#: Meios em que o pedido novo espera um pagamento que vence sozinho.
_EXPIRING_PAYMENT_METHODS = frozenset({"pix", "link"})


def _advance_block_copy(order: Order, advance_block, method: str, *, payment_pending: bool = False) -> tuple[str, str]:
    """O rótulo curto e a frase do bloqueio do avanço, na voz do operador.

    ``NO_NEXT_STEP`` não é bloqueio que se mostra (o pedido novo espera o aceite,
    não um fato de fora): sem frase, para o cartão não escrever "Pedido não possui
    próxima etapa" (G24). O pagamento ganha as horas da cobrança (G06).

    A exceção é o pedido NOVO esperando um Pix (ou link) que vence: o Aceitar
    fica travado pelo pagamento e o pedido cancela sozinho no vencimento. Sem a
    frase, o cartão dizia só "Bloqueado" e o motivo morava no ``title`` do botão,
    que tablet e celular não mostram (beta 06/11, PIXEXP-05).
    """
    if (
        order.status == Order.Status.NEW
        and payment_pending
        and method in _EXPIRING_PAYMENT_METHODS
        and advance_block in (None, "", operator_orders.AdvanceBlock.NO_NEXT_STEP, operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED)
    ):
        return _payment_wait_copy(order, method, awaiting_acceptance=True)
    if not advance_block or advance_block == operator_orders.AdvanceBlock.NO_NEXT_STEP:
        return "", ""
    if advance_block == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED:
        if payment_svc.capture_failure(order) is not None:
            return CARD_CAPTURE_FAILED_LABEL, CARD_CAPTURE_FAILED_REASON
        if payment_svc.awaiting_repayment(order) is not None:
            label, times = _payment_wait_copy(order, method)
            if label in LAPSED_PAYMENT_LABELS:
                return label, times
            return AWAITING_REPAYMENT_LABEL, (
                "A cobrança do cartão falhou e nada foi cobrado. Pedimos ao cliente um novo pagamento: "
                f"{times}. Sem pagamento no prazo, o pedido cancela sozinho."
            )
        return _payment_wait_copy(order, method)
    return advance_block_label(advance_block), operator_orders.advance_block_message(advance_block, order)


def advance_block_label(advance_block: operator_orders.AdvanceBlock) -> str:
    """Rótulo curto para o botão desabilitado (o motivo inteiro vai no title).

    Só ganha rótulo o bloqueio TEMPORÁRIO — aquele que a espera resolve. Pedido
    cancelado ou concluído não tem próxima etapa e por isso não ganha botão
    nenhum: lugar ocupado por algo que nunca vai destravar é ruído.
    """
    return _ADVANCE_BLOCK_LABELS.get(advance_block, "")


def _payment_status(order: Order) -> str:
    """Return the operator-facing payment status without duplicating Payman."""
    if order.channel_ref == "ifood":
        from shopman.shop.services.ifood_ingest import payment_status_from_payload

        return payment_status_from_payload(((order.data or {}).get("ifood") or {}).get("payments") or {}, order.total_q)
    return payment_svc.get_payment_status(order) or ""


def _payment_method_label(method: str, payment_data: dict, *, labels: dict | None = None, order: Order | None = None) -> str:
    if not method:
        _report_order_without_payment(order)
        return ""
    label = labels[method] if labels is not None else payment_method_label(method)
    if method == "mixed" and payment_data.get("tenders"):
        label = " + ".join(
            f"{labels[t.get('method', '')] if labels is not None and t.get('method', '') in labels else payment_method_label(t.get('method', ''))} R$ {format_money(int(t.get('amount_q') or 0))}"
            for t in payment_data["tenders"]
        )
    if payment_data.get("collection") == "on_delivery":
        if payment_data.get("cod_settled_at"):
            return f"{label} · pagamento confirmado"
        handoff = "retirada" if order is not None and not _is_delivery(order) else "entrega"
        return f"{label} na {handoff}"
    return label


def _cash_settlement_context(orders):
    """One canonical custody lookup per projection; GET must not create a drawer."""
    if not any(_can_settle_delivery_cash(order, (order.data or {}).get("payment") or {}) for order in orders):
        return None, ""
    from shopman.cashman.models import Terminal

    from shopman.backstage.services import pos as pos_service
    from shopman.backstage.services.exceptions import POSError

    if not Terminal.objects.filter(is_active=True).exists():
        return None, "Abra um turno de caixa para registrar o acerto."
    try:
        shift = pos_service.current_shift(strict=True)
    except POSError as exc:
        return None, str(exc)
    return shift, "" if shift else "Abra um turno de caixa para registrar o acerto."


def _cash_settlement_actions(order, user, context):
    if not _can_settle_delivery_cash(order, (order.data or {}).get("payment") or {}):
        return ()
    shift, reason = context if context is not None else _cash_settlement_context([order])
    authorized = bool(user and user.is_active and user.is_staff and user.has_perm("shop.manage_orders"))
    if not authorized:
        reason = "Identifique uma pessoa com permissão para gerenciar pedidos."
    is_pickup = not _is_delivery(order)
    return (Action(ref="settle-delivery-cash", kind="mutation", label=(
        "Receber na retirada" if is_pickup else "Acertar entrega"
    ),
        enabled=authorized and not reason, reason=reason, method="POST", idempotency="required",
        payload_schema={"base_revision": operator_orders.cash_settlement_revision(order, shift),
            "expected_actor_id": getattr(user, "pk", None), "cash_shift_id": shift.pk if shift else None},
        confirmation={"required": True, "description": _settlement_description(shift) if shift else reason}),)


def _settlement_description(shift) -> str:
    """Onde o dinheiro entra, como o operador reconhece: o caixa e quando abriu.

    Antes dizia "turno 42", o número interno do turno, que ninguém no balcão vê.
    """
    opened = timezone.localtime(shift.opened_at)
    terminal = shift.terminal.label or shift.terminal.ref
    return f"O dinheiro entra no caixa {terminal}, no turno aberto às {format_clock(opened)}."


def _can_settle_delivery_cash(order: Order, payment_data: dict) -> bool:
    fulfillment_ready = (
        order.status == Order.Status.READY
        if not _is_delivery(order)
        else order.status in {Order.Status.DISPATCHED, Order.Status.DELIVERED, Order.Status.COMPLETED}
    )
    return (
        payment_data.get("method") in {"cash", "credit", "debit", "mixed"}
        and payment_data.get("collection") == "on_delivery"
        and not payment_data.get("cod_settled_at")
        and fulfillment_ready
    )


def _payment_link_fields(order: Order, method: str) -> dict:
    """Só o pedido de LINK paga o custo (uma leitura no Payman + uma Directive)."""
    return _payment_link_read(order, method)[0]


def _payment_link_read(order: Order, method: str) -> tuple[dict, str]:
    """Os campos do link e, quando o envio não se confirma, a frase do problema.

    A segunda parte alimenta "O que falta neste pedido": link que pode não ter
    chegado é pendência, com o reenvio ao lado.
    """
    if method != "link":
        return {}, ""
    from shopman.shop.services import notification as notification_svc

    notice, unconfirmed = _payment_link_delivery(order)
    fields = {
        "can_resend_payment_link": notification_svc.payment_link_resend_refusal(order) is None,
        "payment_link_notice": notice,
    }
    return fields, notice if unconfirmed else ""


#: Motivos de envio omitido em que o link NÃO chegou ao cliente e o pedido segue devendo.
_LINK_NOT_DELIVERED_REASONS = frozenset({"customer_opt_out", "expected_no_contact"})


def payment_link_notice(order: Order) -> str:
    """Describe the delivery evidence; worker completion alone proves no send."""
    return _payment_link_delivery(order)[0]


def _payment_link_delivery(order: Order) -> tuple[str, bool]:
    """``(frase, o envio não se confirmou)`` do link de pagamento.

    Toda frase nomeia só o que existe na tela: o reenvio ("Reenviar link de
    pagamento") e o contato do cliente. "Copie o link" e "confira com o
    responsável" apontavam para um botão e uma pessoa que não existem (P2-22).
    """
    from django.utils.dateparse import parse_datetime

    from shopman.shop.services import notification as notification_svc

    directive = notification_svc.latest_delivery(order, notification_svc.PAYMENT_LINK_TEMPLATE)
    if directive is None:
        return "", False
    delivery = (directive.payload or {}).get("notification_delivery") or {}
    if delivery.get("status") in {"started", "unknown"}:
        return (
            "Envio do link não confirmado pelo provedor. Antes de reenviar, pergunte ao cliente se o link chegou.",
            True,
        )
    if delivery.get("status") == "accepted":
        recorded = parse_datetime(str(delivery.get("recorded_at") or ""))
        when = _format_time_of_day(recorded) if recorded and timezone.is_aware(recorded) else ""
        at = f" {when}" if when else ""
        # "Entregue" só com comprovante do provedor (D3). Ver
        # docs/reference/comprovante-de-entrega.md.
        if delivery.get("proof") == notification_svc.PROOF_RECEIPT and delivery.get("message_id"):
            return f"Link entregue pelo provedor{at}, com comprovante. Leitura pelo cliente não confirmada.", False
        return f"Link aceito pelo provedor{at}, sem comprovante de entrega.", False
    if delivery.get("status") == "skipped":
        if delivery.get("reason") == "notification_not_required":
            # Aviso que não se aplica não é envio que deixou de sair: nada a dizer.
            return "", False
        reason = {
            "customer_opt_out": "o cliente não autorizou notificações",
            "expected_no_contact": "não há contato disponível",
            "payment_not_pending": "o pagamento não está pendente",
            "payment_link_already_paid": "o cliente já pagou",
            "payment_link_order_cancelled": "o pedido foi cancelado",
            "payment_link_expired": "o link venceu",
            "payment_link_unavailable": "o link não está disponível",
        }.get(delivery.get("reason"), "o envio foi omitido")
        return f"Link não enviado: {reason}.", delivery.get("reason") in _LINK_NOT_DELIVERED_REASONS
    if directive.status == "queued":
        return "Envio do link na fila.", False
    if directive.status == "running":
        return "Envio do link em processamento; aceite ainda não confirmado.", False
    if directive.status == "done":
        return "Processamento concluído sem confirmação de envio. Confira o contato antes de reenviar.", True
    return "O envio do link falhou. Reenvie o link.", True


def _format_time_of_day(dt) -> str:
    """"às 14h32" hoje; "em 02/09 às 14h32" em outro dia."""
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    hour = format_clock(local)
    if local.date() == timezone.localdate():
        return f"às {hour}"
    return f"em {local:%d/%m} às {hour}"


#: ``fiscal_state`` (serviço) → ``(fiscal_status, fiscal_status_label)`` da pill.
#:
#: A copy segue o PONTO em que a nota nasce, não o status do pedido: o Pix de
#: balcão emite na captura (``lifecycle._on_paid``), a encomenda emite na saída
#: da mercadoria (retirada ou entrega), e "Fiscal na conclusão" mentia para os
#: dois. ``fiscal_status`` mantém as chaves que a tela do Gestor já lê
#: (``failed`` liga o "Reprocessar NFC-e"); ``fiscal_state`` é o vocabulário
#: canônico, o mesmo do PDV.
_FISCAL_PILL = {
    "authorized": ("authorized", "NFC-e autorizada"),
    "failed": ("failed", "NFC-e não autorizada"),
    "queued": ("pending", "NFC-e em emissão"),
    "awaiting_payment": ("awaiting_payment", "NFC-e sai quando o pagamento confirmar"),
    "awaiting_pickup": ("awaiting_pickup", "NFC-e sai na retirada"),
    "awaiting_delivery": ("awaiting_delivery", "NFC-e sai na entrega"),
    # A regra da casa só emite quando pedem (nota, CPF ou comprovante): a pill diz
    # o fato em português claro e sem alarme, o MESMO texto do PDV
    # (`pos-nuxt/app/presentation/saleResult.ts`). Se o cliente pedir depois, o
    # "Solicitar NFC-e…" do PDV sai com o gerente.
    "not_expected": ("not_requested", "NFC-e não solicitada"),
}

#: O pedido cancelado sem nenhuma tentativa de emissão (``not_issued``): a nota não
#: vai sair, e a pill diz o fato em vez de prometer. "NFC-e sai quando o pagamento
#: confirmar" num Pix vencido (#3127) e "NFC-e em emissão" num cancelado sem nota
#: (#3130) eram rótulos que mentiam. Quando a cobrança digital nunca confirmou, a
#: frase diz por quê.
_NOT_ISSUED_LABEL = "Sem NFC-e: o pedido foi cancelado"
_NOT_ISSUED_BEFORE_PAYMENT_LABEL = "Sem NFC-e: o pedido foi cancelado antes do pagamento"


def _not_issued_label(order: Order) -> str:
    from shopman.shop.services.payment_gate import payment_is_captured, requires_captured_payment

    if requires_captured_payment(order) and not payment_is_captured(order):
        return _NOT_ISSUED_BEFORE_PAYMENT_LABEL
    return _NOT_ISSUED_LABEL


class _FiscalEvidence(NamedTuple):
    """Evidência fiscal lida em LOTE para um quadro: uma query por fonte, não por card."""

    directive_status: dict[str, str]
    failed_alert_refs: frozenset[str]


def _fiscal_status(
    order: Order,
    *,
    directive_status: str | None = None,
    emit_failed_alert: bool | None = None,
) -> tuple[str, str, str, tuple[dict[str, str], ...]]:
    """``(fiscal_status, fiscal_status_label, fiscal_state, links)`` da pill fiscal."""
    from shopman.shop.services import fiscal as fiscal_service

    data = order.data or {}
    state = fiscal_service.fiscal_state(
        order, directive_status=directive_status, emit_failed_alert=emit_failed_alert,
    )
    if data.get("nfce_cancelled"):
        # Nota cancelada é fato posterior à autorização: a chave continua lá, o
        # estado canônico segue ``authorized``, e a pill diz o que aconteceu.
        status, label = "cancelled", "NFC-e cancelada"
    elif state == "not_issued":
        status, label = "not_issued", _not_issued_label(order)
    else:
        status, label = _FISCAL_PILL[state]

    links = []
    if data.get("nfce_danfe_url"):
        links.append({"label": "DANFE", "url": data["nfce_danfe_url"]})
    if data.get("nfce_qrcode_url"):
        links.append({"label": "QR Code", "url": data["nfce_qrcode_url"]})
    return status, label, state, tuple(links)


def _fiscal_states_for(orders) -> _FiscalEvidence:
    """Latest canonical Directive evidence + open emit-failed alerts, one query each."""
    from shopman.orderman.models import Directive

    from shopman.backstage.models import OperatorAlert
    from shopman.shop.directives import FISCAL_EMIT_NFCE
    from shopman.shop.services.fiscal import EMIT_FAILED_ALERT_TYPE

    refs = [order.ref for order in orders]
    if not refs:
        return _FiscalEvidence({}, frozenset())
    result: dict[str, str] = {}
    rows = Directive.objects.filter(
        topic=FISCAL_EMIT_NFCE, payload__order_ref__in=refs,
    ).order_by("-created_at", "-pk").values_list("payload__order_ref", "status")
    for ref, status in rows:
        result.setdefault(ref, status)
    failed = frozenset(
        OperatorAlert.objects.filter(
            type=EMIT_FAILED_ALERT_TYPE, resolved_at__isnull=True, order_ref__in=refs,
        ).values_list("order_ref", flat=True)
    )
    return _FiscalEvidence(result, failed)


def _contact_request(order: Order) -> ContactRequestProjection | None:
    from shopman.shop.services import customer_contact

    request = customer_contact.open_request(order)
    if request is None:
        return None
    return ContactRequestProjection(
        rating=request.rating,
        comment=request.comment,
        requested_at_display=_format_datetime(request.requested_at),
        origin=request.origin,
    )


def _customer_contact(order: Order, customer_data: dict) -> dict[str, str]:
    """Telefone/e-mail/ref do cliente, prontos para a tela do operador.

    O telefone vem do SNAPSHOT do pedido (``Order.data["customer"]``), não do
    cadastro: é o número que a pessoa deu para ESTE pedido, e é por ele que se
    fala sobre este pedido. O cadastro só entra como reserva, quando o snapshot
    veio sem telefone.

    O e-mail é o oposto: nenhum escritor de ``Order.data["customer"]`` grava
    e-mail (ver ``docs/reference/data-schemas.md``), então ele só existe pelo
    cadastro — e só quando o pedido está ligado a um.
    """
    # O handle do pedido, quando ele é o telefone do cliente, é o número deste
    # pedido também: o nome exibido já o usa (``_customer_handle``), e sem ele o
    # "Chamar no WhatsApp" sumia de quem pediu só com o telefone (21/11/2026).
    phone_raw = str(
        customer_data.get("phone") or order.data.get("customer_phone") or _customer_handle(order) or ""
    ).strip()
    customer_ref = str(customer_data.get("ref") or "").strip()
    email = ""

    if customer_ref:
        # Uma consulta, e só no DETALHE (o board nunca passa por aqui): o e-mail
        # só existe no cadastro, e o telefone às vezes falta no snapshot.
        # Cliente apagado do cadastro não é erro — é um pedido que continua
        # existindo, e a tela segue com o que o snapshot deu.
        try:
            from shopman.guestman.services import customer as customer_service

            customer = customer_service.get(customer_ref)
        except ImportError:
            customer = None
        if customer is not None:
            phone_raw = phone_raw or str(getattr(customer, "phone", "") or "").strip()
            email = str(getattr(customer, "email", "") or "").strip()

    from shopman.shop.services.notification import customer_phone_is_platform_relay

    if phone_raw and customer_phone_is_platform_relay(order):
        return {**_relay_contact(phone_raw, customer_data), "customer_email": email, "customer_ref": customer_ref}

    e164 = normalize_phone(phone_raw) if phone_raw else ""
    digits = e164.lstrip("+")
    return {
        "customer_phone": _format_customer_display(phone_raw) if phone_raw else "",
        "customer_phone_uri": f"tel:{e164}" if e164 else "",
        "customer_whatsapp_url": f"https://wa.me/{digits}" if digits else "",
        "customer_relay_phone": "",
        "customer_relay_code": "",
        "customer_relay_expires_at": "",
        "customer_email": email,
        "customer_ref": customer_ref,
    }


def _relay_contact(phone_raw: str, customer_data: dict) -> dict[str, str]:
    """O caminho de voz que o iFood deixa: 0800 da central + localizador.

    Não é o telefone do cliente. Medido em 21/09/2026: o detalhe oferecia
    "WhatsApp" para o 0800 da central e "Ligar" para ele sem o código — a
    ligação caía na central, não na pessoa. O relé é só voz (sem WhatsApp), e a
    ligação só completa com o localizador, que vence.
    """
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    digits = "".join(ch for ch in phone_raw if ch.isdigit())
    code = str(customer_data.get("phone_localizer") or "").strip()
    expires_raw = str(customer_data.get("phone_localizer_expiration") or "").strip()
    try:
        expires = parse_datetime(expires_raw) if expires_raw else None
    except (TypeError, ValueError):
        expires = None
    expired = expires is not None and timezone.is_aware(expires) and expires <= timezone.now()
    usable = bool(digits and code and not expired)
    return {
        "customer_phone": "",          # não é o número da pessoa; não se exibe como se fosse
        "customer_whatsapp_url": "",   # relé é voz: WhatsApp para a central não existe
        # Vírgula = pausa na discagem (iOS e Android): disca a central e, quando
        # ela atende, digita o localizador. Sem código válido, sem botão.
        "customer_phone_uri": f"tel:{digits},{code}" if usable else "",
        "customer_relay_phone": phone_raw,
        "customer_relay_code": code if not expired else "",
        "customer_relay_expires_at": expires.isoformat() if expires is not None else "",
    }


# O iFood entrega o nome do cliente MASCARADO em pedido de teste — 32 asteriscos,
# não um campo vazio. Medido no alpha em 19/09/2026: ``customer_name`` chegava como
# "********************************" e o card imprimia isso na linha do cliente,
# onde parece defeito de renderização e ocupa o lugar do dado que importa. Máscara
# não é nome: quem lê precisa saber que NÃO HÁ nome para chamar, e de quem é a
# decisão de ocultar. Nome de verdade, inclusive abreviado ("Marina A."), passa.
_MASKED_NAME_CHARS = set("*·•.…-_ ")
_MASKED_NAME_LABEL = "Nome oculto pelo iFood"


def _is_masked_name(label: str) -> bool:
    """Um rótulo feito só de caracteres de máscara não identifica ninguém."""
    return bool(label) and set(label) <= _MASKED_NAME_CHARS and any(ch in "*·•…" for ch in label)


def _board_whatsapp_url(order: Order) -> str:
    """O WhatsApp do cliente para o cartão, sem consultar o cadastro.

    A leitura barata do quadro (o cadastro só entra no detalhe): o telefone do
    pedido ou o handle que é o cliente, o mesmo número que o detalhe usa
    (``_customer_contact``). O relé do iFood é voz, não WhatsApp: vazio.
    """
    data = order.data or {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    phone_raw = str(customer.get("phone") or data.get("customer_phone") or _customer_handle(order) or "").strip()
    if not phone_raw:
        return ""
    from shopman.shop.services.notification import customer_phone_is_platform_relay

    if customer_phone_is_platform_relay(order):
        return ""
    digits = (normalize_phone(phone_raw) or "").lstrip("+")
    return f"https://wa.me/{digits}" if digits else ""


#: A saída do cartão que chama o cliente no WhatsApp (a mesma ``ref`` do detalhe).
ACTION_CONTACT_CUSTOMER = "contact-customer"
CONTACT_CUSTOMER_LABEL = "Chamar no WhatsApp"


def _contact_customer_action(whatsapp_url: str) -> tuple[Action, ...]:
    """ "Chamar no WhatsApp" ao lado do "Resolver" no cartão da promessa em risco (#2434)."""
    if not whatsapp_url:
        return ()
    return (
        Action(
            ref=ACTION_CONTACT_CUSTOMER, kind="link", label=CONTACT_CUSTOMER_LABEL,
            href=whatsapp_url, idempotency="none",
        ),
    )


def _customer_handle(order: Order) -> str:
    """O handle do pedido só quando ele É o cliente (telefone, WhatsApp).

    No PDV o handle é a comanda (``pos_tab``, "00001008"): mostrá-la no lugar do
    cliente punha um número de comanda como nome de gente (beta 05/11, PDV-10).
    Mesma régua de ``customer_orders`` para o telefone do pedido.
    """
    return order.handle_ref if order.handle_type in {"phone", "whatsapp"} else ""


def _format_customer_display(value: str) -> str:
    label = (value or "").strip()
    if not label:
        return ""
    if _is_masked_name(label):
        return _MASKED_NAME_LABEL

    digits = "".join(ch for ch in label if ch.isdigit())
    if not digits:
        return label

    looks_like_phone = label.startswith("+") or label.startswith("(") or len(digits) >= 10
    if not looks_like_phone:
        return label

    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]

    if digits.startswith("55") and len(digits) in (12, 13):
        ddd = digits[2:4]
        number = digits[4:]
        if len(number) == 9:
            return f"({ddd}) {number[:5]}-{number[5:]}"
        if len(number) == 8:
            return f"({ddd}) {number[:4]}-{number[4:]}"

    if label.startswith("+"):
        return "+" + digits

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"

    return label


#: O prazo de aceite quando o pedido novo não tem timer agendado (o do dia).
ACCEPT_WINDOW_SECONDS = 300


def _acceptance_clock(order: Order, deadline, now) -> tuple[float, float]:
    """(segundos corridos, segundos do prazo) do aceite do pedido novo.

    Com timer agendado (``confirmation.timeout``), conta o prazo DELE: 5 min no
    pedido do dia, 60 na encomenda e no pedido que chega com a casa fechada (dono,
    09/11; ``lifecycle.acceptance_timeout_minutes``). Contar 5 min da criação para
    todos deixava a encomenda vermelha aos 4 min, com 56 ainda pela frente.
    """
    timer = acceptance_timer_goal(deadline if isinstance(deadline, AcceptanceTimer) else None)
    if timer is not None:
        minutes, since = timer
        return (now - since).total_seconds(), minutes * 60
    return (now - order.created_at).total_seconds(), ACCEPT_WINDOW_SECONDS


def _timer_class(status: str, elapsed: float, window: float = ACCEPT_WINDOW_SECONDS) -> str:
    """O tom do aceite: no prazo até a metade dele (como o iFood; dono, 13/11/2026),
    atenção até 80%, urgente depois."""
    if status == "new":
        if elapsed < window * 0.5:
            return "timer-ok"
        elif elapsed < window * 0.8:
            return "timer-warning"
        else:
            return "timer-urgent"
    return "timer-muted"


def _is_delivery(order: Order) -> bool:
    return get_fulfillment_type(order) == "delivery"


def _fulfillment_label(is_delivery: bool) -> str:
    """Rótulo do recebimento na tela do operador, em português.

    Estava escrito ``"Delivery" if is_delivery else "Retirada"``, inglês e
    português no mesmo ternário e em dois lugares — o operador lia "Delivery"
    no cartão. A convenção do projeto é URL em inglês, TEXTO de tela em
    português; centralizar aqui impede que as duas cópias voltem a divergir.
    """
    return "Entrega" if is_delivery else "Retirada"


def _delivery_address(order: Order) -> tuple[str, str]:
    """Endereço de entrega do pedido: ``(endereço, instruções)``.

    O Gestor é a tela de quem DESPACHA, e não tinha o endereço em lugar nenhum:
    a projection não trazia o campo e o app não tinha uma ocorrência de
    "address". O dado sempre existiu em ``Order.data`` (o PDV já o expunha), só
    não chegava a quem precisa mandar o pedido para algum lugar.

    Devolve ``("", "")`` na retirada, para a tela não ter que decidir nada: se
    veio vazio, não há endereço a mostrar.
    """
    if not _is_delivery(order):
        return "", ""

    data = order.data or {}
    structured = data.get("delivery_address_structured")
    structured = structured if isinstance(structured, dict) else {}

    address = str(data.get("delivery_address") or structured.get("formatted_address") or "").strip()
    complement = str(structured.get("complement") or "").strip()
    # O complemento é o que faz o entregador achar a porta (apto, bloco, fundos)
    # e nem sempre entra no texto formatado do Places. Só anexa quando ainda não
    # está lá, para não repetir "apto 42" duas vezes na mesma linha.
    if complement and complement.lower() not in address.lower():
        address = f"{address} - {complement}" if address else complement

    instructions = str(structured.get("delivery_instructions") or "").strip()
    return address, instructions


# O histórico é texto de tela, e texto de tela é em português. Sem um rótulo
# aqui o evento caía num `event.type.replace("_", " ").title()`, e o operador
# lia "Created" no histórico do pedido dele.
_EVENT_LABELS = {
    "operator_comment": "Comentário",
    "kitchen_note_changed": "Nota da cozinha atualizada",
    "order_assigned": "Atendimento assumido",
    "order_unassigned": "Atendimento liberado",
    "created": "Pedido criado",
    "payment_collected": "Pagamento recebido",
    "payment_switched_to_pix": "Cliente trocou o cartão recusado por Pix",
    "equipment_returned": "Maquininha devolvida",
    "partner_custody_recorded": "Separado para o entregador da {service} (troco ou maquininha)",
    "partner_custody_returned": "A corrida não coletou: o que ia com o entregador voltou",
    "order_rescheduled": "Data combinada alterada",
    # O lote foi cancelado e a reserva deste pedido ficou sem lastro (#2547).
    "production_hold_lost": "Lote cancelado: o item ficou em falta",
    # O lote rendeu menos do que as reservas, ou passou da hora com o pedido esperando (#2594).
    "production_hold_short": "Lote rendeu menos: o item ficou em falta",
    "production_lot_late": "Lote atrasado: o item ainda não ficou pronto",
    # O lote ficou pronto com desconto, que a reserva deste pedido não aceita (#2723).
    "production_hold_grade": "Lote ficou pronto com desconto: o item ficou em falta",
    "order_edited": "Encomenda editada",
    "card_machine_refund_recorded": "Estorno na maquininha registrado",
    "fiscal_requeued": "NFC-e enviada de novo",
    # ``{service}`` é o nome do serviço da corrida do pedido (``_build_timeline``).
    "courier_dispatch_requested": "Entregador da {service} chamado",
    "courier_ride_opened": "Corrida aberta na {service}",
    # A mesma corrida segue chamada: o serviço redistribui sozinho (``will_reopen``).
    "courier_ride_reopened": "O entregador desistiu e a {service} procura outro",
    "courier_ride_restored": "A {service} retomou a corrida que constava como encerrada",
    "courier_custody_separated": "Troco e maquininha separados de novo",
    "courier_dispatch_released": "Chamada da {service} feita de novo",
    "courier_closed_here": "Corrida encerrada aqui",
    "courier_cancel_requested": "Cancelamento da corrida pedido à {service}",
    "courier_reminder_dismissed": "Lembrete de chamar o entregador dispensado",
    # Entregador da casa (``services/own_fleet``): a casa escolheu a pessoa, e ela
    # marcou um caso na folha "Problema" do link.
    "courier_assigned": "Entregador da casa escolhido para a entrega",
    "courier_problem": "Entregador da casa marcou um problema na entrega",
    "fiscal_issue_override": "NFC-e emitida com autorização do gerente",
    "cash_refund_recorded": "Devolução em dinheiro registrada no caixa",
    "return_initiated": "Devolução iniciada",
    "refund_processed": "Estorno processado",
    # Venda só em conta: a devolução ou o não retirado tira o valor da conta (#2606, #2697).
    "account_debt_reduced": "Valor tirado da conta do cliente",
    "volume_checked": "Volume conferido",
    "volume_check_wrong_bag": "Sacola de outro pedido lida na conferência",
    # UX-G2: a saída tocada fica na janela de desfazer antes de ser gravada.
    "handoff_requested": "Saída tocada (janela de desfazer)",
    "handoff_undone": "Saída desfeita",
    "handoff_refused": "Saída não gravada",
    "auto_ready_undone": "Pronto desfeito",
    "volumes_declared": "Volumes declarados",
    "ifood_accept_failed": "O aceite não chegou ao iFood",
    "ifood_accept_retried": "Aceite enviado de novo ao iFood",
    "ifood_accept_sent": "O iFood recebeu o aceite",
    "ifood_accept_confirmed": "O iFood confirmou o pedido",
    "concierge_discount": "Desconto da Concierge",
    "concierge_cancelled": "Cancelado pela Concierge a pedido do cliente",
    "customer_contact_requested": "Cliente avaliou mal e pediu para falar com o responsável",
    "customer_cancellation_requested": "Cliente solicitou o cancelamento",
    "customer_contact_resolved": "Ouvidoria resolvida",
    # A letra da corrida vira a frase do Gestor (``courier_state_label``) em
    # ``_build_timeline``; este é o rótulo da letra que ninguém nomeou.
    "courier_status": "Corrida da {service} atualizada",
    # O dinheiro, nos três fatos que o Payman distingue. Autorizar NÃO é cobrar:
    # o Gestor dizia "Payment.authorized · Pagamento confirmado" para um cartão
    # só reservado (beta 06/11, F4).
    "payment.authorized": "Cartão autorizado (ainda não cobrado)",
    "payment.captured": "Pagamento recebido",
    "payment.capture_failed": "Cobrança do cartão recusada (nada foi cobrado)",
    "payment.repayment_requested": "Novo pagamento pedido ao cliente",
    "payment.method_changed": "Cliente trocou o pagamento para Pix",
    "payment.refunded": "Pagamento estornado",
    # WP-G13: quem tentou é o autor da linha; quem autorizou e o que o gateway
    # respondeu vão no detalhe (``_refund_retry_detail``).
    "payment.refund_retry": "Estorno tentado de novo",
    # "Estornar" no detalhe do Gestor (#2727, item 5): a tentativa, saída ou não.
    "payment.order_refund": "Estorno pedido no Gestor",
    "payment.counter_takeover": "Cobrança online cancelada: o cliente paga no balcão",
    # #2897: o saldo da encomenda cobrado em Pix no balcão (novo, ou o Pix online
    # do cliente aproveitado); quem gerou é o autor da linha.
    "payment.counter_pix": "Pix do saldo gerado no balcão",
}

#: O que a linha do tempo diz de um evento ainda sem rótulo: nunca o identificador.
UNLABELLED_EVENT_LABEL = "Registro do sistema"

#: O Pix que caiu numa cobrança já encerrada e foi registrado à parte.
_OUTSIDE_CHARGE_CAPTURE_LABEL = "Pix recebido numa cobrança já encerrada"

#: Os eventos de dinheiro levam o meio e o valor como detalhe.
_PAYMENT_EVENT_TYPES = frozenset({"payment.authorized", "payment.captured", "payment.refunded", "account_debt_reduced"})

#: A mesma edição, com o rótulo de quem fez quando não foi o balcão. A Concierge
#: acrescenta itens e altera o pedido (data, item, endereço, OC-11) pelo MESMO
#: serviço (``order_edit``), e a equipe lê no histórico.
_EDIT_SOURCE_LABELS = {
    "concierge:add": "Itens acrescentados pela Concierge a pedido do cliente",
    "concierge:amend": "Pedido alterado pela Concierge a pedido do cliente",
}

# Mudança de status, nas duas grafias que existem no banco: o model escreve
# `status_changed` e o histórico importado escreve `status_change`. Só a
# primeira era reconhecida, então a esmagadora maioria dos eventos virava
# "Status Change" no `.title()`.
_STATUS_EVENT_TYPES = {"status_changed", "status_change"}


# Quem fez, na língua de quem lê. O ``event.actor`` é um código de máquina
# ("pos:fran", "auto_confirm", "system:counter_handoff") e chegava cru ao
# histórico do Gestor e do PDV. Gente vira o nome da pessoa; processo vira o nome
# do ato. O que não está aqui e não é ninguém da equipe sai sem autor (melhor
# vazio que jargão).
_SYSTEM_ACTOR_LABELS = {
    "auto_confirm": "Confirmação automática",
    "system:counter_handoff": "Entrega no balcão",
    "system:counter_kds_handoff": "Entrega no balcão",
    "system:handoff": "Entrega ao cliente",
    "system:post_handoff": "Conclusão após a entrega",
    "system:kds_dispatch": "Cozinha",
    "system:payment": "Pagamento confirmado",
    "system:pix-confirmation": "Pagamento confirmado",
    # Conferência com o gateway e o vigia da autorização do cartão não
    # CONFIRMAM pagamento: o primeiro só descobre uma autorização, o segundo
    # cancela a que venceu. "Pagamento confirmado" ali era rótulo que mente.
    "payment.gateway_reconcile": "",
    "payment.card_authorization": "Prazo da autorização do cartão",
    "payment.timeout": "Prazo do pagamento",
    "payment.timeout_gateway_check": "Prazo do pagamento",
    "confirmation.timeout": "Prazo de aceite",
    "delivery.auto_complete": "Conclusão automática",
    "customer.self_confirm": "Cliente",
    "customer:self-service": "Cliente",
    "customer": "Cliente",
    "concierge": "Concierge",
    "auto_reject_unavailable": "Recusa automática",
    "auto_reject_oos": "Recusa automática",
    "DANFE impressa": "DANFE impressa",
    "Via Cozinha impressa": "Via Cozinha impressa",
}
_SYSTEM_ACTOR_PREFIXES = (
    ("system:ifood", "iFood"),
    ("ifood", "iFood"),
    # O nome do serviço da corrida, trocado em ``_build_timeline``.
    ("courier", "{service}"),
)
# Prefixos que só dizem DE ONDE a pessoa agiu; o nome vem depois dos dois-pontos.
_PERSON_ACTOR_PREFIXES = frozenset({
    "pos", "gestor", "operator", "kds", "production", "admin", "manager",
    "order-status", "fiscal-requeue", "equipment-back", "card-machine-refund",
})


def _actor_username(actor: str) -> str:
    """O username por trás de ``"pos:fran"``/``"equipment-back:gestor:ana"``, ou ``actor``."""
    current = str(actor or "").strip()
    while ":" in current and current.split(":", 1)[0] in _PERSON_ACTOR_PREFIXES:
        current = current.split(":", 1)[1]
    return current


def _actor_names(actors) -> dict[str, str]:
    from django.contrib.auth import get_user_model

    usernames = {_actor_username(actor) for actor in actors if actor}
    usernames.discard("")
    if not usernames:
        return {}
    names: dict[str, str] = {}
    for user in get_user_model().objects.filter(username__in=usernames):
        names[user.username] = (user.get_full_name() or "").strip() or user.username
    return names


def _timeline_actor(actor: str, names: dict[str, str]) -> str:
    actor = str(actor or "").strip()
    if not actor:
        return ""
    if actor in _SYSTEM_ACTOR_LABELS:
        return _SYSTEM_ACTOR_LABELS[actor]
    for prefix, label in _SYSTEM_ACTOR_PREFIXES:
        if actor == prefix or actor.startswith((f"{prefix}:", f"{prefix}.", f"{prefix}_")):
            return label
    username = _actor_username(actor)
    if username in names:
        return names[username]
    # Código de processo que ninguém nomeou ("system:oven-sweep", "lifecycle.on_ready"):
    # sem autor, em vez de jargão. Pessoa da casa sem cadastro sai pelo próprio nome.
    if actor.startswith("system") or "." in actor or "_" in username or ":" in username:
        return ""
    return username


def _cancellation_detail(order: Order) -> str:
    """O motivo e a observação interna do cancelamento, para a linha "Cancelado".

    O cancelamento grava os dois em ``order.data`` (``cancellation_reason_key`` e
    ``cancellation_internal_note``) e não no evento: sem esta leitura, quem chega
    no turno seguinte lia só "Cancelado" e não sabia por quê.
    """
    from shopman.shop.services import cancel_reasons

    data = order.data or {}
    reason = cancel_reasons.cancel_reason(data.get("cancellation_reason_key"))
    label = reason.label if reason else ""
    note = str(data.get("cancellation_internal_note") or "").strip()
    if data.get("no_show"):
        # Não retirado (WP-G11): o gesto é assinado por um Gerente, e quem chega
        # no turno seguinte lê quem assinou ao lado do motivo.
        from shopman.backstage.projections.order_no_show import approver_username

        approver = approver_username(order)
        if approver:
            name = _actor_names([approver]).get(approver, approver)
            label = f"{label} · autorizado por {name}" if label else f"Autorizado por {name}"
    if label and note:
        return f"{label}: {note}"
    return label or note


def _build_timeline(order: Order) -> tuple[TimelineEventProjection, ...]:
    events = list(order.events.order_by("seq"))
    names = _actor_names(event.actor for event in events)
    service = _courier_service_name({"service": _courier_service_ref(order)})
    result: list[tuple] = []
    for event in events:
        payload = event.payload or {}
        new_status = payload.get("new_status", "")
        if event.type in _STATUS_EVENT_TYPES and new_status:
            label = order_status_label(new_status)
        elif event.type == "order_edited" and payload.get("source") in _EDIT_SOURCE_LABELS:
            label = _EDIT_SOURCE_LABELS[payload["source"]]
        elif event.type == "payment.captured" and payload.get("outside_charge"):
            label = _OUTSIDE_CHARGE_CAPTURE_LABEL
        elif event.type == "customer_contact_requested" and payload.get("origin") == "cancellation":
            label = "Cliente quis cancelar com o preparo começado e pediu para falar com o responsável"
        elif event.type == "courier_status" and (ride_label := courier_state_label(
            {"service": _courier_service_ref(order), "status": payload.get("status")}
        )):
            label = f"{service}: {ride_label}"
        elif event.type in _EVENT_LABELS:
            label = _EVENT_LABELS[event.type].replace("{service}", service)
        else:
            # Tipo que ninguém rotulou. Identificador não é texto de tela: a linha
            # diz que houve um registro, em português, e o defeito grita no log com
            # o tipo, para ganhar rótulo em ``_EVENT_LABELS``. Antes saía o código
            # humanizado ("Customer cancellation requested") na tela do operador.
            logger.error("order_queue.event_without_label type=%s order=%s", event.type, order.ref)
            label = UNLABELLED_EVENT_LABEL

        if event.type in _PRODUCTION_PROMISE_EVENTS:
            detail = _production_hold_lost_detail(payload)
        elif event.type in {"payment.refund_retry", "payment.order_refund"}:
            detail = _refund_retry_detail(payload)
        elif event.type in _PAYMENT_EVENT_TYPES:
            detail = _payment_event_detail(payload)
        else:
            detail = _event_detail(payload)
        if not detail and event.type in _STATUS_EVENT_TYPES and new_status == Order.Status.CANCELLED:
            detail = _cancellation_detail(order)

        result.append(
            (
                event.created_at,
                TimelineEventProjection(
                    label=label,
                    event_type=event.type,
                    timestamp_display=_format_datetime(event.created_at),
                    actor=_timeline_actor(event.actor, names).replace("{service}", service),
                    detail=detail,
                ),
            )
        )
    # O que o iFood conduz (entregador, saída e encerramento lá) entra na mesma
    # linha, na ordem da hora em que chegou.
    for when, label, detail in ifood_projection.timeline_facts(order):
        result.append(
            (
                when,
                TimelineEventProjection(
                    label=label,
                    event_type="ifood_fact",
                    timestamp_display=_format_datetime(when),
                    actor="iFood",
                    detail=detail,
                ),
            )
        )
    result.sort(key=lambda item: item[0])
    return tuple(projection for _when, projection in result)


def _short_date(raw) -> str:
    from datetime import date as _date

    try:
        return _date.fromisoformat(str(raw or "")).strftime("%d/%m")
    except ValueError:
        return "sem data"


def _payment_event_detail(payload: dict) -> str:
    """"Pix · R$ 22,00": o meio e o valor do fato de dinheiro, sem chave interna."""
    method = str(payload.get("method") or "")
    parts = [payment_method_label(method)] if method else []
    if payload.get("amount_q"):
        parts.append(_money(payload.get("amount_q")))
    return " · ".join(part for part in parts if part)


#: O evento que ``shop/services/production_promise`` grava quando o lote cancelado
#: leva a reserva do pedido.
_PRODUCTION_HOLD_LOST_EVENT = "production_hold_lost"
#: Os três fatos da promessa de produção (cancelado, rendeu menos, atrasado) têm o
#: mesmo detalhe: o item e o lote.
_PRODUCTION_PROMISE_EVENTS = frozenset(
    {_PRODUCTION_HOLD_LOST_EVENT, "production_hold_short", "production_lot_late", "production_hold_grade"}
)


def _production_hold_lost_detail(payload: dict) -> str:
    """O item e o lote que ele perdeu ("4x Ciabatta · lote de 19/11").

    O ``reason`` desse evento é um código (``production_voided``), não uma frase:
    na linha do tempo ele aparecia cru ao lado do título (prévia do WP-G08).
    """
    name = str(payload.get("product_name") or payload.get("sku") or "").strip()
    qty = str(payload.get("qty") or "").strip()
    item = f"{qty}x {name}" if qty and name else name
    lot = f"lote de {_short_date(payload.get('date'))}" if payload.get("date") else ""
    return " · ".join(part for part in (item, lot) if part)


def _refund_retry_detail(payload: dict) -> str:
    """"Pix · R$ 22,00 · autorizado por Joyce · não saiu: …": a tentativa de estorno do Gestor."""
    parts = [_payment_event_detail(payload)]
    approver = str(payload.get("approved_by") or "").strip()
    if approver:
        parts.append(f"autorizado por {_actor_names([approver]).get(approver, approver)}")
    if payload.get("outcome") == "refunded":
        parts.append("o meio de pagamento confirmou")
    else:
        answer = str(payload.get("message") or "").strip()
        parts.append(f"não saiu: {answer}" if answer else "não saiu")
    return " · ".join(part for part in parts if part)


def _event_detail(payload: dict) -> str:
    if not payload:
        return ""
    # Mudança de status não ganha detalhe próprio: o título do evento já é o status
    # novo e o anterior é a linha de cima. O "Aceito -> Pronto" repetia o título, e o
    # primeiro evento saía "- -> Novo" (dono, 08/10/2026). O motivo, quando houver,
    # continua aparecendo pelo fim da função.
    if payload.get("to_date"):
        # Reagendamento: "12/10 → 15/10", e o motivo quando houver.
        moved = f"{_short_date(payload.get('from_date'))} → {_short_date(payload.get('to_date'))}"
        return f"{moved}: {payload['reason']}" if payload.get("reason") else moved
    if payload.get("source") in {"pos:edit", *_EDIT_SOURCE_LABELS} and payload.get("customer_note"):
        # Edição da encomenda: a MESMA frase que o cliente recebeu — o que
        # mudou, o total novo e o destino da diferença.
        return str(payload["customer_note"])
    for key in ("reason", "note", "error"):
        value = payload.get(key)
        if value:
            return str(value)
    # Sem detalhe legível, NENHUM detalhe. O fallback despejava o payload cru ao
    # lado do evento — `{"from_session": "SESS-V53LZVEYKF3Q"}` na tela de quem
    # atende o balcão. Chave interna não é informação para o operador.
    return ""


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return format_local(local, "%d/%m às {clock}")
