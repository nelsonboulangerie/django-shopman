"""Capacidade dos apps de operação — a regra que transforma leitura em aviso.

Quem mede é o próprio app: a rota ``/health/capacity`` da layer ``operator-kit`` lê
a memória e a CPU do CONTÊINER (do serviço inteiro — certo tanto com um app por
contêiner quanto com vários processos Nitro dividindo o mesmo), pelo cgroup ou,
sem cgroup legível, pela soma dos processos visíveis, e reporta a
amostra aqui, na mesma chamada que autentica o operador e devolve os limites do
Admin. Não há processo novo nem laço em segundo plano: a amostra só existe
enquanto alguém tem um app aberto — e é justamente no pico, com os apps abertos,
que a pergunta importa. Sem ninguém olhando, o alerta nativo da DigitalOcean
(``CPU_UTILIZATION``/``MEM_UTILIZATION`` no spec) cobre.

Por que não o ``maintenance-worker``: ele roda no contêiner do Django e não
enxerga o contêiner dos Nuxt. Medir de lá seria inventar número.

A regra (por serviço):

- uso = o MAIOR entre memória% e CPU%;
- acima do crítico, conta desde a primeira amostra acima; passados
  ``sustain_minutes`` sem cair, nasce ``OperatorAlert`` crítico
  ``operator_capacity_critical`` (dedupe por serviço: um aberto por vez);
- abaixo da atenção pelo mesmo tempo, o alerta aberto é resolvido pelo sistema;
- entre atenção e crítico nenhuma contagem anda — nem para avisar, nem para
  resolver;
- lacuna maior que ``STALE_GAP_SECONDS`` entre amostras quebra a série: sem
  leitura no meio, "acima há 5 min" seria suposição.

O estado da série mora no cache (Redis compartilhado em produção, como o
batimento dos workers) — sem modelo novo para um par de timestamps.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from django.core.cache import cache
from django.utils import timezone

from shopman.shop.operator_capacity_policy import OperatorCapacityPolicy

logger = logging.getLogger(__name__)

ALERT_TYPE = "operator_capacity_critical"
RESOLVED_BY = "monitor de capacidade"

#: Os apps reportam a cada 30–60 s. Três minutos sem amostra = série quebrada.
STALE_GAP_SECONDS = 180

_SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_CACHE_KEY = "shopman:operator_capacity:{service}"

#: Nome que o gestor reconhece. Serviço fora da lista aparece pelo próprio nome.
SERVICE_LABELS: dict[str, str] = {
    "operator-floor": "Apps do chão de loja (PDV, Cozinha, Pedidos, Produção, Central)",
    "operator-office": "Apps do escritório (Marketing, B.I., Compras)",
    "pos": "PDV",
    "kds": "Cozinha",
    "orders": "Pedidos",
    "production": "Produção",
    "hub": "Central de Apps",
    "marketing": "Marketing",
    "bi": "B.I.",
    "purchase": "Compras",
}


class InvalidCapacitySample(ValueError):
    """Amostra fora do contrato — recusada inteira, nunca meio aproveitada."""


@dataclass(frozen=True)
class CapacitySample:
    service: str
    available: bool
    memory_percent: float | None
    cpu_percent: float | None

    @property
    def peak(self) -> float | None:
        values = [v for v in (self.memory_percent, self.cpu_percent) if v is not None]
        return max(values) if values else None


@dataclass(frozen=True)
class CapacityEvaluation:
    level: str  # "unknown" | "normal" | "attention" | "critical"
    recorded: bool
    alerted: bool = False
    resolved: int = 0


def service_label(service: str) -> str:
    return SERVICE_LABELS.get(service, service)


def parse_sample(payload: Any) -> CapacitySample:
    """Reduz o corpo do BFF a uma amostra fechada (serviço + dois percentuais)."""
    if not isinstance(payload, dict):
        raise InvalidCapacitySample("corpo")
    service = payload.get("service")
    if not isinstance(service, str) or not _SERVICE_RE.match(service):
        raise InvalidCapacitySample("service")
    available = payload.get("available")
    if not isinstance(available, bool):
        raise InvalidCapacitySample("available")
    memory = _percent(payload.get("memory_percent"), "memory_percent")
    cpu = _percent(payload.get("cpu_percent"), "cpu_percent")
    if not available:
        # "Sem leitura" não carrega número: se vier, é contrato quebrado do lado de lá.
        memory = cpu = None
    return CapacitySample(service=service, available=available, memory_percent=memory, cpu_percent=cpu)


def _percent(raw: Any, field: str) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
        raise InvalidCapacitySample(field)
    if not 0 <= raw <= 100:
        raise InvalidCapacitySample(field)
    return round(float(raw), 1)


def level_for(peak: float | None, policy: OperatorCapacityPolicy) -> str:
    if peak is None:
        return "unknown"
    if peak >= policy.critical_percent:
        return "critical"
    if peak >= policy.attention_percent:
        return "attention"
    return "normal"


def evaluate_sample(
    sample: CapacitySample,
    policy: OperatorCapacityPolicy,
    *,
    now: float | None = None,
) -> CapacityEvaluation:
    """Anda a série do serviço com esta amostra e avisa/resolve quando for a hora."""
    peak = sample.peak
    level = level_for(peak, policy)
    if not sample.available or peak is None:
        return CapacityEvaluation(level="unknown", recorded=False)

    now = timezone.now().timestamp() if now is None else float(now)
    key = _CACHE_KEY.format(service=sample.service)
    state = cache.get(key)
    if not isinstance(state, dict) or not _fresh(state.get("last_at"), now):
        state = {}

    sustain_seconds = policy.sustain_minutes * 60
    alerted = False
    resolved = 0

    if level == "critical":
        above_since = state.get("above_since") or now
        state.update(above_since=above_since, below_since=None, settled=False)
        if now - above_since >= sustain_seconds and not state.get("alerted"):
            alerted, covered = _raise_alert(sample, policy, minutes=int((now - above_since) // 60))
            # Criado agora ou já aberto (dedupe): nos dois casos esta série está
            # avisada. Se a gravação falhou, a próxima amostra tenta de novo.
            state["alerted"] = covered
    elif level == "normal":
        below_since = state.get("below_since") or now
        state.update(above_since=None, below_since=below_since, alerted=False)
        if now - below_since >= sustain_seconds and not state.get("settled"):
            outcome = _resolve_alerts(sample.service)
            # Falha ao resolver deixa a série em aberto: a próxima amostra tenta de novo.
            resolved = outcome or 0
            state["settled"] = outcome is not None
    else:
        state.update(above_since=None, below_since=None, alerted=False, settled=False)

    state["last_at"] = now
    cache.set(key, state, timeout=STALE_GAP_SECONDS * 2)
    return CapacityEvaluation(level=level, recorded=True, alerted=alerted, resolved=resolved)


def _fresh(last_at: Any, now: float) -> bool:
    return isinstance(last_at, int | float) and 0 <= now - last_at <= STALE_GAP_SECONDS


def dedupe_key(service: str) -> str:
    # Colchetes fecham o nome: "[pos]" não casa com "[pos-2]" no ``contains``.
    return f"operator_capacity[{service}]"


def _format_percent(value: float | None) -> str:
    return "sem leitura" if value is None else f"{round(value):d}%"


def _raise_alert(
    sample: CapacitySample,
    policy: OperatorCapacityPolicy,
    *,
    minutes: int,
) -> tuple[bool, bool]:
    """Devolve (criou agora, há aviso aberto cobrindo o serviço)."""
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.observability import create_operator_alert

    minutes = max(minutes, policy.sustain_minutes)
    message = (
        f"{service_label(sample.service)}: acima de {policy.critical_percent}% da capacidade "
        f"há {minutes} min — memória {_format_percent(sample.memory_percent)}, "
        f"CPU {_format_percent(sample.cpu_percent)}. As telas podem ficar lentas ou travar "
        "no movimento. Se não baixar, aumente o tamanho do serviço na DigitalOcean ou "
        "confira se algum app ficou preso."
    )
    alert = create_operator_alert(
        type=ALERT_TYPE,
        severity="critical",
        message=message,
        dedupe_key=dedupe_key(sample.service),
        service=sample.service,
        memory_percent=sample.memory_percent,
        cpu_percent=sample.cpu_percent,
    )
    if alert is not None:
        return True, True
    # ``None`` é dedupe (já há um aberto) OU falha de gravação (já logada por
    # ``create_operator_alert``). Só o primeiro encerra a tentativa desta série.
    # ``recent_exists`` olha só os abertos (``active_only``); o corte de tempo não vale ali.
    return False, alert_adapter.recent_exists(
        ALERT_TYPE,
        timezone.now(),
        message_contains=dedupe_key(sample.service),
    )


def _resolve_alerts(service: str) -> int | None:
    from shopman.shop.adapters import alert as alert_adapter

    try:
        return alert_adapter.resolve_matching(
            ALERT_TYPE,
            message_contains=dedupe_key(service),
            actor=RESOLVED_BY,
        )
    except Exception:
        # A leitura do app não pode cair porque o fechamento do aviso falhou; o
        # aviso segue aberto (o lado seguro) e o log diz por quê.
        logger.exception("operator_capacity.resolve_failed service=%s", service)
        return None


__all__ = [
    "ALERT_TYPE",
    "CapacityEvaluation",
    "CapacitySample",
    "InvalidCapacitySample",
    "STALE_GAP_SECONDS",
    "dedupe_key",
    "evaluate_sample",
    "level_for",
    "parse_sample",
    "service_label",
]
