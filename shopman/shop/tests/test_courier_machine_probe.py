"""Sonda de homologação da TaOn: só lê por padrão, não vaza dado pessoal, e escrever pede confirmação."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

MACHINE = {
    "username": "u", "password": "senha-secreta", "api_key": "chave-secreta",
    "base_url": "https://api-vendas.taximachine.com.br/api/integracao",
    "details_base": "https://api-vendas.taximachine.com.br/api/integracao/v1",
}
PICKUP = "-23.3100,-51.1600;Rua da Loja 10;Centro;Londrina;PR"
STOP_A = "-23.3150,-51.1650;Rua A 100;Centro;Londrina;PR"
STOP_B = "-23.3200,-51.1700;Rua B 200;Centro;Londrina;PR"

DETAILS = {
    "request_id": 900, "short_code": "E", "full_code": "IN_PROGRESS",
    "driver": {"id": 5539, "name": "Felipe Nunes", "phone": "(43) 99898-9898", "cpf": "111.222.333-44",
               "vehicle_plate": "MOJ-8232", "vehicle_model": "gol"},
    "progress": {"accepted_at": "2026-11-16T14:00:00+00:00", "accept_lat": -23.31, "accept_lng": -51.16},
    "stops": [
        {"id": 46868, "order": 1, "status": "FINISHED", "external_id": "A47",
         "address": "Rua A 100", "customer_name": "Maria Cliente", "comprovante": None},
        {"id": 46869, "order": 2, "status": "PENDING", "external_id": "C03",
         "address": "Rua B 200", "customer_name": "João Cliente", "comprovante": None},
    ],
}
LINKS = [
    {"parada_id": "46868", "link_rastreio": "https://rastreio.exemplo.com/pedido/rastreio/fd15b167",
     "codigo_confirmacao": "3622"},
    {"parada_id": "46869", "link_rastreio": "https://rastreio.exemplo.com/pedido/rastreio/2372c587",
     "codigo_confirmacao": "2335"},
]
PERSONAL = ("Felipe Nunes", "99898-9898", "111.222.333-44", "MOJ-8232", "Maria Cliente", "João Cliente",
            "Rua A 100", "fd15b167", "2372c587", "3622", "2335", "senha-secreta", "chave-secreta", "-23.31")


class _Response:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = "" if payload is None else str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("sem JSON")
        return self._payload


def _api(method, url, **kwargs):
    """Uma TaOn de mentira: responde por caminho, como a doc descreve."""
    params = kwargs.get("params") or {}
    if "/v2/" in url:
        if url.endswith("/webhooks"):
            return _Response(200, {"success": True, "data": []})
        if url.endswith("/status"):
            return _Response(400, {"success": False, "errors": [
                {"code": 97, "message": "Solicitação foi agrupada", "solicitacao_agrupadora_id": 987654}]})
        if url.endswith("/detalhes"):
            return _Response(200, {"success": True, "data": DETAILS})
        if url.endswith("/links-rastreio"):
            return _Response(200, {"success": True, "data": LINKS})
        if url.endswith("/impulsionar"):
            return _Response(200, {"success": True, "data": {"id_mch": 900, "valor": 3.0, "origem": "empresa"}})
        return _Response(404, {"success": False, "errors": [{"code": 25, "message": "Solicitação não encontrada."}]})
    if url.endswith("/estimarSolicitacao"):
        stops = params.get("latlng_paradas", "")
        if stops and "," not in stops:
            return _Response(400, {"success": False, "errors": [{"code": 24, "message": "Formato da entrada incorreto."}]})
        return _Response(200, {"success": True, "response": {
            "estimativa_valor": 12.0 if stops else 8.0, "estimativa_minutos": 14 if stops else 9,
            "estimativa_km": 5.7 if stops else 3.4}}, headers={"X-RateLimit-Remaining": "997"})
    if "/request/" in url:
        return _Response(200, DETAILS)
    if "/obterLinkRastreio/" in url:
        return _Response(200, {"success": True, "response": LINKS})
    if url.endswith("/solicitacao") and "data_hora_solicitacao_min" in params:
        return _Response(200, {"success": True, "response": [
            {"id": "900", "status_solicitacao": "D", "data_hora_solicitacao": "2026-11-16 14:00:00",
             "nome_passageiro": "Maria Cliente",
             "paradas": [{"numero_pedido": "A47", "nome_cliente_parada": "Maria Cliente"}, {"numero_pedido": "C03"}]}]})
    if url.endswith("/solicitacao"):
        return _Response(200, {"success": True, "response": [{
            "id": "900", "status_solicitacao": "E", "nome_condutor": "Felipe Nunes", "taxas_cancelamento": None,
            "paradas": [{"id": 46868, "numero_pedido": "A47", "link_rastreio_pedido": LINKS[0]["link_rastreio"]},
                        {"id": 46869, "numero_pedido": "", "link_rastreio_pedido": None}]}]})
    if url.endswith("/solicitacaoStatus"):
        return _Response(200, {"success": True, "response": {"status": "E"}})
    if url.endswith("/listarWebhook"):
        return _Response(200, {"success": True, "response": {"quantidade_webhooks": 1, "webhooks": [
            {"id": 7, "tipo": "status", "url": "https://api.exemplo.com.br/api/webhooks/machine/?token=segredo-123"}]}})
    if url.endswith("/categoria"):
        return _Response(200, {"success": True, "response": [{"id": "1", "nome": "Moto"}]})
    return _Response(200, {"success": True, "response": {}})


def _run(*args):
    out = StringIO()
    with patch("requests.request", side_effect=_api) as http:
        call_command("courier_machine_probe", *args, stdout=out)
    return out.getvalue(), http


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_default_run_only_reads_and_says_whether_the_key_opens_v2():
    output, http = _run("--pickup", PICKUP, "--ride", "900")
    assert {call.args[0] for call in http.call_args_list} == {"GET"}
    assert "HOMOLOGAÇÃO" in output
    assert "a api-key VALE na v2" in output
    assert "https://api-vendas.taximachine.com.br/api/v2/integracao" in output


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_report_answers_the_probes_without_personal_data():
    output, _ = _run("--pickup", PICKUP, "--ride", "900")
    for secret in (*PERSONAL, "segredo-123"):
        assert secret not in output, secret
    # O que a rodada precisa ler: formato dos links, paradas e o agrupamento.
    assert "links: LISTA com 2 itens (um por parada)" in output
    assert "parada_id=46868 · parte fixa https://rastreio.exemplo.com/pedido/rastreio/<8 caracteres> · código presente" in output
    assert "stops: 2 · status vistos: ['FINISHED', 'PENDING']" in output
    assert "listagem: 2 paradas · numero_pedido em 1 · link_rastreio_pedido em 1" in output
    assert "solicitacao_agrupadora_id: 987654" in output
    assert "external_id: 'A47'" in output


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_quote_probe_tells_which_separator_counts_the_stops():
    output, http = _run("--pickup", PICKUP, "--stop", STOP_A, "--stop", STOP_B)
    assert {call.args[0] for call in http.call_args_list} == {"GET"}
    assert "veredito lat,lng|lat,lng: paradas contadas (5.7 km contra 3.4 km da direta)" in output
    assert "X-RateLimit-Remaining=997" in output
    sent = [call.kwargs["params"].get("latlng_paradas") for call in http.call_args_list
            if call.args[1].endswith("/estimarSolicitacao")]
    assert "-23.3150,-51.1650" in sent and "-23.3150;-51.1650" in sent
    assert "veredito lat;lng|lat;lng" not in output  # recusada pela TaOn: sem veredito, só a recusa


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_window_lists_recent_rides_by_our_order_refs():
    """A busca que acha a corrida aberta sem resposta: por data, casando o pedido em cada parada."""
    output, http = _run("--pickup", PICKUP, "--window", "30")
    assert {call.args[0] for call in http.call_args_list} == {"GET"}
    assert "1 corridas na janela" in output
    assert "id=900 · status=D · aberta 2026-11-16 14:00:00 · 2 paradas · numero_pedido: A47, C03" in output
    assert "Maria Cliente" not in output


@override_settings(SHOPMAN_MACHINE=MACHINE)
@pytest.mark.parametrize("args", [
    ("--ride", "900", "--boost", "3"),                                    # sem --write
    ("--ride", "900", "--boost", "3", "--write"),                          # sem --confirm
    ("--ride", "900", "--boost", "3", "--write", "--confirm", "901"),      # confirmação de outra corrida
    ("--ride", "900", "--ride", "901", "--cancel", "10", "--write", "--confirm", "900"),  # duas corridas
    ("--ride", "900", "--boost", "3", "--cancel", "10", "--write", "--confirm", "900"),   # duas escritas
])
def test_write_probe_refuses_before_any_call(args):
    with patch("requests.request", side_effect=_api) as http, pytest.raises(CommandError):
        call_command("courier_machine_probe", *args, stdout=StringIO())
    http.assert_not_called()


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_confirmed_write_sends_exactly_that_write(tmp_path):
    report = tmp_path / "laudo.txt"
    output, http = _run("--ride", "900", "--boost", "3", "--write", "--confirm", "900", "--out", str(report))
    posts = [call for call in http.call_args_list if call.args[0] != "GET"]
    assert [(call.args[0], call.args[1], call.kwargs["json"]) for call in posts] == [
        ("POST", "https://api-vendas.taximachine.com.br/api/v2/integracao/entregas/900/impulsionar", {"valor": 3.0}),
    ]
    assert "origem: 'empresa'" in output
    assert "ESCRITA na corrida 900" in report.read_text(encoding="utf-8")


@override_settings(SHOPMAN_MACHINE={**MACHINE, "api_key": ""})
def test_refuses_without_credentials():
    with patch("requests.request") as http, pytest.raises(CommandError):
        call_command("courier_machine_probe", stdout=StringIO())
    http.assert_not_called()
