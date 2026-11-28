"""OC-06: a chamada do WhatsApp na home diz quem responde.

A frase só promete o que é verdade para quem lê (X1). "A assistente virtual
responde" exige que a Concierge responda TODO visitante: ligada, com conexão de
WhatsApp ativa e admitindo quem não está em lista nenhuma. Com coorte fechada,
quem está fora dela é atendido como antes, e a home mantém "de pessoa para pessoa".
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


def _concierge(*, allowed_subjects=("sub-1",), **overrides) -> dict:
    connection = {**WHATSAPP_CONNECTION, "options": {"allowed_subjects": list(allowed_subjects)}}
    config = {
        "contract_version": 3,
        "operation_mode": "assist",
        "enabled": True,
        "connections": {"manychat-whatsapp-primary": connection},
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


def test_concierge_on_with_closed_cohort_keeps_person_to_person(rf, settings):
    """Ligada + conexão + coorte de 1 contato: o visitante da home está fora dela."""
    settings.SHOPMAN_CONCIERGE = _concierge(allowed_subjects=("sub-1",))

    assert HUMAN_PROMISE in _whatsapp_cta(rf)["message"]


def test_no_configuration_today_answers_every_visitor(rf, settings):
    """Sem restrição de coorte não existe hoje: lista vazia FECHA a conexão
    (``service.is_allowed``), ninguém é atendido. Então a home sempre cai no texto
    antigo até abrir a coorte ganhar mecanismo na admissão (#3430)."""
    settings.SHOPMAN_CONCIERGE = _concierge(allowed_subjects=())

    assert HUMAN_PROMISE in _whatsapp_cta(rf)["message"]


def test_concierge_answering_every_visitor_says_who_answers(rf, settings, monkeypatch):
    """Quando a admissão aceitar quem não está em lista nenhuma (o mecanismo de
    #3430, simulado aqui no próprio ``service.is_allowed``), a home diz que a
    assistente responde, sem mudar o predicado."""
    from shopman.storefront.concierge import service

    settings.SHOPMAN_CONCIERGE = _concierge(allowed_subjects=())
    monkeypatch.setattr(service, "is_allowed", lambda binding: binding.subject != "")

    cta = _whatsapp_cta(rf)

    assert HUMAN_PROMISE not in cta["message"]
    assert "assistente virtual" in cta["message"]
    assert cta["title"]


def test_concierge_off_home_keeps_person_to_person(rf, settings, monkeypatch):
    from shopman.storefront.concierge import service

    settings.SHOPMAN_CONCIERGE = _concierge(enabled=False)
    monkeypatch.setattr(service, "is_allowed", lambda binding: True)

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
def test_concierge_that_does_not_answer_whatsapp_keeps_person_to_person(rf, settings, monkeypatch, overrides):
    """Mesmo com a admissão aberta a todos, sem os outros portões a casa não promete."""
    from shopman.storefront.concierge import service

    settings.SHOPMAN_CONCIERGE = _concierge(**overrides)
    monkeypatch.setattr(service, "is_allowed", lambda binding: True)

    assert HUMAN_PROMISE in _whatsapp_cta(rf)["message"]
