"""O desconto sai do LOTE, não da posição (ADR-017 / D1-RETIREMENT-PLAN C1).

O que estes testes amarram é a razão de o D-1 estar sendo aposentado: a posição
``"ontem"`` é um proxy binário de "último dia" que só funciona para pão de um
dia. A validade do lote vale para qualquer prazo — o caso do queijo, que
originou a superação.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from shopman.stockman.models import Batch

from shopman.shop.modifiers import DiscountModifier, LotDiscountModifier
from shopman.shop.services import lot_pricing

pytestmark = pytest.mark.django_db


def _session(items):
    session = MagicMock()
    session.items = items
    session.data = {}
    session.pricing = {}
    session.update_items = lambda x: None
    session.save = MagicMock()
    return session


def _line(sku, *, price_q, batch_ref="", qty=1, meta=None):
    line_meta = {"_list_q": price_q, **(meta or {})}
    if batch_ref:
        line_meta["batch_ref"] = batch_ref
    return {"sku": sku, "unit_price_q": price_q, "qty": qty, "meta": line_meta}


# ── percent_for_lot ──────────────────────────────────────────────────


class TestPercentForLot:
    def test_lot_without_nonconformity_is_full_price(self):
        Batch.objects.create(ref="PAO-1", sku="PAO", production_date=timezone.localdate())
        assert lot_pricing.percent_for_lot("PAO-1") == 0

    def test_lot_carries_the_percent_frozen_at_inspection(self):
        Batch.objects.create(
            ref="PAO-2", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=50, nonconformity_reason="Assou demais",
        )
        assert lot_pricing.percent_for_lot("PAO-2") == 50

    def test_operator_may_deepen_the_discount_never_shrink_it(self):
        """max(automatic, declared): quem inspecionou viu o pão (ADR-017 §7)."""
        Batch.objects.create(
            ref="PAO-3", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=20,
        )
        assert lot_pricing.percent_for_lot("PAO-3", declared_percent=40) == 40
        assert lot_pricing.percent_for_lot("PAO-3", declared_percent=10) == 20

    def test_unknown_lot_fails_safe_to_full_price(self):
        assert lot_pricing.percent_for_lot("NAO-EXISTE") == 0
        assert lot_pricing.percent_for_lot("") == 0


# ── O modifier ───────────────────────────────────────────────────────


class TestLotDiscountModifier:
    def test_line_gets_the_discount_of_its_own_lot(self):
        Batch.objects.create(
            ref="LOTE-A", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=50,
        )
        session = _session([_line("PAO", price_q=1000, batch_ref="LOTE-A")])
        LotDiscountModifier().apply(channel=MagicMock(), session=session, ctx={})

        assert session.items[0]["unit_price_q"] == 500
        assert session.pricing["lot_discount"]["total_discount_q"] == 500

    def test_two_lots_of_the_same_bake_price_differently(self):
        """A fornada partida: um grupo a preço cheio, outro com desconto.

        É isto que a posição nunca soube fazer — "ontem" é um balde só.
        """
        today = timezone.localdate()
        Batch.objects.create(ref="LOTE-CHEIO", sku="PAO", production_date=today)
        Batch.objects.create(
            ref="LOTE-MARCADO", sku="PAO", production_date=today, nonconformity_percent=50
        )
        session = _session([
            _line("PAO", price_q=1000, batch_ref="LOTE-CHEIO"),
            _line("PAO", price_q=1000, batch_ref="LOTE-MARCADO"),
        ])
        LotDiscountModifier().apply(channel=MagicMock(), session=session, ctx={})

        assert session.items[0]["unit_price_q"] == 1000
        assert session.items[1]["unit_price_q"] == 500

    def test_the_cheese_case_a_twenty_day_product_prices_by_its_lot(self):
        """O caso que originou a superação do D-1.

        Um queijo com validade de 20 dias não tem "ontem" — mas o lote dele
        carrega validade e (se houver) desconto, pelo mesmo caminho do pão.
        """
        Batch.objects.create(
            ref="QUEIJO-L1",
            sku="QUEIJO-POMERODE",
            production_date=timezone.localdate() - timedelta(days=15),
            expiry_date=timezone.localdate() + timedelta(days=5),
            nonconformity_percent=20,
            nonconformity_reason="Perto do vencimento",
        )
        session = _session([_line("QUEIJO-POMERODE", price_q=3200, batch_ref="QUEIJO-L1")])
        LotDiscountModifier().apply(channel=MagicMock(), session=session, ctx={})

        assert session.items[0]["unit_price_q"] == 2560  # 3200 − 20%
        context = lot_pricing.lot_context("QUEIJO-L1")
        assert context["expiry_date"] == (timezone.localdate() + timedelta(days=5)).isoformat()
        assert context["reason"] == "Perto do vencimento"

    def test_line_without_a_lot_is_untouched(self):
        session = _session([_line("PAO", price_q=1000)])
        LotDiscountModifier().apply(channel=MagicMock(), session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000
        assert "lot_discount" not in session.pricing

    def test_does_not_compound_over_a_bigger_existing_discount(self):
        """Maior desconto ganha — nunca compõe."""
        Batch.objects.create(
            ref="LOTE-20", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=20,
        )
        # A linha já saiu a 600 (40% de desconto de promoção).
        line = _line("PAO", price_q=1000, batch_ref="LOTE-20")
        line["unit_price_q"] = 600
        session = _session([line])
        LotDiscountModifier().apply(channel=MagicMock(), session=session, ctx={})

        assert session.items[0]["unit_price_q"] == 600  # o desconto maior fica

    def test_frozen_price_is_final(self):
        """Preço fixado pelo operador não recebe desconto automático."""
        Batch.objects.create(
            ref="LOTE-50", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=50,
        )
        session = _session([
            _line("PAO", price_q=1000, batch_ref="LOTE-50", meta={"price_overridden": True})
        ])
        LotDiscountModifier().apply(channel=MagicMock(), session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000


# ── Lote × promoção/cupom: maior desconto ganha na fronteira order 15 → 20 ──


class TestLotDiscountVsPromotion:
    """A interação LotDiscountModifier(order 15) → DiscountModifier(order 20).

    O lote roda ANTES do desconto de promoção/cupom/manual. O DiscountModifier
    precisa calcular o percentual sobre o preço de LISTA e vencer a linha só em
    "maior desconto ganha" — se calcular sobre o ``unit_price_q`` já reduzido
    pelo lote, empilha o percentual sobre um preço já descontado e cobra a MENOS.

    Regressão do furo de auditoria alpha (cobrança silenciosa a menor): o guard
    de total não pega, porque a tela e a cobrança leem o mesmo ``line_total_q``
    furado — nenhuma divergência para o ``expected_total_q`` acusar.
    """

    def _channel(self):
        return MagicMock(ref="web")

    def _promo(self, percent):
        from shopman.shop.models import Promotion

        now = timezone.now()
        Promotion.objects.create(
            ref=f"promo-{percent}", name=f"Promo {percent}",
            type=Promotion.PERCENT, value=percent, is_active=True,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
        )
        from django.core.cache import cache
        cache.clear()

    def test_percent_promo_does_not_compound_on_lot_discount(self):
        """Lote 50% vs promo 30%: cobra 500 (lote vence), NUNCA 350 (empilhado)."""
        Batch.objects.create(
            ref="LOTE-LIQ", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=50,
        )
        self._promo(30)
        session = _session([_line("PAO", price_q=1000, batch_ref="LOTE-LIQ")])

        LotDiscountModifier().apply(channel=self._channel(), session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 500  # lote 50%
        DiscountModifier().apply(channel=self._channel(), session=session, ctx={})

        unit = session.items[0]["unit_price_q"]
        assert unit == 500, (
            f"promo 30% empilhou sobre o lote: cobrou {unit}, esperado 500 "
            f"(cobrança a menor de {500 - unit})"
        )
        # Transparência: o lote fica, a promo não entra nesta linha.
        pricing = session.pricing or {}
        assert (pricing.get("lot_discount") or {}).get("total_discount_q") == 500
        assert "PAO" not in [d.get("sku") for d in (pricing.get("discount") or {}).get("items", [])]

    def test_bigger_percent_promo_replaces_lot_discount_best_wins(self):
        """Lote 20% vs promo 40%: promo vence (600), lote é revertido — sem compor."""
        Batch.objects.create(
            ref="LOTE-P20", sku="PAO", production_date=timezone.localdate(),
            nonconformity_percent=20,
        )
        self._promo(40)
        session = _session([_line("PAO", price_q=1000, batch_ref="LOTE-P20")])

        LotDiscountModifier().apply(channel=self._channel(), session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 800  # lote 20%
        DiscountModifier().apply(channel=self._channel(), session=session, ctx={})

        unit = session.items[0]["unit_price_q"]
        assert unit == 600, (
            f"melhor desconto não substituiu: cobrou {unit}, esperado 600 "
            f"(promo 40% sobre a lista, não 1000×0,8×0,6=480 empilhado)"
        )
        # Transparência reconciliada: o lote saiu, a promo entrou.
        pricing = session.pricing or {}
        assert "lot_discount" not in pricing or not pricing.get("lot_discount")
        assert (pricing.get("discount") or {}).get("total_discount_q") == 400
