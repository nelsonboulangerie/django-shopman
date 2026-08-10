"""As campanhas do seed passam pela própria validação — e uma delas dispara sozinha.

Dois motivos para existir:

1. **Feature sem exemplo é feature invisível.** Staging nasceria sem nenhuma campanha
   agendada, e ninguém descobre o recurso lendo o model. Foi o mesmo furo do disparo
   manual: o código existia e a tela não tinha o que mostrar.
2. **O seed não passa por formulário**, então `update_or_create` **não** chama `clean()`.
   Sem este teste, o dia em que alguém copiar uma campanha e trocar o gatilho, o seed
   passa a plantar em staging exatamente a campanha que nunca dispara.
"""

from __future__ import annotations

from io import StringIO

import pytest

from shopman.shop.models import Campaign, Trigger
from shopman.shop.services import campaign_schedule as sched

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    from config.management.commands.seed import Command

    command = Command()
    command.stdout = StringIO()
    command._seed_campaigns()
    return Campaign.objects.all()


def test_every_seeded_campaign_survives_its_own_validation(seeded):
    """⚠️ O guarda que o `update_or_create` não dá de graça."""
    for campaign in seeded:
        campaign.full_clean()  # levanta se o par gatilho×agendamento for impossível


def test_the_seed_ships_a_campaign_that_fires_on_its_own(seeded):
    firing = [c for c in seeded if c.trigger == Trigger.SCHEDULE]
    assert firing, "sem exemplo agendado, o recurso não aparece em staging"

    for campaign in firing:
        assert sched.fires_on_its_own(campaign.schedule)
        assert sched.next_occurrence(campaign.schedule) is not None, campaign.name


def test_the_scheduled_campaign_still_asks_for_review(seeded):
    """Relógio decide QUANDO; o gestor decide o quê e para quem. Nada sai sozinho."""
    for campaign in seeded:
        if campaign.trigger == Trigger.SCHEDULE:
            assert campaign.requires_approval is True
            assert campaign.expires_after_minutes > 0, "relâmpago não revisado caduca"
