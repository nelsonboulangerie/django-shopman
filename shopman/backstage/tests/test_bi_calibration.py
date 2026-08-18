"""Os dois comandos que preparam a curadoria e a calibração (F2 + F3).

O que estes testes guardam:

- a proposta **nunca se passa por curadoria** (`reviewed=False`), porque o nome
  do produto engana e número sobre palpite não pode parecer conferido;
- o que o mapa não alcança sai **listado**, nunca chutado;
- as variantes do `bi_calibrate` **remapeiam a leitura**, sem regra alternativa —
  duas regras seriam duas verdades a manter.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.models import (
    ConsumptionRole,
    HistoricalSale,
    HistoricalSaleItem,
    ProductConsumptionTag,
    Reading,
)


@pytest.fixture
def roles(db):
    return {
        reading: ConsumptionRole.objects.create(ref=ref, label=label, reading=reading)
        for ref, label, reading in [
            ("consome-aqui", "Consome aqui", Reading.ANCHOR),
            ("leva", "Leva", Reading.TAKEAWAY),
            ("hibrido", "Híbrido", Reading.HYBRID),
        ]
    }


@pytest.fixture
def catalog(db):
    """Um cardápio mínimo com as coleções que o proponente conhece."""
    from shopman.offerman.models import Collection, CollectionItem, Product

    made = {}
    for ref, name in [("bebidas-quentes", "Bebidas quentes"), ("rusticos", "Rústicos"),
                      ("finos", "Finos"), ("balcao", "Balcão")]:
        made[ref] = Collection.objects.create(ref=ref, name=name)
    for sku, name, collections in [
        ("CAFE", "Café", ["bebidas-quentes"]),
        ("PAO", "Pão francês", ["rusticos"]),
        ("CROISSANT", "Croissant", ["finos"]),
        ("MISTERIO", "Produto do balcão", ["balcao"]),
        ("DOIS-MUNDOS", "Ambíguo", ["bebidas-quentes", "rusticos"]),
    ]:
        product = Product.objects.create(sku=sku, name=name)
        for collection_ref in collections:
            CollectionItem.objects.create(collection=made[collection_ref], product=product)
    return made


def _run(command, *args):
    out = StringIO()
    call_command(command, *args, stdout=out, stderr=out)
    return out.getvalue()


# ── O proponente ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_proposal_never_passes_as_curation(roles, catalog):
    _run("propose_consumption_tags")
    for tag in ProductConsumptionTag.objects.all():
        assert tag.reviewed is False
        assert "revisar" in tag.note


@pytest.mark.django_db
def test_collections_map_to_readings(roles, catalog):
    _run("propose_consumption_tags")
    tags = {t.sku: t.role.reading for t in ProductConsumptionTag.objects.select_related("role")}
    assert tags["CAFE"] == Reading.ANCHOR
    assert tags["PAO"] == Reading.TAKEAWAY
    assert tags["CROISSANT"] == Reading.HYBRID


@pytest.mark.django_db
def test_what_the_map_cannot_reach_is_listed_not_guessed(roles, catalog):
    output = _run("propose_consumption_tags")
    # "Balcão" agrupa por ONDE vende, não pelo que é — propor dali seria chutar.
    assert not ProductConsumptionTag.objects.filter(sku="MISTERIO").exists()
    assert "MISTERIO" in output
    # Produto em duas coleções que discordam também é decisão de gente.
    assert not ProductConsumptionTag.objects.filter(sku="DOIS-MUNDOS").exists()
    assert "DOIS-MUNDOS" in output


@pytest.mark.django_db
def test_curated_tag_is_never_overwritten_by_a_proposal(roles, catalog):
    ProductConsumptionTag.objects.create(
        sku="CAFE", role=roles[Reading.TAKEAWAY], note="decisão do dono", reviewed=True
    )
    _run("propose_consumption_tags")
    tag = ProductConsumptionTag.objects.select_related("role").get(sku="CAFE")
    assert tag.role.reading == Reading.TAKEAWAY
    assert tag.reviewed is True
    assert tag.note == "decisão do dono"


@pytest.mark.django_db
def test_dry_run_writes_nothing(roles, catalog):
    output = _run("propose_consumption_tags", "--dry-run")
    assert ProductConsumptionTag.objects.count() == 0
    assert "nada gravado" in output


@pytest.mark.django_db
def test_missing_vocabulary_stops_instead_of_half_tagging(db, catalog):
    output = _run("propose_consumption_tags")
    assert "Faltam papéis" in output
    assert ProductConsumptionTag.objects.count() == 0


# ── A calibração ─────────────────────────────────────────────────────────────


@pytest.fixture
def history(roles):
    """Duas vendas: café sozinho, e café com croissant (a cesta em disputa)."""
    now = timezone.now() - timedelta(days=1)
    for external_id, items in [
        (1, [("CAFE", 1)]),
        (2, [("CAFE", 1), ("CROISSANT", 1)]),
    ]:
        sale = HistoricalSale.objects.create(
            source="yooga", external_id=external_id, occurred_at=now,
            total_q=1000, payment="Dinheiro",
        )
        for seq, (sku, qty) in enumerate(items):
            HistoricalSaleItem.objects.create(
                sale=sale, seq=seq, product_name=sku, sku=sku,
                qty=Decimal(qty), unit_price_q=500, line_total_q=500,
            )
    ProductConsumptionTag.objects.create(sku="CAFE", role=roles[Reading.ANCHOR], reviewed=True)
    ProductConsumptionTag.objects.create(sku="CROISSANT", role=roles[Reading.HYBRID], reviewed=True)


@pytest.mark.django_db
def test_payment_report_counts_the_raw_forms(history):
    output = _run("bi_calibrate")
    assert "Formas de pagamento" in output
    assert "Dinheiro" in output


@pytest.mark.django_db
def test_unrecognised_payment_form_is_flagged_with_its_own_words(roles):
    HistoricalSale.objects.create(
        source="yooga", external_id=9, occurred_at=timezone.now() - timedelta(days=1),
        total_q=500, payment="Fiado do seu Zé",
    )
    output = _run("bi_calibrate")
    assert "NÃO reconhece" in output
    assert "Fiado do seu Zé" in output


@pytest.mark.django_db
def test_the_two_variants_disagree_exactly_where_the_owner_said(history):
    """Café + croissant é a cesta em disputa — e o teste cobra os NÚMEROS.

    base: as duas vendas são consumo local (o croissant acompanha o café).
    ambíguo-leva: a segunda vira "consumiu e levou" — que é exatamente o
    deslocamento que a contraproposta do booleano provoca.
    """
    output = _run("bi_calibrate")

    def counts(mode_label: str) -> list[int]:
        line = next(ln for ln in output.splitlines() if ln.strip().startswith(mode_label))
        return [int(n) for n in re.findall(r"(\d+)\s+\d+[.,]\d%", line)]

    assert counts("Consumiu aqui") == [2, 1]
    assert counts("Consumiu e levou") == [0, 1]
    assert counts("Levou") == [0, 0]


@pytest.mark.django_db
def test_calibration_without_tags_says_what_to_do_instead_of_showing_zeros(db):
    HistoricalSale.objects.create(
        source="yooga", external_id=1, occurred_at=timezone.now() - timedelta(days=1),
        total_q=500, payment="PIX",
    )
    output = _run("bi_calibrate")
    assert "Nenhum SKU etiquetado" in output
    assert "propose_consumption_tags" in output


@pytest.mark.django_db
def test_role_override_adds_a_third_variant_without_a_second_rule(history):
    output = _run("bi_calibrate", "--role", "hibrido=takeaway")
    assert "hibrido=takeaway" in output


# ── O seed não inventa histórico onde já há histórico ────────────────────────


@pytest.mark.django_db
def test_seed_does_not_invent_history_where_real_history_exists():
    """Somar dois anos sintéticos a dois anos reais faria toda leitura ser
    metade ficção — o `source` rotula a série, mas os totais são a soma.
    """
    from config.management.commands.seed import Command

    HistoricalSale.objects.create(
        source="yooga", external_id=1, occurred_at=timezone.now() - timedelta(days=1),
        total_q=1000, payment="PIX",
    )
    created = Command()._seed_long_sales_history({}, days=30)
    assert created == 0
    assert HistoricalSale.objects.count() == 1
    assert HistoricalSale.objects.filter(source="seed").count() == 0


@pytest.mark.django_db
def test_a_previously_seeded_environment_cleans_itself_when_real_data_arrives():
    """Ambiente semeado no passado se limpa ao rodar de novo com dado real."""
    from config.management.commands.seed import Command

    HistoricalSale.objects.create(
        source="seed", external_id=9, occurred_at=timezone.now() - timedelta(days=2),
        total_q=500, payment="Dinheiro",
    )
    HistoricalSale.objects.create(
        source="yooga", external_id=1, occurred_at=timezone.now() - timedelta(days=1),
        total_q=1000, payment="PIX",
    )
    Command()._seed_long_sales_history({}, days=30)
    assert list(HistoricalSale.objects.values_list("source", flat=True)) == ["yooga"]


# ── O comando cirúrgico: referência sim, operação não ────────────────────────


@pytest.mark.django_db
def test_bi_reference_installs_the_three_tables_and_nothing_else():
    """A guarda que justifica o comando existir.

    Rodar o `seed` completo num ambiente com operação de verdade injetaria venda
    de demonstração junto — e a leitura do B.I. passaria a somar operação real
    com inventada. Este comando instala CADASTRO e não encosta em movimento.
    """
    from shopman.orderman.models import Order, Session
    from shopman.stockman.models import Move

    from shopman.backstage.models import (
        ConsumptionRole,
        DayClosing,
        ProductConsumptionTag,
        SeatingSpot,
    )

    Order.objects.create(ref="REAL-1", channel_ref="pdv",
                         status=Order.Status.COMPLETED, total_q=1000)
    operational_before = (
        Order.objects.count(), Session.objects.count(),
        Move.objects.count(), DayClosing.objects.count(),
    )

    _run("setup_bi_reference")

    assert ConsumptionRole.objects.count() == 3
    assert ProductConsumptionTag.objects.count() == 59
    assert ProductConsumptionTag.objects.filter(reviewed=True).count() == 59
    # 4 mesas internas + 4 externas + 6 lugares de balcão contam no teto; o
    # bistrô (2) e o bancão externo ficam fora, e é justamente por ficarem fora
    # que "bateu no teto" continua sendo um sinal.
    assert SeatingSpot.objects.count() == 17
    assert SeatingSpot.objects.filter(counts_in_capacity=True).count() == 14

    operational_after = (
        Order.objects.count(), Session.objects.count(),
        Move.objects.count(), DayClosing.objects.count(),
    )
    assert operational_after == operational_before, "o comando criou operação"


@pytest.mark.django_db
def test_bi_reference_is_idempotent():
    from shopman.backstage.models import ProductConsumptionTag, SeatingSpot

    _run("setup_bi_reference")
    _run("setup_bi_reference")
    assert ProductConsumptionTag.objects.count() == 59
    assert SeatingSpot.objects.count() == 17


@pytest.mark.django_db
def test_bi_reference_dry_run_writes_nothing():
    from shopman.backstage.models import ProductConsumptionTag

    output = _run("setup_bi_reference", "--dry-run")
    assert ProductConsumptionTag.objects.count() == 0
    assert "nada gravado" in output


@pytest.mark.django_db
def test_the_seed_is_the_source_and_wins_over_an_admin_edit():
    """Reinstalar desfaz edição feita no Admin — e isso é decisão, não surpresa.

    A curadoria canônica mora no seed. Quem editar no Admin e quiser preservar
    precisa levar a mudança para lá; do contrário a próxima instalação a desfaz.
    """
    from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag, Reading

    _run("setup_bi_reference")
    leva = ConsumptionRole.objects.get(reading=Reading.TAKEAWAY)
    ProductConsumptionTag.objects.filter(sku="ESPRESSO").update(role=leva, note="mexi no Admin")

    _run("setup_bi_reference")
    tag = ProductConsumptionTag.objects.select_related("role").get(sku="ESPRESSO")
    assert tag.role.reading == Reading.ANCHOR


# ── As categorias reais do Yooga (medidas em 18/08, no staging) ──────────────


@pytest.mark.parametrize(
    "category,expected,linhas",
    [
        ("Pães Finos", "hybrid", 38369),
        ("Pães Rústicos", "takeaway", 15299),
        ("Cafés", "anchor", 5211),
        ("Sanduíches & Tartines", "anchor", 907),
        ("Sobremesas", "anchor", 108),
        ("Mercearia", "takeaway", 33),
        ("Bebidas", "anchor", 24),
    ],
)
def test_every_real_yooga_category_reads_as_the_owner_decided(category, expected, linhas):
    """As sete categorias que existem de verdade nos dois anos de histórico.

    ⚠️ "Pães Finos" é o caso que motivou o teste: a palavra genérica "pão" casa
    com ela e a mandaria para "leva", quando a viennoiserie é híbrida. São 38.369
    linhas — errar aqui inclinaria o retrato inteiro dos dois anos.
    """
    from shopman.backstage.management.commands.propose_consumption_tags import (
        HISTORICAL_KEYWORD_READING,
    )

    lowered = category.lower()
    for needle, reading in HISTORICAL_KEYWORD_READING:
        if needle in lowered:
            assert reading == expected, (
                f"{category} ({linhas} linhas) casou '{needle}' → {reading}, "
                f"mas o dono decidiu {expected}"
            )
            return
    raise AssertionError(f"{category} ({linhas} linhas) não casa com nenhuma palavra")


def test_the_specific_keyword_beats_the_generic_one():
    """A guarda é a ORDEM: genérico antes de específico apagaria a decisão."""
    from shopman.backstage.management.commands.propose_consumption_tags import (
        HISTORICAL_KEYWORD_READING,
    )

    order = [needle for needle, _ in HISTORICAL_KEYWORD_READING]
    for specific, generic in (("pães finos", "pão"), ("pães rústicos", "pão"),
                              ("sanduíche", "pão"), ("mercearia", "pão")):
        assert order.index(specific) < order.index(generic), (
            f"'{specific}' precisa vir antes de '{generic}' — a primeira que casa vence"
        )
