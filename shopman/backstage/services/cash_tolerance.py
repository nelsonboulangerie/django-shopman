"""A tolerância do caixa: a diferença que o gerente aceita sem ir atrás.

Decisão do dono (04/10/2026): o padrão é **0,5% do dinheiro do dia**, com piso
de **R$ 2** e teto de **R$ 20**, configurável por loja (``Shop.defaults["pos"]
["cash_tolerance"]``, no Admin da loja) e por terminal (``Terminal.metadata
["cash_tolerance"]``, no Admin do terminal; vale por cima da loja, chave a chave).

## O operador nunca vê o veredito

O fechamento continua cego (ADR-011 §4): a tela do Fim do dia diz "Caixa fechado
· contagem cega registrada" e mais nada. O veredito nasce DEPOIS do fechamento,
por quem ouve o livro (``shift_closed``), e vai para dois lugares que o balcão
não lê:

* uma nota no livro do turno (``note`` com ``payload.event = "cash_tolerance"``),
  congelada com a régua daquele dia (mudar a configuração amanhã não reescreve o
  passado). O relatório do turno no Admin (``cashman.audit_shift``) lê a última;
* fora da tolerância, um ``OperatorAlert`` ``cash_out_of_tolerance`` no público
  ``finance``, que só quem audita o caixa enxerga.

A correção da contagem pelo gerente (``count_correction``) refaz o veredito: a
nota nova vale, a antiga fica como história.

## "Dinheiro do dia"

É o dinheiro que entrou na gaveta pelo trabalho do turno: vendas em dinheiro
(``sale``), acertos de entrega (``cod_settled``) e acertos de conta
(``account_settled``). Fundo de troco e suprimento não entram: não são venda, e
somá-los alargaria a régua num dia de troco gordo sem nada ter sido vendido.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Os padrões do dono: 0,5% do dinheiro do dia, entre R$ 2 e R$ 20.
DEFAULT_PERCENT = Decimal("0.5")
DEFAULT_MIN_Q = 200
DEFAULT_MAX_Q = 2000

#: A chave nos dois JSONs (loja e terminal).
CONFIG_KEY = "cash_tolerance"

#: A nota do livro que guarda o veredito (lida pelo Admin do turno).
TOLERANCE_EVENT = "cash_tolerance"

#: O alerta de fora da tolerância (público ``finance``).
ALERT_TYPE = "cash_out_of_tolerance"


@dataclass(frozen=True)
class TolerancePolicy:
    percent: Decimal = DEFAULT_PERCENT
    min_q: int = DEFAULT_MIN_Q
    max_q: int = DEFAULT_MAX_Q

    def tolerance_q(self, cash_received_q: int) -> int:
        """``percent`` do dinheiro do dia, preso entre o piso e o teto."""
        raw = (Decimal(max(0, int(cash_received_q))) * self.percent / Decimal(100)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return max(self.min_q, min(self.max_q, int(raw)))

    def as_dict(self) -> dict:
        return {"percent": str(self.percent), "min_q": self.min_q, "max_q": self.max_q}


def _parse(raw, base: TolerancePolicy) -> TolerancePolicy:
    """Lê um bloco ``cash_tolerance`` por cima de ``base``; valor inválido mantém o de baixo.

    Erro de digitação nunca desliga a régua nem a escancara: cai no valor de baixo
    (o da loja, ou o padrão do dono), com aviso no log.
    """
    if not isinstance(raw, dict):
        return base
    percent, min_q, max_q = base.percent, base.min_q, base.max_q
    if raw.get("percent") not in (None, ""):
        try:
            candidate = Decimal(str(raw["percent"]))
            if candidate < 0 or candidate > 100:
                raise InvalidOperation
            percent = candidate
        except (InvalidOperation, ValueError):
            logger.warning("cash_tolerance.percent inválido (%r); mantendo %s.", raw.get("percent"), percent)
    for key in ("min_q", "max_q"):
        value = raw.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            logger.warning("cash_tolerance.%s inválido (%r); mantendo o valor de baixo.", key, value)
            continue
        if key == "min_q":
            min_q = value
        else:
            max_q = value
    if max_q < min_q:
        logger.warning("cash_tolerance com teto (%s) abaixo do piso (%s); usando o piso como teto.", max_q, min_q)
        max_q = min_q
    return TolerancePolicy(percent=percent, min_q=min_q, max_q=max_q)


def shop_policy() -> TolerancePolicy:
    """A régua da loja (``Shop.defaults["pos"]["cash_tolerance"]``), ou o padrão do dono."""
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        defaults = (getattr(shop, "defaults", None) or {}) if shop else {}
        pos_cfg = defaults.get("pos") if isinstance(defaults, dict) else {}
        raw = (pos_cfg or {}).get(CONFIG_KEY)
    except Exception:
        logger.debug("cash_tolerance.shop_lookup_failed", exc_info=True)
        return TolerancePolicy()
    return _parse(raw, TolerancePolicy())


def policy_for(terminal) -> TolerancePolicy:
    """A régua deste terminal: a da loja, com o que o terminal sobrescreve por cima."""
    base = shop_policy()
    metadata = getattr(terminal, "metadata", None) if terminal is not None else None
    if not isinstance(metadata, dict):
        return base
    return _parse(metadata.get(CONFIG_KEY), base)


def cash_received_q(shift) -> int:
    """O dinheiro do dia deste turno: vendas, acertos de entrega e de conta."""
    from django.db.models import Sum
    from shopman.cashman.models import Entry

    total = (
        Entry.objects.filter(
            shift=shift,
            kind__in=(Entry.Kind.SALE, Entry.Kind.COD_SETTLED, Entry.Kind.ACCOUNT_SETTLED),
            amount_q__gt=0,
        ).aggregate(total=Sum("amount_q"))["total"]
    )
    return int(total or 0)


def record_verdict(shift, *, operator=None):
    """Grava o veredito do turno no livro e, fora da régua, avisa quem audita.

    Devolve a nota gravada, ou ``None`` quando o turno ainda não foi contado.
    """
    from shopman.cashman import services as cash
    from shopman.cashman.models import Entry

    difference_q = cash.difference(shift)
    if difference_q is None:
        return None
    if operator is None:
        count = Entry.objects.filter(shift=shift, kind=Entry.Kind.COUNT).order_by("id").first()
        operator = count.operator if count is not None else shift.opened_by
    policy = policy_for(shift.terminal)
    received = cash_received_q(shift)
    tolerance = policy.tolerance_q(received)
    within = abs(int(difference_q)) <= tolerance
    note = cash.record(
        Entry.Kind.NOTE,
        shift=shift,
        operator=operator,
        reason="Veredito da tolerância do caixa",
        payload={
            "event": TOLERANCE_EVENT,
            "within": within,
            "difference_q": int(difference_q),
            "tolerance_q": tolerance,
            "cash_received_q": received,
            "policy": policy.as_dict(),
        },
    )
    if not within:
        _alert(shift, difference_q=int(difference_q), tolerance_q=tolerance)
    return note


def _alert(shift, *, difference_q: int, tolerance_q: int) -> None:
    from shopman.backstage.services.alerts import create_alert
    from shopman.utils.monetary import format_money

    label = str(shift.terminal.label or shift.terminal.ref)
    sign = "sobra" if difference_q > 0 else "falta"
    when = shift.closed_at or shift.opened_at
    day = timezone.localtime(when).strftime("%d/%m")
    create_alert(
        type=ALERT_TYPE,
        severity="warning",
        message=(
            f"O caixa do {label} de {day} fechou fora da tolerância: {sign} de "
            f"R$ {format_money(abs(difference_q))}, e a tolerância do dia era R$ {format_money(tolerance_q)}. "
            "Confira as aberturas da gaveta no relatório do turno, no gestor."
        ),
    )


def on_shift_closed(sender, shift, count=None, **kwargs) -> None:
    """``shift_closed``: o veredito nasce depois do fechamento cego, nunca antes."""
    try:
        record_verdict(shift, operator=getattr(count, "operator", None))
    except Exception:
        logger.exception("cash_tolerance.verdict_failed", extra={"shift": getattr(shift, "pk", None)})


def on_entry_recorded(sender, entry, **kwargs) -> None:
    """A correção da contagem refaz o veredito (o gerente recontou)."""
    from shopman.cashman.models import Entry

    if entry.kind != Entry.Kind.COUNT_CORRECTION:
        return
    try:
        record_verdict(entry.shift, operator=entry.operator)
    except Exception:
        logger.exception("cash_tolerance.verdict_failed", extra={"shift": entry.shift_id})
