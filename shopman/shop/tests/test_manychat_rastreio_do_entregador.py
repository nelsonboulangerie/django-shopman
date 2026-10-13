"""O link do entregador (TaOn/Machine) também no WhatsApp (decisão do dono, 13/10/2026).

O ``order_dispatched`` com corrida e link de rastreio sai pelo flow da variante
``order_dispatched_courier`` (template ``pedido_saiu_entrega_rastreio``), cujo
segundo botão é ``<base fixa>{{1}}``. O adapter grava o resto do link no campo
``courier_tracking_path``. Qualquer coisa que impeça o botão de sair inteiro cai no
flow antigo, nunca num botão quebrado ou vazio.
"""

from __future__ import annotations

import logging

import pytest

from shopman.shop.adapters import notification_manychat as mc

pytestmark = pytest.mark.django_db

BASE = "https://rastreio.taon.example/r/"
OLD_FLOW = "content20260101120000_dispatched"
COURIER_FLOW = "content20260101120000_courier"


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, dict]] = []

    def _fake(endpoint, payload, config):
        seen.append((endpoint, payload))
        return {"success": True}

    monkeypatch.setattr(mc, "_api_call", _fake)
    monkeypatch.setattr(
        mc, "_get_config", lambda: {"api_token": "tok", "flow_map": {"order_dispatched": OLD_FLOW}}
    )
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: "sub-1")
    return seen


@pytest.fixture
def logs(monkeypatch):
    """O que o adapter registrou, por nível (o logger do projeto não propaga à raiz)."""
    seen: list[tuple[int, str]] = []
    for level, name in ((logging.WARNING, "warning"), (logging.ERROR, "error")):
        monkeypatch.setattr(
            mc.logger,
            name,
            lambda msg, *args, _level=level, **kw: seen.append((_level, msg % args if args else msg)),
        )
    return seen


@pytest.fixture
def base(settings):
    settings.SHOPMAN_MACHINE = {**getattr(settings, "SHOPMAN_MACHINE", {}), "tracking_link_base": BASE}
    return BASE


@pytest.fixture
def courier_flow(db):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_dispatched_courier", subject="x", body="y", whatsapp_flow_ns=COURIER_FLOW
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


def _ctx(tracking_url: str = "") -> dict:
    return {
        "order_ref": "NB-261013-A47",
        "courier_tracking_url": tracking_url,
        "courier_tracking_suffix": f"\nAcompanhe o entregador: {tracking_url}" if tracking_url else "",
    }


def test_variant_on_and_base_ok_sends_the_courier_flow_with_the_path(calls, base, courier_flow):
    assert mc.send("+5543981234567", "order_dispatched", _ctx(f"{BASE}abc123XYZ")) is True

    assert _flow_ns(calls) == COURIER_FLOW
    fields = _fields(calls)
    assert fields["courier_tracking_path"] == "abc123XYZ"
    assert fields["order_ref"] == "NB-261013-A47"
    assert fields["order_ref_short"] == "A47"
    # O contrato da variante é fechado: o link inteiro não vira campo.
    assert "courier_tracking_url" not in fields


def test_flow_map_also_turns_the_variant_on(calls, base, monkeypatch):
    monkeypatch.setattr(
        mc,
        "_get_config",
        lambda: {
            "api_token": "tok",
            "flow_map": {"order_dispatched": OLD_FLOW, "order_dispatched_courier": COURIER_FLOW},
        },
    )
    assert mc.send("+5543981234567", "order_dispatched", _ctx(f"{BASE}abc")) is True
    assert _flow_ns(calls) == COURIER_FLOW


def test_variant_off_falls_back_to_the_old_flow_with_a_warning(calls, base, logs):
    assert mc.send("+5543981234567", "order_dispatched", _ctx(f"{BASE}abc")) is True

    assert _flow_ns(calls) == OLD_FLOW
    assert "courier_tracking_path" not in _fields(calls)
    warnings = [(lvl, msg) for lvl, msg in logs if "courier_tracking_flow_missing" in msg]
    assert len(warnings) == 1 and warnings[0][0] == logging.WARNING
    assert "pedido_saiu_entrega_rastreio" in warnings[0][1]
    assert not [msg for lvl, msg in logs if lvl == logging.ERROR]


@pytest.mark.parametrize(
    ("configured_base", "link", "reason"),
    [
        ("", f"{BASE}abc", "base_missing"),
        (BASE, "https://outro.example/r/abc", "link_outside_base"),
        (BASE, BASE, "path_empty"),
        (BASE, f"{BASE}abc?t=segredo", "path_unsafe"),
    ],
)
def test_unusable_link_falls_back_to_the_old_flow_with_an_error(
    calls, settings, courier_flow, logs, configured_base, link, reason
):
    settings.SHOPMAN_MACHINE = {
        **getattr(settings, "SHOPMAN_MACHINE", {}),
        "tracking_link_base": configured_base,
    }
    assert mc.send("+5543981234567", "order_dispatched", _ctx(link)) is True

    assert _flow_ns(calls) == OLD_FLOW
    assert "courier_tracking_path" not in _fields(calls)
    errors = [msg for lvl, msg in logs if lvl == logging.ERROR]
    assert len(errors) == 1
    assert f"reason={reason}" in errors[0]
    # A URL da corrida não vai para o log.
    assert link not in errors[0]


def test_without_a_ride_the_old_flow_goes_quietly(calls, base, courier_flow, logs):
    assert mc.send("+5543981234567", "order_dispatched", _ctx("")) is True

    assert _flow_ns(calls) == OLD_FLOW
    assert "courier_tracking_path" not in _fields(calls)
    assert logs == []


def test_other_events_never_take_the_variant(calls, base, courier_flow, monkeypatch):
    monkeypatch.setattr(
        mc,
        "_get_config",
        lambda: {"api_token": "tok", "flow_map": {"order_ready_delivery": OLD_FLOW}},
    )
    assert mc.send("+5543981234567", "order_ready_delivery", _ctx(f"{BASE}abc")) is True
    assert _flow_ns(calls) == OLD_FLOW
    assert "courier_tracking_path" not in _fields(calls)
