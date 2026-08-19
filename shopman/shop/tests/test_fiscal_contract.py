"""O contrato fiscal precisa cobrir o que a cadeia realmente chama.

Regressão do audit do Fiscalman (F4): ``FiscalBackend.emit`` no ``contracts.py``
não declarava ``delivery``, que o handler passa e o FocusNFeBackend aceita.
Funcionava porque ``runtime_checkable`` **não confere assinaturas** — o Protocol
não protegia nada: um segundo backend implementado fielmente *pelo contrato*
quebraria com ``TypeError`` na primeira entrega a domicílio.

Estes testes olham a assinatura, justamente porque ``isinstance`` não olha.
"""

from __future__ import annotations

import inspect

import pytest
from shopman.fiscalman.contracts import FiscalBackend, FiscalDocumentResult
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend
from shopman.shop.handlers.fiscal import NFCeEmitHandler
from shopman.shop.models import Channel

pytestmark = pytest.mark.django_db

AUTHORIZED = FiscalDocumentResult(
    success=True, access_key="4125" + "0" * 40, status="authorized"
)


def _contract_params() -> set[str]:
    return set(inspect.signature(FiscalBackend.emit).parameters) - {"self"}


class ContractOnlyBackend:
    """Backend implementado ao pé da letra do Protocol — nada além dele."""

    def __init__(self):
        self.received: dict = {}

    def emit(self, **kwargs):
        unexpected = set(kwargs) - _contract_params()
        if unexpected:
            raise TypeError(f"emit() got an unexpected keyword argument {sorted(unexpected)}")
        self.received = kwargs
        return AUTHORIZED

    def query_status(self, *, reference):
        return FiscalDocumentResult(success=False)

    def cancel(self, *, reference, reason):
        raise NotImplementedError


@pytest.fixture
def emit_directive(db):
    Channel.objects.create(ref="pdv", name="PDV")
    order = Order.objects.create(
        ref="ORD-FISCAL-CONTRACT-1",
        channel_ref="pdv",
        status=Order.Status.COMPLETED,
        total_q=5000,
    )
    return Directive.objects.create(
        topic="fiscal.emit_nfce",
        payload={
            "order_ref": order.ref,
            "items": [],
            "payment": {"method": "cash", "amount_q": 5000},
            "customer": {},
            "delivery": {"address": {"route": "Rua X"}},
        },
    )


def test_a_backend_written_strictly_to_the_contract_survives_the_handler(emit_directive):
    backend = ContractOnlyBackend()

    NFCeEmitHandler(backend).handle(message=emit_directive, ctx={})

    assert backend.received["delivery"] == {"address": {"route": "Rua X"}}


def test_the_reference_adapter_accepts_every_keyword_the_contract_declares():
    adapter = set(inspect.signature(FocusNFeBackend.emit).parameters)
    missing = _contract_params() - adapter
    assert not missing, f"FocusNFeBackend.emit não aceita {sorted(missing)} do contrato"


def test_runtime_checkable_alone_would_not_have_caught_this():
    # Documenta por que os testes acima existem: isinstance passa mesmo com a
    # assinatura errada, então ele não serve de guarda.
    class WrongSignature:
        def emit(self):  # sem nenhum dos parâmetros do contrato
            return AUTHORIZED

        def query_status(self, *, reference):
            return AUTHORIZED

        def cancel(self, *, reference, reason):
            raise NotImplementedError

    assert isinstance(WrongSignature(), FiscalBackend)
