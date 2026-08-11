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
    # Promoções primeiro: a campanha agendada anuncia uma oferta, e sem elas a
    # verificação de `promotion_ref` não teria como ser feita.
    command._seed_promotions()
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


def test_the_announced_offer_exists_and_assembles_a_bag(seeded):
    """⚠️ `promotion_ref` é SlugField solto — nada no banco impede apontar para o vazio.

    Uma campanha que anuncia oferta inexistente produz mensagem com link que responde
    404, e o gestor só descobre pelo cliente reclamando. E oferta que não nomeia item
    nenhum daria um "quero esta oferta" que não monta sacola nenhuma.
    """
    from config.management.commands.seed import Command
    from shopman.shop.services import offers as offer_service

    announced = [c for c in seeded if c.promotion_ref]
    assert announced, "o seed precisa exercitar a oferta acionável em staging"

    # O catálogo entra aqui e não no fixture: a pergunta deste teste é justamente se a
    # oferta anunciada encontra produto NO catálogo que o seed monta. Sem ele, o teste
    # passaria a medir a própria fixture.
    catalog = Command()
    catalog.stdout = StringIO()
    catalog._seed_catalog()

    for campaign in announced:
        promotion = offer_service.get_offer(campaign.promotion_ref, channel_ref="")
        assert offer_service.offer_skus(promotion), campaign.promotion_ref


# ── O público comportamental precisa de dado atrás ───────────────────


def test_the_seeded_history_is_attributable_to_customers(db):
    """⚠️ O defeito que zerava o Marketing inteiro, calado.

    O histórico do cliente filtra por `data__customer_ref`
    (`CustomerOrderHistoryService._base_queryset`). O seed criava os pedidos com o cliente EM
    MÃO e não gravava o elo: todo `CustomerInsight` nascia vazio, RFM dizia "lost" para
    todos, e campeões/em-risco/recompra resolviam ZERO. Uma campanha alcançaria ninguém e
    ninguém saberia por quê.
    """
    from io import StringIO

    from shopman.orderman.models import Order

    from config.management.commands.seed import Command

    command = Command()
    command.stdout = StringIO()
    command._seed_shop()
    products = command._seed_catalog()
    customers = command._seed_customers()
    channels = command._seed_channels()
    command._seed_orders(products, customers, channels)

    total = Order.objects.count()
    attributable = (
        Order.objects.exclude(data__customer_ref=None)
        .exclude(data__customer_ref="")
        .count()
    )

    assert total > 0, "o seed precisa criar pedidos"
    assert attributable > 0, "nenhum pedido atribuível: o público comportamental resolve zero"
    # A maioria do histórico é de cliente conhecido; o resto é balcão anônimo, legítimo.
    assert attributable > total // 2, f"só {attributable} de {total} atribuíveis"


def test_the_seeded_history_produces_favorites(db):
    """Favorito e recompra saem de `snapshot["items"]` — sem eles, zero calado."""
    from io import StringIO

    from shopman.guestman.contrib.insights import InsightService
    from shopman.guestman.contrib.insights.models import CustomerInsight

    from config.management.commands.seed import Command

    command = Command()
    command.stdout = StringIO()
    command._seed_shop()
    products = command._seed_catalog()
    customers = command._seed_customers()
    command._seed_orders(products, customers, command._seed_channels())
    InsightService.recalculate_all()

    with_history = [i for i in CustomerInsight.objects.all() if i.total_orders]
    assert with_history, "nenhum insight viu pedido: o elo com o cliente quebrou"
    assert any(i.favorite_products for i in with_history), (
        "nenhum favorito derivado: `snapshot['items']` está vazio"
    )


def test_the_order_snapshot_carries_items(db):
    """⚠️ `snapshot["items"]` é o que vira favorito e recompra.

    Em produção quem grava é o `CommitService`; o seed cria `Order` direto. Sem os itens no
    snapshot, `favorite_products` nasce vazio e "comprou nos últimos N dias" resolve zero.

    E o snapshot é campo SELADO: tem de ir na criação, porque o orderman levanta
    `ImmutabilityError` em escrita posterior — e está certo em levantar.
    """
    from shopman.orderman.exceptions import ImmutabilityError
    from shopman.orderman.models import Order

    order = Order.objects.create(
        ref="SNAP-1", channel_ref="web", session_key="k", status="new", total_q=100,
        snapshot={"items": [{"sku": "PAO", "qty": 1}]},
    )
    assert order.snapshot["items"][0]["sku"] == "PAO"

    order.snapshot = {"items": []}
    with pytest.raises(ImmutabilityError):
        order.save(update_fields=["snapshot"])
