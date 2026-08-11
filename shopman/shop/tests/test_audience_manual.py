"""Disparo manual: o gestor decide agora, e escolhe para quem.

Campanha manual não tem evento nem SKU — daí `resolve(rules, *, sku="")`. Os públicos
novos são **irmãos** dos de evento: devolvem `Recipient`, passam pelo mesmo `_merge` e
pelo mesmo filtro de consentimento. Nenhum model novo: `CustomerInsight` já é o motor de
segmentação, e um segundo seria o terceiro dono de um fato que já tem dois.

O teste que guarda a fronteira é `test_consent_still_rules_every_manual_audience`: o
consentimento não é um dos públicos, é a lei acima de todos eles. Escolher um cliente na
tela não é permissão dele para receber.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.guestman import ConsentService
from shopman.guestman.contrib.insights.models import CustomerInsight
from shopman.guestman.models import Customer, PriceTier
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.services import audience

pytestmark = pytest.mark.django_db


def _customer(phone: str, *, ref: str = "", price_tier=None, birthday=None, opted_in: bool = True):
    customer = Customer.objects.create(
        ref=ref or f"CLI-{phone[-4:]}",
        first_name="Ana",
        phone=phone,
        price_tier=price_tier,
        birthday=birthday,
    )
    if opted_in:
        ConsentService.grant_consent(
            customer.ref, audience.DELIVERY_CONSENT_CHANNEL, source="test"
        )
    return customer


def _insight(customer, **kwargs):
    return CustomerInsight.objects.create(customer=customer, **kwargs)


# ── "estes clientes" ─────────────────────────────────────────────────


def test_chosen_customers_are_reached(db):
    chosen = _customer("+5543999990001", ref="CLI-A")
    _customer("+5543999990002", ref="CLI-B")

    result = audience.resolve({"customer_refs": ["CLI-A"]})
    assert [r.phone for r in result.general] == [chosen.phone]


def test_choosing_a_customer_without_a_phone_reaches_nobody(db):
    Customer.objects.create(ref="CLI-SEM", first_name="Sem", phone="")
    assert audience.resolve({"customer_refs": ["CLI-SEM"]}).total == 0


# ── faixa de preço ────────────────────────────────────────────────────────────


def test_price_tier_audience(db):
    corp = PriceTier.objects.create(ref="corporativo", name="Corporativo")
    varejo = PriceTier.objects.create(ref="varejo", name="Varejo")
    inside = _customer("+5543999990003", ref="CLI-C", price_tier=corp)
    _customer("+5543999990004", ref="CLI-D", price_tier=varejo)

    result = audience.resolve({"price_tiers": ["corporativo"]})
    assert [r.phone for r in result.general] == [inside.phone]


# ── segmento RFM ─────────────────────────────────────────────────────


def test_rfm_segment_audience(db):
    champion = _customer("+5543999990005", ref="CLI-E")
    _insight(champion, rfm_segment="champion")
    sleeping = _customer("+5543999990006", ref="CLI-F")
    _insight(sleeping, rfm_segment="hibernating")

    result = audience.resolve({"rfm_segments": ["champion", "loyal_customer"]})
    assert [r.phone for r in result.general] == [champion.phone]


# ── risco de evasão (win-back) ───────────────────────────────────────


def test_churn_risk_floor_selects_only_above_it(db):
    at_risk = _customer("+5543999990007", ref="CLI-G")
    _insight(at_risk, churn_risk=Decimal("0.85"))
    healthy = _customer("+5543999990008", ref="CLI-H")
    _insight(healthy, churn_risk=Decimal("0.20"))

    result = audience.resolve({"churn_risk_min": 0.7})
    assert [r.phone for r in result.general] == [at_risk.phone]


def test_a_broken_churn_floor_reaches_nobody_instead_of_exploding(db):
    at_risk = _customer("+5543999990007", ref="CLI-G")
    _insight(at_risk, churn_risk=Decimal("0.85"))

    assert audience.resolve({"churn_risk_min": "muito"}).total == 0


# ── aniversariantes ──────────────────────────────────────────────────


def test_birthday_today_ignores_the_year(db):
    today = timezone.localdate()
    birthday_person = _customer(
        "+5543999990009", ref="CLI-I", birthday=today.replace(year=today.year - 30)
    )
    _customer("+5543999990010", ref="CLI-J", birthday=today + timedelta(days=1))

    result = audience.resolve({"birthday_today": True})
    assert [r.phone for r in result.general] == [birthday_person.phone]


def test_customer_without_a_birthday_is_never_a_birthday_audience(db):
    _customer("+5543999990011", ref="CLI-K", birthday=None)
    assert audience.resolve({"birthday_today": True}).total == 0


# ── quem comprou o quê (interesse genuíno) ───────────────────────────


def _bought(customer, sku: str, *, days_ago: int):
    last = timezone.localdate() - timedelta(days=days_ago)
    _insight(
        customer,
        favorite_products=[
            {"sku": sku, "name": sku, "qty": "3", "last_order_at": last.isoformat()}
        ],
    )


def test_bought_skus_chosen_by_the_manager(db):
    buyer = _customer("+5543999990012", ref="CLI-L")
    _bought(buyer, "CROISSANT", days_ago=5)
    other = _customer("+5543999990013", ref="CLI-M")
    _bought(other, "BAGUETE", days_ago=5)

    result = audience.resolve({"bought_skus": ["CROISSANT"], "bought_within_days": 30})
    assert [r.phone for r in result.general] == [buyer.phone]


def test_bought_respects_the_window(db):
    cold = _customer("+5543999990014", ref="CLI-N")
    _bought(cold, "CROISSANT", days_ago=200)

    assert audience.resolve({"bought_skus": ["CROISSANT"], "bought_within_days": 30}).total == 0


def test_bought_collections_resolve_through_offerman(db):
    """Coleção é REGRA, não lista — resolver pelo offerman é o que faz a inteligente valer."""
    coll = Collection.objects.create(ref="finos", name="Finos", is_active=True)
    croissant = Product.objects.create(
        sku="CROISSANT", name="Croissant", base_price_q=900, is_published=True, is_sellable=True
    )
    CollectionItem.objects.create(collection=coll, product=croissant)

    buyer = _customer("+5543999990015", ref="CLI-O")
    _bought(buyer, "CROISSANT", days_ago=3)

    result = audience.resolve({"bought_collections": ["finos"], "bought_within_days": 30})
    assert [r.phone for r in result.general] == [buyer.phone]


def test_bought_without_a_window_reaches_nobody(db):
    """Sem janela não há pergunta: "comprou" sem "quando" seria a base toda."""
    buyer = _customer("+5543999990016", ref="CLI-P")
    _bought(buyer, "CROISSANT", days_ago=3)

    assert audience.resolve({"bought_skus": ["CROISSANT"]}).total == 0


# ── as leis que valem para todos ─────────────────────────────────────


def test_consent_still_rules_every_manual_audience(db):
    """Escolher alguém na tela não é permissão dele. O consentimento está acima.

    É a razão de o disparo manual não ser um caminho paralelo: ele passa pelo mesmo
    `_filter_opted_in` que o disparo por evento.
    """
    _customer("+5543999990017", ref="CLI-Q", opted_in=False)
    assert audience.resolve({"customer_refs": ["CLI-Q"]}).total == 0


def test_the_same_person_in_two_audiences_is_one_recipient(db):
    """Dedupe por telefone: o gestor combina públicos sem disparar em dobro."""
    corp = PriceTier.objects.create(ref="corporativo", name="Corporativo")
    person = _customer("+5543999990018", ref="CLI-R", price_tier=corp)
    _insight(person, rfm_segment="champion")

    result = audience.resolve(
        {"customer_refs": ["CLI-R"], "price_tiers": ["corporativo"], "rfm_segments": ["champion"]}
    )
    assert result.total == 1
    assert {"chosen", "price_tiers", "rfm"} <= result.general[0].reasons


def test_no_rules_reaches_nobody(db):
    """Campanha sem público não é campanha para todos — é campanha para ninguém."""
    _customer("+5543999990019", ref="CLI-S")
    assert audience.resolve({}).total == 0


def test_event_rules_are_inert_without_a_sku(db):
    """Regra de evento numa campanha manual não explode: fica inerte."""
    _customer("+5543999990020", ref="CLI-T")
    assert audience.resolve({"favorites": True, "alerts": True}).total == 0


def test_manual_audience_still_splits_into_waves(db):
    """VIP primeiro vale no manual também — é política de entrega, não de público."""
    champion = _customer("+5543999990021", ref="CLI-U")
    _insight(champion, rfm_segment="champion")
    _customer("+5543999990022", ref="CLI-V")  # não-VIP, para a onda geral existir

    result = audience.resolve(
        {"customer_refs": ["CLI-U", "CLI-V"], "vip_first_minutes": 15}
    )
    assert {w.key: w.delay_minutes for w in result.waves()} == {"vip": 0, "general": 15}


# ── O público escolhido tem de sobreviver até o ENVIO ────────────────
#
# ⚠️ Aqui vivia um defeito da F8. O handler de envio re-resolve a audiência na hora de
# despachar — de propósito, porque entre criar e aprovar os favoritos e alertas mudam.
# Só que ele relia `announcement.rule.audience_rules`, a campanha SALVA. Num disparo
# manual com público escolhido, o anúncio prometia N pessoas na tela e enviava para as
# da campanha (em geral zero).
#
# O resumo mentia sozinho: `audience.total` dizia 3 e o envio alcançava 0, sem erro
# nenhum. Estes testes amarram as duas pontas.


def test_the_chosen_audience_survives_to_dispatch(db):
    from shopman.shop.models import Announcement, AnnouncementTemplate, Campaign, Trigger
    from shopman.shop.services import campaign as campaign_service

    tier = PriceTier.objects.create(ref="corporativo", name="Corporativo")
    _customer("+5543999990031", ref="CLI-W1", price_tier=tier)
    _customer("+5543999990032", ref="CLI-W2", price_tier=tier)

    template = AnnouncementTemplate.objects.create(name="Recado", body="Um recado.")
    rule = Campaign.objects.create(
        name="Recado", trigger=Trigger.MANUAL, template=template,
        platforms=["whatsapp"], audience_rules={},  # a campanha NÃO tem público
    )

    announcement = campaign_service.fire_now(
        rule.pk, audience_rules={"price_tiers": ["corporativo"]}
    )

    # O que a tela promete.
    assert announcement.audience["total"] == 2

    # O que o handler vai usar — lendo do banco, como ele lê.
    fresh = Announcement.objects.get(pk=announcement.pk)
    chosen = (fresh.trigger_context or {}).get("audience_rules")
    assert chosen == {"price_tiers": ["corporativo"]}, "a escolha tem de viajar com o anúncio"
    assert audience.resolve(chosen).total == 2, "o envio tem de alcançar o que foi prometido"

    # E a campanha salva continua sem público.
    rule.refresh_from_db()
    assert rule.audience_rules == {}


def test_without_a_choice_the_campaign_audience_still_rules(db):
    """Disparo manual sem escolha usa o público da campanha — nada muda para ele."""
    from shopman.shop.models import Announcement, AnnouncementTemplate, Campaign, Trigger
    from shopman.shop.services import campaign as campaign_service

    tier = PriceTier.objects.create(ref="corporativo", name="Corporativo")
    _customer("+5543999990033", ref="CLI-W3", price_tier=tier)

    template = AnnouncementTemplate.objects.create(name="Recado", body="Um recado.")
    rule = Campaign.objects.create(
        name="Recado", trigger=Trigger.MANUAL, template=template,
        platforms=["whatsapp"], audience_rules={"price_tiers": ["corporativo"]},
    )

    announcement = campaign_service.fire_now(rule.pk)

    fresh = Announcement.objects.get(pk=announcement.pk)
    assert "audience_rules" not in (fresh.trigger_context or {})
    assert announcement.audience["total"] == 1


# ── Combinação: somar (união) vs cruzar (interseção) ─────────────────
#
# ⚠️ A união era o ÚNICO comportamento, e ela não sabe dizer "leais QUE são atacado":
# pedir as duas coisas devolvia a soma das duas. Recorte é o que faz a campanha valer a
# pena — sem interseção, toda regra somada só engordava a lista e o custo.


def _loyal_wholesaler_and_friends():
    """Três pessoas: uma fiel-e-atacado, uma só fiel, uma só atacado."""
    atacado = PriceTier.objects.create(ref="atacado", name="Atacado")
    both = _customer("+5543999991001", ref="CLI-BOTH", price_tier=atacado)
    only_loyal = _customer("+5543999991002", ref="CLI-LOYAL")
    only_wholesale = _customer("+5543999991003", ref="CLI-WHOLE", price_tier=atacado)
    _insight(both, rfm_segment="loyal_customer")
    _insight(only_loyal, rfm_segment="loyal_customer")
    _insight(only_wholesale, rfm_segment="at_risk")
    return both, only_loyal, only_wholesale


def test_by_default_rules_add_up(db):
    """O padrão continua sendo a união — nada muda para quem já configurou campanha."""
    both, only_loyal, only_wholesale = _loyal_wholesaler_and_friends()

    result = audience.resolve({"rfm_segments": ["loyal_customer"], "price_tiers": ["atacado"]})

    assert {r.phone for r in result.general} == {
        both.phone, only_loyal.phone, only_wholesale.phone
    }
    assert result.match == audience.MATCH_ANY


def test_match_all_intersects_instead_of_adding(db):
    """"leais QUE são atacado" — o recorte que não existia."""
    both, only_loyal, only_wholesale = _loyal_wholesaler_and_friends()

    result = audience.resolve({
        "rfm_segments": ["loyal_customer"],
        "price_tiers": ["atacado"],
        "match": audience.MATCH_ALL,
    })

    assert [r.phone for r in result.general] == [both.phone]
    assert only_loyal.phone not in {r.phone for r in result.general}
    assert only_wholesale.phone not in {r.phone for r in result.general}


def test_the_summary_tells_the_whole_story(db):
    """"leais 2, atacado 2, total 1" — sem o `match`, um "1" é indecifrável depois."""
    _loyal_wholesaler_and_friends()

    summary = audience.resolve({
        "rfm_segments": ["loyal_customer"],
        "price_tiers": ["atacado"],
        "match": audience.MATCH_ALL,
    }).summary()

    assert summary["match"] == audience.MATCH_ALL
    # As contagens por regra são de ANTES do cruzamento, de propósito.
    assert summary["rfm_count"] == 2
    assert summary["price_tiers_count"] == 2
    assert summary["total"] == 1


def test_a_single_rule_intersects_with_nothing(db):
    """Uma regra só: cruzar e somar dão o mesmo, e nenhum dos dois pode zerar."""
    both, only_loyal, _ = _loyal_wholesaler_and_friends()

    result = audience.resolve({
        "rfm_segments": ["loyal_customer"], "match": audience.MATCH_ALL,
    })

    assert {r.phone for r in result.general} == {both.phone, only_loyal.phone}


def test_a_rule_that_could_not_run_is_not_a_requirement(db):
    """⚠️ Regra de evento sem SKU não vira exigência — senão o manual zerava calado.

    `favorites` e `alerts` precisam do SKU do evento. No disparo manual não há SKU, então
    elas não rodam. Se "pedida" contasse como "exigida", cruzar num disparo manual
    devolveria zero sempre, e o gestor leria isso como "não tem ninguém".
    """
    both, _, _ = _loyal_wholesaler_and_friends()

    result = audience.resolve({
        "rfm_segments": ["loyal_customer"],
        "price_tiers": ["atacado"],
        "favorites": True,   # não roda: sem SKU
        "alerts": True,      # idem
        "match": audience.MATCH_ALL,
    })

    assert [r.phone for r in result.general] == [both.phone]


def test_intersecting_disjoint_rules_reaches_nobody(db):
    """Cruzar coisas que não se cruzam devolve zero — e isso é a resposta certa."""
    _loyal_wholesaler_and_friends()

    result = audience.resolve({
        "rfm_segments": ["champion"],  # ninguém é champion aqui
        "price_tiers": ["atacado"],
        "match": audience.MATCH_ALL,
    })

    assert result.total == 0


def test_consent_still_rules_when_intersecting(db):
    """A interseção estreita ANTES do consentimento, e o consentimento continua lei."""
    atacado = PriceTier.objects.create(ref="atacado", name="Atacado")
    silent = _customer("+5543999992001", ref="CLI-MUDO", price_tier=atacado, opted_in=False)
    _insight(silent, rfm_segment="loyal_customer")

    result = audience.resolve({
        "rfm_segments": ["loyal_customer"],
        "price_tiers": ["atacado"],
        "match": audience.MATCH_ALL,
    })

    assert result.total == 0


def test_an_unknown_match_mode_falls_back_to_adding(db):
    """Valor errado alarga (visível na contagem), nunca estreita (viraria "0" calado)."""
    both, only_loyal, only_wholesale = _loyal_wholesaler_and_friends()

    result = audience.resolve({
        "rfm_segments": ["loyal_customer"],
        "price_tiers": ["atacado"],
        "match": "todos",  # não existe
    })

    assert result.total == 3
    assert result.match == audience.MATCH_ANY


def test_the_campaign_refuses_an_unknown_match_mode(db):
    """E o model recusa na entrada, para o erro não chegar calado até o disparo."""
    from django.core.exceptions import ValidationError

    from shopman.shop.models.campaign import Campaign

    # `clean()` direto, e não `full_clean()`: o alvo aqui é a regra de combinação, não o
    # `template` obrigatório — e é `clean()` que o admin e o serializer acabam chamando.
    campaign = Campaign(name="Cruza errado", audience_rules={"price_tiers": ["atacado"], "match": "E"})
    with pytest.raises(ValidationError) as err:
        campaign.clean()
    assert "audience_rules" in err.value.message_dict
