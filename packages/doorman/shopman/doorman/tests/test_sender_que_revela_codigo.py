"""A trava de produção conhece os DOIS irmãos, e os próximos também.

O `ConsoleSender` era recusado pelo nome; o `LogSender`, que loga o código em
claro exatamente do mesmo jeito, passava batido — e era ele que os dois specs
da DO declaravam. O remédio tinha ido no site reportado, não no irmão.

A varredura abaixo é o que impede a volta: todo sender do módulo precisa
RESPONDER `reveals_code`, no próprio corpo da classe. Sender novo que esqueça
não passa no CI, em vez de passar batido e aparecer no log de produção.
"""

import inspect

import pytest
from django.core.exceptions import ImproperlyConfigured
from shopman.doorman import senders as senders_module
from shopman.doorman.apps import enforce_production_settings
from shopman.doorman.conf import DoormanSettings
from shopman.doorman.senders import sender_reveals_code

_PATH = "shopman.doorman.senders."

#: Os dublês da casa: entregam para quem tem acesso ao processo, não para o
#: cliente. Qualquer sender novo que faça isso entra aqui.
REVELAM = {"ConsoleSender", "LogSender"}


def _senders_do_modulo():
    for nome, obj in vars(senders_module).items():
        if inspect.isclass(obj) and not nome.endswith("Protocol") and hasattr(obj, "send_code"):
            yield nome, obj


class TestVarreduraDeSenders:
    def test_todo_sender_declara_reveals_code_no_proprio_corpo(self):
        """Herdar ou omitir não vale: a resposta é explícita, por classe."""
        sem_resposta = [
            nome for nome, cls in _senders_do_modulo() if "reveals_code" not in cls.__dict__
        ]
        assert not sem_resposta, (
            f"sender(es) sem `reveals_code` declarado: {sem_resposta}. "
            "Declare True se a classe imprime/loga o código, False se entrega "
            "ao cliente — a trava de produção lê esse atributo."
        )

    def test_a_varredura_enxerga_todos_os_senders(self):
        """Guarda da própria guarda: se o filtro parar de achar, o teste acima
        vira verde vazio — que é o modo silencioso de um gate morrer."""
        nomes = {nome for nome, _ in _senders_do_modulo()}
        assert nomes >= REVELAM | {"EmailSender", "WhatsAppCloudAPISender", "SMSSender"}

    def test_quem_revela_e_quem_entrega(self):
        for nome, cls in _senders_do_modulo():
            assert cls.reveals_code is (nome in REVELAM), nome


class TestSenderRevealsCode:
    @pytest.mark.parametrize("nome", sorted(REVELAM))
    def test_dubles_da_casa_revelam(self, nome):
        assert sender_reveals_code(_PATH + nome) is True

    @pytest.mark.parametrize("nome", ["EmailSender", "WhatsAppCloudAPISender", "SMSSender"])
    def test_senders_de_verdade_nao_revelam(self, nome):
        assert sender_reveals_code(_PATH + nome) is False

    def test_sender_de_terceiro_sem_o_atributo_conta_como_entregador(self):
        """Provedor externo não tem que conhecer atributo nosso. O `ComteleSMSSender`
        é o caso real: vive em `shopman.shop.adapters` e entrega SMS de verdade."""
        assert sender_reveals_code("shopman.doorman.tests.test_sender_que_revela_codigo.FakeSMS") is False

    def test_caminho_que_nao_importa_nao_derruba_a_checagem(self):
        """Não-sei não é motivo para recusar: o caminho quebrado tem mensagem
        própria mais adiante no boot."""
        assert sender_reveals_code("modulo.que.nao.existe.Sender") is False


class FakeSMS:
    """Sender de terceiro: entrega de verdade e não declara `reveals_code`."""

    def send_code(self, target, code, method):
        return True


def _ds(**kwargs) -> DoormanSettings:
    base = {
        "ACCESS_LINK_API_KEY": "chave-de-producao",
        "DEFAULT_DOMAIN": "loja.exemplo.com.br",
        "MESSAGE_SENDER_CLASS": _PATH + "EmailSender",
        "DELIVERY_CHAIN": [],
    }
    base.update(kwargs)
    return DoormanSettings(**base)


class TestTravaDeProducao:
    """O que o boot faz quando `settings.DEBUG` é False."""

    @pytest.mark.parametrize("nome", sorted(REVELAM))
    def test_recusa_sender_que_revela_com_cadeia_vazia(self, nome):
        with pytest.raises(ImproperlyConfigured, match="REVEALS the OTP code"):
            enforce_production_settings(_ds(MESSAGE_SENDER_CLASS=_PATH + nome))

    @pytest.mark.parametrize("nome", sorted(REVELAM))
    def test_com_cadeia_declarada_o_sender_unico_nem_entra_em_cena(self, nome):
        """`send_code_with_fallback` só cai no MESSAGE_SENDER_CLASS quando a
        cadeia está vazia. Com cadeia, o dublê é inerte — e é por isso que o
        alpha de hoje não vaza, apesar de declarar o LogSender."""
        enforce_production_settings(
            _ds(MESSAGE_SENDER_CLASS=_PATH + nome, DELIVERY_CHAIN=["sms", "email"])
        )

    def test_sender_de_verdade_com_cadeia_vazia_passa(self):
        enforce_production_settings(_ds())

    def test_as_outras_duas_travas_seguem_de_pe(self):
        with pytest.raises(ImproperlyConfigured, match="ACCESS_LINK_API_KEY"):
            enforce_production_settings(_ds(ACCESS_LINK_API_KEY=""))
        with pytest.raises(ImproperlyConfigured, match="DEFAULT_DOMAIN"):
            enforce_production_settings(_ds(DEFAULT_DOMAIN="localhost:8000"))
