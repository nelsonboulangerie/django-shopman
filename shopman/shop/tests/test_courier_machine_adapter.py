"""Adapter Machine (courier): borda HTTP, conversão de dinheiro e trava de DEBUG."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
from django.test import override_settings

from shopman.shop.adapters import courier_machine, courier_mock
from shopman.shop.adapters.courier_machine import CourierError

MACHINE = {
    "base_url": "https://api.machine.test/api/integracao",
    "details_base": "https://api.machine.test/api/integracao/v1",
    "username": "user-1",
    "password": "pass-1",
    "api_key": "key-1",
    "forma_pagamento": "F",
    "retorno": False,
    "timeout": 5,
    "cancel_reason_id": 1,
}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _ok(response):
    return _FakeResponse(200, {"success": True, "response": response})


# ── conversão de dinheiro ───────────────────────────────────────────


def test_to_q_converts_reais_float_to_centavos():
    assert courier_machine._to_q(12.5) == 1250
    assert courier_machine._to_q(994.25) == 99425
    assert courier_machine._to_q("7.9") == 790
    assert courier_machine._to_q(None) == 0
    assert courier_machine._to_q("abc") == 0


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_estimate_returns_centavos_and_metrics():
    payload = {"estimativa_valor": 12.55, "estimativa_minutos": 18, "estimativa_km": 4.05}
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok(payload),
    ) as mock_request:
        est = courier_machine.estimate(
            pickup={"lat": "-23.30", "lng": "-51.16"},
            dropoff={"lat": "-23.31", "lng": "-51.17"},
        )
    assert est.value_q == 1255
    assert est.minutes == 18.0
    assert est.km == 4.05
    kwargs = mock_request.call_args.kwargs
    assert kwargs["auth"] == ("user-1", "pass-1")
    assert kwargs["headers"] == {"api-key": "key-1"}
    assert kwargs["params"]["lat_partida"] == "-23.30"
    assert kwargs["params"]["lng_desejado"] == "-51.17"


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_estimate_sends_the_address_the_delivery_api_requires():
    """Na API de entregas v1 o endereço é obrigatório nos dois pontos; a coordenada só refina."""
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"estimativa_valor": 9.9}),
    ) as mock_request:
        courier_machine.estimate(
            pickup={"lat": "-23.34", "lng": "-51.15", "street": "Av. Madre Leônia Milito 446",
                    "neighborhood": "Bela Suíça", "city": "Londrina", "state": "PR"},
            dropoff={"lat": "-23.31", "lng": "-51.16", "street": "Rua das Flores 123",
                     "neighborhood": "Centro", "city": "Londrina", "state": "PR"},
        )
    args, kwargs = mock_request.call_args
    assert args == ("GET", "https://api.machine.test/api/integracao/estimarSolicitacao")
    assert kwargs["params"] == {
        "lat_partida": "-23.34",
        "lng_partida": "-51.15",
        "endereco_partida": "Av. Madre Leônia Milito 446",
        "bairro_partida": "Bela Suíça",
        "cidade_partida": "Londrina",
        "estado_partida": "PR",
        "lat_desejado": "-23.31",
        "lng_desejado": "-51.16",
        "endereco_desejado": "Rua das Flores 123",
        "bairro_desejado": "Centro",
        "cidade_desejado": "Londrina",
        "estado_desejado": "PR",
    }


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_estimate_without_coordinates_returns_none_without_network():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        side_effect=AssertionError("must not call network without coords"),
    ):
        assert courier_machine.estimate(pickup={"lat": None, "lng": None}, dropoff={}) is None


# ── dispatch ────────────────────────────────────────────────────────


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_dispatch_posts_payload_and_returns_id_mch():
    body = {"forma_pagamento": "F", "partida": {}, "paradas": [{"id_externo": "ORD-1"}]}
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"id_mch": 678}),
    ) as mock_request:
        result = courier_machine.dispatch(body)
    assert result.courier_ref == "678"
    assert result.inert is False
    args, kwargs = mock_request.call_args
    assert args == ("POST", "https://api.machine.test/api/integracao/abrirSolicitacao")
    assert kwargs["json"] is body


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_dispatch_without_id_mch_is_terminal_error():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({}),
    ):
        with pytest.raises(CourierError) as exc:
            courier_machine.dispatch({})
    assert exc.value.transient is False


# ── erros: transient vs terminal ────────────────────────────────────


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_network_error_is_transient():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        side_effect=requests.ConnectionError("boom"),
    ):
        with pytest.raises(CourierError) as exc:
            courier_machine.get_status("123")
    assert exc.value.transient is True


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_5xx_is_transient():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_FakeResponse(502, text="bad gateway"),
    ):
        with pytest.raises(CourierError) as exc:
            courier_machine.get_status("123")
    assert exc.value.transient is True


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_api_refusal_is_terminal_with_error_detail():
    refusal = {"success": False, "errors": [{"code": 25, "message": "Solicitação não encontrada."}]}
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_FakeResponse(400, refusal),
    ):
        with pytest.raises(CourierError) as exc:
            courier_machine.cancel("999")
    assert exc.value.transient is False
    assert "Solicitação não encontrada" in str(exc.value)


@override_settings(DEBUG=False, SHOPMAN_MACHINE={**MACHINE, "username": ""})
def test_missing_credentials_is_terminal():
    with pytest.raises(CourierError) as exc:
        courier_machine.get_status("123")
    assert exc.value.transient is False
    assert courier_machine.is_configured() is False


# ── status e detalhes ───────────────────────────────────────────────


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_get_status_returns_raw_letter():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"status": "E"}),
    ):
        assert courier_machine.get_status("511") == "E"


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_get_details_uses_v1_base_and_unwrapped_body():
    details = {"request_id": 1, "driver": {"name": "João"}}
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_FakeResponse(200, details),
    ) as mock_request:
        assert courier_machine.get_details("42")["driver"]["name"] == "João"
    args = mock_request.call_args.args
    assert args == ("GET", "https://api.machine.test/api/integracao/v1/request/42")


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_get_position_none_when_driver_not_active():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"lat_condutor": None, "lng_condutor": None}),
    ):
        assert courier_machine.get_position("511") is None


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_tracking_links_returns_list():
    links = [{"parada_id": "1", "link_rastreio": "https://r/x", "codigo_confirmacao": 3622}]
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok(links),
    ):
        assert courier_machine.tracking_links("42") == links


@override_settings(DEBUG=False, SHOPMAN_MACHINE=MACHINE)
def test_tracking_links_understands_the_documented_single_link():
    """OpenAPI v1 de entregas: ``response`` é ``{"link": ...}``, não a lista por parada."""
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"link": "https://rastreio.taximachine.com.br/rastreio/XXXXX"}),
    ):
        assert courier_machine.tracking_links("42") == [
            {
                "parada_id": "",
                "link_rastreio": "https://rastreio.taximachine.com.br/rastreio/XXXXX",
                "codigo_confirmacao": None,
            }
        ]


def test_register_webhook_rejects_unknown_kind():
    with pytest.raises(ValueError):
        courier_machine.register_webhook("https://x/", kind="tudo")


# ── trava de DEBUG (inert) ──────────────────────────────────────────


@override_settings(DEBUG=True, SHOPMAN_MACHINE=MACHINE)
def test_inert_in_debug_makes_no_network_call():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        side_effect=AssertionError("external network call must not happen in DEBUG"),
    ):
        result = courier_machine.dispatch({"paradas": [{"id_externo": "ORD-1"}]})
        assert result.inert is True
        assert result.courier_ref == ""
        assert courier_machine.get_status("1") == ""
        assert courier_machine.estimate(pickup={"lat": 1, "lng": 1}, dropoff={"lat": 2, "lng": 2}) is None
        assert courier_machine.get_position("1") is None
        assert courier_machine.cancel("1") is True


@override_settings(DEBUG=True, SHOPMAN_MACHINE=MACHINE, SHOPMAN_MACHINE_ALLOW_IN_DEBUG=True)
def test_opt_in_restores_real_calls_in_debug():
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"status": "A"}),
    ) as mock_request:
        assert courier_machine.get_status("511") == "A"
    assert mock_request.called


# ── mock adapter ────────────────────────────────────────────────────


def test_mock_adapter_dispatch_and_status_cycle():
    courier_mock.reset()
    result = courier_mock.dispatch({"paradas": [{"id_externo": "ORD-9"}]})
    assert result.courier_ref == "MOCK-ORD-9"
    assert courier_mock.get_status("MOCK-ORD-9") == "D"
    courier_mock.set_status("MOCK-ORD-9", "E")
    assert courier_mock.get_status("MOCK-ORD-9") == "E"
    assert courier_mock.get_position("MOCK-ORD-9") is not None
    courier_mock.set_status("MOCK-ORD-9", "F")
    with pytest.raises(CourierError):
        courier_mock.cancel("MOCK-ORD-9")
    courier_mock.reset()
    with pytest.raises(CourierError):
        courier_mock.get_status("MOCK-ORD-9")


# ── endereços: o que o adapter monta é o que a doc da Machine publica ─────

#: Produção, conforme o OpenAPI v1 (servers) de docs.machine.global.
PRODUCTION_BASE = "https://api.taximachine.com.br/api/integracao"
CREDENTIALS_ONLY = {"username": "u", "password": "p", "api_key": "k"}


def _called_url(call, *args, **kwargs):
    with patch(
        "shopman.shop.adapters.courier_machine.requests.request",
        return_value=_ok({"status": "D", "id_mch": 1, "lat_condutor": None, "lng_condutor": None}),
    ) as mock_request:
        call(*args, **kwargs)
    method, url = mock_request.call_args.args
    return method, url, mock_request.call_args.kwargs


@override_settings(DEBUG=False, SHOPMAN_MACHINE=CREDENTIALS_ONLY)
def test_adapter_fallback_builds_the_documented_details_url():
    """Sem base configurada, o adapter cai no endereço de produção documentado."""
    assert _called_url(courier_machine.get_details, "123")[:2] == (
        "GET",
        "https://api.taximachine.com.br/api/integracao/v1/request/123",
    )


@override_settings(DEBUG=False)
def test_settings_details_url_is_the_documented_one():
    """O SHOPMAN_MACHINE carregado (settings_test espelha o padrão do settings.py)."""
    from django.conf import settings

    with override_settings(SHOPMAN_MACHINE={**settings.SHOPMAN_MACHINE, **CREDENTIALS_ONLY}):
        assert _called_url(courier_machine.get_details, "123")[:2] == (
            "GET",
            "https://api.taximachine.com.br/api/integracao/v1/request/123",
        )


def test_settings_py_defaults_are_the_documented_addresses():
    """Trava o padrão escrito no config/settings.py (o que vale quando a env não existe).

    O settings_test sobrescreve as duas bases, então só a leitura do arquivo prova o
    padrão de produção. Medido em 01/10/2026: o padrão dos detalhes era
    ``.../integracao/v1``, sem o ``/api``.
    """
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "config" / "settings.py").read_text(encoding="utf-8")
    defaults = dict(re.findall(r'os\.environ\.get\("(MACHINE_(?:API|DETAILS)_BASE)", "([^"]+)"\)', source))
    assert defaults == {
        "MACHINE_API_BASE": PRODUCTION_BASE,
        "MACHINE_DETAILS_BASE": f"{PRODUCTION_BASE}/v1",
    }


@override_settings(DEBUG=False, SHOPMAN_MACHINE={**CREDENTIALS_ONLY, "base_url": PRODUCTION_BASE})
@pytest.mark.parametrize(
    ("call", "args", "kwargs", "method", "url", "query", "body"),
    [
        (courier_machine.estimate, (), {"pickup": {"lat": 1, "lng": 2}, "dropoff": {"lat": 3, "lng": 4}},
         "GET", "/estimarSolicitacao", {"lat_partida": 1, "lng_partida": 2, "lat_desejado": 3, "lng_desejado": 4},
         None),
        (courier_machine.dispatch, ({"paradas": []},), {}, "POST", "/abrirSolicitacao", None, {"paradas": []}),
        (courier_machine.get_status, ("77",), {}, "GET", "/solicitacaoStatus", {"id_mch": "77"}, None),
        (courier_machine.get_position, ("77",), {}, "GET", "/posicaoCondutor", {"id_mch": "77"}, None),
        (courier_machine.cancel, ("77",), {"reason_id": 2}, "POST", "/cancelar", None,
         {"id_mch": "77", "motivo_id": 2}),
        (courier_machine.tracking_links, ("77",), {}, "GET", "/obterLinkRastreio/77", None, None),
        (courier_machine.register_webhook, ("https://x.test/h",), {"kind": "status"}, "POST", "/cadastrarWebhook",
         None, {"tipo": "status", "url": "https://x.test/h", "responsabilidade": "solicitante"}),
    ],
)
def test_each_call_hits_the_documented_v1_path(call, args, kwargs, method, url, query, body):
    """Método, caminho e parâmetros principais de cada chamada, um por um, contra o OpenAPI v1."""
    called_method, called_url, sent = _called_url(call, *args, **kwargs)
    assert (called_method, called_url) == (method, f"{PRODUCTION_BASE}{url}")
    assert sent["params"] == query
    assert sent["json"] == body
    assert sent["headers"] == {"api-key": "k"}
    assert sent["auth"] == ("u", "p")
