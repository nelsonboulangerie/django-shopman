"""A casa entrega o link; o ManyChat só avisa que alguém pediu.

Em 01 e 02/09 quatro links foram criados e NENHUM foi usado — `used_at` nulo nos
quatro. O backend cumpria a parte dele e a mensagem, montada dentro do ManyChat,
não chegava. Estes testes pinam o caminho novo e, principalmente, a armadilha que
ele NÃO pode cair: o `{tracking_url}` de toda notificação de pedido nasce pelo
mesmo serviço, com a mesma `source`, e não pode virar mensagem extra.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client

from shopman.shop.handlers.access_link import on_access_link_created

URL = "/api/auth/access/create/"
KEY = "entrega-direta"


def _token(**metadata):
    return SimpleNamespace(metadata=metadata)


def _cliente(phone="+5543984035793", name="Joyce"):
    return SimpleNamespace(phone=phone, name=name)


class TestQuemPedeRecebe:
    def test_o_link_e_entregue_por_whatsapp(self):
        with patch("shopman.shop.notifications.notify") as notify:
            notify.return_value = SimpleNamespace(success=True, error=None)
            on_access_link_created(
                None, token=_token(deliver="manychat"), customer=_cliente(),
                url="https://menu.nelsonboulangerie.com.br/a?t=abc",
            )
        assert notify.called
        kw = notify.call_args.kwargs
        assert kw["event"] == "access_link"
        assert kw["backend"] == "manychat"
        assert kw["context"]["access_url"].endswith("?t=abc")

    def test_com_sacola_a_mensagem_diz_que_ela_veio_junto(self):
        with patch("shopman.shop.notifications.notify") as notify:
            notify.return_value = SimpleNamespace(success=True, error=None)
            on_access_link_created(
                None, token=_token(deliver="manychat", cart_session_key="c1"),
                customer=_cliente(), url="https://x/a?t=1",
            )
        assert "sacola" in notify.call_args.kwargs["context"]["cart_note"].lower()

    def test_sem_sacola_o_sufixo_some_limpo(self):
        with patch("shopman.shop.notifications.notify") as notify:
            notify.return_value = SimpleNamespace(success=True, error=None)
            on_access_link_created(
                None, token=_token(deliver="manychat"), customer=_cliente(),
                url="https://x/a?t=1",
            )
        assert notify.call_args.kwargs["context"]["cart_note"] == ""


class TestAArmadilhaQueNaoPodeAcontecer:
    def test_link_de_notificacao_NAO_vira_mensagem(self):
        """Todo `{tracking_url}` de pedido cria um AccessLink com source=manychat.

        Sem o filtro por intenção, cada aviso de pedido mandaria uma mensagem
        extra no WhatsApp do cliente.
        """
        with patch("shopman.shop.notifications.notify") as notify:
            on_access_link_created(
                None, token=_token(order_ref="NB-1"), customer=_cliente(),
                url="https://x/a?t=1",
            )
        assert not notify.called

    def test_sem_url_ou_sem_telefone_grita_e_nao_manda(self):
        with patch("shopman.shop.notifications.notify") as notify:
            with patch("shopman.shop.handlers.access_link.logger") as log:
                on_access_link_created(
                    None, token=_token(deliver="manychat"),
                    customer=_cliente(phone=""), url="https://x/a?t=1",
                )
        assert not notify.called
        assert log.error.called

    def test_envio_que_falha_grita(self):
        with patch("shopman.shop.notifications.notify") as notify:
            notify.return_value = SimpleNamespace(success=False, error="24h window closed")
            with patch("shopman.shop.handlers.access_link.logger") as log:
                on_access_link_created(
                    None, token=_token(deliver="manychat"), customer=_cliente(),
                    url="https://x/a?t=1",
                )
        assert log.error.called, "mensagem que não saiu tem de ser distinguível de cliente que desistiu"

    def test_excecao_no_envio_nao_derruba_a_criacao_do_token(self):
        with patch("shopman.shop.notifications.notify", side_effect=OSError("timeout")):
            on_access_link_created(
                None, token=_token(deliver="manychat"), customer=_cliente(),
                url="https://x/a?t=1",
            )  # não levanta


@pytest.mark.django_db
class TestPontaAPonta:
    @pytest.fixture(autouse=True)
    def _key(self, settings):
        base = dict(getattr(settings, "DOORMAN", {}) or {})
        base["ACCESS_LINK_API_KEY"] = KEY
        settings.DOORMAN = base

    def test_o_endpoint_marca_a_intencao_de_entregar(self):
        from shopman.doorman.models import AccessLink

        r = Client().post(
            URL,
            data=json.dumps({"subscriber": {"id": "mc-1", "whatsapp_id": "5543999990001"}}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {KEY}",
        )
        assert r.status_code == 200, r.content
        link = AccessLink.objects.order_by("-created_at").first()
        assert link.metadata.get("deliver") == "manychat", (
            "sem esta marca o handler não sabe distinguir o link PEDIDO do link "
            "embutido numa notificação de pedido"
        )


class TestEntregaParaQuemFalou:
    """02/09: o ManyChat recusou com o código 3011 — "última interação há 19521h".

    O envio resolvia o destinatário pelo TELEFONE, e o resolver, não achando
    contato com aquele número, CRIA um assinante novo. Contato nascido há
    segundos não tem janela de 24h, então o ManyChat recusa. Mandávamos para um
    estranho enquanto quem acabou de escrever esperava.
    """

    def test_manda_para_o_assinante_gravado_pela_view(self):
        with patch("shopman.shop.notifications.notify") as notify:
            notify.return_value = SimpleNamespace(success=True, error=None)
            on_access_link_created(
                None,
                token=_token(deliver="manychat", deliver_to="117684058"),
                customer=_cliente(phone="+554384128247"),
                url="https://x/a?t=1",
            )
        assert notify.call_args.kwargs["recipient"] == "117684058", (
            "o telefone faria o adapter procurar — e criar — outro contato"
        )

    def test_sem_o_assinante_o_telefone_ainda_serve_de_fallback(self):
        with patch("shopman.shop.notifications.notify") as notify:
            notify.return_value = SimpleNamespace(success=True, error=None)
            on_access_link_created(
                None, token=_token(deliver="manychat"),
                customer=_cliente(phone="+554384128247"), url="https://x/a?t=1",
            )
        assert notify.call_args.kwargs["recipient"] == "+554384128247"


@pytest.mark.django_db
def test_o_endpoint_grava_o_assinante_que_falou(settings):
    from shopman.doorman.models import AccessLink

    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base

    r = Client().post(
        URL,
        data=json.dumps({"subscriber": {"id": "117684058", "whatsapp_id": "5543984128247"}}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {KEY}",
    )
    assert r.status_code == 200, r.content
    link = AccessLink.objects.order_by("-created_at").first()
    assert link.metadata.get("deliver_to") == "117684058"
