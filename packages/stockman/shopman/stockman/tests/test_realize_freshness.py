"""
Realize preserva o frescor da fornada — regressão do alpha de 26/08/2026.

O defeito: ``StockPlanning.realize`` creditava toda fornada num único quant
físico sem data por posição (``get_or_create(target_date=None, batch='')``).
A validade de quant sem data é julgada pelo ``created_at`` do QUANT — e o
acumulador nasce uma vez e vive para sempre. Depois que ele envelhece além da
shelf-life, cada fornada nova realizada nele fica invisível para a
disponibilidade, junto com o estoque velho.

O contrato correto: cada realize credita o lote do dia da fornada
(``<SKU>-<AAAAMMDD>``), com ``Batch.production_date`` e ``expiry_date``
derivados da shelf-life do produto. A validade passa a ser do LOTE, não do
quant que o acumula — inclusive quando a fornada esquecida de ontem é
expedida hoje.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.stockman import stock
from shopman.stockman.models import Batch, Quant

pytestmark = pytest.mark.django_db


@pytest.fixture
def pao_do_dia(db):
    """Perecível de 2 dias — o caso típico da vitrine da padaria."""
    return SimpleNamespace(sku="PAO-DO-DIA", name="Pão do dia", shelf_life_days=2)


class TestRealizeFreshness:
    def test_fresh_batch_visible_even_with_aged_showcase_quant(
        self, pao_do_dia, vitrine, today
    ):
        """A fornada de hoje aparece mesmo quando a vitrine carrega um
        acumulador sem data mais velho que a shelf-life (o cenário do alpha:
        quant criado no seed, dias atrás)."""
        aged = Quant.objects.create(
            sku=pao_do_dia.sku, position=vitrine, _quantity=Decimal("50")
        )
        Quant.objects.filter(pk=aged.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )

        stock.plan(Decimal("5"), pao_do_dia, today, reason="Produção")
        stock.realize(pao_do_dia, today, Decimal("5"), vitrine)

        assert stock.available(pao_do_dia, today) >= Decimal("5")

    def test_realize_stamps_daily_lot(self, pao_do_dia, vitrine, today):
        """O físico continua sem data (invariante), mas carrega o lote do dia,
        com produção e validade no Batch."""
        stock.plan(Decimal("5"), pao_do_dia, today, reason="Produção")
        physical = stock.realize(pao_do_dia, today, Decimal("5"), vitrine)

        expected_ref = f"{pao_do_dia.sku}-{today:%Y%m%d}"
        assert physical.target_date is None
        assert physical.batch == expected_ref

        lot = Batch.objects.get(ref=expected_ref)
        assert lot.sku == pao_do_dia.sku
        assert lot.production_date == today
        assert lot.expiry_date == today + timedelta(days=2)

    def test_two_realizes_same_day_share_one_lot(self, pao_do_dia, vitrine, today):
        """Duas fornadas do mesmo dia somam no mesmo lote diário."""
        stock.plan(Decimal("3"), pao_do_dia, today, reason="Produção")
        first = stock.realize(pao_do_dia, today, Decimal("3"), vitrine)
        stock.plan(Decimal("4"), pao_do_dia, today, reason="Produção")
        second = stock.realize(pao_do_dia, today, Decimal("4"), vitrine)

        assert first.pk == second.pk
        assert second.quantity == Decimal("7")
        assert Batch.objects.filter(sku=pao_do_dia.sku).count() == 1

    def test_forgotten_batch_expedited_late_keeps_its_age(
        self, pao_do_dia, vitrine, today
    ):
        """A fornada esquecida de anteontem, expedida hoje, envelhece pelo
        LOTE — não ganha cara de fresca só porque o quant nasceu agora."""
        baked = today - timedelta(days=3)  # além da shelf-life de 2 dias

        stock.plan(Decimal("6"), pao_do_dia, baked, reason="Produção")
        stock.realize(pao_do_dia, baked, Decimal("6"), vitrine)

        assert stock.available(pao_do_dia, today) == Decimal("0")

    def test_yesterdays_lot_still_valid_within_shelflife(
        self, pao_do_dia, vitrine, today
    ):
        """Dentro da shelf-life, o lote de ontem continua vendável."""
        yesterday = today - timedelta(days=1)

        stock.plan(Decimal("6"), pao_do_dia, yesterday, reason="Produção")
        stock.realize(pao_do_dia, yesterday, Decimal("6"), vitrine)

        assert stock.available(pao_do_dia, today) == Decimal("6")

    def test_non_perishable_lot_has_no_expiry(self, product, vitrine, today):
        """Produto sem shelf-life ganha lote do dia sem validade — rastreável,
        nunca expira."""
        stock.plan(Decimal("5"), product, today, reason="Produção")
        physical = stock.realize(product, today, Decimal("5"), vitrine)

        lot = Batch.objects.get(ref=physical.batch)
        assert lot.expiry_date is None
        assert stock.available(product, today + timedelta(days=30)) == Decimal("5")

    def test_realize_adopts_partition_lot_when_given(self, pao_do_dia, vitrine, today):
        """Com ``to_batch`` (o lote da partição de qualidade), o realize credita
        NELE — e garante produção+validade no Batch mesmo sem rastreabilidade."""
        ref = f"{pao_do_dia.sku}-{today:%Y%m%d}-77"
        stock.plan(Decimal("5"), pao_do_dia, today, reason="Produção")
        physical = stock.realize(
            pao_do_dia, today, Decimal("5"), vitrine, to_batch=ref,
        )

        assert physical.batch == ref
        lot = Batch.objects.get(ref=ref)
        assert lot.production_date == today
        assert lot.expiry_date == today + timedelta(days=2)

    def test_realize_never_overwrites_frozen_quality_facts(
        self, pao_do_dia, vitrine, today
    ):
        """O lote já congelado pela inspeção (desconto/motivo) atravessa o
        realize intocado — get_or_create, nunca update."""
        ref = f"{pao_do_dia.sku}-{today:%Y%m%d}-88"
        Batch.objects.create(
            ref=ref, sku=pao_do_dia.sku, production_date=today,
            expiry_date=today + timedelta(days=2),
            nonconformity_percent=30, nonconformity_reason="Queimou a base",
        )
        stock.plan(Decimal("5"), pao_do_dia, today, reason="Produção")
        stock.realize(pao_do_dia, today, Decimal("5"), vitrine, to_batch=ref)

        lot = Batch.objects.get(ref=ref)
        assert lot.nonconformity_percent == 30
        assert lot.nonconformity_reason == "Queimou a base"


class TestReceiveFreshness:
    """O ``receive`` de perecível tem a mesma armadilha do acumulador: a
    reposição de balcão sem lote caía num quant sem data que envelhece uma vez
    e esconde toda reposição nova. Perecível reposto sem lote explícito ganha
    o lote do dia; não-perecível e entradas com lote/data seguem como eram."""

    def _use_perishable_validator(self, settings):
        from shopman.stockman.adapters.sku_validation import reset_sku_validator

        settings.STOCKMAN = {
            **settings.STOCKMAN,
            "SKU_VALIDATOR": "shopman.stockman.tests.fakes.PerishableSkuValidator",
        }
        reset_sku_validator()

    def test_perishable_counter_restock_gets_daily_lot(
        self, settings, vitrine, today
    ):
        self._use_perishable_validator(settings)
        quant = stock.receive(
            quantity=Decimal("6"), sku="CROISSANT", position=vitrine,
            reason="Reposição de balcão",
        )

        ref = f"CROISSANT-{today:%Y%m%d}"
        assert quant.batch == ref
        lot = Batch.objects.get(ref=ref)
        assert lot.production_date == today
        assert lot.expiry_date == today  # shelflife 0 → vale só hoje

    def test_perishable_restock_visible_despite_aged_accumulator(
        self, settings, vitrine, today
    ):
        """O cenário do alpha, agora pela porta do receive: acumulador velho na
        vitrine não engole a reposição fresca."""
        self._use_perishable_validator(settings)
        product = SimpleNamespace(sku="CROISSANT", shelf_life_days=0)
        aged = Quant.objects.create(
            sku="CROISSANT", position=vitrine, _quantity=Decimal("50")
        )
        Quant.objects.filter(pk=aged.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )

        stock.receive(
            quantity=Decimal("6"), sku="CROISSANT", position=vitrine,
            reason="Reposição de balcão",
        )

        assert stock.available(product, today) == Decimal("6")

    def test_non_perishable_receive_unchanged(self, vitrine):
        """Sem shelf-life não há armadilha (quant sem data é sempre válido):
        o contrato atual fica intacto."""
        quant = stock.receive(
            quantity=Decimal("6"), sku="PAO-FORMA", position=vitrine,
            reason="Reposição",
        )
        assert quant.batch == ""
        assert not Batch.objects.exists()

    def test_explicit_batch_and_dated_entries_unchanged(self, settings, vitrine, today):
        self._use_perishable_validator(settings)
        explicit = stock.receive(
            quantity=Decimal("6"), sku="CROISSANT", position=vitrine,
            batch="CROISSANT-NF-123", reason="Compra",
        )
        planned = stock.receive(
            quantity=Decimal("6"), sku="CROISSANT", position=vitrine,
            target_date=today + timedelta(days=1), reason="Planejado",
        )
        assert explicit.batch == "CROISSANT-NF-123"
        assert planned.batch == ""
