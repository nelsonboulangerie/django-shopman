"""Campanha exclusiva de grupo: o Marketing escreve ``campaign_refs`` e o envio obedece.

Até 19/10/2026 o Gestor gravava ``PriceTierAdvantage(kind="exclusive_notifications")
.config["campaign_refs"]`` e ninguém lia: um grupo podia "ter" um aviso exclusivo que
saía para todo mundo. Estes testes amarram as três pontas:

1. o Marketing é o dono da chave e mexe só na referência da campanha dele;
2. a campanha exclusiva só alcança membros dos grupos que a declaram, qualquer que
   seja o público escolhido, na contagem, no disparo e no envio das ondas;
3. falha fechada: vantagem desligada tira os membros, nunca abre para todos.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer, PriceTier, PriceTierAdvantage

from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger
from shopman.shop.services import audience, campaign_exclusivity
from shopman.shop.services import campaign as campaign_service

pytestmark = pytest.mark.django_db


def _customer(phone: str, ref: str, *tiers, opted_in: bool = True):
    today = timezone.localdate()
    customer = Customer.objects.create(
        ref=ref,
        first_name="Ana",
        phone=phone,
        price_tiers=list(tiers),
        birthday=today.replace(year=today.year - 30),
    )
    if opted_in:
        ConsentService.grant_consent(ref, audience.DELIVERY_CONSENT_CHANNEL, source="test")
    return customer


@pytest.fixture
def groups():
    equipe = PriceTier.objects.create(ref="equipe", name="Equipe")
    alianca = PriceTier.objects.create(ref="alianca", name="Aliança Francesa")
    varejo = PriceTier.objects.create(ref="varejo", name="Varejo")
    return equipe, alianca, varejo


@pytest.fixture
def campaign():
    template = AnnouncementTemplate.objects.create(name="Recado", body="Um recado.")
    return Campaign.objects.create(
        name="Prévia da Aliança",
        trigger=Trigger.MANUAL,
        template=template,
        platforms=["whatsapp"],
        audience_rules={},
    )


def _refs(tier_ref: str) -> list[str]:
    advantage = PriceTierAdvantage.objects.get(tier__ref=tier_ref, kind="exclusive_notifications")
    return list(advantage.config.get("campaign_refs") or [])


# ── 1. O Marketing é o dono da chave ─────────────────────────────────────────


def test_marking_a_group_creates_the_advantage_switched_on(groups, campaign):
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])

    advantage = PriceTierAdvantage.objects.get(tier__ref="alianca", kind="exclusive_notifications")
    assert advantage.is_active is True
    assert advantage.config == {"campaign_refs": [f"campaign:{campaign.pk}"]}
    assert campaign_exclusivity.for_campaign(campaign.pk).declared == ("alianca",)


def test_the_marketing_touches_only_its_own_reference(groups, campaign):
    """Outra campanha, prioridade e interruptor do Gestor ficam como estavam."""
    _equipe, alianca, _varejo = groups
    PriceTierAdvantage.objects.create(
        tier=alianca,
        kind="exclusive_notifications",
        is_active=False,
        priority=7,
        config={"campaign_refs": ["campaign:999"], "outra_chave": "fica"},
    )

    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])
    advantage = PriceTierAdvantage.objects.get(tier=alianca, kind="exclusive_notifications")
    assert advantage.config == {
        "campaign_refs": ["campaign:999", f"campaign:{campaign.pk}"],
        "outra_chave": "fica",
    }
    assert (advantage.is_active, advantage.priority) == (False, 7)

    campaign_exclusivity.set_exclusive_tiers(campaign.pk, [])
    advantage.refresh_from_db()
    assert advantage.config["campaign_refs"] == ["campaign:999"]


def test_moving_the_exclusivity_removes_it_from_the_group_left_behind(groups, campaign):
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca", "equipe"])
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["equipe"])

    assert _refs("alianca") == []
    assert _refs("equipe") == [f"campaign:{campaign.pk}"]


def test_unknown_group_is_refused_before_writing(groups, campaign):
    with pytest.raises(campaign_exclusivity.CampaignExclusivityError):
        campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca", "sumiu"])
    assert not PriceTierAdvantage.objects.filter(kind="exclusive_notifications").exists()


def test_the_list_reads_every_campaign_in_one_query(groups, campaign):
    other = Campaign.objects.create(
        name="Outra", trigger=Trigger.MANUAL, template=campaign.template, platforms=["whatsapp"]
    )
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca", "equipe"])
    campaign_exclusivity.set_exclusive_tiers(other.pk, ["equipe"])

    with CaptureQueriesContext(connection) as ctx:
        declared = campaign_exclusivity.declared_by_campaign()
    assert len(ctx.captured_queries) == 1
    assert declared == {
        f"campaign:{campaign.pk}": ("alianca", "equipe"),
        f"campaign:{other.pk}": ("equipe",),
    }


# ── 2. O envio obedece ──────────────────────────────────────────────────────


def test_exclusive_campaign_reaches_only_members_even_with_another_audience(groups, campaign):
    equipe, alianca, varejo = groups
    member = _customer("+5543999992001", "CLI-AL", alianca)
    _customer("+5543999992002", "CLI-VA", varejo)
    _customer("+5543999992003", "CLI-EQ", equipe)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])

    # O público escolhido é "todo o varejo + equipe + aliança"; a exclusividade filtra.
    rules = {"price_tiers": ["varejo", "equipe", "alianca"]}
    result = audience.resolve(rules, campaign_id=campaign.pk)

    assert [r.phone for r in result.all_recipients()] == [member.phone]
    assert result.excluded_by_reason["outside_exclusive_groups"] == 2
    assert result.counts["exclusive_groups_count"] == 1
    # Sem a campanha (contagem avulsa) nada é restringido.
    assert audience.resolve(rules).total == 3


def test_member_of_several_declaring_groups_receives_once(groups, campaign):
    equipe, alianca, _varejo = groups
    both = _customer("+5543999992011", "CLI-BOTH", equipe, alianca)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca", "equipe"])

    result = audience.resolve({"price_tiers": ["alianca", "equipe"]}, campaign_id=campaign.pk)

    assert [r.phone for r in result.all_recipients()] == [both.phone]
    assert result.total == 1


def test_switched_off_advantage_takes_members_out_and_never_opens_to_all(groups, campaign):
    equipe, alianca, _varejo = groups
    _customer("+5543999992021", "CLI-AL2", alianca)
    on_team = _customer("+5543999992022", "CLI-EQ2", equipe)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca", "equipe"])
    PriceTierAdvantage.objects.filter(tier=alianca, kind="exclusive_notifications").update(
        is_active=False
    )

    result = audience.resolve({"price_tiers": ["alianca", "equipe"]}, campaign_id=campaign.pk)
    assert [r.phone for r in result.all_recipients()] == [on_team.phone]

    PriceTierAdvantage.objects.filter(tier=equipe, kind="exclusive_notifications").update(
        is_active=False
    )
    nobody = audience.resolve({"price_tiers": ["alianca", "equipe"]}, campaign_id=campaign.pk)
    assert nobody.total == 0
    assert nobody.excluded_by_reason["outside_exclusive_groups"] == 2


def test_consent_still_rules_inside_the_group(groups, campaign):
    _equipe, alianca, _varejo = groups
    _customer("+5543999992031", "CLI-SEM", alianca, opted_in=False)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])

    assert audience.resolve({"price_tiers": ["alianca"]}, campaign_id=campaign.pk).total == 0


def test_membership_lookup_does_not_grow_with_the_audience(groups, campaign):
    """Sem N+1: 1 consulta da exclusividade + 1 da filiação, para 3 ou 30 pessoas."""
    _equipe, alianca, varejo = groups
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])

    def queries(n_customers: int, offset: int) -> int:
        for i in range(n_customers):
            _customer(f"+55439999{offset + i:05d}", f"CLI-N{offset + i}", alianca if i % 2 else varejo)
        rules = {"price_tiers": ["alianca", "varejo"]}
        with CaptureQueriesContext(connection) as plain:
            audience.resolve(rules)
        with CaptureQueriesContext(connection) as exclusive:
            audience.resolve(rules, campaign_id=campaign.pk)
        return len(exclusive.captured_queries) - len(plain.captured_queries)

    assert queries(3, 10000) == 2
    assert queries(30, 20000) == 2


def test_fire_now_seals_only_the_members_and_the_waves_send_to_them(groups, campaign):
    """De ponta a ponta: o anúncio promete N, e o envio de cada onda alcança os mesmos N."""
    equipe, alianca, varejo = groups
    member = _customer("+5543999992041", "CLI-AL3", alianca)
    _customer("+5543999992042", "CLI-VA3", varejo)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])

    announcement = campaign_service.fire_now(
        campaign.pk, audience_rules={"price_tiers": ["varejo", "alianca"]}
    )

    assert announcement.audience["total"] == 1
    assert announcement.audience["excluded_by_reason"]["outside_exclusive_groups"] == 1
    sent = audience.select_wave(
        announcement.trigger_context["audience_rules"],
        "all",
        campaign_id=announcement.rule_id,
    )
    assert [r.phone for r in sent] == [member.phone]


# ── 3. Apagar a campanha não abre a porta (frente 3b) ────────────────────────
# Medido em 19/10/2026: o anúncio liga à campanha por FK ``SET_NULL``. Apagada a
# campanha, o ``rule_id`` virava nulo, ``for_campaign(None)`` dizia "não exclusiva", e
# as ondas que ainda faltavam saíam para o público escolhido inteiro.


def _send_wave(announcement, wave: str = "all") -> list[str]:
    from types import SimpleNamespace
    from unittest.mock import patch

    from shopman.shop.handlers.campaign import AnnouncementNotifyHandler

    message = SimpleNamespace(
        pk=announcement.pk, payload={"announcement_id": announcement.pk, "wave": wave}
    )
    with patch("shopman.shop.handlers.campaign._send_to", return_value=(0, 0)) as send:
        AnnouncementNotifyHandler().handle(message=message, ctx={})
    return [r.phone for r in send.call_args.args[0]]


def test_waves_of_a_deleted_exclusive_campaign_still_reach_only_members(groups, campaign):
    from shopman.shop.models import Announcement

    equipe, alianca, varejo = groups
    member = _customer("+5543999992051", "CLI-AL5", alianca)
    _customer("+5543999992052", "CLI-VA5", varejo)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])
    announcement = campaign_service.fire_now(
        campaign.pk, audience_rules={"price_tiers": ["varejo", "alianca"]}
    )
    assert _send_wave(announcement) == [member.phone]

    campaign.delete()  # qualquer caminho: o pre_delete herda antes da FK virar nula
    announcement = Announcement.objects.get(pk=announcement.pk)

    assert announcement.rule_id is None
    assert announcement.trigger_context["exclusive_price_tiers"] == ["alianca"]
    assert _send_wave(announcement) == [member.phone]
    # A referência morreu junto: grupo nenhum aponta para a campanha apagada.
    assert _refs("alianca") == []


def test_inherited_exclusivity_with_the_advantage_switched_off_reaches_nobody(groups, campaign):
    from shopman.shop.models import Announcement

    _equipe, alianca, varejo = groups
    _customer("+5543999992061", "CLI-AL6", alianca)
    _customer("+5543999992062", "CLI-VA6", varejo)
    campaign_exclusivity.set_exclusive_tiers(campaign.pk, ["alianca"])
    announcement = campaign_service.fire_now(
        campaign.pk, audience_rules={"price_tiers": ["varejo", "alianca"]}
    )
    campaign.delete()
    PriceTierAdvantage.objects.filter(tier=alianca, kind="exclusive_notifications").update(
        is_active=False
    )

    assert _send_wave(Announcement.objects.get(pk=announcement.pk)) == []


def test_deleting_a_campaign_that_is_not_exclusive_leaves_its_announcements_as_they_were(
    groups, campaign
):
    from shopman.shop.models import Announcement

    _equipe, alianca, varejo = groups
    _customer("+5543999992071", "CLI-AL7", alianca)
    _customer("+5543999992072", "CLI-VA7", varejo)
    announcement = campaign_service.fire_now(
        campaign.pk, audience_rules={"price_tiers": ["varejo", "alianca"]}
    )
    campaign.delete()
    announcement = Announcement.objects.get(pk=announcement.pk)

    assert "exclusive_price_tiers" not in announcement.trigger_context
    assert len(_send_wave(announcement)) == 2
