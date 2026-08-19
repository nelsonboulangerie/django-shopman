"""De-paras do B.I. como dado, e a máquina que só propõe (BI-DATA-FOUNDATION-PLAN, P1).

Cobre as três tabelas (produto por fonte; categoria e forma de pagamento como
vocabulário por trecho, em ordem), a disciplina do sugestor (nunca confirma,
nunca sobrescreve, declara o que não achou), o SKU exato vencendo o nome
parecido, e a regra de que só ``confirmed`` entra na leitura.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.backstage.bi.mapping import (
    normalize_name,
    suggest_categories,
    suggest_payments,
    suggest_products,
)
from shopman.backstage.models import (
    AliasStatus,
    CategoryAlias,
    HistoricalSale,
    HistoricalSaleItem,
    PaymentMethodAlias,
    ProductAlias,
)
from shopman.backstage.projections.bi_payments import normalize_historical_payment
from shopman.backstage.services.consumption import category_readings, reading_for
from shopman.backstage.tests.support import historical_batch, install_bi_vocabularies


@pytest.fixture
def catalog(db):
    return {
        sku: Product.objects.create(sku=sku, name=name)
        for sku, name in (
            ("CT", "Croissant Tradicional"),
            ("PC", "Pain au Chocolat"),
            ("BA", "Baguete Tradicional"),
            ("MD", "Madeleine"),
        )
    }


def _history(*lines):
    """Uma venda histórica com as linhas (sku, nome, categoria)."""
    sale = HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga",
        external_id=HistoricalSale.objects.count() + 1,
        occurred_at=timezone.now(), total_q=100, payment="Dinheiro",
    )
    for seq, (sku, name, category) in enumerate(lines, start=1):
        HistoricalSaleItem.objects.create(
            sale=sale, seq=seq, product_name=name, sku=sku, category=category,
            qty=Decimal("1"), unit_price_q=100, line_total_q=100,
        )
    return sale


# ── Sugestão de produto ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_exact_sku_wins_before_any_fuzzy_match(catalog):
    _history(("CT", "Croissant", "Pães Finos"))
    result = suggest_products("yooga")
    alias = ProductAlias.objects.get(source="yooga", external_sku="CT")
    assert alias.product == catalog["CT"]
    assert alias.score == 100
    assert alias.status == AliasStatus.PROPOSED  # a máquina não confirma
    assert (result.created, result.matched) == (1, 1)


@pytest.mark.django_db
def test_similar_name_is_proposed_with_its_score_and_never_confirmed(catalog):
    _history(("X-PAIN", "Pain Au Chocolat Grande", "Pães Finos"))
    suggest_products("yooga", min_score=80)
    alias = ProductAlias.objects.get(external_sku="X-PAIN")
    assert alias.product == catalog["PC"]
    assert 80 <= alias.score <= 100
    assert alias.status == AliasStatus.PROPOSED
    assert "PC" in alias.note


@pytest.mark.django_db
def test_below_the_cut_stays_in_the_queue_with_the_best_guess_declared(catalog):
    _history(("ZZ", "Kombucha de Hibisco", "Bebidas"))
    result = suggest_products("yooga", min_score=80)
    alias = ProductAlias.objects.get(external_sku="ZZ")
    assert alias.product is None
    assert alias.score is not None and alias.score < 80
    assert "abaixo do corte" in alias.note
    assert result.unmatched == 1


@pytest.mark.django_db
def test_lines_without_sku_get_an_alias_by_name(catalog):
    _history(("", "Madeleine", "Confeitaria"))
    suggest_products("yooga")
    alias = ProductAlias.objects.get(source="yooga", external_sku="", external_name="Madeleine")
    assert alias.product == catalog["MD"]


@pytest.mark.django_db
def test_suggestion_never_touches_what_already_has_an_alias(catalog):
    _history(("CT", "Croissant", "Pães Finos"))
    rejected = ProductAlias.objects.create(
        source="yooga", external_sku="CT", external_name="Croissant",
        product=None, status=AliasStatus.REJECTED, note="decidido pelo dono",
    )
    result = suggest_products("yooga")
    rejected.refresh_from_db()
    assert rejected.status == AliasStatus.REJECTED and rejected.product is None
    assert (result.created, result.skipped_existing) == (0, 1)


@pytest.mark.django_db
def test_dry_run_writes_nothing(catalog):
    _history(("CT", "Croissant", "Pães Finos"))
    result = suggest_products("yooga", dry_run=True)
    assert result.created == 1
    assert ProductAlias.objects.count() == 0


def test_name_normalisation_forgets_accents_case_and_spacing():
    assert normalize_name("  Pão   de   QUEIJO ") == "pao de queijo"


# ── Categoria e forma de pagamento: só o que nenhuma regra cobre ─────────────


@pytest.mark.django_db
def test_uncovered_category_and_payment_are_queued_without_meaning():
    install_bi_vocabularies()
    sale = _history(("", "Coca-Cola", "Bebidas"), ("", "Vela", "Decoração"))
    sale.payment = "Fiado do seu Zé"
    sale.save(update_fields=["payment"])

    categories = suggest_categories()
    payments = suggest_payments()

    assert categories.created == 1  # "Bebidas" já casa com "bebida"
    queued = CategoryAlias.objects.get(pattern="decoração")
    assert queued.status == AliasStatus.PROPOSED and queued.reading == ""
    assert queued.position > CategoryAlias.objects.confirmed().order_by("-position").first().position

    assert payments.created == 1
    assert PaymentMethodAlias.objects.get(pattern="fiado do seu zé").method_key == ""
    # A leitura continua ignorando o que não foi confirmado.
    assert normalize_historical_payment("Fiado do seu Zé")[0] == "raw:fiado do seu zé"


@pytest.mark.django_db
def test_only_confirmed_rules_read(db):
    CategoryAlias.objects.create(pattern="bebida", reading="anchor", position=10)  # proposed
    assert reading_for("", "Bebidas", {}, category_rules=category_readings()) is None
    alias = CategoryAlias.objects.get()
    alias.status = AliasStatus.CONFIRMED
    alias.save()
    assert reading_for("", "Bebidas", {}, category_rules=category_readings()) == "anchor"


@pytest.mark.django_db
def test_order_is_the_rule_specific_before_generic(db):
    CategoryAlias.objects.create(pattern="pão", reading="takeaway", position=90, status="confirmed")
    CategoryAlias.objects.create(pattern="pães finos", reading="hybrid", position=10, status="confirmed")
    assert reading_for("", "Pães Finos", {}, category_rules=category_readings()) == "hybrid"


@pytest.mark.django_db
def test_confirming_a_vocabulary_row_without_meaning_is_refused(db):
    with pytest.raises(ValidationError):
        CategoryAlias(pattern="x", status=AliasStatus.CONFIRMED).full_clean()
    with pytest.raises(ValidationError):
        PaymentMethodAlias(pattern="x", status=AliasStatus.CONFIRMED).full_clean()
    with pytest.raises(ValidationError):
        ProductAlias(source="yooga").full_clean()


# ── O comando e o seed ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_command_reports_and_points_to_the_admin(catalog, capsys):
    _history(("CT", "Croissant", "Pães Finos"))
    call_command("suggest_aliases", "--source", "yooga", "--kind", "product")
    out = capsys.readouterr().out
    assert "De-para de produto" in out and "CT" in out
    assert "Nada foi confirmado" in out
    assert ProductAlias.objects.filter(status=AliasStatus.PROPOSED).count() == 1


@pytest.mark.django_db
def test_seed_installs_the_vocabularies_confirmed_and_idempotent():
    install_bi_vocabularies()
    install_bi_vocabularies()
    assert CategoryAlias.objects.count() == 22
    assert PaymentMethodAlias.objects.count() == 15
    assert not CategoryAlias.objects.exclude(status=AliasStatus.CONFIRMED).exists()
    assert normalize_historical_payment("Cartão de Crédito")[0] == "credit"
    assert reading_for("", "Pães Finos", {}, category_rules=category_readings()) == "hybrid"
