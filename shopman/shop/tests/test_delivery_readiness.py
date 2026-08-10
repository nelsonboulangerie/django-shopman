"""Entrega não quer dizer a mesma coisa em toda plataforma.

Este arquivo existe por causa de uma correção do dono: a primeira versão do aviso de
alcance só sabia falar de WhatsApp, porque foi escrita durante um teste de WhatsApp.
Anúncio é conteúdo que sai por vários canais, e **cada um tem exigência própria**:

· publicar no Instagram não tem destinatário, nem consentimento, nem janela de 24h;
· mandar WhatsApp tem os três.

A TV saiu da lista de plataformas (ADR-020 §10): ela mostra a promoção porque a promoção
vale naquele canal, não porque um anúncio a escolheu como destino.

O teste que guarda o desenho é `test_publication_does_not_inherit_whatsapp_rules`: se
alguém voltar a tratar tudo como mensagem, ele quebra.
"""

from __future__ import annotations

import pytest

from shopman.shop.services import delivery_readiness as dr

pytestmark = pytest.mark.django_db


@pytest.fixture
def no_transport(monkeypatch):
    """Sem transporte de mensagem direta e sem adapter de publicação."""
    monkeypatch.setattr("shopman.shop.handlers.campaign._whatsapp_backend", lambda: None)
    monkeypatch.setattr("shopman.shop.handlers.campaign._posting_adapter", lambda p: None)


@pytest.fixture
def with_transport(monkeypatch):
    monkeypatch.setattr("shopman.shop.handlers.campaign._whatsapp_backend", lambda: "manychat")
    return monkeypatch


def _by_platform(states):
    return {state.platform: state for state in states}


def test_each_platform_is_classified_by_how_it_delivers(no_transport):
    states = _by_platform(dr.readiness_for(["instagram", "whatsapp"]))

    assert states["instagram"].kind == dr.PUBLICATION
    assert states["whatsapp"].kind == dr.DIRECT_MESSAGE


def test_the_store_tv_is_no_longer_a_platform(no_transport):
    """⚠️ A TV saiu, e por isso é tratada como desconhecida — não como pronta.

    Enquanto ela era plataforma, o anúncio gravava `published` e empurrava num canal SSE
    com ZERO consumidores: o painel dizia "publicado" e nenhuma TV mostrava nada. Pior que
    código morto, era sucesso falso.
    """
    (state,) = dr.readiness_for(["tv"])
    assert state.kind == "unknown"
    assert state.ready is False


def test_publication_without_an_adapter_is_blocked(no_transport):
    for platform in ("instagram", "facebook", "google_business"):
        (state,) = dr.readiness_for([platform])
        assert state.ready is False, platform
        assert "integração" in state.reason


def test_publication_does_not_inherit_whatsapp_rules(with_transport, monkeypatch):
    """⚠️ O teste que guarda o desenho.

    Publicação não tem janela de 24h nem template aprovado. Se alguém voltar a tratar
    tudo como mensagem, o Instagram passaria a "limitar por janela" — o que não faz
    sentido nenhum, e é exatamente o erro que esta função corrige.
    """
    adapter = type("A", (), {"is_available": staticmethod(lambda *a, **k: True)})()
    monkeypatch.setattr("shopman.shop.handlers.campaign._posting_adapter", lambda p: adapter)

    (state,) = dr.readiness_for(["instagram"])
    assert state.ready is True
    assert state.limitation == "", "publicação não tem janela de 24h"


def test_publication_with_an_adapter_but_no_credential_is_blocked(monkeypatch):
    adapter = type("A", (), {"is_available": staticmethod(lambda *a, **k: False)})()
    monkeypatch.setattr("shopman.shop.handlers.campaign._posting_adapter", lambda p: adapter)

    (state,) = dr.readiness_for(["instagram"])
    assert state.ready is False
    assert "credencial" in state.reason


def test_direct_message_without_transport_is_blocked(no_transport):
    (state,) = dr.readiness_for(["whatsapp"])
    assert state.ready is False
    assert "transporte" in state.reason


def test_direct_message_without_template_is_ready_but_limited(with_transport):
    """O meio-termo honesto: sai, mas não para todo mundo."""
    (state,) = dr.readiness_for(["whatsapp"])
    assert state.ready is True
    assert "24 horas" in state.limitation


def test_direct_message_with_template_has_no_limitation(with_transport):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="announcement_published", subject="x", body="y",
        whatsapp_flow_ns="content20260101120000_1",
    )

    (state,) = dr.readiness_for(["whatsapp"])
    assert state.ready is True
    assert state.limitation == ""


def test_an_unknown_platform_says_so_instead_of_pretending(no_transport):
    """Plataforma que o sistema não conhece não pode passar por pronta."""
    (state,) = dr.readiness_for(["tiktok"])
    assert state.ready is False
    assert state.kind == "unknown"


def test_the_order_asked_is_the_order_returned(no_transport):
    states = dr.readiness_for(["google_business", "whatsapp", "instagram"])
    assert [s.platform for s in states] == ["google_business", "whatsapp", "instagram"]


def test_no_platforms_no_states(no_transport):
    assert dr.readiness_for([]) == ()
    assert dr.readiness_for(None) == ()


# ── O que a projection faz com isso ──────────────────────────────────


def test_the_board_only_warns_about_platforms_in_use(no_transport):
    """Avisar sobre Instagram numa loja que só usa WhatsApp treina o gestor a ignorar."""
    from shopman.backstage.projections import marketing as mp
    from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger

    template = AnnouncementTemplate.objects.create(name="T", body="oi")
    Campaign.objects.create(
        name="Só WhatsApp", trigger=Trigger.MANUAL, template=template,
        platforms=["whatsapp"], is_active=True,
    )

    platforms = {limit.platform for limit in mp.build_board().reach_limits}
    assert platforms == {"whatsapp"}


def test_the_board_separates_blocking_from_limiting(with_transport):
    from shopman.backstage.projections import marketing as mp
    from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger

    with_transport.setattr("shopman.shop.handlers.campaign._posting_adapter", lambda p: None)
    template = AnnouncementTemplate.objects.create(name="T", body="oi")
    Campaign.objects.create(
        name="Tudo", trigger=Trigger.MANUAL, template=template,
        platforms=["instagram", "whatsapp"], is_active=True,
    )

    limits = {limit.platform: limit for limit in mp.build_board().reach_limits}
    assert limits["instagram"].blocking is True, "sem adapter, nada publica"
    assert limits["whatsapp"].blocking is False, "sem template, publica só na janela"


def test_a_fully_ready_platform_produces_no_noise(with_transport):
    from shopman.backstage.projections import marketing as mp
    from shopman.shop.models import AnnouncementTemplate, Campaign, NotificationTemplate, Trigger

    NotificationTemplate.objects.create(
        event="announcement_published", subject="x", body="y",
        whatsapp_flow_ns="content20260101120000_1",
    )
    template = AnnouncementTemplate.objects.create(name="T", body="oi")
    Campaign.objects.create(
        name="Só WhatsApp", trigger=Trigger.MANUAL, template=template,
        platforms=["whatsapp"], is_active=True,
    )

    assert mp.build_board().reach_limits == ()
