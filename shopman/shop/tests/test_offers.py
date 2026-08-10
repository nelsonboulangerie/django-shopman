"""A oferta anunciada, resolvida no CLIQUE.

O que este arquivo protege é **quando** cada pergunta é respondida. Se a sacola fosse
montada no envio, o preço envelheceria enquanto a mensagem dorme no WhatsApp, o estoque
ficaria segurado para quem nunca clicou, e haveria uma `Session` órfã por destinatário.

Os dois testes que mais importam são `test_the_price_is_the_price_of_the_click` e
`test_an_offer_without_named_skus_has_no_bag`: o primeiro é a razão de o módulo existir; o
segundo impede o botão que promete montar sacola e não monta nada.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.models import Promotion
from shopman.shop.services import offers

pytestmark = pytest.mark.django_db


@pytest.fixture
def croissant():
    return Product.objects.create(
        sku="CRO-001", name="Croissant", base_price_q=1200,
        is_published=True, is_sellable=True
    )


@pytest.fixture
def pao():
    return Product.objects.create(
        sku="PAO-001", name="Pão francês", base_price_q=100,
        is_published=True, is_sellable=True
    )


def _promotion(**over) -> Promotion:
    now = timezone.now()
    defaults = {
        "ref": "relampago-17h30",
        "name": "Relâmpago das 17h30",
        "type": Promotion.PERCENT,
        "value": 20,
        "valid_from": now - timedelta(hours=1),
        "valid_until": now + timedelta(hours=1),
        "skus": ["CRO-001"],
        "is_active": True,
    }
    return Promotion.objects.create(**{**defaults, **over})


class _Cart:
    """Sacola de teste que registra o que recebeu — inclusive o preço."""

    def __init__(self, *, refuse: set[str] | None = None):
        self.items: list[dict] = []
        self.refuse = refuse or set()

    def add_item(self, request, *, sku, qty, unit_price_q, name, is_d1):
        if sku in self.refuse:
            raise RuntimeError("estoque recusou")
        self.items.append({"sku": sku, "qty": qty, "unit_price_q": unit_price_q, "name": name})


# ── Achar a oferta ───────────────────────────────────────────────────


def test_a_live_offer_is_found(croissant):
    promotion = _promotion()
    assert offers.get_offer("relampago-17h30", channel_ref="").pk == promotion.pk


def test_an_unknown_offer_says_it_is_gone():
    with pytest.raises(offers.OfferUnavailable):
        offers.get_offer("nunca-existiu")


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"is_active": False}, "encerrada"),
        ({"valid_from": timezone.now() + timedelta(hours=2),
          "valid_until": timezone.now() + timedelta(hours=3)}, "começou"),
        ({"valid_from": timezone.now() - timedelta(hours=3),
          "valid_until": timezone.now() - timedelta(hours=2)}, "terminou"),
    ],
)
def test_a_dead_offer_says_which_kind_of_dead(over, expected):
    """⚠️ Validade é conferida no clique, não no envio.

    A mensagem dorme horas: uma relâmpago que venceu nesse meio-tempo não pode montar
    sacola. E o texto diz QUAL caso é, porque "não deu" não ajuda quem clicou.
    """
    _promotion(**over)

    with pytest.raises(offers.OfferUnavailable) as exc:
        offers.get_offer("relampago-17h30", channel_ref="")

    assert expected in str(exc.value)


def test_an_offer_from_another_channel_does_not_apply(croissant):
    from shopman.shop.models import Channel

    promotion = _promotion()
    other = Channel.objects.create(ref="ifood", name="iFood")
    promotion.channels.add(other)

    with pytest.raises(offers.OfferUnavailable):
        offers.get_offer("relampago-17h30", channel_ref="web")


def test_an_offer_with_no_channels_applies_everywhere(croissant):
    """M2M vazio = vale em todos, mesma semântica de `RuleConfig.channels`."""
    _promotion()
    assert offers.get_offer("relampago-17h30", channel_ref="web") is not None


# ── O que a oferta consegue montar ───────────────────────────────────


def test_the_named_skus_become_the_bag(croissant, pao):
    promotion = _promotion(skus=["CRO-001", "PAO-001"])
    assert offers.offer_skus(promotion) == ("CRO-001", "PAO-001")


def test_an_offer_without_named_skus_has_no_bag(croissant):
    """⚠️ `skus` vazio quer dizer "vale para tudo", e não existe sacola de "tudo".

    Sem esta distinção, o botão "montar sacola" apareceria numa oferta que não nomeia
    nada e não montaria nada — pior que botão nenhum.
    """
    promotion = _promotion(skus=[], collections=[])
    assert offers.offer_skus(promotion) == ()


def test_a_collection_offer_finds_its_products(croissant, pao):
    from shopman.offerman.models import Collection, CollectionItem

    collection = Collection.objects.create(ref="paes", name="Pães")
    CollectionItem.objects.create(collection=collection, product=pao, sort_order=1)
    CollectionItem.objects.create(collection=collection, product=croissant, sort_order=2)

    promotion = _promotion(skus=[], collections=["paes"])

    assert offers.offer_skus(promotion) == ("PAO-001", "CRO-001")


def test_named_skus_win_over_collections(croissant, pao):
    """Quem nomeou o SKU foi explícito; a coleção é o caminho mais largo."""
    from shopman.offerman.models import Collection, CollectionItem

    collection = Collection.objects.create(ref="paes", name="Pães")
    CollectionItem.objects.create(collection=collection, product=pao)

    promotion = _promotion(skus=["CRO-001"], collections=["paes"])

    assert offers.offer_skus(promotion) == ("CRO-001",)


# ── Montar (o clique) ────────────────────────────────────────────────


def test_the_price_is_the_price_of_the_click(croissant):
    """⚠️ A razão de este módulo existir.

    O preço entra na sacola resolvido AGORA. Se ele fosse congelado no envio, uma
    mensagem que dormiu a noite chegaria com o preço de ontem — e a padaria honraria um
    valor que não é mais o dela, ou desmentiria a própria mensagem no checkout.
    """
    promotion = _promotion()
    croissant.base_price_q = 1500
    croissant.save()
    cart = _Cart()

    result = offers.add_offer_items(None, promotion, cart_service=cart, channel_ref="web")

    assert result.added == ("CRO-001",)
    assert cart.items[0]["unit_price_q"] == 1500


def test_what_is_not_sellable_is_reported_not_hidden(croissant):
    promotion = _promotion(skus=["CRO-001", "FANTASMA"])
    cart = _Cart()

    result = offers.add_offer_items(None, promotion, cart_service=cart, channel_ref="web")

    assert result.added == ("CRO-001",)
    assert result.skipped == ("FANTASMA",)


def test_what_stock_refuses_is_reported_not_hidden(croissant, pao):
    """Sacola parcial explicada é melhor que erro na cara de quem clicou num anúncio."""
    promotion = _promotion(skus=["CRO-001", "PAO-001"])
    cart = _Cart(refuse={"PAO-001"})

    result = offers.add_offer_items(None, promotion, cart_service=cart, channel_ref="web")

    assert result.added == ("CRO-001",)
    assert result.skipped == ("Pão francês",)
    assert result.assembled is True


def test_an_offer_that_assembles_nothing_says_so(croissant):
    promotion = _promotion(skus=["CRO-001"])
    cart = _Cart(refuse={"CRO-001"})

    result = offers.add_offer_items(None, promotion, cart_service=cart, channel_ref="web")

    assert result.added == ()
    assert result.assembled is False


# ── A Action que a campanha emite ────────────────────────────────────


def test_the_action_follows_the_reorder_contract():
    """Mesmo contrato do `reorder` porque é a mesma natureza de gesto (ADR-012)."""
    action = offers.offer_action("relampago-17h30")

    assert action["kind"] == "mutation"
    assert action["method"] == "POST"
    assert action["href"] == "/api/v1/offers/relampago-17h30/claim/"
    assert action["idempotency"] == "required"


def test_the_action_href_is_never_an_access_link():
    """⚠️ `AccessLink` expira em 5 min e é single-use: morreria antes do clique.

    E esticar esse prazo para campanha espalharia links de concessão de sessão, de vida
    longa, em históricos de conversa que são encaminhados e printados.
    """
    action = offers.offer_action("relampago-17h30")
    assert "acesso" not in action["href"]
    assert "token" not in action["href"]


# ── O anúncio aponta para a oferta ───────────────────────────────────


def test_an_announcement_of_an_offer_links_to_the_offer(croissant):
    from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger
    from shopman.shop.services import campaign as campaign_service

    _promotion()
    template = AnnouncementTemplate.objects.create(name="Relâmpago", body="{{link}}")
    rule = Campaign.objects.create(
        name="Relâmpago", trigger=Trigger.MANUAL, template=template,
        platforms=["whatsapp"], promotion_ref="relampago-17h30",
    )

    announcement = campaign_service._create_announcement(rule, {"sku": "CRO-001"})

    assert "/oferta/relampago-17h30" in announcement.content["link"]
    assert announcement.content["actions"][0]["ref"] == "claim_offer"


def test_an_announcement_without_an_offer_keeps_linking_to_the_product(croissant):
    """Campanha sem oferta atrás não ganha Action nenhuma — nem link de oferta."""
    from shopman.shop.models import AnnouncementTemplate, Campaign, Trigger
    from shopman.shop.services import campaign as campaign_service

    template = AnnouncementTemplate.objects.create(name="Fornada", body="{{link}}")
    rule = Campaign.objects.create(
        name="Fornada", trigger=Trigger.PRODUCTION_FINISHED, template=template,
        platforms=["whatsapp"],
    )

    announcement = campaign_service._create_announcement(rule, {"sku": "CRO-001"})

    assert "/oferta/" not in announcement.content["link"]
    assert "actions" not in announcement.content
