"""MATRIZ DE DIAGNÓSTICO — o `create` do access link, assinante a assinante.

Caso real (01/09): a Joyce está no ManyChat, mas chegou pelo **Instagram**. Tem
`subscriber_id`, não tem `whatsapp_id`. O login pelo WhatsApp não gerou link; o
SMS funcionou. Este arquivo enumera as formas de payload que o ManyChat pode
mandar e registra o que cada uma devolve HOJE.

Não é teste de regressão: é instrumento de laudo. Cada asserção documenta o
comportamento observado, para que a correção mude uma linha visível aqui.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client

URL = "/api/auth/access/create/"
KEY = "matriz-de-diagnostico"


@pytest.fixture(autouse=True)
def _api_key(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = KEY
    settings.DOORMAN = base


def _post(payload: dict):
    return Client().post(
        URL, data=json.dumps(payload), content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {KEY}",
    )


@pytest.mark.django_db
class TestMatrizDeAssinantes:
    def test_1_whatsapp_novo_com_whatsapp_id(self):
        r = _post({
            "subscriber": {"id": "mc-wa-novo", "whatsapp_id": "5543999990001", "first_name": "Ana"},
            "access_code": "#menu NB-AAAA",
        })
        print("\n[1] WhatsApp novo, com whatsapp_id      →", r.status_code, r.content[:120])

    def test_2_instagram_novo_sem_whatsapp_id_sem_metadata(self):
        r = _post({
            "subscriber": {"id": "mc-ig-novo", "ig_id": "17841400000001", "ig_username": "joyce", "first_name": "Joyce"},
            "access_code": "#menu NB-BBBB",
        })
        print("[2] Instagram novo, SEM whatsapp_id     →", r.status_code, r.content[:120])

    def test_3_instagram_novo_com_metadata_channel_instagram(self):
        r = _post({
            "subscriber": {"id": "mc-ig-novo2", "ig_id": "17841400000002", "first_name": "Joyce"},
            "access_code": "#menu NB-CCCC",
            "metadata": {"channel": "instagram"},
        })
        print("[3] Instagram novo + metadata.channel   →", r.status_code, r.content[:120])

    def test_4_whatsapp_id_vazio_string(self):
        r = _post({
            "subscriber": {"id": "mc-ig-novo3", "whatsapp_id": "", "first_name": "Joyce"},
            "access_code": "#menu NB-DDDD",
        })
        print("[4] whatsapp_id = string VAZIA          →", r.status_code, r.content[:120])

    def test_5_so_subscriber_id_no_topo(self):
        r = _post({"subscriber_id": "mc-so-id", "access_code": "#menu NB-EEEE"})
        print("[5] só subscriber_id no topo            →", r.status_code, r.content[:120])

    def test_6_instagram_com_email(self):
        r = _post({
            "subscriber": {"id": "mc-ig-mail", "ig_id": "17841400000003", "email": "joyce@example.com", "first_name": "Joyce"},
            "access_code": "#menu NB-FFFF",
            "metadata": {"channel": "instagram"},
        })
        print("[6] Instagram + email, canal instagram  →", r.status_code, r.content[:120])

    def test_7_cliente_ja_existe_por_telefone_sem_whatsapp_id(self):
        """A Joyce DEPOIS de ter logado por SMS: Customer com telefone já existe."""
        from shopman.guestman.models import Customer
        from shopman.guestman.services import customer as customer_service

        customer_service.create(
            ref=Customer.generate_ref(), first_name="Joyce",
            phone="5543999990007", source_system="doorman",
        )
        r = _post({
            "subscriber": {"id": "mc-ig-depois", "ig_id": "17841400000004", "first_name": "Joyce"},
            "access_code": "#menu NB-GGGG",
            "metadata": {"channel": "instagram"},
        })
        print("[7] Instagram, Customer já existe (SMS) →", r.status_code, r.content[:120])


@pytest.mark.django_db
class TestAssinanteJaVinculado:
    """A pessoa do Instagram que o sistema JÁ conhece — o vínculo existe."""

    def _joyce_vinculada(self):
        from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
        from shopman.guestman.models import Customer
        from shopman.guestman.services import customer as customer_service

        c = customer_service.create(
            ref=Customer.generate_ref(), first_name="Joyce",
            phone="5543999990008", source_system="doorman",
        )
        CustomerIdentifier.objects.create(
            customer=c, identifier_type=IdentifierType.MANYCHAT,
            identifier_value="mc-ig-vinculada", is_primary=True,
        )
        return c

    def test_8_vinculada_com_metadata_instagram(self):
        self._joyce_vinculada()
        r = _post({
            "subscriber": {"id": "mc-ig-vinculada", "ig_id": "17841400000005", "first_name": "Joyce"},
            "access_code": "#menu NB-HHHH",
            "metadata": {"channel": "instagram"},
        })
        print("[8] Instagram JÁ VINCULADA + metadata  →", r.status_code, r.content[:120])

    def test_9_vinculada_sem_metadata(self):
        self._joyce_vinculada()
        r = _post({
            "subscriber": {"id": "mc-ig-vinculada", "ig_id": "17841400000005", "first_name": "Joyce"},
            "access_code": "#menu NB-IIII",
        })
        print("[9] Instagram JÁ VINCULADA, sem metadata→", r.status_code, r.content[:120])


@pytest.mark.django_db
class TestVariavelNaoRenderizada:
    """O corpo REAL que o ManyChat mandou para a Joyce em 01/09."""

    CORPO_DA_JOYCE = {
        "source": "manychat",
        "subscriber": {
            "id": "489760326",
            "whatsapp_id": "{{phone}}",
            "first_name": "Joyce",
        },
        "access_code": (
            "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=17977763199107464"
            "&signature=Ab035A76yatScvNo-tUb5HFGO0gyp0gtUfq3KJSKJGWZZ56QzkKdYf_kRpJq3CMr"
        ),
        "metadata": {"channel": "whatsapp"},
    }

    def test_10_a_recusa_nomeia_o_campo_e_diz_o_que_fazer(self):
        r = _post(self.CORPO_DA_JOYCE)
        body = r.json()
        print("\n[10] corpo real da Joyce →", r.status_code, body.get("error"))
        assert r.status_code == 422
        assert body["error_code"] == "unrendered_variable"
        assert body["fields"] == ["subscriber.whatsapp_id"]
        # A recusa antiga mandava procurar o campo errado.
        assert "whatsapp_id requires" not in body["error"]

    def test_11_variavel_renderizada_nao_dispara_o_aviso(self):
        payload = {
            **self.CORPO_DA_JOYCE,
            "subscriber": {**self.CORPO_DA_JOYCE["subscriber"], "whatsapp_id": "5543999990012"},
        }
        r = _post(payload)
        print("[11] mesma coisa com o numero real →", r.status_code)
        assert r.status_code == 200
