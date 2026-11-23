"""OC-06: a chamada do WhatsApp na home diz quem responde.

Com a Concierge atendendo o WhatsApp da casa, a home não promete "de pessoa para
pessoa": quem responde primeiro é a assistente virtual. Desligada (ou sem conexão
de WhatsApp ativa, ou só observando), o texto de sempre fica.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

HUMAN_PROMISE = "de pessoa para pessoa"

WHATSAPP_CONNECTION = {
    "active": True,
    "provider": "manychat",
    "account": "acct-1",
    "channel": "whatsapp",
    "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
    "options": {"allowed_subjects": ["sub-1"]},
}


def _concierge(**overrides) -> dict:
    config = {
        "contract_version": 3,
        "operation_mode": "assist",
        "enabled": True,
        "connections": {"manychat-whatsapp-primary": dict(WHATSAPP_CONNECTION)},
    }
    config.update(overrides)
    return config


def _whatsapp_cta(rf) -> dict:
    from shopman.shop.models import Shop
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home

    Shop.load() or Shop.objects.create(name="Test Padaria")
    payload = projection_data(build_home(rf.get("/api/v1/storefront/home/")))
    return payload["sections_copy"]["whatsapp_cta"]


def test_concierge_on_home_does_not_promise_person_to_person(rf, settings):
    settings.SHOPMAN_CONCIERGE = _concierge()

    cta = _whatsapp_cta(rf)

    assert HUMAN_PROMISE not in cta["message"]
    assert "assistente virtual" in cta["message"]
    assert cta["title"]


def test_concierge_off_home_keeps_person_to_person(rf, settings):
    settings.SHOPMAN_CONCIERGE = _concierge(enabled=False)

    assert HUMAN_PROMISE in _whatsapp_cta(rf)["message"]


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"operation_mode": "observe"}, id="so-observa"),
        pytest.param({"contract_version": 0}, id="sem-contrato"),
        pytest.param({"connections": {}}, id="sem-conexao"),
        pytest.param(
            {"connections": {"manychat-whatsapp-primary": {**WHATSAPP_CONNECTION, "active": False}}},
            id="conexao-inativa",
        ),
        pytest.param(
            {"connections": {"ig": {**WHATSAPP_CONNECTION, "channel": "instagram"}}},
            id="conexao-de-outro-canal",
        ),
    ],
)
def test_concierge_that_does_not_answer_whatsapp_keeps_person_to_person(rf, settings, overrides):
    settings.SHOPMAN_CONCIERGE = _concierge(**overrides)

    assert HUMAN_PROMISE in _whatsapp_cta(rf)["message"]

