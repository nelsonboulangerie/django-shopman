"""O freio e o medidor da porta de IA (ID3A-PLAN, E1).

Toda chamada paga que passa por ``shopman.shop.ai`` faz três coisas aqui:

1. **Pergunta se pode** (``check``): a loja desligou a IA (``Shop.ai_limits``
   ``enabled: false``) ou o teto do dia já foi atingido? Então nem sai.
2. **Reserva** o custo estimado no ``AiSpendDay`` do dia, na loja e na função,
   com um ``UPDATE`` condicional: duas chamadas ao mesmo tempo não furam o teto.
3. **Acerta** depois: devolve a reserva, soma o custo real e grava o
   ``AiInvocation``. A 80% do teto chega um aviso; no teto, um alerta e a IA para
   até o dia seguinte.

A estimativa erra para cima: entrada pelo tamanho do pedido (um token a cada três
caracteres) e saída pelo ``max_tokens`` inteiro. Modelo fora da tabela pública de
preço conta pelo preço mais alto dela.

Medir nunca derruba a chamada, mas o freio derruba: quando ele diz não, levanta
``AIDisabled`` ou ``AIBudgetExceeded``, que são ``AINotConfigured`` para quem
chama. Cada função já sabe seguir sem IA quando ela não está configurada.
"""

from __future__ import annotations

import json
import logging
import math
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from shopman.shop.ai import AINotConfigured
from shopman.shop.services.ai_pricing import LLM_PRICES, model_prices

logger = logging.getLogger(__name__)

#: Teto diário da loja quando ``Shop.ai_limits`` não diz outro (D-039).
DEFAULT_SHOP_USD_PER_DAY = 3.0
#: Nenhum teto passa disto sem mudança de código revisada: protege do "3000" no lugar de "3".
HARD_CAP_USD_PER_DAY = 20.0
#: Teto próprio de função quando a loja não diz outro (D-039: triagem e resumo do Suporte).
DEFAULT_PURPOSE_USD_PER_DAY: dict[str, float] = {
    "support_triage": 0.50,
    "support_summary": 1.00,
}
#: Fração do teto que dispara o aviso.
WARNING_FRACTION = 0.80
#: Jev (TypeSafe): US$ 0,042 por milhão de tokens de entrada, saída grátis.
JEV_PRICES = (0.042, 0.0)
#: Saída suposta quando o pedido não diz ``max_tokens``.
DEFAULT_MAX_OUTPUT_TOKENS = 4096
CHARS_PER_TOKEN = 3

SHOP_SCOPE = "shop"


class AIDisabled(AINotConfigured):
    """A loja desligou a IA paga (``Shop.ai_limits`` ``enabled: false``)."""


class AIBudgetExceeded(AINotConfigured):
    """O teto de gasto do dia, da loja ou da função, foi atingido."""


# ── Política ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Limits:
    enabled: bool = True
    shop_usd_per_day: float = DEFAULT_SHOP_USD_PER_DAY
    purposes: dict[str, float] = field(default_factory=dict)

    def cap_usd(self, scope: str) -> float | None:
        if scope == SHOP_SCOPE:
            return self.shop_usd_per_day
        if scope in self.purposes:
            return self.purposes[scope]
        return DEFAULT_PURPOSE_USD_PER_DAY.get(scope)


def _usd(value, default: float | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or number < 0:
        return default
    return min(number, HARD_CAP_USD_PER_DAY)


def limits() -> Limits:
    """A política da loja, lida da ``Shop``. JSON torto vale o padrão, nunca "sem teto"."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    raw = getattr(shop, "ai_limits", None) if shop else None
    raw = raw if isinstance(raw, dict) else {}
    purposes_raw = raw.get("purposes")
    purposes: dict[str, float] = {}
    if isinstance(purposes_raw, dict):
        for name, value in purposes_raw.items():
            cap = _usd(value, None)
            if cap is not None:
                purposes[str(name)] = cap
    return Limits(
        enabled=raw.get("enabled", True) is not False,
        shop_usd_per_day=_usd(raw.get("usd_per_day"), DEFAULT_SHOP_USD_PER_DAY),
        purposes=purposes,
    )


def _micros(usd: float) -> int:
    return int(math.ceil(usd * 1_000_000))


def _scopes(purpose: str) -> tuple[str, ...]:
    return (SHOP_SCOPE, purpose)


def _today():
    return timezone.localdate()


# ── Preço e estimativa ──────────────────────────────────────────────────────


def prices_for(model: str, *, protocol: str = "anthropic") -> tuple[tuple[float, float], bool]:
    """``((entrada, saída) em US$/M, estimado?)``. Fora da tabela: o mais caro dela."""
    if protocol == "jev":
        return JEV_PRICES, False
    prices = model_prices(model)
    if prices is not None:
        return prices, False
    worst_in = max(p[0] for p in LLM_PRICES.values())
    worst_out = max(p[1] for p in LLM_PRICES.values())
    return (worst_in, worst_out), True


def estimate_input_tokens(request: dict) -> int:
    parts = [request.get(key) for key in ("system", "messages", "tools")]
    try:
        size = len(json.dumps(parts, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        size = len(str(parts))
    return max(1, size // CHARS_PER_TOKEN)


def estimate_usd(model: str, *, tokens_in: int, tokens_out: int, protocol: str = "anthropic") -> float:
    (price_in, price_out), _estimated = prices_for(model, protocol=protocol)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def _token(usage, key: str) -> int:
    value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def usage_tokens(usage) -> dict[str, int]:
    return {
        "tokens_in": _token(usage, "input_tokens"),
        "tokens_out": _token(usage, "output_tokens"),
        "tokens_cache_read": _token(usage, "cache_read_input_tokens"),
        "tokens_cache_write": _token(usage, "cache_creation_input_tokens"),
    }


def actual_usd(model: str, tokens: dict[str, int], *, protocol: str = "anthropic") -> tuple[float, bool]:
    from shopman.shop.services.ai_pricing import CACHE_READ_FACTOR, CACHE_WRITE_FACTOR

    (price_in, price_out), estimated = prices_for(model, protocol=protocol)
    usd = (
        tokens["tokens_in"] * price_in
        + tokens["tokens_cache_read"] * price_in * CACHE_READ_FACTOR
        + tokens["tokens_cache_write"] * price_in * CACHE_WRITE_FACTOR
        + tokens["tokens_out"] * price_out
    ) / 1_000_000
    return usd, estimated


# ── Freio ───────────────────────────────────────────────────────────────────


def check(purpose: str) -> None:
    """Levanta ``AIDisabled`` ou ``AIBudgetExceeded`` se a função não pode chamar agora."""
    from shopman.shop.models import AiSpendDay

    policy = limits()
    if not policy.enabled:
        raise AIDisabled("a IA está desligada na loja (Loja → Inteligência artificial → freio de IA)")
    rows = {
        row.scope: row
        for row in AiSpendDay.objects.filter(date=_today(), scope__in=_scopes(purpose))
    }
    for scope in _scopes(purpose):
        cap = policy.cap_usd(scope)
        row = rows.get(scope)
        if cap is None or row is None:
            continue
        if row.spent_usd_micros + max(0, row.reserved_usd_micros) >= _micros(cap):
            raise AIBudgetExceeded(_budget_message(scope, cap))


def _budget_message(scope: str, cap: float) -> str:
    where = "da loja" if scope == SHOP_SCOPE else f"da função {scope}"
    return f"o teto de gasto de IA {where} (US$ {cap:.2f} por dia) foi atingido; volta amanhã"


@dataclass
class Lease:
    purpose: str
    connection_ref: str
    model: str
    protocol: str
    reserved_micros: int
    started: float = field(default_factory=time.perf_counter)


def reserve(
    purpose: str,
    *,
    connection_ref: str,
    model: str,
    estimate_usd_value: float,
    protocol: str = "anthropic",
) -> Lease:
    """Reserva o custo estimado na loja e na função, ou recusa e grava a recusa."""
    from shopman.shop.models import AiOutcome, AiSpendDay

    policy = limits()
    lease = Lease(purpose, connection_ref, model, protocol, _micros(estimate_usd_value))
    if not policy.enabled:
        _record(lease, outcome=AiOutcome.KILLED, reserved=0)
        raise AIDisabled("a IA está desligada na loja (Loja → Inteligência artificial → freio de IA)")
    today = _today()
    denied_scope = None
    for scope in _scopes(purpose):
        AiSpendDay.objects.get_or_create(date=today, scope=scope)
    with transaction.atomic():
        for scope in _scopes(purpose):
            cap = policy.cap_usd(scope)
            rows = AiSpendDay.objects.filter(date=today, scope=scope)
            if cap is not None:
                rows = rows.alias(total=F("spent_usd_micros") + F("reserved_usd_micros")).filter(
                    total__lte=_micros(cap) - lease.reserved_micros
                )
            if not rows.update(
                reserved_usd_micros=F("reserved_usd_micros") + lease.reserved_micros,
                calls=F("calls") + 1,
            ):
                denied_scope = scope
                transaction.set_rollback(True)
                break
    if denied_scope is not None:
        cap = policy.cap_usd(denied_scope) or 0.0
        AiSpendDay.objects.filter(date=today, scope__in=_scopes(purpose)).update(denied=F("denied") + 1)
        _record(lease, outcome=AiOutcome.BUDGET_DENIED, reserved=0)
        _alert_stopped(denied_scope, cap)
        raise AIBudgetExceeded(_budget_message(denied_scope, cap))
    return lease


def settle(lease: Lease, *, usage=None, error: BaseException | None = None) -> None:
    """Devolve a reserva, soma o custo real e grava a chamada. Nunca levanta."""
    from shopman.shop.models import AiOutcome, AiSpendDay

    try:
        tokens = usage_tokens(usage) if usage is not None else usage_tokens({})
        usd, estimated = actual_usd(lease.model, tokens, protocol=lease.protocol)
        spent = _micros(usd) if usd > 0 else 0
        with transaction.atomic():
            AiSpendDay.objects.filter(date=_today(), scope__in=_scopes(lease.purpose)).update(
                reserved_usd_micros=F("reserved_usd_micros") - lease.reserved_micros,
                spent_usd_micros=F("spent_usd_micros") + spent,
                errors=F("errors") + (1 if error is not None else 0),
            )
        _record(
            lease,
            outcome=AiOutcome.ERROR if error is not None else AiOutcome.OK,
            reserved=lease.reserved_micros,
            cost=spent,
            estimated=estimated,
            tokens=tokens,
            error_type=type(error).__name__ if error is not None else "",
        )
        _alert_if_near_cap(lease.purpose)
    except Exception:
        logger.exception("ai_governor.settle_failed purpose=%s", lease.purpose)


@contextmanager
def metered(
    purpose: str,
    *,
    connection_ref: str,
    model: str,
    estimate_usd_value: float,
    protocol: str = "anthropic",
):
    """Reserva antes, acerta depois. O ``yield`` entrega um dict onde se põe o ``usage``."""
    lease = reserve(
        purpose,
        connection_ref=connection_ref,
        model=model,
        estimate_usd_value=estimate_usd_value,
        protocol=protocol,
    )
    box: dict = {}
    try:
        yield box
    except BaseException as exc:
        settle(lease, usage=box.get("usage"), error=exc)
        raise
    settle(lease, usage=box.get("usage"))


def _record(
    lease: Lease,
    *,
    outcome: str,
    reserved: int,
    cost: int = 0,
    estimated: bool = False,
    tokens: dict[str, int] | None = None,
    error_type: str = "",
) -> None:
    from shopman.shop.models import AiInvocation

    tokens = tokens or {}
    latency = int((time.perf_counter() - lease.started) * 1000)
    try:
        AiInvocation.objects.create(
            purpose=lease.purpose,
            connection_ref=lease.connection_ref[:40],
            model=lease.model[:80],
            outcome=outcome,
            error_type=error_type[:80],
            tokens_in=tokens.get("tokens_in", 0),
            tokens_out=tokens.get("tokens_out", 0),
            tokens_cache_read=tokens.get("tokens_cache_read", 0),
            tokens_cache_write=tokens.get("tokens_cache_write", 0),
            reserved_usd_micros=reserved,
            cost_usd_micros=cost,
            cost_estimated=estimated,
            latency_ms=max(0, latency),
        )
        logger.info(
            "ai.invocation purpose=%s outcome=%s model=%s latency_ms=%d cost_usd_micros=%d",
            lease.purpose, outcome, lease.model, latency, cost,
        )
    except Exception:
        logger.exception("ai_governor.record_failed purpose=%s", lease.purpose)


# ── Alertas ─────────────────────────────────────────────────────────────────


def _scope_label(scope: str) -> str:
    return "da loja" if scope == SHOP_SCOPE else f"da função {scope}"


def _alert_once(alert_type: str, severity: str, message: str, marker: str) -> None:
    from shopman.shop.adapters import alert

    try:
        start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if alert.recent_exists(alert_type, start, message_contains=marker, active_only=False):
            return
        alert.create(alert_type, severity, message)
    except Exception:
        logger.exception("ai_governor.alert_failed type=%s", alert_type)


def _alert_stopped(scope: str, cap: float) -> None:
    day = _today().strftime("%d/%m/%Y")
    _alert_once(
        "ai_budget_stopped",
        "error",
        f"A IA parou em {day}: o teto de gasto {_scope_label(scope)} (US$ {cap:.2f} por dia) foi "
        "atingido. Volta amanhã, ou suba o teto em Loja → Inteligência artificial.",
        f"{_scope_label(scope)} (",
    )


def _alert_if_near_cap(purpose: str) -> None:
    from shopman.shop.models import AiSpendDay

    policy = limits()
    for row in AiSpendDay.objects.filter(date=_today(), scope__in=_scopes(purpose)):
        cap = policy.cap_usd(row.scope)
        if not cap:
            continue
        if row.spent_usd_micros >= _micros(cap * WARNING_FRACTION):
            day = _today().strftime("%d/%m/%Y")
            _alert_once(
                "ai_budget_warning",
                "warning",
                f"A IA gastou US$ {row.spent_usd:.2f} em {day}, mais de 80% do teto "
                f"{_scope_label(row.scope)} (US$ {cap:.2f} por dia).",
                f"teto {_scope_label(row.scope)} (",
            )
