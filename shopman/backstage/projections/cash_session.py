"""CashSessionReportProjection — leitura X/Z e histórico de turnos do dia, sobre o livro.

Read model da antesala do PDV (ADMIN-ROLE-PLAN WP-ADM-4, benchmark Odoo POS):

- **Leitura X** — parcial do turno ABERTO do operador: fundo de troco, movimentos
  (sangria/suprimento), contagem de vendas e vendas por método.
- **Leitura Z** — fechamento de cada turno FECHADO do dia: fundo de troco, valor
  CONTADO (contagem cega), movimentos e totais operacionais de vendas.
- **Histórico do dia** — totais agregados de turnos e vendas.

Duas fontes, cada uma dona da sua pergunta (ADR-022):

- **``cashman``** (o livro do turno): fundo de troco (``float_in``), movimentos
  (``cash_out``/``cash_in``), contagem (``count`` + correções) e QUAIS vendas
  passaram por este turno (``sale``/``cod_settled``/``refund``, por ``order_ref``
  e ``payment_ref``).
- **``payman``** (o livro de pagamentos): QUANTO cada venda recebeu, por método.
  A linha ``sale`` aponta os intents (``payment_ref`` e ``payload.intents``); o
  valor e o método vêm de lá. Uma linha sem intent resolvível (dado antigo,
  seed) entra pelo efeito em dinheiro da própria linha, e só como dinheiro.

⚠️ BLIND COUNT (anti-fraude): o PDV NUNCA expõe o valor ESPERADO da gaveta —
nem no X (turno aberto), nem no Z (turno fechado). A conferência (esperado vs
contado vs diferença) é da retaguarda (Admin/Unfold, ``cashman.audit_shift``).
Aqui, o Z mostra o que o operador CONTOU e o que a operação registrou, nada
derivável do esperado. Por construção: esta projection nunca chama
``cashman.services.balance``/``expected_before_count``/``difference``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.backstage.presentation.status import payment_method_label

logger = logging.getLogger(__name__)

_METHOD_ORDER = ("cash", "pix", "card", "external")


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MovementRowProjection:
    """A manual drawer movement inside a shift."""

    kind: str  # "sangria" | "suprimento" (vocabulário do balcão; o livro diz cash_out/cash_in)
    kind_label: str  # "Saída de caixa" | "Entrada de caixa"
    amount_q: int  # sempre positivo; a direção vem do `kind`
    amount_display: str
    reason: str
    created_by: str
    created_at: str  # ISO datetime


@dataclass(frozen=True)
class SalesByMethodRowProjection:
    """Sales received by one payment method within a shift."""

    method: str  # "cash" | "pix" | "card" | "external"
    method_label: str
    orders_count: int
    amount_q: int
    amount_display: str


@dataclass(frozen=True)
class ShiftReadingProjection:
    """One shift's operational reading (X when open, Z when closed).

    BLIND: never carries the expected drawer amount nor the variance — the
    reconciliation lives in the backoffice, not at the terminal.
    """

    shift_id: int
    status: str  # "open" | "closed"
    terminal_ref: str
    terminal_label: str
    operator: str
    opened_at: str  # ISO datetime
    closed_at: str  # ISO datetime, "" while open
    opening_amount_q: int
    opening_amount_display: str
    counted_amount_q: int | None  # blind count; None while open
    counted_amount_display: str  # "" while open
    movements: tuple[MovementRowProjection, ...]
    movements_in_q: int  # suprimentos
    movements_in_display: str
    movements_out_q: int  # sangrias
    movements_out_display: str
    sales_count: int
    sales_total_q: int
    sales_total_display: str
    sales_by_method: tuple[SalesByMethodRowProjection, ...]
    notes: str  # "" while open


@dataclass(frozen=True)
class DayTotalsProjection:
    """Aggregated shift/sales history for the day (closed shifts)."""

    shifts_count: int
    sales_count: int
    sales_total_q: int
    sales_total_display: str
    counted_total_q: int
    counted_total_display: str
    sales_by_method: tuple[SalesByMethodRowProjection, ...]


@dataclass(frozen=True)
class CashSessionReportProjection:
    """Top-level read model for the session report page (/session/report)."""

    date: str  # ISO date
    date_display: str  # "17/07/2026"
    x_reading: ShiftReadingProjection | None  # operator's OPEN shift, or None
    has_open_shift: bool
    z_readings: tuple[ShiftReadingProjection, ...]  # today's CLOSED shifts
    has_closed_shifts: bool
    day_totals: DayTotalsProjection


# ── Builder ────────────────────────────────────────────────────────────


def build_cash_session_report(*, operator) -> CashSessionReportProjection:
    """Build the X/Z report for today, scoped to the requesting operator's X.

    The X reading belongs to the operator asking (their open shift); the Z list
    covers every shift closed today, terminal-wide — the shift history the
    antesala shows. Neither exposes expected/variance (blind count).
    """
    from shopman.cashman import services as cash
    from shopman.cashman.models import Shift

    today = timezone.localdate()

    open_shift = cash.open_shift_for(operator)
    x_reading = _shift_reading(open_shift) if open_shift else None

    closed = (
        Shift.objects.filter(status=Shift.Status.CLOSED, closed_at__date=today)
        .select_related("terminal", "operator")
        .order_by("closed_at")
    )
    z_readings = tuple(_shift_reading(shift) for shift in closed)

    return CashSessionReportProjection(
        date=today.isoformat(),
        date_display=today.strftime("%d/%m/%Y"),
        x_reading=x_reading,
        has_open_shift=x_reading is not None,
        z_readings=z_readings,
        has_closed_shifts=bool(z_readings),
        day_totals=_day_totals(z_readings),
    )


# ── Internals ──────────────────────────────────────────────────────────


def _shift_reading(shift) -> ShiftReadingProjection:
    from shopman.cashman import services as cash
    from shopman.cashman.models import Entry

    from shopman.backstage.services.pos import MOVEMENT_API_BY_KIND

    entries = list(cash.timeline(shift))
    Kind = Entry.Kind

    opening_amount_q = sum(e.amount_q for e in entries if e.kind == Kind.FLOAT_IN)

    movements = tuple(
        MovementRowProjection(
            kind=MOVEMENT_API_BY_KIND[e.kind],
            kind_label=str(e.get_kind_display()),
            amount_q=abs(int(e.amount_q)),
            amount_display=format_money(abs(int(e.amount_q))),
            reason=e.reason,
            created_by=e.operator.get_username() if e.operator_id else "",
            created_at=e.at.isoformat() if e.at else "",
        )
        for e in entries
        if e.kind in (Kind.CASH_OUT, Kind.CASH_IN)
    )
    movements_in_q = sum(row.amount_q for row in movements if row.kind == "suprimento")
    movements_out_q = sum(row.amount_q for row in movements if row.kind == "sangria")

    sales_count, sales_total_q, by_method = _shift_sales(entries)
    is_open = shift.is_open
    # O que o operador CONTOU (com correções gerenciais posteriores). Nunca o
    # esperado: ``counted`` é a única leitura do pacote que esta tela pode fazer.
    counted_q = None if is_open else cash.counted(shift)
    notes = "" if is_open else _count_notes(entries)

    return ShiftReadingProjection(
        shift_id=shift.pk,
        status="open" if is_open else "closed",
        terminal_ref=shift.terminal.ref,
        terminal_label=shift.terminal.label or shift.terminal.ref,
        operator=shift.operator.get_username(),
        opened_at=shift.opened_at.isoformat() if shift.opened_at else "",
        closed_at=shift.closed_at.isoformat() if shift.closed_at else "",
        opening_amount_q=opening_amount_q,
        opening_amount_display=format_money(opening_amount_q),
        counted_amount_q=counted_q,
        counted_amount_display="" if counted_q is None else format_money(counted_q),
        movements=movements,
        movements_in_q=movements_in_q,
        movements_in_display=format_money(movements_in_q),
        movements_out_q=movements_out_q,
        movements_out_display=format_money(movements_out_q),
        sales_count=sales_count,
        sales_total_q=sales_total_q,
        sales_total_display=format_money(sales_total_q),
        sales_by_method=_method_rows(by_method),
        notes=notes,
    )


def _count_notes(entries) -> str:
    """As observações do fechamento moram no payload da contagem."""
    for entry in entries:
        if entry.kind == "count":
            return str((entry.payload or {}).get("notes") or "")
    return ""


def _shift_sales(entries) -> tuple[int, int, dict[str, dict]]:
    """Vendas do turno: QUAIS vêm do livro, QUANTO e POR MÉTODO vêm do ``payman``.

    Cada ``sale``/``cod_settled`` aponta seus intents (``payment_ref`` e
    ``payload.intents``); o valor líquido (captura − estornos) e o método são
    do intent. Uma linha cujo intent não resolve entra pelo efeito em dinheiro
    da própria linha — é o que o livro sabe sozinho, e só como ``cash``.
    ``refund`` já está descontado no ``payman`` quando o intent resolve; sem
    intent, é o efeito negativo da linha, também em dinheiro.
    """
    from shopman.cashman.models import Entry

    Kind = Entry.Kind
    money_kinds = (Kind.SALE, Kind.COD_SETTLED, Kind.REFUND)
    money_entries = [e for e in entries if e.kind in money_kinds]

    refs_by_entry: dict[int, list[str]] = {}
    all_refs: set[str] = set()
    for entry in money_entries:
        refs = _intent_refs(entry)
        refs_by_entry[entry.pk] = refs
        all_refs.update(refs)

    intents = _intents_by_ref(all_refs)

    by_method: dict[str, dict] = {}
    seen_refs: set[str] = set()
    for entry in money_entries:
        resolved = [ref for ref in refs_by_entry[entry.pk] if ref in intents]
        if resolved:
            # ``refund`` com intent: o estorno já está líquido no intent da venda.
            if entry.kind == Kind.REFUND:
                continue
            for ref in resolved:
                if ref in seen_refs:
                    continue  # duas linhas do mesmo intent (tenders): conta uma vez
                seen_refs.add(ref)
                method, amount_q = intents[ref]
                _tally(by_method, method, amount_q)
            continue
        if entry.amount_q != 0:
            _tally(by_method, "cash", int(entry.amount_q))

    sales_count = len({e.order_ref or f"#{e.pk}" for e in money_entries if e.kind == Kind.SALE})
    sales_total_q = sum(int(bucket["amount_q"]) for bucket in by_method.values())
    return sales_count, sales_total_q, by_method


def _intent_refs(entry) -> list[str]:
    payload = entry.payload or {}
    refs: list[str] = []
    if entry.payment_ref:
        refs.append(str(entry.payment_ref))
    intents = payload.get("intents") or {}
    if isinstance(intents, dict):
        refs.extend(str(ref) for ref in intents.values() if ref)
    # Ordem estável, sem repetição.
    return list(dict.fromkeys(refs))


def _intents_by_ref(refs: set[str]) -> dict[str, tuple[str, int]]:
    """``ref → (método, valor líquido)`` para os intents que liquidaram."""
    if not refs:
        return {}
    from django.db.models import Sum
    from shopman.payman.models import PaymentIntent, PaymentTransaction

    settled = (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED)
    intents = PaymentIntent.objects.filter(ref__in=refs, status__in=settled).values_list("ref", "method", "amount_q")
    refunded = dict(
        PaymentTransaction.objects.filter(intent__ref__in=refs, type=PaymentTransaction.Type.REFUND)
        .values("intent__ref")
        .annotate(total=Sum("amount_q"))
        .values_list("intent__ref", "total")
    )
    return {
        ref: (str(method or "").strip().lower() or "external", int(amount_q or 0) - int(refunded.get(ref) or 0))
        for ref, method, amount_q in intents
    }


def _tally(by_method: dict[str, dict], method: str, amount_q: int) -> None:
    bucket = by_method.setdefault(method, {"orders_count": 0, "amount_q": 0})
    bucket["orders_count"] += 1
    bucket["amount_q"] += amount_q


def _method_rows(by_method: dict[str, dict]) -> tuple[SalesByMethodRowProjection, ...]:
    ordered = sorted(
        by_method.items(),
        key=lambda pair: (
            _METHOD_ORDER.index(pair[0]) if pair[0] in _METHOD_ORDER else len(_METHOD_ORDER),
            pair[0],
        ),
    )
    return tuple(
        SalesByMethodRowProjection(
            method=method,
            method_label=payment_method_label(method),
            orders_count=int(bucket["orders_count"]),
            amount_q=int(bucket["amount_q"]),
            amount_display=format_money(int(bucket["amount_q"])),
        )
        for method, bucket in ordered
    )


def _day_totals(z_readings: tuple[ShiftReadingProjection, ...]) -> DayTotalsProjection:
    sales_total_q = sum(reading.sales_total_q for reading in z_readings)
    counted_total_q = sum(reading.counted_amount_q or 0 for reading in z_readings)

    merged: dict[str, dict] = {}
    for reading in z_readings:
        for row in reading.sales_by_method:
            bucket = merged.setdefault(row.method, {"orders_count": 0, "amount_q": 0})
            bucket["orders_count"] += row.orders_count
            bucket["amount_q"] += row.amount_q

    return DayTotalsProjection(
        shifts_count=len(z_readings),
        sales_count=sum(reading.sales_count for reading in z_readings),
        sales_total_q=sales_total_q,
        sales_total_display=format_money(sales_total_q),
        counted_total_q=counted_total_q,
        counted_total_display=format_money(counted_total_q),
        sales_by_method=_method_rows(merged),
    )
