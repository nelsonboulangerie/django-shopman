"""A confirmação da ENCOMENDA diz a data também no WhatsApp fora da janela (20/10/2026).

O texto livre já dizia "confirmado para retirada amanhã" (#1911), mas fora da janela
de 24h sai o modelo aprovado ``pedido_confirmado``, de texto fixo. A encomenda passa a
sair pela variante ``order_accepted_preorder`` (modelo ``pedido_encomenda_confirmada``:
"Sua encomenda {{1}} está confirmada para {{2}}. O total é {{3}}. …"), com a promessa
no campo ``status_note``. Enquanto o modelo está em análise na Meta não há flow, e a
encomenda segue pelo ``pedido_confirmado``.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from shopman.shop.adapters import notification_manychat as mc
from shopman.shop.services.notification import _commitment_note, _commitment_suffix, _status_note

pytestmark = pytest.mark.django_db

OLD_FLOW = "content20260101120000_confirmado"
PREORDER_FLOW = "content20261020120000_encomenda"


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
    monkeypatch.setattr(mc, "_get_config", lambda: _config({"order_accepted": OLD_FLOW}))
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: "sub-1")
    return seen


@pytest.fixture
def variant_on(monkeypatch):
    monkeypatch.setattr(
        mc,
        "_get_config",
        lambda: _config({"order_accepted": OLD_FLOW, "order_accepted_preorder": PREORDER_FLOW}),
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


def _order(**data):
    return SimpleNamespace(ref="NB-261020-A47", data=data, status="confirmed", channel_ref="web")


def _amanha():
    return timezone.localdate() + timedelta(days=1)


def _ctx(order) -> dict:
    return {
        "order_ref": order.ref,
        "order_total_display": "R$ 38,00",
        "status_note": _status_note(order, "order_accepted", None),
    }


def test_encomenda_fora_da_janela_sai_pelo_modelo_novo_com_as_quatro_variaveis(calls, variant_on):
    order = _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="pickup")

    assert mc.send("+5543981234567", "order_accepted", _ctx(order)) is True

    assert _flow_ns(calls) == PREORDER_FLOW
    fields = _fields(calls)
    assert fields["order_ref_short"] == "A47"  # {{1}}
    assert fields["status_note"] == "retirada amanhã"  # {{2}}
    assert fields["total"] == "R$ 38,00"  # {{3}}
    assert fields["order_total_display"] == "R$ 38,00"
    assert fields["order_ref"] == "NB-261020-A47"  # botão
    # Contrato fechado: só o que o modelo usa vira campo.
    assert set(fields) == {"order_ref", "order_ref_short", "status_note", "total", "order_total_display"}


def test_pedido_do_dia_continua_no_pedido_confirmado(calls, variant_on):
    order = _order(delivery_date=timezone.localdate().isoformat(), fulfillment_type="pickup")

    assert mc.send("+5543981234567", "order_accepted", _ctx(order)) is True

    assert _flow_ns(calls) == OLD_FLOW
    assert "status_note" not in _fields(calls)


def test_enquanto_o_modelo_esta_em_analise_a_encomenda_sai_pelo_pedido_confirmado(calls, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(mc.logger, "info", lambda msg, *args, **kw: seen.append(msg % args if args else msg))
    order = _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="delivery")

    assert mc.send("+5543981234567", "order_accepted", _ctx(order)) is True

    assert _flow_ns(calls) == OLD_FLOW
    assert "status_note" not in _fields(calls)
    pending = [msg for msg in seen if "preorder_accepted_flow_pending" in msg]
    assert len(pending) == 1 and "pedido_encomenda_confirmada" in pending[0]


def test_flow_no_admin_tambem_liga_a_variante(calls):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_accepted_preorder", subject="x", body="y", whatsapp_flow_ns=PREORDER_FLOW
    )
    order = _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="pickup")

    assert mc.send("+5543981234567", "order_accepted", _ctx(order)) is True

    assert _flow_ns(calls) == PREORDER_FLOW


def test_frase_sem_ponto_final_e_sem_travessao_e_da_mesma_fonte_do_texto_livre():
    hoje = timezone.localdate()
    sabado = hoje + timedelta(days=(5 - hoje.weekday()) % 7 or 7)
    if sabado == hoje + timedelta(days=1):
        sabado += timedelta(days=7)
    for order in (
        _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="pickup"),
        _order(delivery_date=sabado.isoformat(), is_preorder=True, fulfillment_type="delivery"),
    ):
        note = _status_note(order, "order_accepted", None)
        assert note
        assert not note.endswith(".")
        assert "—" not in note and "–" not in note
        assert note == _commitment_note(order)
        assert _commitment_suffix(order) == f" para {note}"
    assert _commitment_note(
        _order(delivery_date=sabado.isoformat(), is_preorder=True, fulfillment_type="delivery")
    ) == f"entrega no sábado, {sabado:%d/%m}"


def test_pedido_do_dia_nao_tem_frase():
    order = _order(delivery_date=timezone.localdate().isoformat(), fulfillment_type="pickup")

    assert _status_note(order, "order_accepted", None) == ""
