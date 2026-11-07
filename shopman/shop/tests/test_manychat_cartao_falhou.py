"""O novo pagamento depois da cobrança de cartão recusada, no WhatsApp (07/11/2026).

Fora da janela de 24h, o ``payment_requested`` sai pelo modelo aprovado
``pagamento_solicitado`` ("Seu pedido está reservado. Falta só o pagamento."), que
não diz que o cartão falhou. No novo pagamento, o aviso passa a sair pela variante
``payment_requested_card_repayment`` (modelo ``pagamento_cartao_nao_passou``), com o
prazo no campo ``payment_deadline``. Falha fechada: sem flow ligado (modelo ainda
em análise na Meta), o aviso segue pelo ``pagamento_solicitado``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.adapters import notification_manychat as mc

pytestmark = pytest.mark.django_db

OLD_FLOW = "content20260101120000_pagamento_solicitado"
REPAYMENT_FLOW = "content20261107120000_cartao_nao_passou"


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _config(flow_map: dict) -> dict:
    return {"api_token": "tok", "flow_map": flow_map}


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, dict]] = []

    def _fake(endpoint, payload, config):
        seen.append((endpoint, payload))
        return {"success": True}

    monkeypatch.setattr(mc, "_api_call", _fake)
    monkeypatch.setattr(mc, "_get_config", lambda: _config({"payment_requested": OLD_FLOW}))
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: "sub-1")
    return seen


@pytest.fixture
def variant_on(monkeypatch):
    monkeypatch.setattr(
        mc,
        "_get_config",
        lambda: _config({"payment_requested": OLD_FLOW, "payment_requested_card_repayment": REPAYMENT_FLOW}),
    )


def _flow_ns(calls) -> str:
    flows = [payload["flow_ns"] for endpoint, payload in calls if endpoint.endswith("sendFlow")]
    assert len(flows) == 1, calls
    return flows[0]


def _fields(calls) -> dict[str, str]:
    return {
        payload["field_name"]: payload["field_value"]
        for endpoint, payload in calls
        if endpoint.endswith("setCustomFieldByName")
    }


def _ctx(*, repayment: dict | None = None, method: str = "card", with_deadline: bool = True) -> dict:
    payment = {"method": method, "intent_ref": "PAY-NEW"}
    if with_deadline:
        payment["expires_at"] = (timezone.now() + timedelta(hours=1)).isoformat()
    if repayment is not None:
        payment["repayment"] = repayment
    return {
        "order_ref": "NB-261107-A47",
        "customer_name": "Ana",
        "payment": payment,
    }


_REPAYMENT = {"after_intent_ref": "PAY-OLD", "pix_allowed": True}


def test_novo_pagamento_sai_pelo_modelo_novo_com_o_prazo(calls, variant_on):
    assert mc.send("+5543981234567", "payment_requested", _ctx(repayment=_REPAYMENT)) is True

    assert _flow_ns(calls) == REPAYMENT_FLOW
    fields = _fields(calls)
    assert fields["customer_name"] == "Ana"  # {{1}}
    assert fields["order_ref_short"] == "A47"  # {{2}}
    assert fields["payment_deadline"]  # {{3}}: "hoje às 18h30"
    assert " às " in fields["payment_deadline"]
    assert fields["order_ref"] == "NB-261107-A47"  # botão
    assert set(fields) == {"customer_name", "customer_name_greeting", "order_ref", "order_ref_short", "payment_deadline"}


def test_enquanto_o_modelo_esta_em_analise_sai_o_pagamento_solicitado(calls, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(mc.logger, "info", lambda msg, *args, **kw: seen.append(msg % args if args else msg))

    assert mc.send("+5543981234567", "payment_requested", _ctx(repayment=_REPAYMENT)) is True

    assert _flow_ns(calls) == OLD_FLOW
    assert "payment_deadline" not in _fields(calls)
    pending = [msg for msg in seen if "card_repayment_flow_pending" in msg]
    assert len(pending) == 1 and "pagamento_cartao_nao_passou" in pending[0]


@pytest.mark.parametrize(
    "ctx",
    [
        _ctx(),  # pagamento comum, sem cobrança recusada
        _ctx(repayment={**_REPAYMENT, "pix_allowed": False}),  # o modelo oferece Pix: sem Pix, não
        _ctx(repayment=_REPAYMENT, method="pix"),  # já trocou para Pix
        _ctx(repayment=_REPAYMENT, with_deadline=False),  # a Meta não aceita variável vazia
    ],
)
def test_fora_do_novo_pagamento_continua_o_pagamento_solicitado(calls, variant_on, ctx):
    assert mc.send("+5543981234567", "payment_requested", ctx) is True

    assert _flow_ns(calls) == OLD_FLOW


def test_flow_no_admin_tambem_liga_a_variante(calls):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="payment_requested_card_repayment", subject="x", body="y", whatsapp_flow_ns=REPAYMENT_FLOW
    )

    assert mc.send("+5543981234567", "payment_requested", _ctx(repayment=_REPAYMENT)) is True

    assert _flow_ns(calls) == REPAYMENT_FLOW
