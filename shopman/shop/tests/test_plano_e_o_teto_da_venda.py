"""O plano da data é o teto da venda, na escrita também (dono, 28/11/2026).

"muito antes de chegar em Promessa em risco, o sistema de disponibilidade, que
considera o planejado, deve travar!!! Tudo bem ter uma forma de tratar algo que
fugiu ao controle, mas é a exceção da exceção." (DEV-2026-099)

Medido antes deste PR, no banco local: o Croissant com lote de 42 em 29/11 aceitava
60 pela loja (42 presas + 18 de demanda sem lote), porque a reserva, quando o canal
aceita encomenda, gravava o que passava do plano como demanda. A leitura
(``decide``) já dizia 42. Agora a escrita obedece à mesma régua:

- data COM lote planejado: acima do plano o commit da loja recusa
  (``insufficient_supply``) e nada vira demanda;
- a única saída é o gerente no PDV, que grava no pedido o que liberou e quem
  liberou (``preorder_over_plan``); só esse excedente vira demanda;
- data SEM lote: segue pedido à Produção (D2, 16/11/2026), até o dono decidir.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.orderman.exceptions import ValidationError
from shopman.orderman.models import Order, Session
from shopman.stockman.models import Hold

from shopman.shop.services import stock as stock_service
from shopman.shop.tests.test_pos_encomenda_acima_do_plano_bloqueia import (  # noqa: F401
    _amanha,
    _carimbo,
    _encomenda,
    _fechar,
    _plano,
    _review,
    joyce,
)
from shopman.shop.tests.test_pos_scheduled_order import balcao  # noqa: F401
from shopman.shop.tests.test_preorder_closed_store_commit import (
    SKU,
    _commit,
    _make_shop_channel_product,
    _open_session,
    _plan_dated_stock,
)

pytestmark = pytest.mark.django_db


def _holds_of(order) -> list[Hold]:
    return list(Hold.objects.filter(pk__in=stock_service.hold_pks(order.data.get("hold_ids") or [])).active())


def _backed_and_demand(order) -> tuple[Decimal, Decimal]:
    holds = _holds_of(order)
    backed = sum((h.quantity for h in holds if h.quant_id is not None), Decimal("0"))
    demand = sum((h.quantity for h in holds if h.quant_id is None), Decimal("0"))
    return backed, demand


# ── Loja ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def loja():
    channel, position = _make_shop_channel_product()
    return channel, position, timezone.localdate() + timedelta(days=2)


def test_loja_acima_do_plano_da_data_recusa_e_nada_vira_demanda(loja):
    channel, position, day = loja
    _plan_dated_stock(position, day, qty=42)
    _open_session(channel.ref, "TETO-60", day, qty=60)

    with pytest.raises(ValidationError) as exc:
        _commit("TETO-60", channel.ref, "TETO-KEY-60")

    assert exc.value.code == "insufficient_supply"
    assert exc.value.context.get("sku") == SKU
    assert not Order.objects.filter(channel_ref=channel.ref).exists()
    assert Session.objects.get(session_key="TETO-60").state == "open"
    assert not Hold.objects.filter(sku=SKU, quant__isnull=True).exists(), "nada vira demanda sem lote"


def test_loja_dentro_do_plano_fecha_no_lote(loja):
    channel, position, day = loja
    _plan_dated_stock(position, day, qty=42)
    _open_session(channel.ref, "TETO-42", day, qty=42)

    order = Order.objects.get(ref=_commit("TETO-42", channel.ref, "TETO-KEY-42").order_ref)

    assert _backed_and_demand(order) == (Decimal("42"), Decimal("0"))


def test_loja_o_lote_ja_prometido_conta_no_teto(loja):
    """42 planejadas, 30 já encomendadas: a segunda encomenda de 20 não cabe."""
    channel, position, day = loja
    _plan_dated_stock(position, day, qty=42)
    _open_session(channel.ref, "TETO-A", day, qty=30)
    _commit("TETO-A", channel.ref, "TETO-KEY-A")
    _open_session(channel.ref, "TETO-B", day, qty=20)

    with pytest.raises(ValidationError) as exc:
        _commit("TETO-B", channel.ref, "TETO-KEY-B")

    assert exc.value.code == "insufficient_supply"
    assert not Hold.objects.filter(sku=SKU, quant__isnull=True).exists()


def test_loja_data_sem_lote_segue_pedido_a_producao(loja):
    """D2 (16/11/2026) fica como está até o dono responder: sem lote, vira demanda."""
    channel, position, day = loja
    _plan_dated_stock(position, day + timedelta(days=1), qty=42)
    _open_session(channel.ref, "TETO-SEM-LOTE", day, qty=10)

    order = Order.objects.get(ref=_commit("TETO-SEM-LOTE", channel.ref, "TETO-KEY-SL").order_ref)

    assert _backed_and_demand(order) == (Decimal("0"), Decimal("10"))


# ── PDV ──────────────────────────────────────────────────────────────────────


def test_pdv_o_gerente_libera_e_o_pedido_grava_o_que_ele_liberou(balcao, joyce, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    _plano("22")
    payload = _encomenda(shift, qty=30)
    payload["manager_approval"] = _carimbo(joyce, operator, _review(operator, dict(payload)))

    with django_capture_on_commit_callbacks(execute=True):
        result = _fechar(operator, payload)

    order = Order.objects.get(ref=result.order_ref)
    released = order.snapshot["data"]["preorder_over_plan"]
    assert released["approved_by"] == "joyce"
    assert released["reason"] == "preorder_over_plan"
    assert released["approved_at"]
    assert released["lines"] == [{
        "date": _amanha().isoformat(),
        "sku": "CR",
        "requested_qty": "30",
        "planned_qty": "22",
        "unclaimed_qty": "22",
    }]
    # Só o excedente liberado vira demanda: 22 no lote, 8 sem lote.
    assert _backed_and_demand(order) == (Decimal("22"), Decimal("8"))


def test_pdv_dentro_do_plano_nao_grava_liberacao(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    _plano("22")

    with django_capture_on_commit_callbacks(execute=True):
        result = _fechar(operator, _encomenda(shift, qty=20))

    order = Order.objects.get(ref=result.order_ref)
    assert "preorder_over_plan" not in order.snapshot["data"]
    assert _backed_and_demand(order) == (Decimal("20"), Decimal("0"))


# ── A reserva, para qualquer caminho que chegue a ela ────────────────────────


def _pedido(ref: str, qty: int, day, *, released_for=None) -> Order:
    data = {"delivery_date": day.isoformat()}
    sealed = dict(data)
    if released_for is not None:
        sealed["preorder_over_plan"] = {
            "reason": "preorder_over_plan",
            "lines": [{"date": released_for.isoformat(), "sku": "CR"}],
            "approved_by": "joyce",
        }
    return Order.objects.create(
        ref=ref, channel_ref="pdv", status=Order.Status.ACCEPTED, total_q=qty * 900, data=data,
        snapshot={"items": [{"sku": "CR", "name": "Croissant", "qty": qty, "line_id": "l1", "meta": {}}], "data": sealed},
    )


def test_portao_de_commit_sem_liberacao_recusa(balcao):  # noqa: F811
    _plano("22")
    order = _pedido("SEM-LIBERACAO", 30, _amanha())

    with pytest.raises(ValidationError) as exc:
        stock_service.hold(order, require_all=True)

    assert exc.value.code == "insufficient_supply"


def test_portao_de_commit_com_a_liberacao_da_data_aceita_o_excedente_como_demanda(balcao):  # noqa: F811
    _plano("22")
    order = _pedido("LIBERADA", 30, _amanha(), released_for=_amanha())

    stock_service.hold(order, require_all=True)

    assert _backed_and_demand(order) == (Decimal("22"), Decimal("8"))


def test_liberacao_de_outra_data_nao_libera_esta(balcao):  # noqa: F811
    _plano("22")
    order = _pedido("OUTRA-DATA", 30, _amanha(), released_for=_amanha() + timedelta(days=1))

    with pytest.raises(ValidationError):
        stock_service.hold(order, require_all=True)


def test_venda_ja_consumada_fora_do_portao_segue_como_demanda(balcao):  # noqa: F811
    """PDV e iFood chegam consumados: recusar cancelaria uma venda real.

    O PDV já travou antes, no gerente (D-041). O excedente vira demanda, que a
    Produção planeja e o Gestor vê como Promessa em risco.
    """
    _plano("22")
    order = _pedido("CONSUMADA", 30, _amanha())

    stock_service.hold(order, require_all=False)

    assert _backed_and_demand(order) == (Decimal("22"), Decimal("8"))
