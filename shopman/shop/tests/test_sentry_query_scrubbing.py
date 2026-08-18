"""O segredo do webhook não pode sair daqui dentro de uma URL.

A Efí autentica o webhook por `?token=` — não por escolha nossa: ela não envia
cabeçalho customizado, o mecanismo dela é hash no fim da URL registrada. Como o
deploy não tem proxy mTLS, esse token é a autenticação ÚNICA do endpoint.

`send_default_pii=False` NÃO remove query string. Sem o `before_send`, todo
erro naquele endpoint mandava o segredo em texto puro para um serviço externo,
e ficava guardado lá. Este teste é o que impede o corte de sumir num refactor.
"""

from __future__ import annotations

import pathlib

import pytest

SETTINGS = pathlib.Path(__file__).resolve().parents[3] / "config" / "settings.py"


def _load_scrubber():
    """Extrai o `_strip_query_string` do settings sem reimportar o módulo."""
    source = SETTINGS.read_text()
    start = source.index("        def _strip_query_string(event, hint):")
    end = source.index("        sentry_sdk.init(", start)
    block = "\n".join(line[8:] for line in source[start:end].splitlines())
    namespace: dict = {}
    exec(compile(block, str(SETTINGS), "exec"), namespace)  # noqa: S102
    return namespace["_strip_query_string"]


@pytest.fixture(scope="module")
def scrub():
    return _load_scrubber()


def test_the_efi_token_never_leaves_inside_the_url(scrub):
    event = {
        "request": {
            "url": "https://api.exemplo.test/api/webhooks/efi/pix/?token=SEGREDO-DA-EFI",
            "query_string": "token=SEGREDO-DA-EFI",
        }
    }
    cleaned = scrub(event, None)

    assert "SEGREDO-DA-EFI" not in str(cleaned)
    assert cleaned["request"]["url"] == "https://api.exemplo.test/api/webhooks/efi/pix/"
    assert "query_string" not in cleaned["request"]


def test_scrubbing_is_not_limited_to_the_efi_route(scrub):
    """Query string é onde token, chave e telefone costumam viajar."""
    event = {"request": {"url": "https://api.exemplo.test/api/v1/x/?phone=43999998888"}}

    assert "43999998888" not in str(scrub(event, None))


def test_url_without_query_survives_intact(scrub):
    event = {"request": {"url": "https://api.exemplo.test/health/"}}

    assert scrub(event, None)["request"]["url"] == "https://api.exemplo.test/health/"


@pytest.mark.parametrize("event", [{}, {"request": None}, {"request": {}}])
def test_event_without_request_does_not_explode(scrub, event):
    """`before_send` que levanta derruba o envio do evento inteiro."""
    assert scrub(dict(event), None) is not None
