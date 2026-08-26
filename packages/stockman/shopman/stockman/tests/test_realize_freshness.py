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
