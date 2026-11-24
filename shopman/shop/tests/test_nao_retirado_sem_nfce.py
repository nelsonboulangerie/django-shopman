"""Encomenda paga e não retirada: o valor retido não tem NFC-e (#2695).

Resposta do contador (24/11/2026, repassada pelo dono): a parte executada de
uma encomenda é o que foi ENTREGUE. Produzir sem entregar não é parte
executada. O valor que a loja retém de uma encomenda paga e não retirada é
multa por desistência, fora da receita bruta do Simples: recibo, sem NFC-e.

No sistema, a NFC-e da encomenda nasce na saída da mercadoria
(``fiscal.emission_waits_for_handoff``, decisão de 26/09/2026), e o "Não
retirado" termina o pedido em ``cancelled`` sem passar pela saída. Estes testes
travam as duas pontas com a emissão LIGADA e um meio de pagamento que exige
nota (Pix), para que o verde não seja só "não havia backend":

- o gesto do Gerente não enfileira emissão nem grava documento fiscal;
- a emissão avulsa do Gestor recusa o pedido, e o ``fiscal.emit`` direto
  (a rede de todo ponto de saída) também não enfileira nada.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.fiscalman.models import FiscalDocument
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.services import fiscal, no_show
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

_FISCAL_ON = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    },
    SHOPMAN_FISCAL_ADAPTER="shopman.backstage.tests.test_pos_counter_handoff_integration.StubFiscalBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.eletronic_payment",
)


@pytest.fixture(autouse=True)
def mundo():
    with _FISCAL_ON:
        fiscal_pool.reset()
        world.make_shop()
        world.product("BOLO", price_q=3000)
        world.lot("BOLO")
        yield
    fiscal_pool.reset()


@pytest.fixture
def fim_do_expediente(monkeypatch):
    moment = world.at(19, 5)
    monkeypatch.setattr(timezone, "now", lambda: moment)
    return moment


def _encomenda_paga_no_pix() -> Order:
    """Bolo feito sob encomenda, pago no Pix, pronto desde as 14h. Sem reserva baixada: vira perda."""
    order = world.ready_order("NAO-RETIRADO-NFCE", [("BOLO", 1, 3000)], held=False, ready_at=world.at(14))
    world.pay(order, "pix")
    order.refresh_from_db()
    return order


def _emissoes(order: Order):
    return Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)


def test_a_emissao_esta_ligada_para_esta_encomenda(fim_do_expediente):
    """Premissa: com a mesma configuração, a regra emitiria na saída."""
    order = _encomenda_paga_no_pix()

    assert fiscal_pool.get_backend() is not None
    assert fiscal.emission_resolver(order)
    assert fiscal.emission_waits_for_handoff(order)


def test_nao_retirado_retem_o_valor_sem_nfce(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _encomenda_paga_no_pix()

    with django_capture_on_commit_callbacks(execute=True):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()

    assert order.status == Order.Status.CANCELLED
    assert order.data["no_show"]["retained_q"] == 3000
    assert not _emissoes(order).exists()
    assert not FiscalDocument.objects.filter(reference=order.ref).exists()
    assert not order.data.get("nfce_access_key")


def test_depois_do_nao_retirado_nenhum_caminho_emite(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _encomenda_paga_no_pix()
    with django_capture_on_commit_callbacks(execute=True):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()

    assert fiscal.issue_override_refusal(order) == "Venda cancelada ou devolvida não emite NFC-e."
    fiscal.emit(order)
    assert not _emissoes(order).exists()
