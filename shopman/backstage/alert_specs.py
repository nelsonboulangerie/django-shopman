"""Como cada aviso crítico se apresenta e quanto tempo dá para agir.

A janela do aviso (``OperatorUrgentAlert`` no operator-kit) lê sempre na mesma ordem
(dono, 08/10/2026): de onde vem, o assunto, quanto falta, o detalhe e o que fazer.
A origem e o assunto são do TIPO e moram aqui, num lugar só; o detalhe é a mensagem
de cada aviso. Todo aviso que interrompe a tela tem prazo: o do mundo lá fora quando
existe (``OperatorAlert.respond_by``, ex.: o iFood), senão a régua da casa, aqui.

Quem ainda não está aqui continua na caixa de Avisos, sem interromper. Cada tipo
novo entra com origem, assunto e régua, num PR próprio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class AlertSpec:
    origin: str
    #: Ícone Lucide da origem, no formato do kit (``i-lucide-...``).
    origin_icon: str
    subject: str
    #: Régua da casa: minutos desde a criação, quando o aviso não traz prazo próprio.
    deadline_minutes: int


ALERT_SPECS: dict[str, AlertSpec] = {
    # O iFood decide sozinho no fim do prazo dele (o aviso traz ``respond_by``).
    "ifood_negotiation_open": AlertSpec("iFood", "i-lucide-bike", "Cliente pediu cancelamento", 10),
    # Pedido novo parado sem aceite: no iFood, o próprio iFood cancela.
    "stale_new_order": AlertSpec("Pedidos", "i-lucide-clipboard-list", "Pedido novo sem aceite", 5),
    # Loja própria: até a cozinha começar ainda dá para cancelar sem desperdício.
    "customer_cancellation_requested": AlertSpec(
        "Loja online", "i-lucide-store", "Cliente pediu cancelamento", 10,
    ),
    # WhatsApp: régua de atendimento de 5 minutos (dono, 08/10/2026).
    "concierge_handoff": AlertSpec("WhatsApp", "i-lucide-message-circle", "Cliente esperando atendente", 5),
    # Marketing: disparo com problema antes da hora marcada.
    "marketing_outbox_stuck": AlertSpec("Marketing", "i-lucide-megaphone", "Disparo travado na fila", 30),
    "marketing_readiness_stale": AlertSpec("Marketing", "i-lucide-megaphone", "Canal de disparo sem prontidão", 30),
    "marketing_partial_without_action": AlertSpec(
        "Marketing", "i-lucide-megaphone", "Disparo saiu pela metade", 30,
    ),
    # Envio para quem pediu para sair: LGPD, travar já.
    "marketing_consent_violation": AlertSpec(
        "Marketing", "i-lucide-shield-alert", "Envio para quem pediu para sair", 5,
    ),
}


#: A régua da casa vale para o aviso recente. Um aviso da casa aberto há mais de um
#: dia já não é "agora": fica na caixa de Avisos, sem interromper. Sem isto, ligar a
#: régua faria cada aviso antigo ainda aberto saltar na tela de uma vez, atrasado.
HOUSE_DEADLINE_WINDOW = timedelta(days=1)


def spec_for(alert_type: str) -> AlertSpec | None:
    return ALERT_SPECS.get(alert_type)


def _house_applies(alert) -> bool:
    from django.utils import timezone

    return (
        spec_for(alert.type) is not None
        and alert.created_at is not None
        and timezone.now() - alert.created_at <= HOUSE_DEADLINE_WINDOW
    )


def deadline_kind(alert) -> str:
    """``external``: quem decide no fim é o mundo lá fora, e o aviso sai com o prazo.
    ``house``: régua da casa; vencida, a causa continua e o aviso fica, atrasado."""
    if alert.respond_by:
        return "external"
    return "house" if _house_applies(alert) else ""


def deadline_for(alert):
    """O prazo do aviso: o do mundo lá fora, senão a régua da casa; ``None`` sem spec."""
    if alert.respond_by:
        return alert.respond_by
    if not _house_applies(alert):
        return None
    return alert.created_at + timedelta(minutes=spec_for(alert.type).deadline_minutes)
