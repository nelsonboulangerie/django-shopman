"""Prontidão por SKU — declarada pela casa, observada nas fornadas, e o encontro.

O eixo que importa aqui é o do buraco que o serviço veio tapar: antes, produto
sem fornada nos últimos 30 dias não restringia horário NENHUM. O dado que faltava
LIBERAVA a promessa. Os testes de declaração são todos sobre isso.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.services.product_readiness import (
    _round_up_minutes,
    bottleneck,
    declared_ready_times,
    format_clock,
    observed_ready_times,
    parse_clock,
    product_names,
    ready_times_for,
)


class RoundUpMinutesTests(TestCase):
    def test_exact_boundary(self):
        self.assertEqual(_round_up_minutes(330, 30), 330)  # 5:30 exato

    def test_rounds_up(self):
        self.assertEqual(_round_up_minutes(331, 30), 360)  # 5:31 → 6:00

    def test_just_past(self):
        self.assertEqual(_round_up_minutes(361, 30), 390)  # 6:01 → 6:30

    def test_zero(self):
        self.assertEqual(_round_up_minutes(0, 30), 0)

    def test_15min_granularity(self):
        self.assertEqual(_round_up_minutes(46, 15), 60)  # 0:46 → 1:00


class ParseClockTests(TestCase):
    def test_reads_hh_mm(self):
        self.assertEqual(parse_clock("12:00"), time(12, 0))

    def test_accepts_single_digit_hour(self):
        self.assertEqual(parse_clock("9:30"), time(9, 30))

    def test_accepts_seconds(self):
        self.assertEqual(parse_clock("12:00:00"), time(12, 0))

    def test_empty_is_not_midnight(self):
        """Ausência é ausência. Virar 00:00 seria inventar uma promessa."""
        self.assertIsNone(parse_clock(""))
        self.assertIsNone(parse_clock(None))

    def test_garbage_is_none(self):
        self.assertIsNone(parse_clock("12h"))
        self.assertIsNone(parse_clock("meio-dia"))
        self.assertIsNone(parse_clock("99:99"))

    def test_format_round_trip(self):
        self.assertEqual(format_clock(parse_clock("9:5")), "09:05")
        self.assertEqual(format_clock(None), "")


class DeclaredReadyTimesTests(TestCase):
    def setUp(self):
        Product.objects.create(
            sku="BF", name="Baguette de Tradition", base_price_q=1600, metadata={"ready_from": "12:00"}
        )
        Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=900, metadata={})
        Product.objects.create(
            sku="TORTO", name="Cadastro torto", base_price_q=100, metadata={"ready_from": "12h"}
        )

    def test_declared_is_read(self):
        self.assertEqual(declared_ready_times(["BF"]), {"BF": time(12, 0)})

    def test_undeclared_is_omitted(self):
        self.assertEqual(declared_ready_times(["CROISSANT"]), {})

    def test_unreadable_declaration_is_omitted(self):
        """Cadastro ilegível não vira meia-noite — vira ausência."""
        self.assertEqual(declared_ready_times(["TORTO"]), {})

    def test_empty_input(self):
        self.assertEqual(declared_ready_times([]), {})

    def test_names_for_the_reason(self):
        self.assertEqual(product_names(["BF"]), {"BF": "Baguette de Tradition"})


class ReadyTimesResolutionTests(TestCase):
    """Declarado e observado juntos — a regra é "vence o mais tarde"."""

    def setUp(self):
        from shopman.craftsman.models import Recipe, WorkOrder

        self.tz = timezone.get_current_timezone()
        today = date.today()

        Product.objects.create(
            sku="DECLARADO-TARDE", name="Pão tardio", base_price_q=100, metadata={"ready_from": "12:00"}
        )
        Product.objects.create(
            sku="DECLARADO-CEDO", name="Pão cedo", base_price_q=100, metadata={"ready_from": "06:00"}
        )
        Product.objects.create(sku="SEM-NADA", name="Sem histórico", base_price_q=100, metadata={})

        # As duas fornadas históricas saem às 08:00.
        for sku in ("DECLARADO-TARDE", "DECLARADO-CEDO"):
            recipe = Recipe.objects.create(
                ref=f"r-{sku.lower()}", name=sku, output_sku=sku, batch_size=Decimal("10")
            )
            for days_ago in range(1, 4):
                day = today - timedelta(days=days_ago)
                WorkOrder.objects.create(
                    recipe=recipe,
                    output_sku=sku,
                    quantity=Decimal("10"),
                    finished=Decimal("10"),
                    status="finished",
                    target_date=day,
                    started_at=datetime.combine(day, time(5, 0), tzinfo=self.tz),
                    finished_at=datetime.combine(day, time(8, 0), tzinfo=self.tz),
                )

    def test_declaration_wins_when_later(self):
        """A casa diz 12h, a fornada sai às 8h → vale 12h."""
        self.assertEqual(ready_times_for(["DECLARADO-TARDE"])["DECLARADO-TARDE"], time(12, 0))

    def test_history_wins_when_later(self):
        """A casa diz 6h, mas há um mês sai às 8h → vale 8h.

        A declaração é PISO. Quem pagaria a diferença de acreditar no cadastro é
        o cliente na porta às 6h.
        """
        self.assertEqual(ready_times_for(["DECLARADO-CEDO"])["DECLARADO-CEDO"], time(8, 0))

    def test_declaration_covers_the_gap(self):
        """Sem histórico, a declaração é a única resposta — e é o caso que
        antes deixava passar qualquer horário."""
        Product.objects.filter(sku="SEM-NADA").update(metadata={"ready_from": "15:00"})
        self.assertEqual(ready_times_for(["SEM-NADA"])["SEM-NADA"], time(15, 0))

    def test_silence_stays_silent(self):
        """Sem declaração e sem histórico o SKU some do resultado. Aqui não se
        inventa restrição nem se dá passe livre — quem decide é o chamador."""
        self.assertEqual(ready_times_for(["SEM-NADA"]), {})

    def test_observed_alone(self):
        self.assertEqual(
            observed_ready_times(["DECLARADO-CEDO"])["DECLARADO-CEDO"], time(8, 0)
        )

    def test_bottleneck_is_the_latest(self):
        hora, sku = bottleneck(["DECLARADO-CEDO", "DECLARADO-TARDE", "SEM-NADA"])
        self.assertEqual(hora, time(12, 0))
        self.assertEqual(sku, "DECLARADO-TARDE")

    def test_bottleneck_of_nothing(self):
        self.assertEqual(bottleneck(["SEM-NADA"]), (None, ""))
        self.assertEqual(bottleneck([]), (None, ""))
