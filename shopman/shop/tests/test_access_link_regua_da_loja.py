"""Higiene do link (OC-09): teto de prazo na API S2S e audiência aplicada na troca.

Antes: a ponte do ManyChat (``api/auth/access/create/``) cunhava link com o prazo que
o chamador pedisse, sem teto (``ttl_minutes: 525600`` era um crachá de um ano), e com
qualquer audiência; a porta da loja trocava qualquer audiência por sessão completa,
porque ``exchange_token`` nunca passava audiência nenhuma.

Depois: prazo acima de 24 h é recusado na hora de cunhar, audiência sem porta na loja
também, e a porta da loja só troca as audiências dela. Os links do cliente (WhatsApp,
``#menu``, código NB, campanha) seguem como estavam.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

URL = "/api/auth/access/create/"
EXCHANGE = "/api/v1/auth/access/"
KEY = "regua-da-loja"
SUBSCRIBER = {"subscriber": {"id": "mc-regua", "whatsapp_id": "5543999990042"}}

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _key(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base


def _post(payload, *, key=KEY):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {key}"} if key else {}
    return Client().post(URL, data=json.dumps(payload), content_type="application/json", **headers)


def _links():
    from shopman.doorman.models import AccessLink

    return AccessLink.objects.count()


class TestTetoDePrazoNaApiS2S:
    def test_sem_prazo_vale_o_padrao_de_sempre(self):
        r = _post(SUBSCRIBER)
        assert r.status_code == 200, r.content
        from shopman.doorman.models import AccessLink

        link = AccessLink.objects.order_by("-created_at").first()
        assert link.expires_at - link.created_at <= timedelta(minutes=6)

    def test_prazo_no_teto_e_cunhado(self):
        r = _post({**SUBSCRIBER, "ttl_minutes": 24 * 60})
        assert r.status_code == 200, r.content

    def test_prazo_acima_do_teto_e_recusado_sem_cunhar(self):
        before = _links()
        r = _post({**SUBSCRIBER, "ttl_minutes": 24 * 60 + 1})
        assert r.status_code == 400
        assert r.json()["error_code"] == "invalid_input"
        assert "24 horas" in r.json()["error"]
        assert _links() == before

    def test_prazo_de_um_ano_e_recusado(self):
        assert _post({**SUBSCRIBER, "ttl_minutes": 525600}).status_code == 400

    @pytest.mark.parametrize("ttl", ["60", True, [5], {"m": 5}])
    def test_prazo_que_nao_e_numero_e_recusado(self, ttl):
        before = _links()
        assert _post({**SUBSCRIBER, "ttl_minutes": ttl}).status_code == 400
        assert _links() == before

    def test_sem_chave_a_recusa_e_do_doorman_e_nao_da_regua(self):
        r = _post({**SUBSCRIBER, "ttl_minutes": 525600}, key="")
        assert r.status_code == 401
        r = _post({**SUBSCRIBER, "ttl_minutes": 525600}, key="errada")
        assert r.status_code == 401


class TestAudienciaNaApiS2S:
    @pytest.mark.parametrize("audience", ["web_general", "web_checkout", "web_account"])
    def test_audiencias_da_loja_sao_cunhadas(self, audience):
        assert _post({**SUBSCRIBER, "audience": audience}).status_code == 200

    def test_audiencia_sem_porta_na_loja_e_recusada_sem_cunhar(self):
        before = _links()
        r = _post({**SUBSCRIBER, "audience": "web_support"})
        assert r.status_code == 400
        assert r.json()["error_code"] == "invalid_input"
        assert _links() == before


class TestAudienciaNaTroca:
    def _token(self, customer, audience):
        from shopman.doorman.models import AccessLink

        return AccessLink.create_with_token(
            customer_id=customer.uuid,
            audience=audience,
            source=AccessLink.Source.INTERNAL,
            metadata={},
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def _customer(self):
        from shopman.guestman.models import Customer

        return Customer.objects.create(ref="CUS-REGUA", first_name="Rita", phone="+5543999990043")

    def test_audiencia_errada_nao_abre_sessao_nem_gasta_o_token(self):
        customer = self._customer()
        link, raw = self._token(customer, "web_support")
        client = Client()

        r = client.post(EXCHANGE, {"token": raw})

        assert r.status_code == 400
        assert client.session.get("_auth_user_id") is None
        link.refresh_from_db()
        assert link.used_at is None

    @pytest.mark.parametrize("audience", ["web_general", "web_checkout", "web_account"])
    def test_audiencias_da_loja_abrem_sessao(self, audience):
        """``web_checkout`` é o link pessoal de campanha (``campaign_identity``): segue entrando."""
        customer = self._customer()
        _link, raw = self._token(customer, audience)
        client = Client()

        r = client.post(EXCHANGE, {"token": raw})

        assert r.status_code == 200, r.content
        assert client.session.get("_auth_user_id") is not None

    def test_entrada_de_reserva_recusa_audiencia_errada(self):
        """``/auth/access/?t=`` (sem loja configurada) aplica a mesma régua."""
        link, raw = self._token(self._customer(), "web_support")
        client = Client()

        r = client.get(f"/auth/access/?t={raw}")

        assert r.status_code == 200
        assert "Link inválido" in r.content.decode()
        assert client.session.get("_auth_user_id") is None
        link.refresh_from_db()
        assert link.used_at is None

    def test_entrada_de_reserva_troca_audiencia_da_loja(self):
        _link, raw = self._token(self._customer(), "web_general")
        client = Client()

        r = client.get(f"/auth/access/?t={raw}")

        assert r.status_code == 302
        assert client.session.get("_auth_user_id") is not None
