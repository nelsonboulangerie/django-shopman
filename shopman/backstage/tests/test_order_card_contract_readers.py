"""Campo do cartão do pedido só existe com leitor (WP-G09, EXCELENCIA-GESTOR P2-09).

O ``OrderCardProjection`` chegou a 107 campos, e 16 deles ninguém lia: nem o
Gestor, nem o kit, nem as vizinhas. Cada campo sem leitor custa uma leitura por
pedido a cada atualização do quadro e, pior, parece dizer algo à tela
("Pagamento simulado" existia no servidor e nunca apareceu no cartão).

A trava: cada campo declara aqui QUEM o lê, e o teste confere que o leitor
existe e de fato escreve o nome do campo em código (comentário não vale).

- Campo novo no cartão sem linha aqui: reprova. Declare o leitor ou não crie.
- Leitor que deixou de ler: reprova. Aponte o leitor de hoje ou apague o campo.
- O detalhe do pedido não é leitor do cartão: ele lê ``OperatorOrderProjection``,
  outro contrato. Apontá-lo aqui reprova.

Antes de apagar um campo, a prova é a busca: ``git grep -w <campo> --
surfaces/orders-nuxt/app surfaces/operator-kit/app`` (o quadro é servido só ao
Gestor, em ``/api/v1/backstage/orders/``).
"""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from shopman.backstage.projections.order_queue import OrderCardProjection

REPO = Path(__file__).resolve().parents[3]

GESTOR = "surfaces/orders-nuxt/app/"
#: O próprio quadro: a lista "Encomendas" se ordena pela hora em que cada
#: encomenda de hoje chega à Cozinha (``build_two_zone_queue``).
SERVER_QUEUE = "shopman/backstage/projections/order_queue.py"

#: Quem lê cada campo do cartão: um arquivo que escreve o nome do campo em código.
CARD_FIELD_READERS: dict[str, str] = {
    "ref": GESTOR + "presentation/board.ts",
    "status": GESTOR + "presentation/board.ts",
    "actions": GESTOR + "presentation/board.ts",
    "status_label": GESTOR + "presentation/board.ts",
    "channel_ref": GESTOR + "presentation/board.ts",
    "channel_name": GESTOR + "presentation/board.ts",
    "channel_icon": GESTOR + "pages/index.vue",
    "customer_name": GESTOR + "presentation/board.ts",
    "created_at_iso": GESTOR + "presentation/board.ts",
    "server_now_iso": GESTOR + "components/OrderCard.vue",
    "elapsed_seconds": GESTOR + "presentation/board.ts",
    "timer_class": GESTOR + "presentation/board.ts",
    "items_summary": GESTOR + "presentation/board.ts",
    "items_count": GESTOR + "presentation/board.ts",
    "total_display": GESTOR + "presentation/board.ts",
    "fulfillment_label": GESTOR + "presentation/orderReason.ts",
    "fulfillment_type": GESTOR + "presentation/board.ts",
    "delivery_address": GESTOR + "presentation/queue.ts",
    "can_confirm": GESTOR + "presentation/board.ts",
    "can_advance": GESTOR + "presentation/board.ts",
    "next_status": GESTOR + "presentation/board.ts",
    "payment_method": GESTOR + "components/OrderCard.vue",
    "payment_method_label": GESTOR + "presentation/board.ts",
    "payment_status": GESTOR + "presentation/orderReason.ts",
    "payment_status_label": GESTOR + "presentation/board.ts",
    "payment_pending": GESTOR + "presentation/board.ts",
    "payment_tone": GESTOR + "presentation/board.ts",
    "advance_block_label": GESTOR + "presentation/board.ts",
    "advance_block_reason": GESTOR + "presentation/board.ts",
    "can_settle_delivery_cash": GESTOR + "presentation/board.ts",
    "fiscal_status": GESTOR + "components/OrderCard.vue",
    "has_customer_note": GESTOR + "components/OrderCard.vue",
    "is_gift": GESTOR + "components/OrderCard.vue",
    "gift_has_recipient": GESTOR + "components/OrderCard.vue",
    "assigned_operator": GESTOR + "presentation/board.ts",
    "awaiting_work_orders": GESTOR + "presentation/board.ts",
    "confirmation_deadline_iso": GESTOR + "presentation/board.ts",
    "confirmation_action": GESTOR + "presentation/board.ts",
    "card_authorization_expires_iso": GESTOR + "components/OrderCard.vue",
    "channel_display_id": GESTOR + "presentation/board.ts",
    "courier_status_label": GESTOR + "presentation/queue.ts",
    "is_preorder": GESTOR + "presentation/queue.ts",
    "commitment_date": GESTOR + "presentation/board.ts",
    "commitment_date_display": GESTOR + "presentation/board.ts",
    "schedule_label": GESTOR + "presentation/board.ts",
    "schedule_state": GESTOR + "presentation/board.ts",
    "kitchen_release_at_iso": SERVER_QUEUE,
    "kitchen_release_label": GESTOR + "presentation/board.ts",
    "kitchen_released_at_iso": GESTOR + "presentation/board.ts",
    "clock_since_iso": GESTOR + "presentation/queue.ts",
    "change_out_suggested_q": GESTOR + "presentation/board.ts",
    "change_out_q": GESTOR + "presentation/board.ts",
    "change_back_pending": GESTOR + "components/OrderCard.vue",
    "change_label": GESTOR + "components/OrderCard.vue",
    "equipment_options": GESTOR + "presentation/board.ts",
    "equipment_label": GESTOR + "presentation/board.ts",
    "equipment_back_pending": GESTOR + "presentation/board.ts",
    "dispatch_needs_machine": GESTOR + "presentation/board.ts",
    "trip_with": GESTOR + "presentation/board.ts",
    "courier_return_orders": GESTOR + "presentation/board.ts",
    "courier_return_lines": GESTOR + "components/CourierBackDialog.vue",
    "waitlist_state": GESTOR + "components/OrderCard.vue",
    "waitlist_label": GESTOR + "components/OrderCard.vue",
    "ifood_cancellation_notice": GESTOR + "components/OrderCard.vue",
    "ifood_pickup_code_label": GESTOR + "components/OrderCard.vue",
    "ifood_logistics_label": GESTOR + "presentation/queue.ts",
    "ifood_schedule_label": GESTOR + "components/OrderCard.vue",
    "ifood_remote_ahead_label": GESTOR + "components/OrderCard.vue",
    "ifood_negotiations": GESTOR + "components/OrderCard.vue",
    "ifood_accept_failed": GESTOR + "presentation/board.ts",
    "ifood_accept_notice": GESTOR + "presentation/board.ts",
    "test_order_label": GESTOR + "components/OrderCard.vue",
    "test_order_notice": GESTOR + "components/OrderCard.vue",
    "danfe_printable": GESTOR + "presentation/danfe.ts",
    "danfe_printed": GESTOR + "presentation/danfe.ts",
    "danfe_state": GESTOR + "presentation/danfe.ts",
    "danfe_problem": GESTOR + "presentation/danfe.ts",
    "undo": GESTOR + "presentation/board.ts",
    "kitchen": GESTOR + "presentation/kitchen.ts",
    "volumes": GESTOR + "presentation/board.ts",
    "volumes_checked": GESTOR + "presentation/volumeCheck.ts",
    "volumes_to_check": GESTOR + "presentation/volumeCheck.ts",
    "ready_at_iso": GESTOR + "presentation/board.ts",
    "dispatched_at_iso": GESTOR + "presentation/board.ts",
    "attention": GESTOR + "presentation/queue.ts",
    "attention_since_iso": GESTOR + "presentation/queue.ts",
    "goal_minutes": GESTOR + "presentation/queue.ts",
    "goal_label": GESTOR + "presentation/queue.ts",
    "ready_eta_iso": GESTOR + "presentation/boardStrip.ts",
    "courier_reminder": GESTOR + "components/OrderCard.vue",
    "payment_lapsed": GESTOR + "presentation/queue.ts",
    "customer_whatsapp_url": GESTOR + "components/OrderCard.vue",
    "advance_block_waits": GESTOR + "presentation/orderPromise.ts",
    "promise": GESTOR + "presentation/orderPromise.ts",
}

#: Leitores do DETALHE do pedido (``OperatorOrderProjection``): não leem o cartão.
DETAIL_READERS = (
    "surfaces/orders-nuxt/app/pages/[ref].vue",
    "surfaces/operator-kit/app/components/OperatorOrderDetail.vue",
    "surfaces/operator-kit/app/types/orderDetail.ts",
)

#: O que não conta como leitura: o espelho gerado do contrato e os tipos que o estreitam.
NOT_READERS = ("surfaces/orders-nuxt/app/generated/", "surfaces/orders-nuxt/app/types/")


def _code(path: Path) -> str:
    """O arquivo sem comentários: campo citado só em comentário não é campo lido."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        text = re.sub(r'""".*?"""', "", text, flags=re.S)
        return re.sub(r"#[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def _card_fields() -> list[str]:
    return [field.name for field in fields(OrderCardProjection)]


def test_todo_campo_do_cartao_declara_quem_o_le():
    declared, contract = set(CARD_FIELD_READERS), set(_card_fields())
    orphans = sorted(contract - declared)
    stale = sorted(declared - contract)
    assert not orphans, (
        f"campo do cartão sem leitor declarado: {orphans}. Quem lê? Declare em "
        "CARD_FIELD_READERS, ou não mande o campo: o contrato leva só o que alguém lê."
    )
    assert not stale, f"leitor declarado de campo que não existe mais no cartão: {stale}"


@pytest.mark.parametrize("field", sorted(CARD_FIELD_READERS))
def test_o_leitor_declarado_le_o_campo(field):
    reader = CARD_FIELD_READERS[field]
    assert reader not in DETAIL_READERS, (
        f"{reader} lê o detalhe do pedido, não o cartão: não serve de leitor de {field!r}."
    )
    assert not reader.startswith(NOT_READERS), f"{reader} é espelho do contrato, não leitor de {field!r}."
    path = REPO / reader
    assert path.is_file(), f"o leitor declarado de {field!r} não existe: {reader}"
    pattern = rf"\b{field}\b"
    if reader == SERVER_QUEUE:
        # No servidor, ler é usar o campo de um cartão já montado (``card.<campo>``).
        pattern = rf"\bcard\.{field}\b"
    assert re.search(pattern, _code(path)), (
        f"{reader} não lê mais {field!r}. Aponte quem lê hoje, ou apague o campo do "
        "cartão (e regenere o contrato com export_orders_schema)."
    )


def test_a_trava_reprova_campo_sem_leitor(monkeypatch):
    """A trava morde: um campo a mais no cartão, sem leitor, é acusado pelo nome."""
    real = _card_fields()
    monkeypatch.setitem(globals(), "_card_fields", lambda: [*real, "campo_que_ninguem_le"])
    with pytest.raises(AssertionError, match="campo_que_ninguem_le"):
        test_todo_campo_do_cartao_declara_quem_o_le()
