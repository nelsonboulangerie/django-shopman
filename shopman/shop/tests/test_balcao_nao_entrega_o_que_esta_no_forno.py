"""O balcão não entrega — nem dá baixa — no pão que ainda está no forno.

A venda de balcão fecha ``COMPLETED`` no ato porque o cliente sai com a
mercadoria na mão (``system:counter_handoff``). A premissa vale para a gôndola
e é FALSA para a fornada planejada: ali o pão ainda está assando, o cliente vai
esperar, e o pedido precisa continuar vivo para que alguém no gestor saiba que
há gente esperando.

Sem o corte, três coisas aconteciam de uma vez na venda mais normal da padaria:
o pedido nascia e morria no mesmo instante (invisível no board), a baixa de
estoque era mandada contra um lote que não saiu, e o ``fulfill_hold`` falhava
gerando um alerta CRÍTICO de "estoque acima do físico".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.utils import timezone

from shopman.shop.services import waitlist
from shopman.shop.services.order_helpers import customer_holds_the_goods


class _FakeOrder(SimpleNamespace):
    """Pedido de balcão o bastante para as duas perguntas deste arquivo."""


def _counter_order(**data) -> _FakeOrder:
    base = {
        "origin_channel": "pos",
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
    }
    base.update(data)
    return _FakeOrder(ref="PDV-TESTE-1", channel_ref="pdv", data=base, snapshot={})


class TestCustomerHoldsTheGoods:
    def test_counter_sale_from_the_shelf_still_hands_over_on_the_spot(self, monkeypatch):
        """O caso comum não pode regredir: pão da gôndola fecha na hora."""
        monkeypatch.setattr(waitlist, "is_in_fermata", lambda order: False)
        assert customer_holds_the_goods(_counter_order()) is True

    def test_bread_still_in_the_oven_is_not_in_anyones_hands(self, monkeypatch):
        """Mesma venda, mesmo balcão — mas o pedido está esperando o lote."""
        monkeypatch.setattr(waitlist, "is_in_fermata", lambda order: True)
        assert customer_holds_the_goods(_counter_order()) is False

    def test_a_mute_stockman_never_freezes_the_counter(self, monkeypatch):
        """Fila é o caminho excepcional. Se a pergunta explode, a venda de
        balcão segue fechando — travar o caixa por causa de um selo seria
        trocar um alerta por uma fila de gente parada."""

        def _boom(order, *, holds=None, quant_available=None):
            raise RuntimeError("stockman mudo")

        monkeypatch.setattr(waitlist, "state_for", _boom)
        assert customer_holds_the_goods(_counter_order()) is True


class TestOneQuestionOnePlace:
    def test_the_manager_and_the_counter_ask_the_same_function(self):
        """O gestor barrava o preparo com a sua própria cópia da pergunta.
        Duas cópias são duas réguas, e a segunda envelhece calada."""
        import inspect

        from shopman.shop.services import operator_orders

        source = inspect.getsource(operator_orders._waiting_for_the_batch)
        assert "waitlist.is_in_fermata" in source
        assert "FERMATA" not in source


@pytest.mark.django_db
class TestStockFulfillWaitsForTheBatch:
    def test_fulfill_is_not_allowed_while_the_batch_has_not_come_out(self, monkeypatch):
        """Não se dá baixa no que não saiu do forno: a reserva em fermata
        aponta para um quant PLANEJADO e o ``fulfill`` falha por construção."""
        from shopman.shop import lifecycle
        from shopman.shop.config import ChannelConfig

        config = ChannelConfig.from_dict({"payment": {"method": "cash", "timing": "external"}})
        order = _counter_order()

        monkeypatch.setattr(waitlist, "is_in_fermata", lambda order: True)
        assert lifecycle._stock_fulfill_allowed(order, config) is False

        monkeypatch.setattr(waitlist, "is_in_fermata", lambda order: False)
        assert lifecycle._stock_fulfill_allowed(order, config) is True


class TestReviewAsksForTheRightDay:
    def test_the_commitment_date_is_the_one_the_order_is_for(self):
        """A review conferia o estoque de HOJE mesmo numa encomenda para
        sexta: o aviso gritava falta que a fornada de sexta cobre, e calava
        falta real da data combinada."""
        from datetime import date

        from shopman.shop.services.pos import _payload_commitment_date

        assert _payload_commitment_date({"delivery_date": "2027-03-05"}) == date(2027, 3, 5)
        # Balcão sem agendamento é hoje; data ilegível não inventa outro dia.
        assert _payload_commitment_date({}) == timezone.localdate()
        assert _payload_commitment_date({"delivery_date": "nao-e-data"}) == timezone.localdate()


class TestTheWarningSaysWhichProblemItIs:
    def test_four_causes_stop_sharing_one_sentence(self):
        """"só N em estoque" mandava o operador caçar unidade na prateleira
        quando o problema era o produto estar pausado, fora do cardápio, ou
        simplesmente ainda no forno."""
        from shopman.shop.services.pos import _availability_shortfall

        assert "pausado" in _availability_shortfall({"is_paused": True})
        assert "fora do cardápio" in _availability_shortfall({"reason_code": "not_in_listing"})
        assert "lote planejado" in _availability_shortfall({"is_planned": True})
        assert "em estoque" in _availability_shortfall({"available_qty": 2})

    def test_half_a_kilo_is_not_reported_as_zero(self):
        """``int(available_qty)`` truncava: meio quilo de queijo virava
        "só 0 em estoque" numa venda que estava correta."""
        from decimal import Decimal

        from shopman.shop.services.pos import _availability_shortfall

        assert "0,5" in _availability_shortfall({"available_qty": Decimal("0.5")})
        # E o inteiro não ganha casas decimais de enfeite.
        assert "só 3 em" in _availability_shortfall({"available_qty": Decimal("3.00")})
