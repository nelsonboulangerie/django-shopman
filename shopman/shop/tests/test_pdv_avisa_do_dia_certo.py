"""O aviso de disponibilidade do PDV fala do dia certo, na língua certa.

A review do balcão é o único ponto do PDV que pergunta ao estoque. Ela
perguntava sempre por HOJE — mesmo numa encomenda para sexta —, truncava
quantidade fracionada e respondia quatro causas diferentes com uma frase só.
"""
from __future__ import annotations

from django.utils import timezone


class TestReviewAsksForTheRightDay:
    def test_the_commitment_date_is_the_one_the_order_is_for(self):
        """A review conferia o estoque de HOJE mesmo numa encomenda para
        sexta: o aviso gritava falta que a fornada de sexta cobre, e calava
        falta real da data combinada."""
        from datetime import date

        from shopman.shop.services.pos import _payload_commitment_date

        assert _payload_commitment_date({"delivery_date": "2027-03-05"}) == date(2027, 3, 5)
        # Balcão sem agendamento é hoje; data ilegível não inventa outro dia.
        assert _payload_commitment_date({}) == timezone.localdate()
        assert _payload_commitment_date({"delivery_date": "nao-e-data"}) == timezone.localdate()


class TestTheWarningSaysWhichProblemItIs:
    def test_three_causes_stop_sharing_one_sentence(self):
        """"só N em estoque" mandava o operador caçar unidade na prateleira
        quando o problema era o produto estar pausado ou fora do cardápio."""
        from shopman.shop.services.pos import _availability_shortfall

        assert "pausado" in _availability_shortfall({"is_paused": True})
        assert "fora do cardápio" in _availability_shortfall({"reason_code": "not_in_listing"})
        assert "em estoque" in _availability_shortfall({"available_qty": 2})

    def test_the_lot_stage_uses_the_production_quantities(self):
        """Planejado: o lote nem começou. Previsto: o lote já foi aberto.
        Se o aberto não cobre o que falta, parte depende do que nem começou."""
        from decimal import Decimal

        from shopman.shop.services.pos import _lot_stage

        assert _lot_stage(Decimal("0"), Decimal("2")) == "Planejado"
        assert _lot_stage(Decimal("1"), Decimal("2")) == "Planejado"
        assert _lot_stage(Decimal("2"), Decimal("2")) == "Previsto"

    def test_half_a_kilo_is_not_reported_as_zero(self):
        """``int(available_qty)`` truncava: meio quilo de queijo virava
        "só 0 em estoque" numa venda que estava correta."""
        from decimal import Decimal

        from shopman.shop.services.pos import _availability_shortfall

        assert "0,5" in _availability_shortfall({"available_qty": Decimal("0.5")})
        # E o inteiro não ganha casas decimais de enfeite.
        assert "só 3 em" in _availability_shortfall({"available_qty": Decimal("3.00")})
