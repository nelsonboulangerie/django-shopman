"""A Concierge está lendo com modelo? A camada 3 da decisão do dono (19/11/2026, "opção 1").

Sem modelo a Concierge ainda atende (regra local, executores, "vou verificar"), mas
entende menos. Hoje isso só se descobria quando o cliente reclamava. Este módulo diz,
por causa, se a leitura de partes (propósito ``intents``) está sem modelo:

- ``no_connection``, ``ambiguous``, ``no_key``, ``not_approved``, ``no_model``: a conexão
  de IA (``ai.AINotConfigured.code``);
- ``brake``: o freio de gasto cortou (``ai_governor``);
- ``provider_failing``: a conexão existe, mas as últimas leituras falharam e nenhuma deu
  certo desde então (rede, cota, chave recusada pelo provedor).

Quem lê: a sonda do Watchman (``storefront.watchman_checks``) e o aviso do Gestor
(``sync_alert``, a cada ciclo do ``maintenance_worker``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: O tipo do aviso no Gestor (``OperatorAlert.type``).
ALERT_TYPE = "concierge_no_model"
#: Falhas seguidas da leitura, sem nenhum acerto, para contar como provedor fora.
PROVIDER_FAILURES = 3
_FAILURES_KEY = "concierge:reading:failures"
_FAILURES_TTL = 60 * 60

#: A causa, dita para quem opera (o aviso no Gestor; sem travessão, sem jargão).
CAUSE_TEXT = {
    "no_connection": "não há conexão de IA ativa para a leitura",
    "ambiguous": "há mais de uma conexão de IA e a loja não disse qual usar",
    "no_key": "a conexão de IA da leitura está sem chave",
    "not_approved": "a conexão de IA da leitura não está liberada para mensagem de cliente",
    "no_model": "a conexão de IA da leitura está sem modelo",
    "brake": "o freio de gasto de IA cortou a leitura",
    "provider_failing": "as últimas leituras falharam no provedor de IA",
    "not_configured": "a leitura está sem conexão de IA utilizável",
}


@dataclass(frozen=True)
class ReadingState:
    """``cause`` vazio: lê com modelo. ``active`` falso: a Concierge nem atende."""

    active: bool
    cause: str = ""
    detail: str = ""

    @property
    def without_model(self) -> bool:
        return self.active and bool(self.cause)


def current() -> ReadingState:
    """O estado de agora. Nunca levanta: falha ao medir conta como "não sei", sem aviso."""
    from shopman.shop import ai, ai_governor

    from . import service

    if service.disabled_reason():
        return ReadingState(active=False)
    try:
        ai.resolve("intents")
    except (ai_governor.AIDisabled, ai_governor.AIBudgetExceeded) as exc:
        return ReadingState(True, "brake", str(exc))
    except ai.AINotConfigured as exc:
        return ReadingState(True, exc.code or "not_configured", str(exc))
    except Exception:
        logger.warning("concierge.reading_health.unreadable", exc_info=True)
        return ReadingState(True)
    if _failures() >= PROVIDER_FAILURES:
        return ReadingState(True, "provider_failing", f"{_failures()} leituras seguidas falharam")
    return ReadingState(True)


def _failures() -> int:
    try:
        return int(cache.get(_FAILURES_KEY) or 0)
    except Exception:
        logger.warning("concierge.reading_health.cache_unreadable")
        return 0


def record_read(*, ok: bool) -> None:
    """A leitura com modelo deu certo ou falhou (``intents.read_with_model``)."""
    try:
        if ok:
            cache.delete(_FAILURES_KEY)
        else:
            cache.set(_FAILURES_KEY, _failures() + 1, _FAILURES_TTL)
    except Exception:
        logger.warning("concierge.reading_health.cache_unwritable")


def alert_message(state: ReadingState) -> str:
    """O texto do aviso: o que acontece com o cliente e a causa."""
    cause = CAUSE_TEXT.get(state.cause, CAUSE_TEXT["not_configured"])
    return (
        "A Concierge está atendendo sem modelo: responde o simples e manda para a equipe o "
        f"que não entende. Causa: {cause}."
    )


def sync_alert() -> dict[str, int]:
    """Abre o aviso da causa de agora e resolve os das causas que passaram.

    Um aviso por causa (``dedupe_key``): trocou a causa, o aviso velho sai e entra o novo.
    Chamado pelo ``maintenance_worker``; nunca levanta.
    """
    # Pela porta de avisos do shop (``adapters.alert``): o storefront não importa o backstage.
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.services.observability import create_operator_alert

    state = current()
    keep = f"concierge:no_model:{state.cause}" if state.without_model else ""
    opened = resolved = 0
    try:
        for cause in CAUSE_TEXT:
            other = f"concierge:no_model:{cause}"
            if other != keep:
                resolved += alert_adapter.resolve_matching(
                    ALERT_TYPE, message_contains=f"Dedupe: {other}", actor="concierge"
                )
        if keep and not alert_adapter.recent_exists(ALERT_TYPE, None, message_contains=f"Dedupe: {keep}"):
            created = create_operator_alert(
                type=ALERT_TYPE,
                severity="error",
                message=alert_message(state),
                dedupe_key=keep,
                debounce_minutes=1,
            )
            opened = 1 if created is not None else 0
    except Exception:
        logger.warning("concierge.reading_health.alert_failed", exc_info=True)
        return {"opened": 0, "resolved": 0}
    return {"opened": opened, "resolved": resolved}
