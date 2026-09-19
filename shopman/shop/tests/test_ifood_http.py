"""Camada HTTP do iFood: retry de recusa de edge, renovação em 401 e forense.

O caso que originou o módulo está medido em 19/09/2026: o polling publicado
alternava 204 e 403 com um único token. Estes testes travam o comportamento que
faltava — repetir a recusa de edge e preservar o ``Reference #`` do Akamai.
"""

from __future__ import annotations

import logging
from unittest import mock

from django.test import override_settings

from shopman.shop.services import ifood_http

_CFG = {
    "client_id": "cid-123",
    "client_secret": "secret-xyz",
    "api_base": "https://merchant-api.ifood.com.br",
    "timeout": 5,
    "retry_backoff": 0,  # sem espera real no teste
}

# Página real do edge, com as entidades HTML que o Akamai devolve.
EDGE_BODY = (
    "<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \n"
    "You don't have permission to access &#34;http&#58;&#47;&#47;merchant&#45;api&#46;ifood"
    "&#46;com&#46;br&#47;order&#47;v1&#46;0&#47;events&#58;polling&#34; on this server.<P>\n"
    "Reference&#32;&#35;18&#46;1f9ab259&#46;1758275496&#46;3d4e5f6a<P>\n</BODY>\n</HTML>\n"
)


class _Resp:
    def __init__(self, status: int, *, text: str = "", json_body=None, headers=None):
        self.status_code = status
        self.text = text
        self._json = json_body
        self.headers = headers or {}

    def json(self):
        return self._json


def _headers(extra=None):
    """Dublê de ``ifood_auth.headers_with_reason``: ``(headers, razão)``."""
    base = {"Authorization": "Bearer tok", "User-Agent": "django-shopman/ifood-integration"}
    if extra:
        base.update(extra)
    return base, ""


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_recusa_de_edge_e_repetida_e_a_segunda_tentativa_vale():
    """O 403 do Akamai é sorteado por tentativa: repetir resolve."""
    respostas = [_Resp(403, text=EDGE_BODY), _Resp(204)]
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
         mock.patch.object(ifood_http.requests, "get", side_effect=respostas) as chamada:
        resp = ifood_http.request("GET", "/order/v1.0/events:polling", label="poll")

    assert resp is not None and resp.status_code == 204
    assert chamada.call_count == 2


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_recusa_de_edge_persistente_desiste_e_preserva_a_referencia():
    """A prova que o suporte do iFood precisa não pode morrer truncada no log.

    O log é capturado por um handler próprio: o logger do projeto não propaga
    para a raiz, então o `caplog` do pytest não enxerga esta mensagem.
    """
    registros: list[str] = []

    class _Captura(logging.Handler):
        def emit(self, record):
            registros.append(record.getMessage())

    handler = _Captura()
    logger = logging.getLogger("shopman.shop.services.ifood_http")
    logger.addHandler(handler)
    try:
        with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
             mock.patch.object(ifood_http.requests, "get", return_value=_Resp(403, text=EDGE_BODY)):
            resp = ifood_http.request("GET", "/order/v1.0/events:polling", label="poll")
    finally:
        logger.removeHandler(handler)

    assert resp is None
    registrado = "\n".join(registros)
    assert "18.1f9ab259.1758275496.3d4e5f6a" in registrado, "a referência do Akamai sumiu do log"
    assert "recusa=edge" in registrado


def test_referencia_do_akamai_sai_do_corpo_com_entidades_html():
    """Sem desescapar o HTML a referência não casa — o ponto vem como &#46;."""
    assert ifood_http.edge_reference(EDGE_BODY) == "18.1f9ab259.1758275496.3d4e5f6a"
    assert ifood_http.edge_reference("<HTML>sem referência</HTML>") == ""


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_403_em_json_e_recusa_da_api_e_nao_se_repete():
    """Escopo/permissão não se resolve repetindo: devolve para quem chamou."""
    negado = _Resp(
        403,
        text='{"error":{"code":"403","message":"forbidden"}}',
        json_body={"error": {"code": "403"}},
        headers={"Content-Type": "application/json"},
    )
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
         mock.patch.object(ifood_http.requests, "get", return_value=negado) as chamada:
        resp = ifood_http.request("GET", "/order/v1.0/events:polling", label="poll")

    assert resp is not None and resp.status_code == 403
    assert chamada.call_count == 1, "recusa da API não é para repetir"


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_401_renova_o_token_uma_vez_e_repete():
    respostas = [_Resp(401, text="expired"), _Resp(200, json_body=[])]
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
         mock.patch.object(ifood_http.ifood_auth, "get_access_token") as renova, \
         mock.patch.object(ifood_http.requests, "get", side_effect=respostas):
        resp = ifood_http.request("GET", "/order/v1.0/events:polling", label="poll")

    assert resp is not None and resp.status_code == 200
    renova.assert_called_once_with(force=True)


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_escrita_nao_repete_5xx_mas_repete_recusa_de_edge():
    """5xx é ambíguo para escrita (a origem pode ter processado); edge não é."""
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
         mock.patch.object(ifood_http.requests, "post", return_value=_Resp(502, text="bad gateway")) as chamada:
        ifood_http.request("POST", "/order/v1.0/events/acknowledgment", label="acknowledge")
    assert chamada.call_count == 1, "escrita não idempotente não repete 5xx"

    respostas = [_Resp(403, text=EDGE_BODY), _Resp(202)]
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
         mock.patch.object(ifood_http.requests, "post", side_effect=respostas) as chamada:
        resp = ifood_http.request("POST", "/order/v1.0/events/acknowledgment", label="acknowledge")
    assert resp is not None and resp.status_code == 202
    assert chamada.call_count == 2, "o edge recusa antes da origem: repetir é seguro"


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_leitura_idempotente_repete_5xx():
    respostas = [_Resp(503, text="unavailable"), _Resp(200, json_body={})]
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason", _headers), \
         mock.patch.object(ifood_http.requests, "get", side_effect=respostas) as chamada:
        resp = ifood_http.request("GET", "/order/v1.0/orders/x", label="fetch_order", idempotent=True)
    assert resp is not None and resp.status_code == 200
    assert chamada.call_count == 2


@override_settings(SHOPMAN_IFOOD=dict(_CFG, client_id="", client_secret=""))
def test_sem_credencial_nao_envia_nada():
    with mock.patch.object(ifood_http.ifood_auth, "headers_with_reason",
                           lambda extra=None: (None, ifood_http.ifood_auth.NOT_CONFIGURED)), \
         mock.patch.object(ifood_http.requests, "get") as chamada:
        assert ifood_http.request("GET", "/order/v1.0/events:polling", label="poll") is None
    chamada.assert_not_called()
