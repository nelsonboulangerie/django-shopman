"""A hora da Cozinha no Gestor (WP-G02, EXCELENCIA-GESTOR P1-02, P1-03, P1-05).

A encomenda do dia caía no fluxo à meia-noite com "Iniciar preparo" em primeiro
plano, âmbar na Fila e "há 3d 4h" no relógio (o tempo desde a compra). O servidor
já sabia a hora dela (``lifecycle.preorder_activation_at``: combinado − preparo −
antecedência); o card não lia. Esta suíte prende:

- antes da hora, o card diz "Vai para a Cozinha às 16h15", não entra em
  ``attention`` e o gesto de iniciar é "Adiantar", secundário;
- o detalhe dá ao gesto o mesmo nome e a mesma frase;
- depois que a encomenda chega à Cozinha, o card pede "Iniciar preparo" e o
  relógio conta da chegada (``kitchen_released_at``), nunca da compra;
- o pedido de agora e a encomenda de outro dia não ganham a frase.

É a J4 do plano (encomenda no dia), por projeção com relógio congelado: a pilha
local não tem relógio de teste.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.order_queue import (
    build_operator_order,
    build_order_card,
    build_two_zone_queue,
)
from shopman.shop.lifecycle import KITCHEN_RELEASED_AT_KEY
from shopman.shop.models import Channel, Shop

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


def _at(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


@pytest.fixture
def relogio(monkeypatch):
    """Crava o relógio: ``relogio(10)`` são 10h de hoje para todo o Django."""

    def set_now(hour: int, minute: int = 0) -> datetime:
        moment = _at(hour, minute)
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment

    return set_now


@pytest.fixture
def operator(db):
    from django.core.cache import cache

    cache.clear()
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "config": {}})
    user = User.objects.create_user("caixa-g02", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    yield user
    cache.clear()


def _order(ref: str, *, days: int = 0, slot: str | None = "17:00-17:30", is_preorder: bool = True, **data) -> Order:
    payload = {
        "customer": {"name": f"Cliente {ref}"},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
        "availability_decision": {"approved": True, "decisions": []},
        **data,
    }
    if is_preorder:
        payload["is_preorder"] = True
        payload["delivery_date"] = (timezone.localdate() + timedelta(days=days)).isoformat()
        if slot:
            payload["delivery_time_slot"] = slot
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=Order.Status.ACCEPTED,
        total_q=1870, data=payload,
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAIN", name="Pain de Campagne", qty=1,
        unit_price_q=1870, line_total_q=1870,
    )
    # Comprada três dias antes: é o relógio que o card NÃO pode mostrar.
    Order.objects.filter(pk=order.pk).update(created_at=_at(18, days=-3), accepted_at=_at(18, 5, days=-3))
    order.refresh_from_db()
    return order


def _advance(card):
    return next(action for action in card.actions if action.ref == "advance")


def test_de_manha_a_encomenda_das_17h_diz_quando_vai_para_a_cozinha(operator, relogio):
    relogio(10)
    order = _order("G02-MANHA")

    card = build_order_card(order, user=operator)

    # 17h − 30 min de preparo − 15 min de antecedência (padrões declarados).
    assert card.kitchen_release_label == "Vai para a Cozinha às 16h15"
    assert card.kitchen_release_at_iso == _at(16, 15).isoformat()
    assert card.kitchen_released_at_iso == ""
    # O combinado segue dito pelo WP-G01, na mesma frase do detalhe.
    assert (card.schedule_label, card.schedule_state) == ("Hoje · 17h às 17h30", "today")


def test_antes_da_hora_o_card_nao_pede_ninguem_e_o_gesto_e_adiantar(operator, relogio):
    relogio(10)
    order = _order("G02-ESPERA")

    card = build_order_card(order, user=operator)
    advance = _advance(card)

    assert card.attention == "", "sem âmbar e sem alarme antes da hora da Cozinha"
    assert (advance.label, advance.priority, advance.enabled) == ("Adiantar", "secondary", True)
    assert card.next_action_label == "Adiantar"
    # O gesto continua existindo: adiantar é escolha consciente de quem opera.
    assert card.can_advance is True


def test_o_detalhe_da_o_mesmo_nome_ao_gesto(operator, relogio):
    relogio(10)
    order = _order("G02-DETALHE")

    detail = build_operator_order(order, user=operator)
    advance = next(action for action in detail.actions if action.ref == "advance")

    assert (advance.label, advance.priority) == ("Adiantar", "secondary")
    assert detail.next_action_label == "Adiantar"
    # E a mesma frase do card, para o gesto não aparecer sem a hora ao lado.
    assert detail.kitchen_release_label == build_order_card(order, user=operator).kitchen_release_label
    assert detail.kitchen_release_label == "Vai para a Cozinha às 16h15"


def test_o_detalhe_de_quem_ja_chegou_nao_tem_a_frase(operator, relogio):
    relogio(16, 20)
    order = _order("G02-DETALHE-CHEGOU", **{KITCHEN_RELEASED_AT_KEY: _at(16, 15).isoformat()})

    detail = build_operator_order(order, user=operator)
    advance = next(action for action in detail.actions if action.ref == "advance")

    assert detail.kitchen_release_label == ""
    assert (advance.label, advance.priority) == ("Iniciar preparo", "primary")


def test_depois_que_chega_a_cozinha_o_card_pede_iniciar_e_conta_da_chegada(operator, relogio):
    relogio(16, 20)
    released = _at(16, 15)
    order = _order("G02-CHEGOU", **{KITCHEN_RELEASED_AT_KEY: released.isoformat()})

    card = build_order_card(order, user=operator)
    advance = _advance(card)

    assert (advance.label, advance.priority) == ("Iniciar preparo", "primary")
    assert card.attention == "start"
    assert card.kitchen_release_label == ""
    assert card.kitchen_released_at_iso == released.isoformat()
    # O relógio conta da chegada à Cozinha: 5 min, não os três dias desde a compra.
    assert card.attention_since_iso == released.isoformat()
    assert card.clock_since_iso == released.isoformat()
    assert card.elapsed_seconds == 5 * 60
    # A meta de quem tem hora combinada segue a hora combinada (17h − estação).
    assert card.goal_label == "combinado para as 17h"


def test_a_fila_do_dia_traz_a_encomenda_que_espera_sem_pedir_ninguem(operator, relogio):
    relogio(10)
    order = _order("G02-FILA")

    queue = build_two_zone_queue(user=operator)
    card = next(card for card in queue.prep if card.ref == order.ref)

    assert card.kitchen_release_label == "Vai para a Cozinha às 16h15"
    assert card.attention == ""


def test_passada_a_hora_sem_o_despertador_o_card_nao_promete_hora_vencida(operator, relogio):
    """O despertador ainda não rodou: o card não diz "vai às 16h15" às 16h30."""
    relogio(16, 30)
    order = _order("G02-VENCIDA")

    card = build_order_card(order, user=operator)

    assert card.kitchen_release_label == ""
    assert _advance(card).label == "Iniciar preparo"


def test_encomenda_sem_hora_combinada_vai_na_abertura_ou_no_comeco_do_dia(operator, relogio):
    relogio(0, 1)
    order = _order("G02-SEM-HORA", slot=None)

    card = build_order_card(order, user=operator)

    # Sem expediente declarado nesta loja de teste: 00:05, o piso do lifecycle.
    assert card.kitchen_release_label == "Vai para a Cozinha às 0h05"


def test_pedido_de_agora_nao_ganha_a_frase_e_conta_da_chegada_do_pedido(operator, relogio):
    relogio(10)
    order = _order("G02-AGORA", is_preorder=False)
    Order.objects.filter(pk=order.pk).update(created_at=_at(9, 50), accepted_at=_at(9, 51))
    order.refresh_from_db()

    card = build_order_card(order, user=operator)

    assert (card.kitchen_release_label, card.kitchen_release_at_iso, card.kitchen_released_at_iso) == ("", "", "")
    assert card.clock_since_iso == order.created_at.isoformat()
    assert card.elapsed_seconds == 10 * 60
    assert _advance(card).label == "Iniciar preparo"


def test_encomenda_de_outro_dia_nao_ganha_a_frase(operator, relogio):
    relogio(10)
    order = _order("G02-AMANHA", days=1)

    card = build_order_card(order, user=operator)

    # O card dela já diz o dia e a janela (WP-G01); a hora da Cozinha é do dia.
    assert card.kitchen_release_label == ""
    assert card.schedule_state == "future"
