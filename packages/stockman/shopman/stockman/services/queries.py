"""
Stock queries — read-only operations.

All methods are classmethod on Stock and use no locking.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from shopman.stockman.models.hold import Hold
from shopman.stockman.models.position import Position
from shopman.stockman.models.quant import Quant
from shopman.stockman.shelflife import filter_valid_quants


@dataclass(frozen=True)
class ShelfDay:
    """O dia de um SKU na prateleira, reconstruído do ledger.

    ``first_in_at`` é a primeira entrada do dia (chegou para venda) e
    ``soldout_at`` o instante a partir do qual o saldo ficou zerado e **não
    voltou a subir** naquele dia — reposição no meio da tarde desfaz o
    esgotamento em vez de contar como um.

    Esgotar é acabar de tanto VENDER. Descarte de fim de dia também zera a
    prateleira, e é o oposto: sobrou. Por isso ``soldout_at`` só se fecha em
    movimento de venda; perda e ajuste baixam o saldo sem virar falta.

    Campos vazios são ausência de fato, nunca zero: dia que terminou com produto
    na prateleira tem ``soldout_at`` vazio.
    """

    date: date
    opening: Decimal
    received: Decimal
    sold: Decimal
    discarded: Decimal
    first_in_at: datetime | None
    soldout_at: datetime | None

    @property
    def had_stock(self) -> bool:
        return self.opening > 0 or self.received > 0

    @property
    def closing(self) -> Decimal:
        return self.opening + self.received - self.sold - self.discarded


def _resolve_stock_profile(sku_or_product):
    """Resolve sku + stock profile from either a product-like object or the catalog contract."""
    from shopman.stockman.adapters.sku_validation import get_sku_validator

    sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
    shelflife = getattr(sku_or_product, "shelf_life_days", None) if not isinstance(sku_or_product, str) else None
    availability_policy = (
        getattr(sku_or_product, "availability_policy", None)
        if not isinstance(sku_or_product, str)
        else None
    )

    if shelflife is None or availability_policy is None:
        info = get_sku_validator().get_sku_info(sku)
        if info is not None:
            if shelflife is None:
                shelflife = info.shelflife_days
            if availability_policy is None:
                availability_policy = info.availability_policy

    return {
        "sku": sku,
        "shelflife": shelflife,
        "availability_policy": availability_policy or "planned_ok",
    }


class StockQueries:
    """Read-only stock query methods."""

    @classmethod
    def available(cls, sku_or_product, target_date: date | None = None,
                  position: Position | None = None, *,
                  product=None) -> Decimal:
        """
        Available quantity for sale/hold.

        available = valid_quantity - active_holds

        Args:
            sku_or_product: SKU string or product object (for backwards compat).
                           If product object, its .sku is used.
            target_date: Desired date (None = today)
            position: Specific position (None = all)
            product: Product object for shelflife filtering (optional).
                    If sku_or_product is a product object, it's used directly.

        Returns:
            Decimal with available quantity
        """
        target = target_date or timezone.localdate()

        # Support both sku string and product object
        profile = _resolve_stock_profile(sku_or_product)
        sku = profile["sku"]
        if product is None:
            product = sku_or_product if not isinstance(sku_or_product, str) else None
        if product is None and profile["shelflife"] is not None:
            from types import SimpleNamespace

            product = SimpleNamespace(
                sku=sku,
                # filter_valid_quants reads `.shelf_life_days` — o nome precisa bater,
                # senão a validade NÃO é aplicada no caminho por sku-string.
                shelf_life_days=profile["shelflife"],
                availability_policy=profile["availability_policy"],
            )

        quants = Quant.objects.filter(sku=sku)

        if position:
            quants = quants.filter(position=position)

        if product is not None:
            quants = filter_valid_quants(quants, product, target)
        else:
            # No product for shelflife — include physical + up to target date
            quants = quants.filter(
                Q(target_date__isnull=True) | Q(target_date__lte=target)
            )

        from shopman.stockman.models.batch import Batch
        expired_refs = list(
            Batch.objects.filter(sku=sku, expiry_date__lt=target).values_list('ref', flat=True)
        )
        if expired_refs:
            quants = quants.exclude(batch__in=expired_refs)

        total = quants.aggregate(
            t=Coalesce(Sum('_quantity'), Decimal('0'))
        )['t']

        held_qs = Hold.objects.filter(
            sku=sku,
            target_date=target,
        ).active()
        if position:
            held_qs = held_qs.filter(quant__position=position)
        held = held_qs.aggregate(
            t=Coalesce(Sum('quantity'), Decimal('0'))
        )['t']

        return total - held

    @classmethod
    def promise(
        cls,
        sku: str,
        quantity,
        *,
        target_date: date | None = None,
        safety_margin: int = 0,
        allowed_positions: list[str] | None = None,
    ):
        """Return Stockman's explicit promise decision for a SKU."""
        from shopman.stockman.services.availability import promise_decision_for_sku

        return promise_decision_for_sku(
            sku,
            quantity,
            target_date=target_date,
            safety_margin=safety_margin,
            allowed_positions=allowed_positions,
        )

    @classmethod
    def demand(cls, sku_or_product, target_date: date) -> Decimal:
        """
        Pending demand (holds without linked stock).

        Returns:
            Sum of Hold.quantity where quant=None and target_date=date
        """
        sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
        return Hold.objects.filter(
            sku=sku,
            target_date=target_date,
            quant__isnull=True,
        ).active().aggregate(
            t=Coalesce(Sum('quantity'), Decimal('0'))
        )['t']

    @classmethod
    def committed(cls, sku_or_product, target_date: date | None = None) -> Decimal:
        """
        Total quantity committed (active holds) for product/date.

        Returns:
            Sum of active hold quantities
        """
        target = target_date or timezone.localdate()
        sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku

        return Hold.objects.filter(
            sku=sku,
            target_date=target,
        ).active().aggregate(
            t=Coalesce(Sum('quantity'), Decimal('0'))
        )['t']

    @classmethod
    def get_quant(cls, sku_or_product, position: Position | None = None,
                  target_date: date | None = None, batch: str = '') -> Quant | None:
        """Get specific quant by coordinates."""
        sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
        return Quant.objects.filter(
            sku=sku,
            position=position,
            target_date=target_date,
            batch=batch
        ).first()

    @classmethod
    def shelf_history(
        cls, skus, *, since: date, until: date
    ) -> dict[str, dict[date, ShelfDay]]:
        """Dia a dia na prateleira: quando chegou, quando acabou.

        Reconstrói o saldo VENDÁVEL e físico (posição vendável, sem
        ``target_date``) a partir do ledger imutável de ``Move``, que é a única
        fonte que carrega o instante de cada entrada e saída. Saldo planejado e
        depósito ficam de fora: a pergunta é sobre o que o cliente encontrava.

        O saldo de abertura de cada dia vem do acumulado anterior a ``since``,
        então a série é fiel mesmo começando no meio da vida do produto.

        Limite conhecido: o instante é o do REGISTRO no ledger. Venda de balcão
        baixa no ato; venda online só quando o pagamento confirma. Um mesmo
        esgotamento aparece um pouco depois conforme o canal.
        """
        from shopman.stockman.models.move import Move

        skus = [skus] if isinstance(skus, str) else list(skus)
        if not skus or since > until:
            return {}

        tz = timezone.get_current_timezone()
        window_start = datetime.combine(since, time.min, tzinfo=tz)
        window_end = datetime.combine(until + timedelta(days=1), time.min, tzinfo=tz)

        quants = Quant.objects.filter(
            sku__in=skus, position__is_saleable=True, target_date__isnull=True
        ).values_list("pk", "sku")
        sku_by_quant = dict(quants)
        if not sku_by_quant:
            return {}

        # Saldo de abertura: tudo que aconteceu antes da janela.
        opening: dict[str, Decimal] = dict.fromkeys(skus, Decimal("0"))
        earlier = (
            Move.objects.filter(quant_id__in=sku_by_quant, timestamp__lt=window_start)
            .values("quant_id")
            .annotate(total=Coalesce(Sum("delta"), Decimal("0")))
        )
        for row in earlier:
            opening[sku_by_quant[row["quant_id"]]] += row["total"]

        moves_by_sku_day: dict[tuple[str, date], list] = {}
        rows = (
            Move.objects.filter(
                quant_id__in=sku_by_quant,
                timestamp__gte=window_start,
                timestamp__lt=window_end,
            )
            .order_by("timestamp")
            .values_list("quant_id", "timestamp", "delta", "kind")
        )
        for quant_id, stamp, delta, kind in rows:
            local = timezone.localtime(stamp)
            key = (sku_by_quant[quant_id], local.date())
            moves_by_sku_day.setdefault(key, []).append((local, delta, kind))

        history: dict[str, dict[date, ShelfDay]] = {}
        for sku in skus:
            balance = opening.get(sku, Decimal("0"))
            days: dict[date, ShelfDay] = {}
            day = since
            while day <= until:
                days[day] = _shelf_day(
                    day, balance, moves_by_sku_day.get((sku, day), [])
                )
                balance = days[day].closing
                day += timedelta(days=1)
            history[sku] = days
        return history

    @classmethod
    def list_quants(cls, sku_or_product=None, position: Position | None = None,
                    include_future: bool = True, include_empty: bool = False):
        """List quants with filters."""
        qs = Quant.objects.all()

        if sku_or_product is not None:
            sku = sku_or_product if isinstance(sku_or_product, str) else sku_or_product.sku
            qs = qs.filter(sku=sku)

        if position is not None:
            qs = qs.filter(position=position)

        if not include_future:
            qs = qs.filter(Q(target_date__isnull=True) | Q(target_date__lte=timezone.localdate()))

        if not include_empty:
            qs = qs.filter(_quantity__gt=0)

        return qs


def _shelf_day(day: date, opening: Decimal, moves: list) -> ShelfDay:
    """Um dia de prateleira a partir do saldo de abertura e dos movimentos.

    ``soldout_at`` é o instante da VENDA que zerou o saldo sem que ele voltasse
    a subir no mesmo dia. Duas exclusões deliberadas: um zero às 10h que recebe
    fornada às 11h não é esgotamento (por isso a decisão só se fecha no fim da
    varredura), e um zero causado por descarte não é esgotamento (é sobra).
    """
    from shopman.stockman.models.move import Move

    balance = opening
    received = Decimal("0")
    sold = Decimal("0")
    discarded = Decimal("0")
    first_in_at = None
    soldout_at = None
    for stamp, delta, kind in moves:
        if delta > 0:
            received += delta
            if first_in_at is None:
                first_in_at = stamp
            soldout_at = None  # repôs: o esgotamento anterior não vingou
        elif kind == Move.Kind.SELL:
            sold += -delta
        else:
            discarded += -delta
        balance += delta
        if (
            balance <= 0
            and soldout_at is None
            and kind == Move.Kind.SELL
            and (opening > 0 or received > 0)
        ):
            soldout_at = stamp
    return ShelfDay(
        date=day,
        opening=opening,
        received=received,
        sold=sold,
        discarded=discarded,
        first_in_at=first_in_at,
        soldout_at=soldout_at,
    )
