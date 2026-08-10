"""O opt-in do ManyChat vira consentimento aqui — nos dois sentidos.

Existe porque o rodapé das mensagens promete "responda SAIR para parar", e o flow nativo
do ManyChat cumpre isso **lá**. Sem esta sincronização a pessoa saía no ManyChat e
continuava consentida no nosso banco: a próxima campanha a alcançaria de novo, e a
promessa da mensagem seria mentira.

Sincronizar ESTADO em vez de tratar evento é o ponto: é idempotente, e cobre a volta
(quem revoga e depois consente de novo) sem handler extra.
"""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.consent.service import ConsentService
from shopman.guestman.contrib.manychat.service import ManychatService
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db

PHONE = "+5543984049009"


def _subscriber(**over) -> dict:
    payload = {
        "id": "4605528796186498",
        "first_name": "Pablo",
        "last_name": "Valentini",
        "whatsapp_id": PHONE,
    }
    payload.update(over)
    return payload


def test_opting_out_on_manychat_revokes_here(db):
    """O caso que a promessa do rodapé depende: SAIR lá tira do alcance aqui."""
    customer, _ = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))
    assert ConsentService.has_consent(customer.ref, "whatsapp") is True

    ManychatService.sync_subscriber(_subscriber(optin_whatsapp=False))

    assert ConsentService.has_consent(customer.ref, "whatsapp") is False


def test_opting_back_in_works_too(db):
    """Estado, não evento: quem volta é alcançável de novo, sem handler extra."""
    customer, _ = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=False))
    assert ConsentService.has_consent(customer.ref, "whatsapp") is False

    ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))

    assert ConsentService.has_consent(customer.ref, "whatsapp") is True


def test_a_missing_field_is_not_a_revocation(db):
    """⚠️ Webhook parcial é comum. "Ausente" nunca pode significar "não consente".

    Tratar campo ausente como revogação apagaria consentimento por silêncio — e um
    payload magro do ManyChat zeraria a base inteira sem ninguém pedir.
    """
    customer, _ = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))
    assert ConsentService.has_consent(customer.ref, "whatsapp") is True

    ManychatService.sync_subscriber(_subscriber())  # sem nenhum optin_*

    assert ConsentService.has_consent(customer.ref, "whatsapp") is True


def test_a_null_field_is_not_a_revocation(db):
    customer, _ = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))
    ManychatService.sync_subscriber(_subscriber(optin_whatsapp=None))
    assert ConsentService.has_consent(customer.ref, "whatsapp") is True


def test_each_channel_is_independent(db):
    """Sair do WhatsApp não é sair do e-mail: consentimento é POR canal."""
    customer, _ = ManychatService.sync_subscriber(
        _subscriber(optin_whatsapp=True, optin_email=True)
    )
    assert ConsentService.has_consent(customer.ref, "whatsapp") is True
    assert ConsentService.has_consent(customer.ref, "email") is True

    ManychatService.sync_subscriber(_subscriber(optin_whatsapp=False, optin_email=True))

    assert ConsentService.has_consent(customer.ref, "whatsapp") is False
    assert ConsentService.has_consent(customer.ref, "email") is True


def test_optin_phone_maps_to_sms(db):
    """`optin_phone` do ManyChat é o canal de SMS aqui — nomes diferentes, mesma coisa."""
    customer, _ = ManychatService.sync_subscriber(_subscriber(optin_phone=True))
    assert ConsentService.has_consent(customer.ref, "sms") is True


def test_a_new_subscriber_already_arrives_with_consent(db):
    """Quem entra pelo ManyChat já consentindo não precisa consentir de novo aqui."""
    customer, created = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))
    assert created is True
    assert ConsentService.has_consent(customer.ref, "whatsapp") is True


def test_the_revocation_reaches_the_campaign_audience(db):
    """A prova que fecha o laço: revogar no ManyChat tira da audiência de campanha."""
    customer, _ = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))
    assert customer.ref in ConsentService.get_marketable_customers("whatsapp")

    ManychatService.sync_subscriber(_subscriber(optin_whatsapp=False))

    assert customer.ref not in ConsentService.get_marketable_customers("whatsapp")


def test_a_broken_consent_write_does_not_break_the_sync(db, monkeypatch):
    """Consentimento é importante, mas não pode derrubar o cadastro do cliente."""
    def _boom(*a, **kw):
        raise RuntimeError("consent store down")

    monkeypatch.setattr(ConsentService, "grant_consent", _boom)

    customer, created = ManychatService.sync_subscriber(_subscriber(optin_whatsapp=True))
    assert created is True
    assert Customer.objects.filter(pk=customer.pk).exists()
