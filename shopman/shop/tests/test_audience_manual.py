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
from shopman.guestman.models import Customer, CustomerGroup
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.services import audience

pytestmark = pytest.mark.django_db


def _customer(phone: str, *, ref: str = "", group=None, birthday=None, opted_in: bool = True):
    customer = Customer.objects.create(
        ref=ref or f"CLI-{phone[-4:]}",
        first_name="Ana",
        phone=phone,
        group=group,
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


# ── grupo ────────────────────────────────────────────────────────────


def test_group_audience(db):
    corp = CustomerGroup.objects.create(ref="corporativo", name="Corporativo")
    varejo = CustomerGroup.objects.create(ref="varejo", name="Varejo")
    inside = _customer("+5543999990003", ref="CLI-C", group=corp)
    _customer("+5543999990004", ref="CLI-D", group=varejo)

    result = audience.resolve({"groups": ["corporativo"]})
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
    corp = CustomerGroup.objects.create(ref="corporativo", name="Corporativo")
    person = _customer("+5543999990018", ref="CLI-R", group=corp)
    _insight(person, rfm_segment="champion")

    result = audience.resolve(
        {"customer_refs": ["CLI-R"], "groups": ["corporativo"], "rfm_segments": ["champion"]}
    )
    assert result.total == 1
    assert {"chosen", "groups", "rfm"} <= result.general[0].reasons


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
