"""O ManyChat falso do harness aceita o que o adapter de produção manda, e guarda (#3272).

O ``notification_manychat`` roda inteiro contra o fake (só o ``base_url`` muda), então o
contrato que importa é o do adapter: a resposta do login começado no computador sai com os
dois botões ("Encerrar acesso" e "Liberar …"), e a jornada os lê em ``/__sent``. Sem isto, a
J14 não tinha onde tocar em "Liberar o Chrome" nem no "Não foi você?".
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from shopman.shop.tests.e2e.fake_manychat import FakeManychat, _handler

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake(settings):
    fake = FakeManychat()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(fake))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    settings.SHOPMAN_MANYCHAT = {
        **settings.SHOPMAN_MANYCHAT,
        "api_token": "e2e-fake-manychat-local-only",
        "base_url": f"{base}/fb",
        "flow_map": {},
    }
    settings.SHOPMAN_MANYCHAT_ALLOW_IN_DEBUG = True
    try:
        yield fake, base
    finally:
        server.shutdown()
        server.server_close()


def _sent(base: str, subscriber: str) -> list[dict]:
    with urlopen(f"{base}/__sent?subscriber={subscriber}", timeout=5) as response:
        return json.loads(response.read())["sent"]


def test_resposta_do_login_no_computador_guarda_os_dois_botoes(fake):
    from shopman.shop.adapters import notification_manychat

    _, base = fake
    ok = notification_manychat.send(
        "9123",
        "access_link_site",
        {
            "access_url": "http://loja/auth/access/?t=x",
            "customer_name": "Teresa",
            "has_cart_context": True,
            "cart_note": "Sua sacola está guardada. ",
            "release_url": "http://loja/liberar-acesso#solta",
            "revoke_url": "http://loja/encerrar-acesso#desfaz",
            "release_target": "o Chrome",
            "release_caption": "Liberar o Chrome",
        },
    )

    assert ok is True
    [message] = _sent(base, "9123")
    assert message["endpoint"] == "/fb/sending/sendContent"
    assert message["buttons"] == [
        {"caption": "Encerrar acesso", "url": "http://loja/encerrar-acesso#desfaz"},
        {"caption": "Liberar o Chrome", "url": "http://loja/liberar-acesso#solta"},
    ]
    assert message["body"]["data"]["content"]["type"] == "whatsapp"
    # Outro assinante não vê a mensagem dela.
    assert _sent(base, "9999") == []


def test_sem_token_ou_sem_assinante_e_recusado_como_no_manychat(fake):
    _, base = fake
    body = json.dumps({"subscriber_id": 1, "data": {"version": "v2", "content": {"type": "whatsapp", "messages": [{"type": "text", "text": "oi"}]}}}).encode()
    request = Request(f"{base}/fb/sending/sendContent", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(HTTPError) as refused:
        urlopen(request, timeout=5)
    assert refused.value.code == 401

    request = Request(
        f"{base}/fb/sending/sendContent",
        data=json.dumps({"data": {}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"},
        method="POST",
    )
    with pytest.raises(HTTPError) as refused:
        urlopen(request, timeout=5)
    assert refused.value.code == 400
    assert _sent(base, "") == []


def test_rota_que_o_fake_nao_conhece_responde_404(fake):
    _, base = fake
    request = Request(f"{base}/fb/page/getFlows", headers={"Authorization": "Bearer x"})
    with pytest.raises(HTTPError) as missing:
        urlopen(request, timeout=5)
    assert missing.value.code == 404


@pytest.mark.django_db(transaction=True)
def test_aviso_do_pedido_acha_o_contato_pelo_telefone_e_chega_no_fake(fake, settings, monkeypatch):
    """#3282: quem entrou por código não tem id do ManyChat. O resolvedor do Guestman,
    o de produção, procura o telefone no fake, cria o contato e o guarda; o aviso chega."""
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
    from shopman.guestman.contrib.manychat import resolver
    from shopman.guestman.models import Customer

    from shopman.shop.adapters import notification_manychat

    _, base = fake
    monkeypatch.setattr(resolver, "_API_BASE", f"{base}/fb")
    settings.MANYCHAT_API_TOKEN = "e2e-fake-manychat-local-only"
    customer = Customer.objects.create(ref="CUS-AVISO-01", first_name="Rosa", phone="+5543991112233")

    ok = notification_manychat.send(
        "+5543991112233",
        "order_cancelled",
        {"order_ref": "ORD-3282", "customer_name": "Rosa"},
    )

    assert ok is True
    [message] = _sent_by_phone(base, "5543991112233")
    assert message["endpoint"] in {"/fb/sending/sendContent", "/fb/sending/sendFlow"}
    ident = CustomerIdentifier.objects.get(customer=customer, identifier_type=IdentifierType.MANYCHAT)
    assert ident.identifier_value == message["subscriber_id"]


def _sent_by_phone(base: str, phone: str) -> list[dict]:
    with urlopen(f"{base}/__sent?phone={phone}", timeout=5) as response:
        return [item for item in json.loads(response.read())["sent"] if item["endpoint"].startswith("/fb/sending/")]
