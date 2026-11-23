"""O turno da Nice pelo motor do framework, atrás da chave e por classe de ação (N9a, #3199).

Aqui o motor do framework conversacional é montado com as portas e os livros do Shopman, e
``run`` decide, turno a turno, se a entrada sai pelo motor ou pelo caminho de hoje. Ninguém
chama ``run`` no turno vivo ainda: a troca no ``service.run_turn`` é o N9b.

As regras (decisão de 22/11/2026, "o motor fala"):

1. **A chave é da loja, por classe** (``Shop.conversational_live_*``, ADR-042), e todas nascem
   desligadas. Desligar "pedido" é o freio da escrita: informar e passar à equipe continuam.
2. **O motor só fala onde a casa tem a frase de hoje.** Os moldes da Nice (``nice_templates``)
   saem da MESMA copy do caminho de hoje. Molde sem frase aprovada fica fora, e o turno que
   precisaria dele cai no caminho de hoje, nunca numa frase genérica do pacote. Hoje são dois:
   o agradecimento e o "Combinado". As frases que mudam esperam a palavra do dono (prévia
   ``previa-n9-frases``).
3. **Primeiro a sombra, depois o vivo.** O turno roda antes em ``environment=shadow`` (sem
   enviar, sem efeito, sem equipe). Só se todos os movimentos escolhidos são de classes
   ligadas e todos os moldes usados (``Composed.template_ids``) são da Nice, o turno roda de
   verdade, com o envio pelo mesmo caminho da resposta (``NiceChannel``). A mesma entrada dá a
   mesma decisão (K40), então o vivo repete o que a sombra conferiu.
4. **Nada derruba o turno.** Qualquer falha aqui devolve ``None``, e o caminho de hoje segue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from conversational_commerce.engine import Engine, Ports
from conversational_commerce.engine.moves import templates
from conversational_commerce.engine.state import Subject
from conversational_commerce.ports import TrustedContext
from conversational_commerce.reply import Template

logger = logging.getLogger(__name__)

#: Classe de ação → movimentos. Movimento fora daqui (desconto, cancelamento, acréscimo, os
#: que o perfil não liga) nunca sai pelo motor no N9.
ACTION_CLASSES = {
    "inform": ("acknowledge", "inform", "cover_readings", "inform_limitation", "ask_clarification"),
    "handoff": ("handoff",),
    "order": ("present_terms", "change_cart", "set_fulfillment", "commit_order"),
}
SWITCH_FIELD = {"inform": "conversational_live_inform", "handoff": "conversational_live_handoff",
                "order": "conversational_live_order"}
CLASS_OF_MOVE = {move: name for name, moves in ACTION_CLASSES.items() for move in moves}

#: Molde do motor → a chave de copy do caminho de hoje com a MESMA frase (prévia de 22/11:
#: "Igual"). As frases que mudam entram só com a palavra do dono, num PR de seguimento.
NICE_TEMPLATE_COPY = {
    "acknowledge.got_it": "CONCIERGE_MEMORY_DECLINED",
    "acknowledge.thanks": "CONCIERGE_SMALL_TALK_THANKS",
}

ENVIRONMENT = "live"


def live_classes() -> frozenset[str]:
    """As classes de ação ligadas na loja. Sem loja, nenhuma."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    if shop is None:
        return frozenset()
    return frozenset(name for name, field in SWITCH_FIELD.items() if getattr(shop, field, False))


def nice_templates() -> dict[str, Template]:
    """Os moldes da Nice, com a frase da copy de hoje. A copy que não vira molde válido fica fora."""
    from .service import copy_message

    package = templates()
    found: dict[str, Template] = {}
    for template_id, key in NICE_TEMPLATE_COPY.items():
        base = package[template_id]
        text = (copy_message(key) or "").strip()
        try:
            found[template_id] = Template(template_id, f"nice:{key}", base.move, text, dict(base.slots))
        except ValueError:
            logger.warning("concierge.turn_framework.template_refused template=%s key=%s", template_id, key)
    return found


class NiceRules:
    """As regras locais da Nice no lugar das de teste do pacote (que são em inglês).

    O motor lê a mensagem por estas regras só no portão (cortesia sozinha não chama o leitor) e
    na queda (teto de chamadas, leitor fora). É a MESMA leitura por regra do caminho de hoje
    (``intents.local_acts``), no vocabulário fechado do framework (``ports.ACT_MAP``). Só dá
    o nome do ato: produto, quantidade e dia vêm do leitor da Nice (``model_reader.NiceReader``).
    """

    def read(self, text: str) -> tuple[str, ...]:
        from .intents import local_acts
        from .ports import ACT_MAP

        found = tuple(dict.fromkeys(ACT_MAP.get(act.act, "unknown") for act in local_acts(text or "")))
        return tuple(act for act in found if act != "unknown")

    def risk_acts(self, text: str) -> tuple[str, ...]:
        return tuple(act for act in self.read(text) if act == "complain")


def subject_for(conversation):
    """O sujeito do turno: a conversa, com a sacola dela. Identidade nunca acima do transporte."""
    from .ports import new_cart_ref, subject_of

    def subject(ctx: TrustedContext, event) -> Subject:
        # Sem sacola ainda, o alvo é a sacola nova da conversa: o primeiro pedido pelo motor tem
        # onde cair, e ela só nasce no efeito (nunca na leitura nem na sombra).
        return Subject(subject_ref=subject_of(conversation.pk), identity_evidence=tuple(event.identity_evidence),
                       cart_ref=conversation.session_key or new_cart_ref(conversation.pk))

    return subject


def build_engine(conversation, *, environment: str = ENVIRONMENT, channel=None) -> Engine | None:
    """O motor com as portas e os livros duráveis do Shopman para esta conversa, ou ``None``."""
    from shopman.shop.conversational.clock import ShopmanClock
    from shopman.shop.conversational.commerce_execute import ShopmanCommerceExecute
    from shopman.shop.conversational.commerce_read import ShopmanCommerceRead
    from shopman.shop.conversational.ledgers import (
        commitment_ledger,
        exposure_ledger,
        memory_store,
        receipt_ledger,
    )
    from shopman.shop.conversational.outcomes import ShopmanOutcomes
    from shopman.shop.conversational.store import ShopmanStore

    from .effect_site import ConciergeEffectSite
    from .model_reader import NiceReader
    from .ports import ConversationOwnership, nice_channel, resolve_text, subject_of
    from .profile import build_profile
    from .staff_port import NiceStaff
    from .tools import ToolContext

    channel = channel or nice_channel()
    if channel is None:
        return None
    profile = build_profile(environment=environment)
    ctx = TrustedContext(tenant=profile.tenant, environment=environment, subject=subject_of(conversation.pk))
    bodies: dict[str, str] = {}
    channel = replace(channel, bodies=bodies)
    channel_ref = conversation.channel_ref or "whatsapp"
    ports = Ports(
        channel=channel, model=NiceReader(),
        commerce_read=ShopmanCommerceRead(channel_ref=channel_ref, ownership=ConversationOwnership()),
        commerce_execute=ShopmanCommerceExecute(site=ConciergeEffectSite(
            ToolContext(conversation=conversation, channel_ref=channel_ref))),
        staff=NiceStaff(), store=ShopmanStore(), clock=ShopmanClock(ctx), outcomes=ShopmanOutcomes())
    return Engine(ports, profile, rules=NiceRules(), resolve_content=resolve_text, subject_of=subject_for(conversation),
                  house_templates=nice_templates(), bodies=bodies,
                  ledger=receipt_ledger(ctx), commitments=commitment_ledger(ctx),
                  memory=memory_store(ctx, subject_of(conversation.pk)), exposures=exposure_ledger(ctx))


@dataclass(frozen=True)
class Verdict:
    """O que a sombra disse: se o turno pode sair pelo motor, e por quê não, quando não."""

    eligible: bool
    reason: str = ""
    moves: tuple[str, ...] = ()
    template_ids: tuple[str | None, ...] = ()


def judge(result, *, enabled: frozenset[str], approved: frozenset[str]) -> Verdict:
    """O turno em sombra pode ir ao vivo? Classe ligada para cada movimento, molde da Nice para cada parte."""
    moves = tuple(result.chosen_moves)
    reply = getattr(result, "reply", None)
    template_ids = tuple(reply.template_ids) if reply is not None else ()
    if not moves or reply is None or not reply.text:
        return Verdict(False, "no_reply", moves, template_ids)
    off = sorted({move for move in moves if CLASS_OF_MOVE.get(move) not in enabled})
    if off:
        return Verdict(False, f"class_off:{','.join(off)}", moves, template_ids)
    missing = sorted({str(t) for t in template_ids if t not in approved})
    if missing:
        return Verdict(False, f"no_nice_template:{','.join(missing)}", moves, template_ids)
    return Verdict(True, "", moves, template_ids)


def _raw(message) -> dict:
    return {**(message.envelope or {}), "message_ref": message.pk}


def run(conversation, message, *, channel=None, interrupted=None):
    """O turno pelo motor, ou ``None`` (o caminho de hoje segue). Nunca levanta.

    Só conta como feito o turno que o motor respondeu E enviou (``answered`` com exposição).
    Segurado, revogado (``interrupted``: a conversa mudou de dono no meio) ou com o envio
    falhado, nada chegou ao cliente pelo motor, e o caminho de hoje responde.
    """
    try:
        enabled = live_classes()
        if not enabled:
            return None
        shadow = build_engine(conversation, environment="shadow", channel=channel)
        if shadow is None:
            return None
        rehearsal = shadow.turn(TrustedContext(tenant=shadow.profile.tenant, environment="shadow",
                                               subject=shadow.ports.clock.ctx.subject), _raw(message))
        verdict = judge(rehearsal, enabled=enabled, approved=frozenset(shadow.house_templates))
        if not verdict.eligible:
            logger.info("concierge.turn_framework.legacy conversation=%s reason=%s", conversation.pk, verdict.reason)
            return None
        live = build_engine(conversation, environment=ENVIRONMENT, channel=channel)
        if live is None:
            return None
        result = live.turn(live.ports.clock.ctx, _raw(message), interrupted=interrupted)
        if result.outcome != "answered" or getattr(result, "exposure", None) is None:
            logger.info("concierge.turn_framework.not_sent conversation=%s outcome=%s fallbacks=%s",
                        conversation.pk, result.outcome, list(result.fallbacks))
            return None
        return result
    except Exception:  # noqa: BLE001 — o motor que cai nunca derruba o turno: segue o caminho de hoje
        logger.warning("concierge.turn_framework.failed conversation=%s", getattr(conversation, "pk", None),
                       exc_info=True)
        return None
