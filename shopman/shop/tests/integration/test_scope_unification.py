"""
Scope unification regression — trava o contrato ``check == reserve``.

Para qualquer SKU × canal × qty, a qty máxima que ``availability.check``
promete precisa ser exatamente a qty que ``availability.reserve`` consegue
holdar. Isso evita o bug em que o modal de shortage mostrava N disponíveis,
o cliente clicava "aceitar N", e o servidor voltava 422 porque o reserve
não conseguia colocar holds suficientes.

Cobre também a regra de D-1 (posição ``ontem`` é staff-only: canais remotos
não veem, PDV vê).
"""

from decimal import Decimal

import pytest
from shopman.stockman.services.movements import StockMovements

from shopman.shop.services import availability

pytestmark = pytest.mark.django_db


@pytest.fixture
def position_ontem(db):
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="ontem",
        defaults={
            "name": "Vitrine D-1",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


@pytest.fixture
def web_channel(db):
    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref="web",
        defaults={
            "name": "Loja online",
            "is_active": True,
            "config": {"stock": {"excluded_positions": ["ontem"]}},
        },
    )
    return channel


@pytest.fixture
def pdv_channel(db):
    from shopman.shop.models import Channel

    channel, _ = Channel.objects.update_or_create(
        ref="pdv",
        defaults={
            "name": "Balcão / PDV",
            "is_active": True,
            "config": {"stock": {}},
        },
    )
    return channel


class TestScopeUnification:
    """``check(sku, qty, channel)['available_qty']`` equals the qty that
    ``reserve(sku, qty, channel)`` is actually able to hold."""

    def test_remote_channel_excludes_ontem(
        self, product, position_loja, position_ontem, web_channel,
    ):
        """Web channel with excluded_positions=['ontem'] must not count
        quants at that position."""
        StockMovements.receive(
            Decimal("5"), product.sku, position=position_loja,
            reason="Produção fresca",
        )
        StockMovements.receive(
            Decimal("7"), product.sku, position=position_ontem,
            reason="D-1 markdown",
        )

        check_result = availability.check(
            product.sku, Decimal("12"), channel_ref="web",
        )
        assert check_result["available_qty"] == Decimal("5")

    def test_staff_channel_sees_ontem(
        self, product, position_loja, position_ontem, pdv_channel,
    ):
        """PDV (staff) without excluded_positions must count all
        saleable positions, including ontem."""
        StockMovements.receive(
            Decimal("5"), product.sku, position=position_loja,
            reason="Produção fresca",
        )
        StockMovements.receive(
            Decimal("7"), product.sku, position=position_ontem,
            reason="D-1 markdown",
        )

        check_result = availability.check(
            product.sku, Decimal("12"), channel_ref="pdv",
        )
        assert check_result["available_qty"] == Decimal("12")

    def test_check_and_reserve_agree_for_fragmented_stock(
        self, product, position_loja, position_ontem, web_channel,
    ):
        """Fragmented stock across quants: the qty reported by check must
        be exactly what reserve can deliver (including fallback across quants).

        Previously, check returned the total across all visible positions while
        reserve, restricted to a single quant at a time, would fall back to the
        split-across-quants path and could fail. With the canonical scope gate
        the two views are forced to agree.
        """
        StockMovements.receive(
            Decimal("10"), product.sku, position=position_loja,
            reason="Lote manhã",
        )
        StockMovements.receive(
            Decimal("4"), product.sku, position=position_ontem,
            reason="D-1 (staff-only)",
        )

        check = availability.check(
            product.sku, Decimal("99"), channel_ref="web",
        )
        promised = check["available_qty"]
        assert promised == Decimal("10")

        reserve = availability.reserve(
            product.sku, promised, session_key="test-session",
            channel_ref="web",
        )
        assert reserve["ok"] is True
        assert reserve["available_qty"] == promised

    def test_reserve_never_holds_on_excluded_position(
        self, product, position_ontem, web_channel,
    ):
        """Remote channel: if the only available stock is at ``ontem``,
        reserve must refuse — matching check, which returns 0 visible."""
        StockMovements.receive(
            Decimal("10"), product.sku, position=position_ontem,
            reason="D-1",
        )

        check = availability.check(
            product.sku, Decimal("1"), channel_ref="web",
        )
        assert check["ok"] is False
        assert check["available_qty"] == Decimal("0")

        reserve = availability.reserve(
            product.sku, Decimal("1"), session_key="test-session",
            channel_ref="web",
        )
        assert reserve["ok"] is False

    def test_staff_channel_can_reserve_ontem(
        self, product, position_ontem, pdv_channel,
    ):
        """PDV reserves at ontem normally — the denylist is a per-channel
        scoping concern, not a global rule."""
        StockMovements.receive(
            Decimal("10"), product.sku, position=position_ontem,
            reason="D-1",
        )

        reserve = availability.reserve(
            product.sku, Decimal("3"), session_key="test-session",
            channel_ref="pdv",
        )
        assert reserve["ok"] is True


class TestLotGates:
    """C2 (D1-RETIREMENT): o LOTE decide o que cada canal vê e reserva.

    O contrato independe da superfície: os testes entram pela API de
    disponibilidade crua (``check``/``reserve`` por ``channel_ref``) — nenhum
    invariante depende de a superfície lembrar de um campo.
    """

    @pytest.fixture
    def sells_all_channel(self, db):
        from shopman.shop.models import Channel

        channel, _ = Channel.objects.update_or_create(
            ref="pdv",
            defaults={
                "name": "Balcão / PDV",
                "is_active": True,
                "config": {"stock": {"sells_nonconforming": True}},
            },
        )
        return channel

    def _marked_lot(self, product, position_loja, today):
        from datetime import timedelta

        from shopman.stockman.models import Batch

        Batch.objects.create(
            sku=product.sku, ref="LOTE-OK",
            expiry_date=today + timedelta(days=1),
        )
        Batch.objects.create(
            sku=product.sku, ref="LOTE-MARCADO",
            expiry_date=today + timedelta(days=1),
            nonconformity_reason="Assou demais",
            nonconformity_percent=50,
        )
        StockMovements.receive(
            Decimal("5"), product.sku, position=position_loja,
            batch="LOTE-OK", reason="fornada conforme",
        )
        StockMovements.receive(
            Decimal("8"), product.sku, position=position_loja,
            batch="LOTE-MARCADO", reason="fornada com desconto",
        )

    def test_remote_channel_neither_sees_nor_reserves_nonconforming(
        self, product, position_loja, web_channel,
    ):
        """Canal remoto (default ``sells_nonconforming=False``): o lote
        marcado não conta na vitrine e não vira hold."""
        from django.utils import timezone

        self._marked_lot(product, position_loja, timezone.localdate())

        check = availability.check(
            product.sku, Decimal("13"), channel_ref="web",
        )
        assert check["available_qty"] == Decimal("5")

        reserve = availability.reserve(
            product.sku, Decimal("5"), session_key="test-session",
            channel_ref="web",
        )
        assert reserve["ok"] is True

        from shopman.stockman.models import Hold

        held_batches = set(
            Hold.objects.filter(sku=product.sku).values_list(
                "quant__batch", flat=True,
            )
        )
        assert "LOTE-MARCADO" not in held_batches

    def test_pos_sells_nonconforming_when_declared(
        self, product, position_loja, sells_all_channel,
    ):
        """PDV com ``sells_nonconforming=True`` vê os dois lotes."""
        from django.utils import timezone

        self._marked_lot(product, position_loja, timezone.localdate())

        check = availability.check(
            product.sku, Decimal("13"), channel_ref="pdv",
        )
        assert check["available_qty"] == Decimal("13")

    def test_expiry_margin_pulls_near_expiry_from_the_channel(
        self, product, position_loja, db,
    ):
        """Canal com ``expiry_margin_days=3``: lote que vence em 2 dias some;
        sem margem, ele conta até vencer."""
        from datetime import timedelta

        from django.utils import timezone
        from shopman.stockman.models import Batch

        from shopman.shop.models import Channel

        today = timezone.localdate()
        Batch.objects.create(
            sku=product.sku, ref="VENCE-2D",
            expiry_date=today + timedelta(days=2),
        )
        StockMovements.receive(
            Decimal("6"), product.sku, position=position_loja,
            batch="VENCE-2D", reason="lote curto",
        )

        Channel.objects.update_or_create(
            ref="web",
            defaults={
                "name": "Loja online",
                "is_active": True,
                "config": {"stock": {"expiry_margin_days": 3}},
            },
        )
        Channel.objects.update_or_create(
            ref="pdv",
            defaults={"name": "PDV", "is_active": True, "config": {}},
        )

        assert availability.check(
            product.sku, Decimal("1"), channel_ref="web",
        )["available_qty"] == Decimal("0")
        assert availability.check(
            product.sku, Decimal("1"), channel_ref="pdv",
        )["available_qty"] == Decimal("6")
