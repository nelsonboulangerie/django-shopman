"""Login pelo WhatsApp que começa no SITE: a resposta traz o botão de volta.

Escada sem fricção do Doorman (decisão do dono, 23/10):

- No COMPUTADOR, a mensagem chega no celular e deixa a liberação esperando pela aba que
  apertou o botão (e só por ela: a liberação mora sob a impressão digital da sessão de
  origem, não sob o código). O botão da resposta nomeia o que libera ("Liberar o
  Chrome"), e só o toque nele deixa a aba entrar.
- No CELULAR, nada é liberado para outra aba: o botão "Voltar à loja" entra no navegador
  que ele abrir. Se é o mesmo navegador da aba que esperava, ela percebe pelo cookie.
- O "Não foi você?" da mensagem desfaz tudo: a defesa contra quem pede a alguém que
  envie a mensagem com o código dele.
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
RELEASE = "/api/v1/auth/whatsapp/release/"
SESSION = "/api/v1/auth/session/"
KEY = "aba-de-origem"


@pytest.fixture(autouse=True)
def _api_key(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base
    settings.SHOPMAN_WA_VERIFY = {"number": "554333231997"}


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


WINDOWS_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _navegador() -> Client:
    """O computador onde o login começou."""
    return Client(HTTP_USER_AGENT=WINDOWS_CHROME)


def _celular() -> Client:
    return Client(HTTP_USER_AGENT=IPHONE)


def _toca_liberar(notify) -> int:
    """O toque em "Liberar o Chrome", no celular de quem recebeu a mensagem."""
    ref = notify.call_args.kwargs["context"]["release_url"].split("#", 1)[1]
    return _celular().post(RELEASE, data=json.dumps({"ref": ref}), content_type="application/json").status_code


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
        # A mensagem sozinha não solta a aba: falta o toque no botão que a nomeia.
        assert browser.post(CLAIM).json() == {"status": "pending"}
        assert not _logado(browser)

        assert _toca_liberar(notify) == 200
        claimed = browser.post(CLAIM).json()
        assert claimed["status"] == "done"
        assert claimed["is_authenticated"] is True
        assert claimed["redirect"] == "/menu"
        assert _logado(browser)

    def test_a_liberacao_vale_uma_vez(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])
        _toca_liberar(notify)

        first = browser.post(CLAIM).json()
        assert first["status"] == "done"
        # Segunda pergunta: a liberação já foi usada; a aba só confirma que está dentro.
        second = browser.post(CLAIM).json()
        assert second["status"] == "done"
        assert "device_trusted" not in second

    def test_outro_navegador_nao_encontra_a_liberacao(self, joyce, notify):
        """O código não é credencial: quem não gerou, não entra — nem sabendo o código."""
        origem = _navegador()
        started = _aperta_o_botao(origem)
        _mensagem_chega(started["code"])
        _toca_liberar(notify)

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
        _toca_liberar(notify)
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
    def test_no_computador_o_botao_nomeia_o_que_libera_e_oferece_o_nao_fui_eu(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        assert started["return_mode"] == "release_this_tab"
        assert started["return_button"] == "Liberar o Chrome"
        _mensagem_chega(started["code"])

        kw = notify.call_args.kwargs
        assert kw["event"] == "access_link_site"
        assert kw["context"]["release_caption"] == "Liberar o Chrome"
        assert kw["context"]["release_target"] == "o Chrome no Windows"
        assert "/liberar-acesso#" in kw["context"]["release_url"]
        assert "/encerrar-acesso#" in kw["context"]["revoke_url"]
        # Referências diferentes: quem tem o link de liberar não ganha o de derrubar.
        assert kw["context"]["release_url"].split("#")[1] != kw["context"]["revoke_url"].split("#")[1]

    def test_o_texto_nao_deixa_placeholder_sobrando(self):
        from shopman.shop.notification_copy import CUSTOMER_COPY

        body = CUSTOMER_COPY["access_link_site"]["body"].format(
            customer_name_greeting=", Joyce",
            cart_note="Sua sacola está guardada. ",
            release_target="o Chrome no Windows",
        )
        assert "{" not in body
        assert body.startswith("Pronto, Joyce! Toque abaixo para entrar na loja com o Chrome no Windows.")
        assert "https://" not in body

    def test_liberar_duas_vezes_nao_estraga_e_referencia_inventada_nao_libera(self, joyce, notify):
        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])

        assert _toca_liberar(notify) == 200
        assert _toca_liberar(notify) == 200
        inventada = _celular().post(RELEASE, data=json.dumps({"ref": "inventada"}), content_type="application/json")
        assert inventada.status_code == 404
        assert browser.post(CLAIM).json()["status"] == "done"


@pytest.mark.django_db
class TestNoCelularNadaELiberadoParaOutraAba:
    def test_a_mensagem_nao_libera_aba_nenhuma_e_o_botao_e_voltar_a_loja(self, joyce, notify):
        aba = _celular()
        started = _aperta_o_botao(aba)
        assert started["return_mode"] == "message_button"
        assert started["return_button"] == "Voltar à loja"

        created = _mensagem_chega(started["code"])
        assert created["released"] is False
        kw = notify.call_args.kwargs
        assert kw["event"] == "access_link"
        assert kw["context"]["access_caption"] == "Voltar à loja"
        # A aba que esperava continua do lado de fora: ninguém a liberou à distância.
        assert aba.post(CLAIM).json() == {"status": "pending"}
        assert not _logado(aba)

    def test_o_botao_entra_no_navegador_que_ele_abre(self, joyce, notify):
        aba = _celular()
        started = _aperta_o_botao(aba)
        created = _mensagem_chega(started["code"])

        # O botão abre o mesmo navegador: o cookie passa a ser de quem entrou, e a aba
        # que esperava só percebe.
        exchanged = aba.post(
            "/api/v1/auth/access/", data=json.dumps({"token": created["token"]}),
            content_type="application/json",
        )
        assert exchanged.status_code == 200, exchanged.content
        claimed = aba.post(CLAIM).json()
        assert claimed["status"] == "done"
        assert claimed["is_authenticated"] is True

    def test_agente_desconhecido_conta_como_celular(self, joyce, notify):
        started = _aperta_o_botao(Client())
        assert started["return_mode"] == "message_button"


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

        # Depois do "Não foi você?", nem o botão de liberar solta mais nada.
        assert _toca_liberar(notify) == 404
        assert browser.post(CLAIM).json() == {"status": "pending"}
        assert not _logado(browser)

    def test_depois_de_a_aba_entrar_derruba_sessao_e_dispositivo(self, joyce, notify):
        from shopman.doorman.models import TrustedDevice

        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])
        _toca_liberar(notify)
        assert browser.post(CLAIM).json()["status"] == "done"
        assert _logado(browser)

        dono = Client()
        response = dono.post(REVOKE, data=json.dumps({"ref": self._ref(notify)}), content_type="application/json")
        assert response.status_code == 200

        assert not _logado(browser)
        assert TrustedDevice.objects.filter(subject_id=joyce.uuid, is_active=True).count() == 0

    def test_derruba_tudo_o_que_a_janela_abriu_e_poupa_a_passkey_antiga(self, joyce, notify):
        """Quem entrou no lugar dela pode, antes do toque, abrir outra sessão, confiar outro
        navegador e cadastrar uma passkey. Cada um desses sobrevive sozinho se o "Não foi
        você?" derrubar só a sessão e o dispositivo da liberação."""
        from datetime import timedelta

        from django.utils import timezone
        from shopman.doorman.models import CustomerUser, Passkey, TrustedDevice

        antiga = Passkey.objects.create(
            customer_id=joyce.uuid, credential_id="cred-antiga", public_key="pk",
        )
        Passkey.objects.filter(pk=antiga.pk).update(created_at=timezone.now() - timedelta(days=30))

        browser = _navegador()
        started = _aperta_o_botao(browser)
        _mensagem_chega(started["code"])
        _toca_liberar(notify)
        assert browser.post(CLAIM).json()["status"] == "done"

        # O que o intruso abriu na janela, por fora da liberação.
        outra_aba = _navegador()
        outra_aba.force_login(CustomerUser.objects.get(customer_id=joyce.uuid).user)
        assert _logado(outra_aba)
        TrustedDevice.create_for("customer", str(joyce.uuid), user_agent=IPHONE)
        Passkey.objects.create(customer_id=joyce.uuid, credential_id="cred-intruso", public_key="pk")

        dono = Client()
        response = dono.post(REVOKE, data=json.dumps({"ref": self._ref(notify)}), content_type="application/json")
        assert response.status_code == 200

        assert not _logado(browser)
        assert not _logado(outra_aba)
        assert TrustedDevice.objects.filter(subject_id=str(joyce.uuid), is_active=True).count() == 0
        assert list(
            Passkey.objects.filter(customer_id=joyce.uuid).values_list("credential_id", flat=True)
        ) == ["cred-antiga"]

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
