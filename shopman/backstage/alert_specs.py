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
    #: ``0``: o tipo só interrompe com prazo próprio (``respond_by``); a spec dá a origem
    #: e o assunto.
    deadline_minutes: int
    #: O prazo próprio (``respond_by``) vencido FICA na tela, dizendo há quanto passou,
    #: como a régua da casa: é promessa da casa, não decisão do mundo lá fora.
    own_deadline_stays: bool = False
    #: Também no topo da tela (o aviso do cabeçalho do kit, na cor da gravidade), e não
    #: só no sino: a operação inteira está degradada, não um pedido.
    on_screen: bool = False


ALERT_SPECS: dict[str, AlertSpec] = {
    # O iFood decide sozinho no fim do prazo dele (o aviso traz ``respond_by``).
    "ifood_negotiation_open": AlertSpec("iFood", "i-lucide-bike", "Cliente pediu cancelamento", 10),
    # A loja pediu o cancelamento e o iFood recusou: o pedido volta a andar e o
    # prazo do iFood continua correndo. Seguir ou tentar de novo, já.
    "ifood_cancellation_refused": AlertSpec("iFood", "i-lucide-bike", "iFood recusou o cancelamento", 5),
    # O aceite saiu daqui e não chegou ao iFood: no fim do prazo dele (``respond_by``)
    # o iFood cancela sozinho, com a cozinha já trabalhando.
    "ifood_accept_not_delivered": AlertSpec("iFood", "i-lucide-bike", "O aceite não chegou ao iFood", 8),
    # O iFood cancelou e o pedido segue ativo aqui: parar antes de entregar.
    "ifood_cancelled_not_applied": AlertSpec("iFood", "i-lucide-bike", "iFood cancelou, pedido segue aqui", 5),
    # Pedido novo parado sem aceite: no iFood, o próprio iFood cancela. Com prazo de
    # aceite da casa (``auto_cancel``), o aviso traz ``respond_by`` = o prazo do pedido,
    # e esta régua só vale para o canal sem prazo (``manual``).
    "stale_new_order": AlertSpec("Pedidos", "i-lucide-clipboard-list", "Pedido novo sem aceite", 5),
    # Cartão autorizado: o Stripe decide sozinho no fim (o aviso traz ``respond_by``
    # nas últimas 24 h; antes disso, fica na caixa de Avisos).
    "card_authorization_expiring": AlertSpec(
        "Loja online", "i-lucide-credit-card", "Cartão autorizado esperando aceite", 60,
    ),
    # WhatsApp: régua de atendimento de 5 minutos (dono, 08/10/2026).
    # No topo da tela também (dono, 20/11/2026): todo handoff é gente esperando gente.
    "concierge_handoff": AlertSpec(
        "WhatsApp", "i-lucide-message-circle", "Cliente esperando atendente", 5, on_screen=True,
    ),
    # "Vou verificar": a pergunta que a Concierge levou à equipe. Conta até o prazo que
    # ela prometeu ao cliente (``respond_by``, contado com a loja aberta, por isso sem
    # régua da casa) e, vencido, fica na tela: a promessa é da casa.
    "concierge_verify": AlertSpec(
        "WhatsApp", "i-lucide-message-circle", "Cliente espera a resposta da equipe", 0, own_deadline_stays=True,
    ),
    # A Concierge fez a mudança (a sacola, o pagamento, o pedido) e a resposta segurou: ela disse ao cliente
    # "já te confirmo", e a equipe confirma até o prazo (``respond_by``). Vencido, fica: a promessa é da casa.
    "concierge_effect_unconfirmed": AlertSpec(
        "WhatsApp", "i-lucide-message-circle", "Cliente espera a confirmação da Concierge", 0, own_deadline_stays=True,
    ),
    # A Concierge atendendo sem modelo (dono, 19/11/2026): no topo do Gestor, até a causa
    # passar. Sem régua: não há prazo, há causa.
    "concierge_no_model": AlertSpec("WhatsApp", "i-lucide-message-circle", "Concierge sem modelo", 0, on_screen=True),
    # Rascunhos de pergunta frequente vindos de conversa (WP-15): sem prazo, há uma causa
    # (o rascunho parado). No topo do Gestor até alguém publicar ou apagar.
    "faq_drafts_waiting": AlertSpec(
        "Concierge", "i-lucide-circle-help", "Rascunhos de pergunta frequente", 0, on_screen=True,
    ),
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

    spec = spec_for(alert.type)
    return (
        spec is not None
        and spec.deadline_minutes > 0
        and alert.created_at is not None
        and timezone.now() - alert.created_at <= HOUSE_DEADLINE_WINDOW
    )


def deadline_kind(alert) -> str:
    """``external``: quem decide no fim é o mundo lá fora, e o aviso sai com o prazo.
    ``house``: régua da casa; vencida, a causa continua e o aviso fica, atrasado."""
    if alert.respond_by:
        spec = spec_for(alert.type)
        return "house" if spec is not None and spec.own_deadline_stays else "external"
    return "house" if _house_applies(alert) else ""


def deadline_for(alert):
    """O prazo do aviso: o do mundo lá fora, senão a régua da casa; ``None`` sem spec."""
    if alert.respond_by:
        return alert.respond_by
    if not _house_applies(alert):
        return None
    return alert.created_at + timedelta(minutes=spec_for(alert.type).deadline_minutes)
