"""Agendamento que DISPARA: a vassoura arma, a fila dispara.

O problema que a F9 resolve é de minuto, não de arquitetura. Antes, o despacho acontecia
no ciclo de manutenção (a cada 5 min), então uma relâmpago das 17h30 podia sair às 17h34 —
numa promoção cujo valor inteiro é o minuto.

A solução usa o que já existia: a vassoura **arma** uma `Directive` com `available_at` no
instante exato, e `process_directives --watch` (~2s) dispara. Latência de armar é
irrelevante (acontece na hora anterior); a de disparar é de segundos. Sem broker, sem
mexer em nenhum threshold da ADR-003.

Os dois testes que mais importam aqui são de DUPLICIDADE: armar duas vezes e criar duas
vezes. Mensagem em dobro chega ao cliente e não tem desfazer.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from django.utils import timezone

from shopman.shop.models import Announcement, AnnouncementTemplate, Campaign, Trigger
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services import campaign_schedule as sched

pytestmark = pytest.mark.django_db


def _at(hour: int, minute: int = 0, day: int = 10) -> datetime:
    """Um instante local determinístico (agosto/2026)."""
    return timezone.make_aware(datetime(2026, 8, day, hour, minute))


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(name="Relâmpago", body="Promoção agora!")


def _campaign(schedule: dict, *, template, trigger=Trigger.SCHEDULE, active=True) -> Campaign:
    return Campaign.objects.create(
        name="Relâmpago das 17h30",
        trigger=trigger,
        template=template,
        platforms=["whatsapp"],
        schedule=schedule,
        is_active=active,
    )


# ── O vocabulário: adiar × disparar ──────────────────────────────────


def test_deferring_types_do_not_fire():
    """`immediate` e `preferred_hours` adiam algo que já existe; não criam ocasião."""
    assert sched.fires_on_its_own({"type": "immediate"}) is False
    assert sched.fires_on_its_own({"type": "preferred_hours", "windows": [["07:00", "11:00"]]}) is False
    assert sched.fires_on_its_own(None) is False


def test_firing_types_fire():
    assert sched.fires_on_its_own({"type": "once", "at": "2026-08-15T07:00:00-03:00"}) is True
    assert sched.fires_on_its_own({"type": "recurring", "windows": [["17:30", "18:30"]]}) is True


def test_once_returns_the_moment_when_it_is_ahead():
    schedule = {"type": "once", "at": _at(17, 30).isoformat()}
    assert sched.next_occurrence(schedule, now=_at(9, 0)) == _at(17, 30)


def test_once_in_the_past_never_fires_again():
    """Ocasião única que passou não volta — senão um deploy antigo reviveria promoção."""
    schedule = {"type": "once", "at": _at(9, 0).isoformat()}
    assert sched.next_occurrence(schedule, now=_at(17, 30)) is None


def test_recurring_finds_the_next_window_start():
    # 10/08/2026 é uma segunda (weekday 0).
    schedule = {"type": "recurring", "windows": [["17:30", "18:30"]], "weekdays": [0]}
    assert sched.next_occurrence(schedule, now=_at(9, 0)) == _at(17, 30)


def test_recurring_skips_to_the_next_allowed_weekday():
    """Sexta e sábado: pedido numa segunda cai na sexta, não amanhã."""
    schedule = {"type": "recurring", "windows": [["17:30", "18:30"]], "weekdays": [4, 5]}
    found = sched.next_occurrence(schedule, now=_at(9, 0))
    assert found == _at(17, 30, day=14)  # sexta


def test_recurring_respects_the_period():
    schedule = {
        "type": "recurring", "windows": [["17:30", "18:30"]], "weekdays": [0],
        "starts_on": "2026-08-17",
    }
    # Hoje é segunda 10; a primeira permitida é a segunda 17.
    assert sched.next_occurrence(schedule, now=_at(9, 0)) == _at(17, 30, day=17)


def test_a_finished_period_never_fires_again():
    schedule = {
        "type": "recurring", "windows": [["17:30", "18:30"]], "weekdays": [0],
        "ends_on": "2026-08-09",
    }
    assert sched.next_occurrence(schedule, now=_at(9, 0)) is None


def test_broken_config_does_not_fire(caplog):
    """⚠️ Sinal OPOSTO ao do caminho que adia.

    Config torta no `preferred_hours` publica agora (marketing não pode travar a
    operação). Aqui ela NÃO dispara: disparo surpresa alcança cliente de verdade, e não
    tem desfazer.
    """
    assert sched.next_occurrence({"type": "once", "at": "isso não é data"}, now=_at(9, 0)) is None
    assert sched.next_occurrence({"type": "recurring", "windows": []}, now=_at(9, 0)) is None
    assert sched.next_occurrence({"type": "recurring"}, now=_at(9, 0)) is None


def test_after_asks_for_the_following_occurrence():
    """É como a vassoura evita rearmar a ocasião que já armou."""
    schedule = {"type": "recurring", "windows": [["17:30", "18:30"]], "weekdays": [0, 1]}
    first = sched.next_occurrence(schedule, now=_at(9, 0))
    second = sched.next_occurrence(schedule, now=_at(9, 0), after=first)

    assert first == _at(17, 30)
    assert second == _at(17, 30, day=11)


# ── Armar (a vassoura) ───────────────────────────────────────────────


def test_arming_creates_a_directive_at_the_exact_moment(template):
    from shopman.orderman.models import Directive

    rule = _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template)

    armed = campaign_service.arm_scheduled(now=_at(17, 0), horizon_minutes=60)

    assert armed == 1
    directive = Directive.objects.get(topic="campaign.occur")
    assert directive.payload["campaign_id"] == rule.pk
    # É o `available_at` que faz a fila esperar o minuto exato.
    assert timezone.localtime(directive.available_at) == _at(17, 30)


def test_arming_ignores_what_is_beyond_the_horizon(template):
    _campaign({"type": "once", "at": _at(23, 0).isoformat()}, template=template)
    assert campaign_service.arm_scheduled(now=_at(9, 0), horizon_minutes=60) == 0


def test_arming_twice_arms_once(template):
    """⚠️ Duplicidade chega ao cliente. Dois ciclos, ou dois workers, armam UMA."""
    from shopman.orderman.models import Directive

    _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template)

    campaign_service.arm_scheduled(now=_at(17, 0), horizon_minutes=60)
    campaign_service.arm_scheduled(now=_at(17, 5), horizon_minutes=60)

    assert Directive.objects.filter(topic="campaign.occur").count() == 1


def test_only_the_schedule_trigger_is_armed(template):
    """Campanha de evento com `once` no schedule não dispara: duas causas, um anúncio."""
    _campaign(
        {"type": "once", "at": _at(17, 30).isoformat()},
        template=template, trigger=Trigger.PRODUCTION_FINISHED,
    )
    assert campaign_service.arm_scheduled(now=_at(17, 0)) == 0


def test_an_inactive_campaign_is_not_armed(template):
    _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template, active=False)
    assert campaign_service.arm_scheduled(now=_at(17, 0)) == 0


# ── Disparar (a fila) ────────────────────────────────────────────────


def test_the_occurrence_creates_the_announcement(template):
    rule = _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template)
    key = campaign_service.occurrence_key(rule, _at(17, 30))

    announcement = campaign_service.create_for_occurrence(rule.pk, key=key)

    assert announcement is not None
    assert announcement.occurrence_key == key
    assert announcement.trigger_context["trigger"] == Trigger.SCHEDULE


def test_the_same_occurrence_creates_only_one_announcement(template):
    """⚠️ O segundo par de olhos do dedupe: retry da fila não manda em dobro."""
    rule = _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template)
    key = campaign_service.occurrence_key(rule, _at(17, 30))

    first = campaign_service.create_for_occurrence(rule.pk, key=key)
    second = campaign_service.create_for_occurrence(rule.pk, key=key)

    assert first is not None
    assert second is None, "repetição é silenciosa, não erro"
    assert Announcement.objects.filter(occurrence_key=key).count() == 1


def test_different_occasions_of_the_same_campaign_coexist(template):
    """O unique é da OCASIÃO, não da campanha: a relâmpago de amanhã também sai."""
    rule = _campaign(
        {"type": "recurring", "windows": [["17:30", "18:30"]], "weekdays": [0, 1]},
        template=template,
    )
    today = campaign_service.occurrence_key(rule, _at(17, 30))
    tomorrow = campaign_service.occurrence_key(rule, _at(17, 30, day=11))

    assert campaign_service.create_for_occurrence(rule.pk, key=today) is not None
    assert campaign_service.create_for_occurrence(rule.pk, key=tomorrow) is not None
    assert Announcement.objects.count() == 2


def test_event_announcements_have_no_occurrence_and_may_repeat(template):
    """Duas fornadas do mesmo pão são dois anúncios legítimos — o unique é PARCIAL."""
    rule = _campaign({}, template=template, trigger=Trigger.PRODUCTION_FINISHED)

    first = campaign_service._create_announcement(rule, {"sku": "PAO"})
    second = campaign_service._create_announcement(rule, {"sku": "PAO"})

    assert first.occurrence_key == ""
    assert second.occurrence_key == ""
    assert Announcement.objects.count() == 2


def test_a_deleted_campaign_does_not_break_the_queue(template):
    rule = _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template)
    key = campaign_service.occurrence_key(rule, _at(17, 30))
    rule.delete()

    assert campaign_service.create_for_occurrence(rule.pk, key=key) is None


def test_the_handler_is_wired_to_the_topic(template):
    """A ponta que fecha o par: a Directive armada tem quem a consuma."""
    from shopman.shop.handlers.campaign import CampaignOccurrenceHandler

    rule = _campaign({"type": "once", "at": _at(17, 30).isoformat()}, template=template)
    key = campaign_service.occurrence_key(rule, _at(17, 30))
    message = type("M", (), {"pk": 1, "payload": {"campaign_id": rule.pk, "occurrence_key": key}})()

    CampaignOccurrenceHandler().handle(message=message, ctx={})

    assert Announcement.objects.filter(occurrence_key=key).exists()


def test_the_handler_survives_a_broken_payload():
    from shopman.shop.handlers.campaign import CampaignOccurrenceHandler

    message = type("M", (), {"pk": 1, "payload": {}})()
    CampaignOccurrenceHandler().handle(message=message, ctx={})  # não explode

    assert Announcement.objects.count() == 0


# ── A combinação impossível ──────────────────────────────────────────


def test_schedule_trigger_without_a_firing_schedule_is_refused(template):
    """⚠️ O erro que salvava limpo e nunca disparava.

    Gatilho "agendado" quer dizer "não há evento, o relógio é a causa". Com um
    agendamento que só adia, não existe causa nenhuma — e a campanha aparecia ATIVA na
    lista sem nunca produzir anúncio.
    """
    from django.core.exceptions import ValidationError

    rule = _campaign({"type": "immediate"}, template=template)
    with pytest.raises(ValidationError) as exc:
        rule.full_clean()
    assert "schedule" in exc.value.message_dict

    empty = _campaign({}, template=template)
    with pytest.raises(ValidationError) as exc:
        empty.full_clean()
    assert "schedule" in exc.value.message_dict


def test_a_firing_schedule_on_an_event_trigger_is_refused(template):
    """O inverso: `once` num gatilho de evento seria ignorado em silêncio."""
    from django.core.exceptions import ValidationError

    rule = _campaign(
        {"type": "once", "at": _at(17, 30).isoformat()},
        template=template, trigger=Trigger.PRODUCTION_FINISHED,
    )
    with pytest.raises(ValidationError) as exc:
        rule.full_clean()
    assert "trigger" in exc.value.message_dict


def test_a_schedule_with_no_next_occasion_is_refused(template):
    """Data no passado, período encerrado ou config torta: recusa na hora de salvar."""
    from django.core.exceptions import ValidationError

    past = _campaign({"type": "once", "at": "2020-01-01T07:00:00-03:00"}, template=template)
    with pytest.raises(ValidationError) as exc:
        past.full_clean()
    assert "schedule" in exc.value.message_dict

    broken = _campaign({"type": "recurring", "windows": []}, template=template)
    with pytest.raises(ValidationError):
        broken.full_clean()


def test_a_valid_pairing_passes(template):
    rule = _campaign({"type": "recurring", "windows": [["17:30", "18:30"]]}, template=template)
    rule.full_clean()  # não levanta

    deferring = _campaign(
        {"type": "preferred_hours", "windows": [["07:00", "11:00"]]},
        template=template, trigger=Trigger.PRODUCTION_FINISHED,
    )
    deferring.full_clean()
