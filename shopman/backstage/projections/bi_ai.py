"""B.I. — quanto a casa gasta com IA e como a Concierge está respondendo (DEV-2026-067).

Só do Dono, só leitura. Três blocos:

- **Gasto por papel e por modelo**: o medidor da porta de IA (``AiInvocation``), uma linha
  por chamada, inclusive a recusada pelo freio. O dinheiro é micro-dólar inteiro, como o
  medidor guarda. Em reais pela PTAX de venda do dia (``services.usd_brl``), e a cotação
  usada vai junto, por dia (decisão de 21/11/2026: o dono pensa em reais).
- **A pauta da conferência**: o veredito da conferência antes do envio
  (``envelope["conference"]`` do primeiro bloco da resposta), com os motivos de reprovação
  somados. Ao lado, o que falta à casa: as perguntas que a Concierge passou à equipe
  ("vou verificar", cartão ``concierge_verify``), agrupadas, com o caminho para o Admin,
  onde a resposta vira pergunta frequente.
- **A alternativa segura**: as respostas que a conferência reprovou. Em sombra (hoje), a
  resposta original saiu e a lista é do que iria para a alternativa.

Fala de cliente só sai pelo redator da Concierge (``shop.concierge_reading``); sem ele,
o texto não sai. Tudo calculado na leitura (ADR-021 §3).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.utils import timezone

DEFAULT_WINDOW_DAYS = 28
MAX_WINDOW_DAYS = 366
MAX_FALLBACKS = 50
MAX_GAPS = 30

#: A conferência ainda só mede (#3040 liga a alternativa segura de verdade).
CONFERENCE_MODE = "shadow"

#: O motivo de reprovação, como o dono lê. A chave é a do framework (``reply.conference``).
REASON_LABELS = {
    "no_next_step": "Sem próximo passo para o cliente",
    "judge_off_target": "Fala de outra coisa",
    "judge_rejected": "O juiz achou que não atende",
    "judge_contradicts": "Se contradiz",
    "unconferred": "Ficou sem conferir (o juiz não respondeu)",
    "held": "A verificação de saída segurou",
}

OMITTED_TEXT = "[texto omitido]"
VERIFY_ALERT_TYPE = "concierge_verify"
_QUESTION_RE = re.compile(r"“([^”]+)”")


@dataclass(frozen=True)
class BIAiSpendRow:
    """Um papel num modelo: chamadas e gasto no período."""

    purpose: str
    purpose_label: str
    model: str
    calls: int
    errors: int
    #: Recusadas pelo teto de gasto ou com a IA desligada na loja.
    denied: int
    cost_usd_micros: int
    #: ``None`` quando algum dia da linha ficou sem cotação.
    cost_brl_micros: int | None
    #: Alguma chamada usou modelo fora da tabela de preço (contado pelo preço mais alto).
    estimated: bool


@dataclass(frozen=True)
class BIAiSpendDay:
    """Um dia: o gasto e a cotação usada para dizê-lo em reais."""

    date: str
    cost_usd_micros: int
    cost_brl_micros: int | None
    #: PTAX de venda usada (R$ por US$, 4 casas), em texto para não perder casa.
    rate: str | None
    #: O dia da PTAX (fim de semana e feriado usam a do último dia útil).
    quoted_on: str | None
    #: A cotação ainda pode mudar (a de hoje antes de publicada, ou a API fora).
    provisional: bool


@dataclass(frozen=True)
class BIAiReason:
    reason: str
    label: str
    count: int


@dataclass(frozen=True)
class BIAiGap:
    """Uma pergunta que a Concierge passou à equipe, agrupada pelo texto."""

    question: str
    count: int
    last_at: str
    admin_url: str


@dataclass(frozen=True)
class BIAiFallback:
    """Uma resposta reprovada pela conferência, com a fala do cliente redigida."""

    at: str
    conversation_id: int
    customer_text: str
    reply_text: str
    reasons: tuple[str, ...]
    admin_url: str


@dataclass(frozen=True)
class BIAiReport:
    date_from: str
    date_to: str
    #: ``shadow``: a conferência só mede. ``enforce``: a reprovada não sai.
    conference_mode: str
    cost_usd_micros: int
    cost_brl_micros: int | None
    calls: int
    errors: int
    denied: int
    estimated_calls: int
    #: Algum dia do período usou cotação provisória.
    provisional_quotes: bool
    rows: tuple[BIAiSpendRow, ...]
    days: tuple[BIAiSpendDay, ...]
    #: Respostas que passaram pela conferência no período.
    conferred: int
    #: Delas, as que a conferência reprovou.
    would_fall: int
    reasons: tuple[BIAiReason, ...]
    gaps: tuple[BIAiGap, ...]
    fallbacks: tuple[BIAiFallback, ...]


def _window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = timezone.localdate()
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days >= MAX_WINDOW_DAYS:
        date_from = date_to - timedelta(days=MAX_WINDOW_DAYS - 1)
    return date_from, date_to


def _redacted(text: str) -> str:
    from shopman.shop import concierge_reading

    clean = concierge_reading.redact(text)
    return OMITTED_TEXT if clean is None else clean


def _admin_url(name: str, *args, query: dict | None = None) -> str:
    from django.urls import NoReverseMatch, reverse

    try:
        url = reverse(name, args=args)
    except NoReverseMatch:
        return ""
    return f"{url}?{urlencode(query)}" if query else url


def _sum_or_none(values: list[int | None]) -> int | None:
    return None if any(v is None for v in values) else sum(v for v in values if v is not None)


def _spend(since: datetime, until: datetime, tz):
    from django.db.models import Count, Q, Sum
    from django.db.models.functions import TruncDate

    from shopman.shop.ai import PURPOSES
    from shopman.shop.models import AiInvocation, AiOutcome
    from shopman.shop.services import usd_brl

    grouped = (
        AiInvocation.objects.filter(created_at__gte=since, created_at__lt=until)
        .annotate(day=TruncDate("created_at", tzinfo=tz))
        .values("purpose", "model", "day")
        .annotate(
            calls=Count("id"),
            errors=Count("id", filter=Q(outcome=AiOutcome.ERROR)),
            denied=Count("id", filter=Q(outcome__in=(AiOutcome.BUDGET_DENIED, AiOutcome.KILLED))),
            estimated=Count("id", filter=Q(cost_estimated=True)),
            cost=Sum("cost_usd_micros"),
        )
    )
    cells = list(grouped)
    quotes = usd_brl.quotes_for({cell["day"] for cell in cells})

    def brl(usd: int, day: date) -> int | None:
        quote = quotes.get(day)
        return None if quote is None else usd_brl.brl_micros(usd, quote.rate)

    rows: dict[tuple[str, str], dict] = {}
    days: dict[date, int] = defaultdict(int)
    for cell in cells:
        key = (cell["purpose"], cell["model"] or "")
        row = rows.setdefault(key, {"calls": 0, "errors": 0, "denied": 0, "estimated": 0, "usd": 0, "brl": []})
        cost = int(cell["cost"] or 0)
        row["calls"] += cell["calls"]
        row["errors"] += cell["errors"]
        row["denied"] += cell["denied"]
        row["estimated"] += cell["estimated"]
        row["usd"] += cost
        row["brl"].append(brl(cost, cell["day"]))
        days[cell["day"]] += cost

    spend_rows = tuple(sorted(
        (
            BIAiSpendRow(
                purpose=purpose,
                purpose_label=PURPOSES.get(purpose, purpose),
                model=model,
                calls=row["calls"],
                errors=row["errors"],
                denied=row["denied"],
                cost_usd_micros=row["usd"],
                cost_brl_micros=_sum_or_none(row["brl"]),
                estimated=row["estimated"] > 0,
            )
            for (purpose, model), row in rows.items()
        ),
        key=lambda r: (-r.cost_usd_micros, -r.calls, r.purpose, r.model),
    ))
    spend_days = []
    for day in sorted(days):
        quote = quotes.get(day)
        spend_days.append(BIAiSpendDay(
            date=day.isoformat(),
            cost_usd_micros=days[day],
            cost_brl_micros=brl(days[day], day),
            rate=None if quote is None else f"{quote.rate:.4f}",
            quoted_on=None if quote is None else quote.quoted_on.isoformat(),
            provisional=bool(quote and quote.provisional),
        ))
    return spend_rows, tuple(spend_days), sum(row["estimated"] for row in rows.values())


def _customer_text(message) -> str:
    """As falas do cliente que esta resposta respondeu (depois da resposta anterior)."""
    from shopman.shop.models import ConversationMessage

    previous = (
        ConversationMessage.objects.filter(
            conversation_id=message.conversation_id,
            kind=ConversationMessage.Kind.REPLY,
            created_at__lt=message.created_at,
        )
        .order_by("-created_at", "-pk")
        .values_list("created_at", flat=True)
        .first()
    )
    inbound = ConversationMessage.objects.filter(
        conversation_id=message.conversation_id,
        kind=ConversationMessage.Kind.INBOUND,
        created_at__lte=message.created_at,
    )
    if previous is not None:
        inbound = inbound.filter(created_at__gt=previous)
    return " / ".join(text for text in inbound.order_by("created_at", "pk").values_list("text", flat=True) if text)


def _conference(since: datetime, until: datetime):
    from shopman.shop.models import ConversationMessage

    replies = ConversationMessage.objects.filter(
        kind=ConversationMessage.Kind.REPLY,
        created_at__gte=since,
        created_at__lt=until,
        envelope__has_key="conference",
    ).order_by("-created_at", "-pk")

    conferred = 0
    reasons: dict[str, int] = defaultdict(int)
    fallbacks: list[BIAiFallback] = []
    would_fall = 0
    for message in replies.iterator():
        record = (message.envelope or {}).get("conference") or {}
        if not isinstance(record, dict) or "decision" not in record:
            continue
        conferred += 1
        if record.get("decision") != "fallback":
            continue
        would_fall += 1
        failed = [
            str(check.get("reason") or name)
            for name, check in (record.get("checks") or {}).items()
            if isinstance(check, dict) and check.get("status") != "pass"
        ]
        for reason in failed:
            reasons[reason] += 1
        if len(fallbacks) < MAX_FALLBACKS:
            fallbacks.append(BIAiFallback(
                at=timezone.localtime(message.created_at).isoformat(),
                conversation_id=message.conversation_id,
                customer_text=_redacted(_customer_text(message)),
                reply_text=_redacted(message.text),
                reasons=tuple(REASON_LABELS.get(reason, reason) for reason in failed),
                admin_url=_admin_url("admin:shop_conversation_change", message.conversation_id),
            ))
    reason_rows = tuple(sorted(
        (BIAiReason(reason=key, label=REASON_LABELS.get(key, key), count=count) for key, count in reasons.items()),
        key=lambda r: (-r.count, r.label),
    ))
    return conferred, would_fall, reason_rows, tuple(fallbacks)


def _question_key(question: str) -> str:
    plain = unicodedata.normalize("NFKD", question.casefold())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w\s]", " ", plain).split())


def _gaps(since: datetime, until: datetime) -> tuple[BIAiGap, ...]:
    from shopman.backstage.models import OperatorAlert

    groups: dict[str, dict] = {}
    alerts = OperatorAlert.objects.filter(
        type=VERIFY_ALERT_TYPE, created_at__gte=since, created_at__lt=until
    ).order_by("created_at", "pk").values_list("message", "created_at")
    for message, created_at in alerts:
        for asked in _QUESTION_RE.findall(message or ""):
            question = _redacted(asked.strip())
            key = _question_key(question)
            if not key:
                continue
            group = groups.setdefault(key, {"question": question, "count": 0, "last_at": created_at})
            group["count"] += 1
            group["last_at"] = max(group["last_at"], created_at)
            group["question"] = question
    rows = sorted(groups.values(), key=lambda g: (-g["count"], -g["last_at"].timestamp()))[:MAX_GAPS]
    return tuple(
        BIAiGap(
            question=g["question"],
            count=g["count"],
            last_at=timezone.localtime(g["last_at"]).isoformat(),
            admin_url=_admin_url("admin:shop_faqentry_add", query={"question": g["question"][:220]}),
        )
        for g in rows
    )


def build_bi_ai(*, date_from: date | None = None, date_to: date | None = None) -> BIAiReport:
    start_day, end_day = _window(date_from, date_to)
    tz = timezone.get_current_timezone()
    since = datetime.combine(start_day, time.min, tzinfo=tz)
    until = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)

    rows, days, estimated_calls = _spend(since, until, tz)
    conferred, would_fall, reasons, fallbacks = _conference(since, until)
    return BIAiReport(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        conference_mode=CONFERENCE_MODE,
        cost_usd_micros=sum(r.cost_usd_micros for r in rows),
        cost_brl_micros=_sum_or_none([d.cost_brl_micros for d in days]),
        calls=sum(r.calls for r in rows),
        errors=sum(r.errors for r in rows),
        denied=sum(r.denied for r in rows),
        estimated_calls=estimated_calls,
        provisional_quotes=any(d.provisional for d in days),
        rows=rows,
        days=days,
        conferred=conferred,
        would_fall=would_fall,
        reasons=reasons,
        gaps=_gaps(since, until),
        fallbacks=fallbacks,
    )
