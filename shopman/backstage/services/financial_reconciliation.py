"""Reconciliação financeira diária para auditoria do operador.

Cruza, num dia local, o pedido (``Order``), o livro de pagamentos (``payman``:
``PaymentIntent`` + ``PaymentTransaction``), o livro-caixa (``cashman.Entry``)
e o fechamento (``DayClosing``). Cada check é uma pergunta com um dono:

- o pedido aponta o intent que o pagou? (``Order.data.payment``);
- o que o Payman diz que liquidou bate com o total selado do pedido, somando
  os intents do pedido (um por MÉTODO numa venda mista do terminal)?
- cada intent respeita a própria máquina de estados (captura, estorno, saldo)?
- o dinheiro que o Payman capturou em espécie é o dinheiro que entrou na
  gaveta segundo o livro-caixa? (``cash_ledger_mismatch``, ADR-022 §5).

Nenhum check depende de ``intent.gateway``: intents sem gateway (dinheiro,
cobrança externa, pix/cartão atestados no balcão numa venda mista) passam
pelas mesmas invariantes de captura/estorno que os de gateway.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Literal

from django.db.models import Q, Sum
from django.utils import timezone
from shopman.cashman.models import Entry
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import DayClosing

Severity = Literal["warning", "error", "critical"]

#: Intent que liquidou: o dinheiro trocou de mãos (e pode já ter voltado).
_SETTLED_STATUSES = frozenset({PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED})
#: Intent ainda em curso: o valor dele é o que o pedido espera receber.
_OPEN_STATUSES = frozenset({PaymentIntent.Status.PENDING, PaymentIntent.Status.AUTHORIZED})
#: Linhas do livro-caixa que são o espelho de um tender em dinheiro do Payman.
_LEDGER_MONEY_KINDS = (Entry.Kind.SALE, Entry.Kind.COD_SETTLED, Entry.Kind.REFUND)
#: Quantos pedidos divergentes o issue lista antes de cortar (o resto está no banco).
_MAX_LISTED_ORDERS = 10


@dataclass(frozen=True)
class FinancialReconciliationIssue:
    code: str
    severity: Severity
    message: str
    order_ref: str = ""
    intent_ref: str = ""
    context: dict[str, int | str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.order_ref:
            data["order_ref"] = self.order_ref
        if self.intent_ref:
            data["intent_ref"] = self.intent_ref
        if self.context:
            data["context"] = self.context
        return data


@dataclass(frozen=True)
class CashLedgerTotals:
    """Os dois lados do dinheiro em espécie do dia: Payman e livro-caixa.

    Lado Payman: capturas − estornos dos intents ``method=cash``. Lado livro:
    ``Σ Entry.amount_q`` das linhas ``sale``, ``cod_settled`` e ``refund``
    (``refund`` já é negativo). Os dois lados têm de bater ao centavo.
    """

    payman_captured_q: int = 0
    payman_refunded_q: int = 0
    ledger_sale_q: int = 0
    ledger_cod_settled_q: int = 0
    ledger_refund_q: int = 0

    @property
    def payman_net_q(self) -> int:
        return self.payman_captured_q - self.payman_refunded_q

    @property
    def ledger_net_q(self) -> int:
        return self.ledger_sale_q + self.ledger_cod_settled_q + self.ledger_refund_q

    @property
    def difference_q(self) -> int:
        return self.payman_net_q - self.ledger_net_q

    def as_dict(self) -> dict[str, int]:
        return {
            "payman_captured_q": self.payman_captured_q,
            "payman_refunded_q": self.payman_refunded_q,
            "payman_net_q": self.payman_net_q,
            "ledger_sale_q": self.ledger_sale_q,
            "ledger_cod_settled_q": self.ledger_cod_settled_q,
            "ledger_refund_q": self.ledger_refund_q,
            "ledger_net_q": self.ledger_net_q,
            "difference_q": self.difference_q,
        }


@dataclass(frozen=True)
class FinancialReconciliationReport:
    date: date
    generated_at: datetime
    order_count: int
    intent_count: int
    transaction_count: int
    order_gross_q: int
    captured_q: int
    refunded_q: int
    chargeback_q: int
    net_q: int
    by_method: dict[str, int]
    by_gateway: dict[str, int]
    issues: tuple[FinancialReconciliationIssue, ...]
    cash_ledger: CashLedgerTotals = field(default_factory=CashLedgerTotals)
    day_closing_id: int | None = None
    persisted: bool = False
    alert_created: bool = False

    @property
    def has_errors(self) -> bool:
        return any(issue.severity in {"error", "critical"} for issue in self.issues)

    @property
    def issue_counts(self) -> dict[str, int]:
        counts = Counter(issue.severity for issue in self.issues)
        return {key: counts.get(key, 0) for key in ("warning", "error", "critical")}

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "order_count": self.order_count,
            "intent_count": self.intent_count,
            "transaction_count": self.transaction_count,
            "order_gross_q": self.order_gross_q,
            "captured_q": self.captured_q,
            "refunded_q": self.refunded_q,
            "chargeback_q": self.chargeback_q,
            "net_q": self.net_q,
            "by_method": self.by_method,
            "by_gateway": self.by_gateway,
            "cash_ledger": self.cash_ledger.as_dict(),
            "issue_counts": self.issue_counts,
            "issues": [issue.as_dict() for issue in self.issues],
            "day_closing_id": self.day_closing_id,
            "persisted": self.persisted,
            "alert_created": self.alert_created,
        }


def build_financial_reconciliation(
    *,
    reconciliation_date: date,
    require_closing: bool = False,
) -> FinancialReconciliationReport:
    """Build a deterministic audit report for one local business date."""
    orders_on_date = list(
        Order.objects.filter(created_at__date=reconciliation_date).only(
            "ref",
            "channel_ref",
            "session_key",
            "snapshot",
            "total_q",
            "currency",
            "status",
            "data",
            "created_at",
        )
    )
    order_refs_on_date = {order.ref for order in orders_on_date}

    tx_intent_ids_on_date = set(
        PaymentTransaction.objects.filter(created_at__date=reconciliation_date).values_list("intent_id", flat=True)
    )
    intents = list(
        PaymentIntent.objects.filter(
            Q(order_ref__in=order_refs_on_date)
            | Q(created_at__date=reconciliation_date)
            | Q(id__in=tx_intent_ids_on_date)
        )
        .distinct()
        .order_by("order_ref", "created_at", "id")
    )
    intent_ids = [intent.id for intent in intents]
    intent_by_ref = {intent.ref: intent for intent in intents}
    intents_by_order: dict[str, list[PaymentIntent]] = defaultdict(list)
    for intent in intents:
        if intent.order_ref:
            intents_by_order[intent.order_ref].append(intent)

    all_order_refs = order_refs_on_date | {intent.order_ref for intent in intents if intent.order_ref}
    orders_by_ref = {
        order.ref: order
        for order in Order.objects.filter(ref__in=all_order_refs).only(
            "ref",
            "channel_ref",
            "session_key",
            "snapshot",
            "total_q",
            "currency",
            "status",
            "data",
            "created_at",
        )
    }

    lifetime_totals = _transaction_totals(
        PaymentTransaction.objects.filter(intent_id__in=intent_ids)
        .values("intent_id", "type")
        .annotate(total=Sum("amount_q"))
    )
    daily_totals = _transaction_totals(
        PaymentTransaction.objects.filter(intent_id__in=intent_ids, created_at__date=reconciliation_date)
        .values("intent_id", "type")
        .annotate(total=Sum("amount_q"))
    )

    issues: list[FinancialReconciliationIssue] = []
    closing = DayClosing.objects.filter(date=reconciliation_date).first()
    if closing is None:
        issues.append(
            FinancialReconciliationIssue(
                code="day_closing_missing",
                severity="error" if require_closing else "warning",
                message="Fechamento do dia ainda não existe para a data reconciliada.",
                context={"date": reconciliation_date.isoformat()},
            )
        )

    for order in orders_on_date:
        _check_order_payment_link(
            order=order,
            intent_by_ref=intent_by_ref,
            intents_by_order=intents_by_order,
            issues=issues,
        )

    # Por pedido, não por intent: a venda mista do terminal tem um intent por
    # MÉTODO, e o que tem de bater com o total selado é a soma deles.
    for order_ref, order_intents in intents_by_order.items():
        order = orders_by_ref.get(order_ref)
        if order is not None:
            _check_order_intent_amounts(order=order, order_intents=order_intents, issues=issues)

    for intent in intents:
        _check_intent(
            intent=intent,
            order=orders_by_ref.get(intent.order_ref),
            totals=lifetime_totals[intent.id],
            issues=issues,
        )

    cash_ledger = _check_cash_ledger(reconciliation_date=reconciliation_date, issues=issues)
    _check_courier_change(reconciliation_date=reconciliation_date, issues=issues)

    by_method = Counter(intent.method or "-" for intent in intents)
    # "-" = intent sem gateway: dinheiro/cobrança externa liquidados no balcão
    # e pix/cartão atestados numa venda mista (``PaymentService.settle``,
    # ADR-022). Nenhum check acima depende de ``intent.gateway``; esses intents
    # passam pelas mesmas invariantes de captura/estorno que os de gateway e
    # entram em ``captured_q``/``net_q``. O dinheiro ainda é cruzado com o
    # livro-caixa em ``_check_cash_ledger``.
    by_gateway = Counter(intent.gateway or "-" for intent in intents)

    captured_q = sum(row["capture"] for row in daily_totals.values())
    refunded_q = sum(row["refund"] for row in daily_totals.values())
    chargeback_q = sum(row["chargeback"] for row in daily_totals.values())

    return FinancialReconciliationReport(
        date=reconciliation_date,
        generated_at=timezone.now(),
        order_count=len(orders_on_date),
        intent_count=len(intents),
        transaction_count=PaymentTransaction.objects.filter(
            intent_id__in=intent_ids,
            created_at__date=reconciliation_date,
        ).count(),
        order_gross_q=sum(
            int(order.total_q or 0)
            for order in orders_on_date
            if order.status not in (Order.Status.CANCELLED, Order.Status.RETURNED)
        ),
        captured_q=captured_q,
        refunded_q=refunded_q,
        chargeback_q=chargeback_q,
        net_q=captured_q - refunded_q - chargeback_q,
        by_method=dict(sorted(by_method.items())),
        by_gateway=dict(sorted(by_gateway.items())),
        issues=tuple(issues),
        cash_ledger=cash_ledger,
        day_closing_id=closing.pk if closing else None,
    )


def persist_financial_reconciliation(
    report: FinancialReconciliationReport,
    *,
    create_alert: bool = True,
) -> FinancialReconciliationReport:
    """Persist report into DayClosing JSON and optionally emit one operator alert."""
    closing = DayClosing.objects.filter(date=report.date).first()
    persisted = False
    if closing is not None:
        data = dict(closing.data or {}) if isinstance(closing.data, dict) else {"items": closing.data or []}
        data["financial_reconciliation"] = _summary_dict(report)
        data["financial_reconciliation_errors"] = [
            issue.as_dict()
            for issue in report.issues
            if issue.severity in {"error", "critical"}
        ]
        closing.data = data
        closing.save(update_fields=["data"])
        persisted = True

    alert_created = False
    if create_alert and report.has_errors:
        from shopman.shop.services import observability

        critical = sum(1 for issue in report.issues if issue.severity == "critical")
        errors = sum(1 for issue in report.issues if issue.severity == "error")
        alert = observability.create_operator_alert(
            type="payment_reconciliation_failed",
            severity="critical" if critical else "error",
            message=(
                f"Reconciliação financeira diária de {report.date.isoformat()} encontrou "
                f"{critical} divergência(s) crítica(s) e {errors} erro(s)."
            ),
            dedupe_key=f"financial-day:{report.date.isoformat()}:{critical}:{errors}",
            debounce_minutes=60,
            issue_counts=report.issue_counts,
        )
        alert_created = alert is not None

    return replace(
        report,
        day_closing_id=closing.pk if closing else report.day_closing_id,
        persisted=persisted,
        alert_created=alert_created,
    )


def _check_order_payment_link(
    *,
    order: Order,
    intent_by_ref: dict[str, PaymentIntent],
    intents_by_order: dict[str, list[PaymentIntent]],
    issues: list[FinancialReconciliationIssue],
) -> None:
    payment = _payment_data(order)
    method = str(payment.get("method") or "").strip()
    intent_ref = str(payment.get("intent_ref") or "").strip()
    referenced = _referenced_intent_refs(payment)
    order_intents = intents_by_order.get(order.ref, [])

    if method in {"pix", "card"} and order.status not in (Order.Status.CANCELLED, Order.Status.RETURNED):
        if not referenced and not order_intents:
            issues.append(
                FinancialReconciliationIssue(
                    code="digital_order_missing_intent",
                    severity="error",
                    message="Pedido digital não tem PaymentIntent vinculado.",
                    order_ref=order.ref,
                    context={"method": method, "status": order.status, "total_q": int(order.total_q or 0)},
                )
            )

    for ref in sorted(referenced):
        if ref not in intent_by_ref:
            issues.append(
                FinancialReconciliationIssue(
                    code="order_data_intent_not_found",
                    severity="error",
                    message="Order.data.payment aponta para intent inexistente no escopo reconciliado.",
                    order_ref=order.ref,
                    intent_ref=ref,
                    context={"where": "intent_ref" if ref == intent_ref else "tenders"},
                )
            )
    if not referenced and order_intents:
        # Venda de um método só grava ``payment.intent_ref``; a mista grava
        # ``tenders[i].intent_ref`` por método. Sem nenhum dos dois, o pedido
        # não sabe quem o pagou.
        newest = sorted(order_intents, key=lambda item: item.created_at, reverse=True)[0]
        issues.append(
            FinancialReconciliationIssue(
                code="order_missing_data_intent_ref",
                severity="warning",
                message="Pedido tem PaymentIntent por order_ref, mas Order.data.payment não aponta nenhum intent.",
                order_ref=order.ref,
                intent_ref=newest.ref,
            )
        )


def _check_order_intent_amounts(
    *,
    order: Order,
    order_intents: list[PaymentIntent],
    issues: list[FinancialReconciliationIssue],
) -> None:
    """O que o Payman liquidou para o pedido tem de somar o total selado.

    Uma venda mista do terminal tem um intent por MÉTODO (dinheiro + pix
    atestado, dinheiro + external), cada um com a sua parte: nenhum deles
    bate sozinho com ``order.total_q``, e é a SOMA dos liquidados que tem de
    bater. Por isso a comparação é por pedido:

    - com intents liquidados (capturados/reembolsados): ``Σ amount_q`` deles
      == total; dois liquidados do MESMO método é cobrança em dobro
      (``multiple_captured_intents_for_order``, crítico);
    - sem nenhum liquidado: cada intent em curso (pendente/autorizado) tem de
      valer o total, porque é ele que vai ser capturado;
    - intent morto (cancelado/falho) não entra: o valor dele não paga nada.
      O intent obsoleto de um carrinho que mudou antes do pagamento deixa de
      soar como divergência.
    """
    settled = [intent for intent in order_intents if intent.status in _SETTLED_STATUSES]
    order_total_q = int(order.total_q or 0)

    if settled:
        settled_q = sum(int(intent.amount_q or 0) for intent in settled)
        if settled_q != order_total_q:
            context: dict[str, int | str] = {
                "order_total_q": order_total_q,
                "intents_amount_q": settled_q,
                "intent_count": len(settled),
            }
            if len(settled) > 1:
                context["intent_refs"] = ", ".join(intent.ref for intent in settled)
            issues.append(
                FinancialReconciliationIssue(
                    code="intent_amount_mismatch",
                    severity="error",
                    message="Soma dos PaymentIntents liquidados diverge do total selado do pedido.",
                    order_ref=order.ref,
                    intent_ref=settled[0].ref if len(settled) == 1 else "",
                    context=context,
                )
            )
        by_method = Counter(intent.method for intent in settled)
        for method, count in sorted(by_method.items()):
            if count > 1:
                issues.append(
                    FinancialReconciliationIssue(
                        code="multiple_captured_intents_for_order",
                        severity="critical",
                        message="Pedido tem mais de um intent capturado/reembolsado para o mesmo método.",
                        order_ref=order.ref,
                        context={"method": method, "intent_count": count},
                    )
                )
        return

    for intent in order_intents:
        if intent.status in _OPEN_STATUSES and int(intent.amount_q or 0) != order_total_q:
            issues.append(
                FinancialReconciliationIssue(
                    code="intent_amount_mismatch",
                    severity="error",
                    message="Valor do PaymentIntent diverge do total selado do pedido.",
                    order_ref=order.ref,
                    intent_ref=intent.ref,
                    context={"order_total_q": order_total_q, "intent_amount_q": int(intent.amount_q or 0)},
                )
            )


def _check_intent(
    *,
    intent: PaymentIntent,
    order: Order | None,
    totals: dict[str, int],
    issues: list[FinancialReconciliationIssue],
) -> None:
    captured_q = totals["capture"]
    refunded_q = totals["refund"]
    chargeback_q = totals["chargeback"]
    returned_q = refunded_q + chargeback_q
    net_q = captured_q - returned_q

    if order is None:
        issues.append(
            FinancialReconciliationIssue(
                code="intent_without_order",
                severity="error",
                message="PaymentIntent não tem pedido correspondente.",
                intent_ref=intent.ref,
                context={"order_ref": intent.order_ref, "amount_q": int(intent.amount_q or 0)},
            )
        )
        return

    payment = _payment_data(order)
    data_intent_ref = str(payment.get("intent_ref") or "").strip()
    if (
        data_intent_ref
        and intent.order_ref == order.ref
        and intent.ref not in _referenced_intent_refs(payment)
    ):
        issues.append(
            FinancialReconciliationIssue(
                code="order_intent_ref_mismatch",
                severity="warning",
                message="Pedido referencia outro intent em Order.data.payment.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"data_intent_ref": data_intent_ref},
            )
        )

    if intent.currency.upper() != order.currency.upper():
        issues.append(
            FinancialReconciliationIssue(
                code="intent_currency_mismatch",
                severity="error",
                message="Moeda do PaymentIntent diverge da moeda do pedido.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"order_currency": order.currency, "intent_currency": intent.currency},
            )
        )

    if intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED) and captured_q <= 0:
        issues.append(
            FinancialReconciliationIssue(
                code="captured_intent_without_capture_transaction",
                severity="critical",
                message="Intent capturado/reembolsado não tem transação de captura.",
                order_ref=order.ref,
                intent_ref=intent.ref,
            )
        )

    if intent.status in (PaymentIntent.Status.PENDING, PaymentIntent.Status.AUTHORIZED) and captured_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="open_intent_has_capture",
                severity="error",
                message="Intent ainda está aberto/autorizado, mas já possui captura registrada.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"intent_status": intent.status, "captured_q": captured_q},
            )
        )

    if chargeback_q > 0:
        # Chargeback não é reembolso: o dinheiro voltou por decisão do
        # banco/PSP (disputa de cartão, MED do Pix), não da loja, e tem prazo
        # de contestação. Sem código próprio ele só aparecia diluído no
        # ``net_q``, que é um número — não um pedido para alguém olhar.
        issues.append(
            FinancialReconciliationIssue(
                code="intent_has_chargeback",
                severity="error",
                message="Intent tem chargeback: dinheiro devolvido por decisão do banco/PSP.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={
                    "chargeback_q": chargeback_q,
                    "captured_q": captured_q,
                    "refunded_q": refunded_q,
                },
            )
        )

    if returned_q > captured_q:
        issues.append(
            FinancialReconciliationIssue(
                code="refund_exceeds_capture",
                severity="critical",
                message="Reembolso/chargeback excede o total capturado.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"captured_q": captured_q, "returned_q": returned_q},
            )
        )

    if captured_q > intent.amount_q:
        issues.append(
            FinancialReconciliationIssue(
                code="capture_exceeds_intent_amount",
                severity="critical",
                message="Captura excede o valor autorizado no PaymentIntent.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"captured_q": captured_q, "intent_amount_q": int(intent.amount_q or 0)},
            )
        )

    if order.status == Order.Status.NEW and net_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="paid_order_not_confirmed",
                severity="critical",
                message="Pedido ainda está new, mas há saldo capturado.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"net_q": net_q},
            )
        )

    if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED) and net_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="terminal_order_with_captured_balance",
                severity="critical",
                message="Pedido cancelado/devolvido ainda tem saldo capturado líquido.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"net_q": net_q, "status": order.status},
            )
        )

    strict_paid_statuses = {
        Order.Status.PREPARING,
        Order.Status.READY,
        Order.Status.DISPATCHED,
        Order.Status.DELIVERED,
        Order.Status.COMPLETED,
    }
    if order.status in strict_paid_statuses and _payment_method(order) in {"pix", "card"} and net_q < order.total_q:
        issues.append(
            FinancialReconciliationIssue(
                code="fulfilled_digital_order_underpaid",
                severity="error",
                message="Pedido digital em fluxo operacional avançado tem saldo capturado abaixo do total.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"net_q": net_q, "order_total_q": int(order.total_q or 0), "status": order.status},
            )
        )

    if intent.status in (PaymentIntent.Status.CANCELLED, PaymentIntent.Status.FAILED) and captured_q > 0:
        issues.append(
            FinancialReconciliationIssue(
                code="terminal_intent_has_capture",
                severity="critical",
                message="Intent terminal falho/cancelado possui captura registrada.",
                order_ref=order.ref,
                intent_ref=intent.ref,
                context={"intent_status": intent.status, "captured_q": captured_q},
            )
        )


def _check_cash_ledger(
    *,
    reconciliation_date: date,
    issues: list[FinancialReconciliationIssue],
) -> CashLedgerTotals:
    """Cruza o dinheiro em espécie do dia: Payman × livro-caixa.

    Por que este check existe: até a ADR-022 a reconciliação era
    estruturalmente cega para dinheiro. Estava ancorada no intent de gateway,
    e dinheiro não tinha intent: a venda em espécie era um JSON no pedido e
    uma coluna no turno, nada que somasse com nada. Hoje o mesmo fato (uma nota
    entrou na gaveta) tem DUAS escritas, na mesma transação do banco: o intent
    ``method=cash`` capturado no Payman (``PaymentService.settle``) e a linha
    ``sale``/``cod_settled`` no livro do turno (``cashman.Entry``), ligadas por
    ``payment_ref``. Duas escritas do mesmo fato têm de bater; quando não
    batem, uma das duas mentiu, ou uma venda entrou num livro sem entrar no
    outro.

    O que se compara, num dia local:

    - Payman: ``Σ PaymentTransaction(CAPTURE) − Σ PaymentTransaction(REFUND)``
      dos intents ``method=cash``, com ``created_at`` no dia;
    - livro: ``Σ Entry.amount_q`` de ``sale``, ``cod_settled`` e ``refund``
      com ``at`` no dia (``refund`` já é negativo; ``sale`` de pix/cartão/COD
      vale zero e não pesa).

    Janela: o instante da TRANSAÇÃO de cada lado, não a data do pedido. Na
    venda do PDV a captura do intent e a linha ``sale`` nascem no mesmo
    ``atomic`` (``_settle_pos_sale``), então ``PaymentTransaction.created_at``,
    ``PaymentIntent.captured_at`` e ``Entry.at`` são o mesmo instante; o mesmo
    vale para o estorno do cancel (``REFUND`` + linha ``refund``) e para o
    acerto de entrega (``settle`` + ``cod_settled``). Por isso nada fica
    "no dia errado" de um lado só:

    - COD liquida no ACERTO: no dia da venda a linha ``sale`` vale zero e não
      há intent de dinheiro; no dia do acerto nascem, juntos, o intent
      capturado e o ``cod_settled``. Conta no dia do acerto, nos dois livros.
    - Venda sem turno não existe mais (o PDV recusa antes do commit), então
      não há venda em dinheiro que tenha intent e não tenha linha. O que
      sobra para este check pegar é o inverso e o parcial: um estorno de
      dinheiro feito FORA do PDV (cancel pelo gestor, devolução parcial) grava
      ``REFUND`` no Payman sem linha ``refund`` na gaveta, e aqui aparece.
    - ``float_in``, ``cash_in``, ``cash_out``, ``count`` não são pagamento:
      mexem na gaveta sem tocar no Payman e ficam fora, de propósito.

    Além do total do dia, compara por pedido (``intent.order_ref`` ×
    ``Entry.order_ref``): dois erros que se compensam no total continuam
    sendo dois erros, e a lista de pedidos é o que deixa a divergência
    localizável em vez de ser só um número.
    """
    payman_by_order: defaultdict[str, int] = defaultdict(int)
    payman_captured_q = payman_refunded_q = 0
    cash_tx = (
        PaymentTransaction.objects.filter(
            created_at__date=reconciliation_date,
            intent__method=PaymentIntent.Method.CASH,
            type__in=[PaymentTransaction.Type.CAPTURE, PaymentTransaction.Type.REFUND],
        )
        .values("intent__order_ref", "type")
        .annotate(total=Sum("amount_q"))
    )
    for row in cash_tx:
        amount_q = int(row["total"] or 0)
        order_ref = str(row["intent__order_ref"] or "")
        if row["type"] == PaymentTransaction.Type.CAPTURE:
            payman_captured_q += amount_q
            payman_by_order[order_ref] += amount_q
        else:
            payman_refunded_q += amount_q
            payman_by_order[order_ref] -= amount_q

    ledger_by_order: defaultdict[str, int] = defaultdict(int)
    ledger_by_kind: dict[str, int] = dict.fromkeys(_LEDGER_MONEY_KINDS, 0)
    ledger_rows = (
        Entry.objects.filter(at__date=reconciliation_date, kind__in=_LEDGER_MONEY_KINDS)
        .values("order_ref", "kind")
        .annotate(total=Sum("amount_q"))
    )
    for row in ledger_rows:
        amount_q = int(row["total"] or 0)
        ledger_by_kind[row["kind"]] += amount_q
        ledger_by_order[str(row["order_ref"] or "")] += amount_q

    totals = CashLedgerTotals(
        payman_captured_q=payman_captured_q,
        payman_refunded_q=payman_refunded_q,
        ledger_sale_q=ledger_by_kind[Entry.Kind.SALE],
        ledger_cod_settled_q=ledger_by_kind[Entry.Kind.COD_SETTLED],
        ledger_refund_q=ledger_by_kind[Entry.Kind.REFUND],
    )

    diverging_orders = sorted(
        order_ref
        for order_ref in set(payman_by_order) | set(ledger_by_order)
        if payman_by_order[order_ref] != ledger_by_order[order_ref]
    )
    if totals.difference_q == 0 and not diverging_orders:
        return totals

    if totals.difference_q == 0:
        message = (
            "Dinheiro do dia: os totais do Payman e do livro-caixa batem, "
            "mas há pedidos que divergem entre si (erros que se compensam)."
        )
    else:
        message = (
            "Dinheiro do dia diverge entre o Payman (capturas − estornos em dinheiro) "
            "e o livro-caixa (venda, acerto de entrega, devolução)."
        )
    context: dict[str, int | str] = {
        "payman_cash_q": totals.payman_net_q,
        "ledger_cash_q": totals.ledger_net_q,
        "difference_q": totals.difference_q,
        "order_count": len(diverging_orders),
    }
    if diverging_orders:
        listed = diverging_orders[:_MAX_LISTED_ORDERS]
        context["orders"] = ", ".join(ref or "(sem pedido)" for ref in listed)
        if len(diverging_orders) > _MAX_LISTED_ORDERS:
            context["orders"] += f", … (+{len(diverging_orders) - _MAX_LISTED_ORDERS})"
    issues.append(
        FinancialReconciliationIssue(
            code="cash_ledger_mismatch",
            severity="error",
            message=message,
            context=context,
        )
    )
    return totals


def _check_courier_change(
    *,
    reconciliation_date: date,
    issues: list[FinancialReconciliationIssue],
) -> None:
    """Troco que saiu com o entregador e não voltou (nem "voltou zero").

    ``courier_out``/``courier_in`` não são pagamento: são custódia temporária do
    entregador, e ficam de fora do cruzamento Payman × livro por construção
    (``_LEDGER_MONEY_KINDS``). O que se confere aqui é o espelho: todo
    ``courier_out`` até o dia tem de ter o seu ``courier_in`` (o acerto da
    entrega exige o valor que voltou, zero incluído). Saiu e não voltou é
    dinheiro da gaveta na rua sem ninguém ter dito o que aconteceu: ``warning``,
    porque a causa comum é entrega ainda em andamento ou acerto que ficou para
    amanhã, e o alerta some sozinho quando o acerto acontece.
    """
    out_rows = (
        Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, at__date__lte=reconciliation_date)
        .values("order_ref")
        .annotate(total=Sum("amount_q"))
    )
    out_by_order = {str(row["order_ref"] or ""): -int(row["total"] or 0) for row in out_rows}
    if not out_by_order:
        return
    back_refs = set(
        Entry.objects.filter(kind=Entry.Kind.COURIER_IN, order_ref__in=list(out_by_order)).values_list(
            "order_ref", flat=True
        )
    )
    unsettled = sorted(ref for ref in out_by_order if ref not in back_refs)
    if not unsettled:
        return
    listed = unsettled[:_MAX_LISTED_ORDERS]
    orders = ", ".join(ref or "(sem pedido)" for ref in listed)
    if len(unsettled) > _MAX_LISTED_ORDERS:
        orders += f", … (+{len(unsettled) - _MAX_LISTED_ORDERS})"
    issues.append(
        FinancialReconciliationIssue(
            code="courier_change_unsettled",
            severity="warning",
            message=(
                "Troco levado pelo entregador sem acerto: saiu da gaveta e ninguém disse "
                "quanto voltou (o acerto da entrega fecha isso, mesmo que tenha voltado zero)."
            ),
            context={
                "order_count": len(unsettled),
                "courier_out_q": sum(out_by_order[ref] for ref in unsettled),
                "orders": orders,
            },
        )
    )


def _referenced_intent_refs(payment: dict) -> set[str]:
    """Os intents que ``Order.data.payment`` aponta: o de cima e os dos tenders."""
    refs: set[str] = set()
    top = str(payment.get("intent_ref") or "").strip()
    if top:
        refs.add(top)
    for tender in payment.get("tenders") or []:
        if isinstance(tender, dict) and tender.get("intent_ref"):
            refs.add(str(tender["intent_ref"]).strip())
    return refs


def _transaction_totals(rows) -> defaultdict[int, dict[str, int]]:
    totals: defaultdict[int, dict[str, int]] = defaultdict(lambda: {"capture": 0, "refund": 0, "chargeback": 0})
    for row in rows:
        tx_type = row["type"]
        if tx_type in totals[row["intent_id"]]:
            totals[row["intent_id"]][tx_type] += int(row["total"] or 0)
    return totals


def _payment_data(order: Order) -> dict:
    payment = (order.data or {}).get("payment") or {}
    return payment if isinstance(payment, dict) else {}


def _payment_method(order: Order) -> str:
    return str(_payment_data(order).get("method") or "").strip()


def _summary_dict(report: FinancialReconciliationReport) -> dict:
    data = report.as_dict()
    return {key: value for key, value in data.items() if key != "issues"}
