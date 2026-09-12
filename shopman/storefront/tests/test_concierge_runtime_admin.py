"""Admin existente mostra certeza de transporte separada de pedido/pagamento."""

import pytest
from django.urls import reverse

from shopman.storefront.tests import test_concierge_admin as fixtures

admin_client = fixtures.admin_client
conversation = fixtures.conversation

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("state", "label"),
    [
        ("unknown", "Envio desconhecido; não reenviar sem verificar"),
        ("accepted", "Aceita pelo fornecedor; entrega não comprovada"),
        ("not_applied", "Envio não aplicado; verificar próxima ação"),
        ("not_applicable", "Estado do envio indisponível"),
    ],
)
def test_transcript_exposes_transport_certainty_without_inventing_delivery(admin_client, conversation, state, label):
    reply = conversation.messages.get(kind="reply")
    reply.transport_state = state
    reply.save(update_fields=["transport_state"])
    response = admin_client.get(reverse("admin:shop_conversation_change", args=[conversation.pk]))
    assert response.status_code == 200
    assert label in response.content.decode()
    assert "Entrega comprovada" not in response.content.decode()


def test_handoff_sync_explains_unknown_without_technical_status(admin_client, conversation):
    conversation.state = "handoff"
    conversation.save(update_fields=["state"])
    conversation.transport_bindings.filter(provider="manychat").update(
        handoff_sync_state="unknown",
    )
    response = admin_client.get(reverse("admin:shop_conversation_change", args=[conversation.pk]))
    html = response.content.decode()
    assert "Não confirmada; atendimento humano preservado" in html
    assert "sincronização do atendimento" in html.lower()


def test_handoff_not_applied_explains_preserved_ownership(admin_client, conversation):
    conversation.state = "handoff"
    conversation.save(update_fields=["state"])
    conversation.transport_bindings.update(handoff_sync_state="not_applied")

    response = admin_client.get(reverse("admin:shop_conversation_change", args=[conversation.pk]))

    assert "Não aplicada; atendimento humano preservado" in response.content.decode()
