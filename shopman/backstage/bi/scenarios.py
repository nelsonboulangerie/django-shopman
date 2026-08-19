"""Cenários com IA: junta os agregados, pergunta, valida, versiona (§7.1 da fundação).

O fluxo inteiro cabe em quatro verbos, e cada um tem um limite escrito:

- ``gather_inputs(focus, window)``: só **camada de leitura** — as projections
  já agregadas (vendas por dia, canal, top produtos; projeção da semana;
  produção, forno, falta/sobra). Nenhum ``Order``, nenhum nome de cliente,
  nenhuma apuração de caixa (o caixa é auditoria; não entra no foco do v1).
- ``build_prompt(inputs)``: a voz é de analista de gestão, não da marca —
  pt-BR, sentence case, sem travessão, e a ordem é PROPOR: cenários com o dado
  que os sustenta e o que eles não sabem. Saída em JSON estrito.
- ``generate(...)``: chama o transporte que já existe (``copy_assist.suggest``,
  com a voz do analista no lugar da voz da loja), valida a resposta com
  pydantic e grava o ``BIScenarioReport`` — ``done`` com os cenários, ou
  ``failed`` com o motivo e a resposta crua. Nunca um cenário inventado.
- ``is_configured()``: a tela só oferece o botão se houver credencial —
  oferecer e falhar depois ensina o gestor a não confiar no recurso.

Custo e latência são declarados no relatório (modelo, duração). Roda sob
demanda; não há agendamento no v1.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 28
MAX_TOKENS = 1800

ANALYST_VOICE = (
    "Você é analista de gestão de uma padaria artesanal brasileira. Recebe agregados do "
    "B.I. da casa (valores em centavos quando o nome termina em _q; datas em ISO) e propõe "
    "cenários para o gestor decidir. Escreva em português do Brasil, sentence case, sem "
    "travessão (—), sem emoji, sem superlativo vazio. Você PROPÕE; nunca afirma que algo "
    "foi feito nem manda fazer. Cada cenário cita o dado que o sustenta e o que ele NÃO "
    "sabe. Se os dados não bastam para um cenário, diga isso em unknowns em vez de inventar. "
    "Responda APENAS com JSON válido no formato pedido, sem texto em volta, sem cercas de código."
)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=120)
    proposal: str = Field(min_length=10, max_length=1200)
    basis: list[str] = Field(default_factory=list, max_length=8)
    unknowns: list[str] = Field(default_factory=list, max_length=8)


class ScenarioPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenarios: list[Scenario] = Field(min_length=1, max_length=6)


class ScenariosNotConfigured(Exception):
    """Sem credencial: é configuração, não falha."""


def is_configured() -> bool:
    from shopman.shop.services.copy_assist import is_configured as assist_configured

    return assist_configured()


# ── Entradas: só camada de leitura ──────────────────────────────────────────


def gather_inputs(focus: str, date_from: date, date_to: date) -> dict:
    """Os agregados que a IA pode ver. Tudo com unidade no nome; nada pessoal."""
    from shopman.backstage.models import BIScenarioReport

    if focus == BIScenarioReport.Focus.SALES:
        return _sales_inputs(date_from, date_to)
    if focus == BIScenarioReport.Focus.PRODUCTION:
        return _production_inputs(date_from, date_to)
    raise ValueError(f"foco desconhecido: {focus!r}")


def _sales_inputs(date_from: date, date_to: date) -> dict:
    from shopman.backstage.projections.bi_forecast import ForecastError, build_bi_forecast
    from shopman.backstage.projections.bi_sales import build_bi_sales

    sales = build_bi_sales(date_from=date_from, date_to=date_to)
    inputs = {
        "focus": "sales",
        "window": {"from": sales.date_from, "to": sales.date_to},
        "totals": {
            "orders": sales.orders_total,
            "revenue_q": sales.revenue_total_q,
            "average_ticket_q": sales.average_ticket_q,
            "cancelled": sales.cancelled_total,
        },
        "previous_period": {
            "orders": sales.previous.orders_total,
            "revenue_q": sales.previous.revenue_total_q,
            "average_ticket_q": sales.previous.average_ticket_q,
        },
        "sources": list(sales.sources),
        "historical_days": sales.historical_days,
        "days": [
            {"date": day.date, "orders": day.orders, "revenue_q": day.revenue_q, "source": day.source}
            for day in sales.days
        ],
        "by_channel": [
            {"channel": row.channel_ref, "orders": row.orders, "revenue_q": row.revenue_q}
            for row in sales.by_channel
        ],
        "top_products": [
            {"sku": row.sku, "name": row.name, "qty": row.qty, "revenue_q": row.revenue_q}
            for row in sales.top_skus
        ],
        "orders_by_weekday_mon_first": list(sales.orders_by_weekday),
        "orders_by_hour": list(sales.orders_by_hour),
    }
    # A projeção da próxima semana entra quando existe; quando não, o motivo entra.
    try:
        forecast = build_bi_forecast(target=timezone.localdate() + timedelta(days=1), horizon="week")
        inputs["next_week_forecast"] = {
            "from": forecast.date_from,
            "to": forecast.date_to,
            "days": [
                {
                    "date": day.date,
                    "weekday": day.weekday_label,
                    "closed": day.closed,
                    "revenue_q": None if day.revenue_q is None else {
                        "expected": day.revenue_q.expected, "low": day.revenue_q.low, "high": day.revenue_q.high,
                    },
                    "orders": None if day.orders is None else {
                        "expected": day.orders.expected, "low": day.orders.low, "high": day.orders.high,
                    },
                    "occasion": None if day.occasion is None else day.occasion.name,
                    "missing_reason": day.missing_reason,
                }
                for day in forecast.days
            ],
            "missing_days": list(forecast.total_missing_days),
        }
    except ForecastError as exc:
        inputs["next_week_forecast"] = {"unavailable": str(exc)}
    return inputs


def _production_inputs(date_from: date, date_to: date) -> dict:
    from shopman.backstage.projections.bi_explore import ExploreError, build_bi_explore
    from shopman.backstage.projections.bi_production import build_bi_production

    production = build_bi_production(date_from=date_from, date_to=date_to)
    inputs = {
        "focus": "production",
        "window": {"from": production.date_from, "to": production.date_to},
        "batches_finished": production.batches_finished,
        "oven_coverage_percent": production.oven_coverage_percent,
        "days": [
            {
                "date": day.date, "planned": day.planned, "finished": day.finished,
                "loss": day.loss, "yield_percent": day.yield_percent,
            }
            for day in production.days
        ],
        "oven_time_by_recipe": [
            {"recipe": row.ref, "runs": row.runs, "avg_minutes": row.avg_minutes, "p90_minutes": row.p90_minutes}
            for row in production.oven_time_by_recipe
        ],
    }
    for key, metric in (
        ("soldout_days_by_sku", "soldout_days"),
        ("leftover_by_sku", "leftover"),
        ("unavailable_hours_by_sku", "unavailable_hours"),
    ):
        try:
            report = build_bi_explore(metric=metric, by="sku", date_from=date_from, date_to=date_to)
            inputs[key] = {
                "unit": report.unit,
                "rows": [{"sku": row.key, "label": row.label, "value": row.value} for row in report.rows[:15]],
                "truncated": report.truncated,
            }
        except ExploreError as exc:
            inputs[key] = {"unavailable": str(exc)}
    return inputs


# ── Prompt, chamada, validação ──────────────────────────────────────────────


def build_prompt(inputs: dict) -> str:
    focus_label = {"sales": "vendas", "production": "produção e abastecimento"}.get(inputs.get("focus"), "")
    return (
        f"Agregados do B.I. ({focus_label}), em JSON:\n{json.dumps(inputs, ensure_ascii=False)}\n\n"
        "Proponha de 2 a 4 cenários para a próxima semana. Cada cenário: um título curto, "
        "uma proposta concreta (o que o gestor poderia decidir e por quê), a lista basis com "
        "os números dos agregados que a sustentam (cite datas e valores), e a lista unknowns "
        "com o que os dados não dizem. Valores _q são centavos: escreva em reais na proposta. "
        'Formato exato: {"scenarios": [{"title": "...", "proposal": "...", "basis": ["..."], '
        '"unknowns": ["..."]}]}'
    )


def inputs_hash(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate(*, focus: str, requested_by=None, date_from: date | None = None, date_to: date | None = None):
    """Uma rodada: junta, pergunta, valida, grava. Devolve o ``BIScenarioReport``.

    Levanta ``ScenariosNotConfigured`` antes de tocar em qualquer coisa quando
    não há credencial. Qualquer outra falha vira relatório ``failed``.
    """
    from shopman.backstage.models import BIScenarioReport
    from shopman.shop.services.copy_assist import CopyAssistError, suggest

    if not is_configured():
        raise ScenariosNotConfigured("Cenários com IA não configurados. Defina AI_ASSIST_API_KEY.")
    date_to = date_to or timezone.localdate()
    date_from = date_from or (date_to - timedelta(days=DEFAULT_WINDOW_DAYS - 1))

    inputs = gather_inputs(focus, date_from, date_to)
    report = BIScenarioReport(
        requested_by=requested_by,
        focus=focus,
        window_from=date_from,
        window_to=date_to,
        model=str(getattr(settings, "AI_ASSIST_MODEL", "") or ""),
        inputs=inputs,
        inputs_hash=inputs_hash(inputs),
    )
    started = time.monotonic()
    try:
        raw = suggest(build_prompt(inputs), max_tokens=MAX_TOKENS, voice=ANALYST_VOICE)
        report.raw_text = raw
        report.scenarios = [scenario.model_dump() for scenario in parse_response(raw).scenarios]
        report.status = BIScenarioReport.Status.DONE
    except (CopyAssistError, ValueError, ValidationError) as exc:
        report.status = BIScenarioReport.Status.FAILED
        report.error = str(exc)[:2000]
        logger.warning("bi.scenarios: rodada falhou focus=%s error=%s", focus, exc)
    report.duration_ms = int((time.monotonic() - started) * 1000)
    report.save()
    return report


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def parse_response(raw: str) -> ScenarioPayload:
    """JSON estrito, com tolerância só para cerca de código que o modelo às vezes insiste em pôr."""
    text = _FENCE.sub("", (raw or "").strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"a resposta não é JSON: {exc}") from exc
    return ScenarioPayload.model_validate(data)
