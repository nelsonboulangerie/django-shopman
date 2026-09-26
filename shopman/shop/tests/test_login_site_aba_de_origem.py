"""Login pelo WhatsApp que começa no SITE: a aba de origem entra sozinha.

A queixa dos testadores era a volta: "vai pro WhatsApp, envia uma tal mensagem,
depois sai do WhatsApp de novo por um link". O link abria no navegador embutido do
WhatsApp, e a aba onde a pessoa estava continuava em "Vamos entrar?".

Agora a mensagem libera o navegador que apertou o botão, e só ele: a liberação mora
sob a impressão digital da sessão de origem, não sob o código. A pessoa volta para a
aba e já está dentro; o link da mensagem vira reserva; e o "Não foi você?" da
mensagem desfaz a entrada — a defesa contra quem pede a alguém que envie a mensagem
com o código dele.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client

CREATE = "/api/auth/access/create/"
START = "/api/v1/auth/whatsapp/start/"
CLAIM = "/api/v1/auth/whatsapp/claim/"
REVOKE = "/api/v1/auth/whatsapp/revoke/"
SESSION = "/api/v1/auth/session/"
KEY = "aba-de-origem"


@pytest.fixture(autouse=True)
def _api_key(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base


@pytest.fixture(autouse=True)
def _cache_limpo():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def notify():
    with patch("shopman.shop.notifications.notify") as mocked:
        mocked.return_value = SimpleNamespace(success=True, error=None)
        yield mocked


@pytest.fixture
def joyce():
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    c = customer_service.create(
        ref=Customer.generate_ref(), first_name="Joyce",
        phone="5543999990009", source_system="doorman",
    )
    CustomerIdentifier.objects.create(
        customer=c, identifier_type=IdentifierType.MANYCHAT,
        identifier_value="mc-joyce", is_primary=True,
    )
    return c


IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


def _navegador() -> Client:
    return Client(HTTP_USER_AGENT=IPHONE)


def _aperta_o_botao(browser: Client) -> dict:
    response = browser.post(START, data=json.dumps({"next": "/menu"}), content_type="application/json")
    assert response.status_code == 200, response.content
    return response.json()


def _mensagem_chega(code: str, text: str | None = None) -> dict:
    response = Client().post(
        CREATE,
        data=json.dumps({
            "subscriber": {"id": "mc-joyce", "whatsapp_id": "5543999990009", "first_name": "Joyce"},
            "access_code": text if text is not None else f"#menu {code}",
        }),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {KEY}",
    )
    assert response.status_code == 200, response.content
    return response.json()


def _logado(browser: Client) -> bool:
    return bool(browser.get(SESSION).json().get("is_authenticated"))


@pytest.mark.django_db
class TestAAbaDeOrigemEntraSozinha:
    def test_antes_da_mensagem_a_aba_espera(self, joyce, notify):
        browser = _navegador()
        _aperta_o_botao(browser)

        assert browser.post(CLAIM).json() == {"status": "pending"}
        assert not _logado(browser)

    def test_a_mensagem_libera_a_aba_que_apertou_o_botao(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)

        created = _mensagem_chega(started["code"])
        assert created["released"] is True

        claimed = browser.post(CLAIM).json()
        assert claimed["status"] == "done"
        assert claimed["is_authenticated"] is True
        assert claimed["redirect"] == "/menu"
        assert _logado(browser)

    def test_a_liberacao_vale_uma_vez(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])

        assert browser.post(CLAIM).json()["status"] == "done"
        # Segunda pergunta: nada mais pendente (e ela já está dentro).
        assert browser.post(CLAIM).json() == {"status": "pending"}

    def test_outro_navegador_nao_encontra_a_liberacao(self, joyce, notify):
        """O código não é credencial: quem não gerou, não entra — nem sabendo o código."""
        origem = _navegador()
        started = _aperta_o_botao(origem)
        _mensagem_chega(started["code"])

        intruso = _navegador()
        intruso.post(START, data="{}", content_type="application/json")
        assert intruso.post(CLAIM).json() == {"status": "pending"}
        assert not _logado(intruso)
        # E a origem continua podendo entrar.
        assert origem.post(CLAIM).json()["status"] == "done"

    def test_entrar_pela_aba_lembra_o_dispositivo(self, joyce, notify):
        from shopman.doorman.models import TrustedDevice

        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])
        claimed = browser.post(CLAIM).json()

        assert claimed.get("device_trusted") is True
        assert TrustedDevice.objects.filter(subject_id=joyce.uuid, is_active=True).count() == 1

    def test_mensagem_organica_nao_libera_ninguem(self, joyce, notify):
        """`#menu` digitado direto no WhatsApp: não há aba de origem, nada muda."""
        created = _mensagem_chega("", text="#menu")
        assert created["released"] is False
        assert notify.call_args.kwargs["event"] == "access_link"


@pytest.mark.django_db
class TestAMensagemMandaVoltar:
    def test_a_mensagem_diz_que_ela_ja_entrou_e_oferece_o_nao_fui_eu(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])

        kw = notify.call_args.kwargs
        assert kw["event"] == "access_link_site"
        assert kw["context"]["access_url"]  # o link segue como reserva
        assert "/encerrar-acesso#" in kw["context"]["revoke_url"]
        assert kw["context"]["origin_note"] == " (Safari / iPhone)"

    def test_o_texto_nao_deixa_placeholder_sobrando(self):
        from shopman.shop.notification_copy import CUSTOMER_COPY

        body = CUSTOMER_COPY["access_link_site"]["body"].format(
            customer_name_greeting=", Joyce", origin_note=" (Safari / iPhone)",
            access_url="https://loja/a?t=x", revoke_url="https://loja/encerrar-acesso#r",
        )
        assert "{" not in body
        assert body.startswith("Pronto, Joyce! Pode voltar ao site")


@pytest.mark.django_db
class TestNaoFuiEu:
    def _ref(self, notify) -> str:
        return notify.call_args.kwargs["context"]["revoke_url"].split("#", 1)[1]

    def test_antes_de_a_aba_voltar_cancela_a_entrada(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])

        dono = Client()
        assert dono.post(REVOKE, data=json.dumps({"ref": self._ref(notify)}), content_type="application/json").status_code == 200

        assert browser.post(CLAIM).json() == {"status": "pending"}
        assert not _logado(browser)

    def test_depois_de_a_aba_entrar_derruba_sessao_e_dispositivo(self, joyce, notify):
        from shopman.doorman.models import TrustedDevice

        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])
        assert browser.post(CLAIM).json()["status"] == "done"
        assert _logado(browser)

        dono = Client()
        response = dono.post(REVOKE, data=json.dumps({"ref": self._ref(notify)}), content_type="application/json")
        assert response.status_code == 200

        assert not _logado(browser)
        assert TrustedDevice.objects.filter(subject_id=joyce.uuid, is_active=True).count() == 0

    def test_referencia_desconhecida_ou_repetida(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])
        ref = self._ref(notify)

        dono = Client()
        body = json.dumps({"ref": ref})
        assert dono.post(REVOKE, data=body, content_type="application/json").status_code == 200
        assert dono.post(REVOKE, data=body, content_type="application/json").status_code == 404
        assert dono.post(REVOKE, data=json.dumps({"ref": "inventada"}), content_type="application/json").status_code == 404


def test_o_codigo_vale_dez_minutos():
    from shopman.doorman.conf import DoormanSettings

    assert DoormanSettings().LINK_STATE_TTL_SECONDS == 600
