from __future__ import annotations

import logging
from unittest import mock

import pytest
import requests
from django.test import override_settings

from shopman.shop.services import ifood_auth

_CFG = {
    "client_id": "cid-123",
    "client_secret": "secret-xyz",
    "api_base": "https://merchant-api.ifood.com.br",
    "timeout": 5,
    "token_retry_backoff": 0,  # sem espera real no teste
}

# Página real do edge do Akamai, com as entidades HTML que ele devolve. A mesma
# recusa que o polling leva atinge o endpoint de autenticação (medido 19/09/2026).
EDGE_BODY = (
    "<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \n"
    "You don't have permission to access &#34;http&#58;&#47;&#47;merchant&#45;api&#46;ifood"
    "&#46;com&#46;br&#47;authentication&#47;v1&#46;0&#47;oauth&#47;token&#34; on this server.<P>\n"
    "Reference&#32;&#35;18&#46;1f9ab259&#46;1758275496&#46;3d4e5f6a<P>\n</BODY>\n</HTML>\n"
)


class _Resp:
    def __init__(self, status: int, body: dict | None = None, *, text: str = "", headers=None):
        self.status_code = status
        self._body = body
        self.text = text or str(body)
        self.headers = headers if headers is not None else {"Content-Type": "application/json"}

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def _edge_denial():
    """A recusa do Akamai: HTML, não JSON — é assim que se sabe quem recusou."""
    return _Resp(403, text=EDGE_BODY, headers={"Content-Type": "text/html"})


@override_settings(SHOPMAN_IFOOD=dict(_CFG, client_id="", client_secret=""))
def test_inert_without_credentials():
    ifood_auth.reset_cache()
    assert ifood_auth.get_access_token() is None


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_fetches_and_caches_token():
    ifood_auth.reset_cache()
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=None):
        captured["url"] = url
        captured["allow_redirects"] = allow_redirects
        captured["data"] = data
        captured["ua"] = headers.get("User-Agent")
        captured["ctype"] = headers.get("Content-Type")
        return _Resp(200, {"accessToken": "tok-1", "expiresIn": 21599})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        t1 = ifood_auth.get_access_token()
        t2 = ifood_auth.get_access_token()  # cacheado → não chama de novo

    assert t1 == "tok-1"
    assert t2 == "tok-1"
    assert captured["url"].endswith("/authentication/v1.0/oauth/token")
    assert captured["data"] == {
        "grantType": "client_credentials",
        "clientId": "cid-123",
        "clientSecret": "secret-xyz",
    }
    assert captured["ua"] == ifood_auth.USER_AGENT
    assert captured["ctype"] == "application/x-www-form-urlencoded"
    assert captured["allow_redirects"] is False


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_force_refetches():
    ifood_auth.reset_cache()
    calls = {"n": 0}

    def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=None):
        calls["n"] += 1
        return _Resp(200, {"accessToken": f"tok-{calls['n']}", "expiresIn": 21599})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        ifood_auth.get_access_token()
        again = ifood_auth.get_access_token(force=True)

    assert calls["n"] == 2
    assert again == "tok-2"


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_returns_none_on_http_error():
    """Recusa da própria API do iFood (JSON): é a credencial, e retry não resolve."""
    ifood_auth.reset_cache()
    negado = _Resp(403, {"error": {"code": "Forbidden", "message": "No permissions granted"}})

    with mock.patch.object(ifood_auth.requests, "post", return_value=negado) as post:
        token, reason = ifood_auth.token_with_reason()

    assert token is None
    assert reason == ifood_auth.DENIED_API
    assert post.call_count == 1


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_authorized_headers_carry_bearer_and_ua():
    ifood_auth.reset_cache()

    def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=None):
        return _Resp(200, {"accessToken": "tok-h", "expiresIn": 21599})

    with mock.patch.object(ifood_auth.requests, "post", fake_post):
        headers = ifood_auth.authorized_headers({"X-Test": "1"})

    assert headers["Authorization"] == "Bearer tok-h"
    assert headers["User-Agent"] == ifood_auth.USER_AGENT
    assert headers["X-Test"] == "1"


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_error_logs_never_contain_response_body(caplog):
    ifood_auth.reset_cache()
    for status in (302, 307, 308):
        with mock.patch.object(ifood_auth.requests, 'post', return_value=_Resp(status, {'accessToken': 'DO-NOT-LOG', 'clientSecret': 'SECRET-NOT-LOGGED'})) as post:
            assert ifood_auth.get_access_token(force=True) is None
        assert post.call_args.kwargs['allow_redirects'] is False
    assert 'SECRET-NOT-LOGGED' not in caplog.text
    assert 'DO-NOT-LOG' not in caplog.text


# ---------------------------------------------------------------------------
# Defeito 1: a chamada de token também leva recusa de borda, e tem de atravessá-la.
# ---------------------------------------------------------------------------


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_recusa_de_edge_no_token_e_repetida_e_a_segunda_tentativa_vale():
    """O 403 do Akamai é sorteado por tentativa: repetir devolve o token."""
    ifood_auth.reset_cache()
    respostas = [_edge_denial(), _Resp(200, {"accessToken": "tok-ok", "expiresIn": 21599})]

    with mock.patch.object(ifood_auth.requests, "post", side_effect=respostas) as post:
        token, reason = ifood_auth.token_with_reason()

    assert token == "tok-ok"
    assert reason == ""
    assert post.call_count == 2


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_recusa_de_edge_no_token_esgota_as_tentativas_com_a_referencia_inteira():
    """Esgotadas as tentativas, o log entrega a ``referencia=`` que o suporte usa.

    O logger de `shopman` não propaga para a raiz, então o `caplog` do pytest
    não enxerga esta mensagem — a captura é por handler no próprio logger.
    """
    ifood_auth.reset_cache()
    registros: list[str] = []

    class _Captura(logging.Handler):
        def emit(self, record):
            registros.append(record.getMessage())

    handler = _Captura()
    logger = logging.getLogger("shopman.shop.services.ifood_auth")
    logger.addHandler(handler)
    try:
        with mock.patch.object(ifood_auth.requests, "post", return_value=_edge_denial()) as post:
            token, reason = ifood_auth.token_with_reason()
    finally:
        logger.removeHandler(handler)

    assert token is None
    assert reason == ifood_auth.DENIED_EDGE
    assert post.call_count == 3
    registrado = "\n".join(registros)
    assert "recusa=edge" in registrado
    assert "referencia=18.1f9ab259.1758275496.3d4e5f6a" in registrado
    # Corpo de recusa de autenticação nunca vai ao log: pode ecoar o que enviamos.
    assert "corpo=" not in registrado


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_transporte_do_token_retenta_porque_pedir_token_nao_tem_efeito():
    ifood_auth.reset_cache()
    respostas = [
        requests.ConnectionError("conexão caiu"),
        _Resp(200, {"accessToken": "tok-retry", "expiresIn": 21599}),
    ]

    with mock.patch.object(ifood_auth.requests, "post", side_effect=respostas) as post:
        token, reason = ifood_auth.token_with_reason()

    assert (token, reason) == ("tok-retry", "")
    assert post.call_count == 2


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_transporte_esgotado_reporta_transporte_nao_falta_de_credencial():
    ifood_auth.reset_cache()

    with mock.patch.object(ifood_auth.requests, "post", side_effect=requests.Timeout("nada")) as post:
        token, reason = ifood_auth.token_with_reason()

    assert token is None
    assert reason == ifood_auth.TRANSPORT
    assert post.call_count == 3


@override_settings(SHOPMAN_IFOOD=dict(_CFG, client_id="", client_secret=""))
def test_sem_credencial_nada_e_enviado():
    """Inerte é inerte: sem credencial nenhuma requisição sai (comportamento atual)."""
    ifood_auth.reset_cache()

    with mock.patch.object(ifood_auth.requests, "post") as post:
        token, reason = ifood_auth.token_with_reason()

    assert token is None
    assert reason == ifood_auth.NOT_CONFIGURED
    post.assert_not_called()


# ---------------------------------------------------------------------------
# Defeito 2: a mensagem mentia — "não configurado" para credencial que está lá.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason,esperado",
    [
        (ifood_auth.NOT_CONFIGURED, "is not configured"),
        (ifood_auth.DENIED_EDGE, "edge"),
        (ifood_auth.DENIED_API, "rejected"),
        (ifood_auth.TRANSPORT, "transport"),
    ],
)
def test_cada_razao_tem_mensagem_propria(reason, esperado):
    assert esperado in ifood_auth.failure_message(reason)


def test_recusa_nunca_e_reportada_como_falta_de_credencial():
    """A frase de "sem credencial" não pode aparecer nas outras razões."""
    sem_credencial = ifood_auth.failure_message(ifood_auth.NOT_CONFIGURED)
    for reason in (ifood_auth.DENIED_EDGE, ifood_auth.DENIED_API, ifood_auth.TRANSPORT):
        assert ifood_auth.failure_message(reason) != sem_credencial
        assert "not configured" not in ifood_auth.failure_message(reason)


@override_settings(SHOPMAN_IFOOD=_CFG)
def test_headers_with_reason_devolve_a_razao_da_recusa():
    ifood_auth.reset_cache()

    with mock.patch.object(ifood_auth.requests, "post", return_value=_edge_denial()):
        headers, reason = ifood_auth.headers_with_reason({"Content-Type": "application/json"})

    assert headers is None
    assert reason == ifood_auth.DENIED_EDGE
