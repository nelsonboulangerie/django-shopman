"""O turno da Nice pelo motor do framework, atrás da chave e por classe de ação (N9a, #3199).

Aqui o motor do framework conversacional é montado com as portas e os livros do Shopman, e
``run`` decide, turno a turno, se a entrada sai pelo motor ou pelo caminho de hoje. Ninguém
chama ``run`` no turno vivo ainda: a troca no ``service.run_turn`` é o N9b.

As regras (decisão de 22/11/2026, "o motor fala"):

1. **A chave é da loja, por classe** (``Shop.conversational_live_*``, ADR-042), e todas nascem
   desligadas. Desligar "pedido" é o freio da escrita: informar e passar à equipe continuam.
2. **O motor só fala onde a casa tem a frase de hoje.** Os moldes da Nice (``nice_templates``)
   saem da copy da casa: a MESMA do caminho de hoje ou a frase nova que o dono aprovou na
   prévia ``previa-n9-frases`` (#3298). Molde sem frase aprovada fica fora, e o turno que
   precisaria dele cai no caminho de hoje, nunca numa frase genérica do pacote.
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
    "order": ("present_terms", "change_cart", "set_fulfillment", "set_delivery_address", "set_payment",
              "commit_order"),
}
SWITCH_FIELD = {"inform": "conversational_live_inform", "handoff": "conversational_live_handoff",
                "order": "conversational_live_order"}
CLASS_OF_MOVE = {move: name for name, moves in ACTION_CLASSES.items() for move in moves}

#: Molde do motor → a chave de copy com a frase da Nice. As duas primeiras são a MESMA frase do
#: caminho de hoje (prévia de 22/11: "Igual"); as cinco seguintes são as frases novas que o dono
#: aprovou na prévia frase a frase (22/11, #3298). As que ele recusou (``ask_clarification.which``,
#: ``inform.price``, ``cover_readings.prices``, ``inform_limitation.offer_team``,
#: ``present_terms.changed``) ficam de fora de propósito: o turno que precisaria delas segue o
#: caminho de hoje, com a frase de hoje.
NICE_TEMPLATE_COPY = {
    "acknowledge.got_it": "CONCIERGE_MEMORY_DECLINED",
    "acknowledge.thanks": "CONCIERGE_SMALL_TALK_THANKS",
    "ask_clarification.more": "CONCIERGE_ENGINE_ASK_MORE",
    "effect.failed": "CONCIERGE_ENGINE_EFFECT_FAILED",
    "handoff.routed": "CONCIERGE_ENGINE_HANDOFF_ROUTED",
    "handoff.routed_no_deadline": "CONCIERGE_ENGINE_HANDOFF_ROUTED_NO_DEADLINE",
    "handoff.not_accepted": "CONCIERGE_ENGINE_HANDOFF_NOT_ACCEPTED",
    # Aprovadas pelo dono em 23/11 (cartão do motor): o "total mudou" diz o total novo (substitui o
    # "Não" de 22/11, porque a frase de antes pedia o código), e o pedido registrado traz o link.
    "present_terms.changed": "CONCIERGE_ENGINE_TOTAL_CHANGED",
    "commit_order.done": "CONCIERGE_ENGINE_ORDER_PLACED",
    # Com os termos inteiros no motor (PR do Core, opção 1 aprovada em 23/11): a sacola e o resumo
    # com a frase de hoje; o resumo termina em "Posso registrar?" (aprovada no lugar do código).
    "change_cart.done": "CONCIERGE_ENGINE_CART_UPDATED",
    "present_terms.confirm": "CONCIERGE_ENGINE_TERMS_CONFIRM",
    # "Deixa pra lá" no resumo, sem efeito no turno: a MESMA frase do fechamento de hoje (#3388, "Igual").
    "acknowledge.terms_declined": "CONCIERGE_CLOSE_GAVE_UP",
    # A forma de pagamento escolhida pelo motor (cartão 5): "Combinado: Pix.", no molde do "Combinado".
    "set_payment.done": "CONCIERGE_ENGINE_PAYMENT_SET",
    # A entrega (cartão 2): as perguntas de hoje (o endereço, o que falta nele, o complemento) e o
    # "Combinado: entrega na Rua das Flores, 120." aprovado pelo dono em 23/11.
    "set_delivery_address.done": "CONCIERGE_ENGINE_ADDRESS_SET",
    "present_terms.needs_delivery_address": "CONCIERGE_CLOSE_ASK_ADDRESS",
    "present_terms.needs_delivery_address_details": "CONCIERGE_ENGINE_ADDRESS_DETAILS",
    "present_terms.needs_delivery_complement": "CONCIERGE_ENGINE_ADDRESS_COMPLEMENT",
    # As recusas do endereço com as frases de hoje: fora da área (a frase do ``set_fulfillment`` e a
    # pergunta do endereço, como o fechamento junta) e endereço que não se localiza.
    "set_delivery_address.not_delivered": "CONCIERGE_ENGINE_ADDRESS_NOT_DELIVERED",
    "set_delivery_address.not_located": "CONCIERGE_ENGINE_ADDRESS_NOT_LOCATED",
}

#: As frases da forma de pagamento: as MESMAS de hoje, com o espaço do motor (``{payment_method}``, as
#: opções do canal) no lugar de ``{options}``. A pergunta (``CONCIERGE_CLOSE_ASK_PAYMENT``) e a forma que
#: o canal não oferece (``CONCIERGE_CLOSE_NO_CASH``): a conversa oferece as formas do canal sem dinheiro
#: (``conversation_payment_methods``, D-003), e o leitor só lê pix, cartão e dinheiro (``model_reader.PAYMENTS``),
#: por isso a forma não oferecida que chega ao motor é o dinheiro.
PAYMENT_TEMPLATES = (
    ("present_terms.needs_payment_method", "CONCIERGE_CLOSE_ASK_PAYMENT", "{options}", "{payment_method}"),
    ("set_payment.not_offered", "CONCIERGE_CLOSE_NO_CASH", "{options}", "{payment_method}"),
)

#: Os moldes do pedido com a frase de hoje (prévia de 22/11, "Igual"; passo 4 do pedido pelo motor).
#: O recebimento é o MESMO "Combinado" do caminho de hoje (``CONCIERGE_CART_FULFILLMENT_NOTED``,
#: ``order_closing.noted``), com os espaços do motor no lugar de ``{how}`` e ``{when}``.
FULFILLMENT_TEMPLATES = {
    "set_fulfillment.done": ("{mode}", "{date}, {window}"),
    "set_fulfillment.done_day": ("{mode}", "{date}"),
    # Derivada das aprovadas (coordenação, 23/11): a hora sem janela da grade.
    "set_fulfillment.done_time": ("{mode}", "{date} às {time}"),
    "set_fulfillment.done_date": ("para", "{date}"),
    "set_fulfillment.done_mode": ("{mode}", ""),
}
FULFILLMENT_COPY = "CONCIERGE_CART_FULFILLMENT_NOTED"

#: Quem atende, dito ao cliente. O dono do compromisso é um papel interno ("operator_on_duty",
#: a fila): o cliente lê só que pediu a alguém da equipe, nunca o nome do papel.
OWNER_TEXT = "alguém da equipe"


def owner_text(value) -> str:
    return OWNER_TEXT


def deadline_text(value) -> str:
    """O prazo em hora local, como a casa fala: "hoje às 15h", "amanhã às 7h10", "24/11 às 9h"."""
    from datetime import UTC, datetime, timedelta

    from django.utils import timezone

    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, UTC)
    local = timezone.localtime(moment)
    today = timezone.localdate()
    day = {today: "hoje", today + timedelta(days=1): "amanhã"}.get(local.date()) or local.strftime("%d/%m")
    from shopman.utils.formatting import format_clock

    return f"{day} às {format_clock(local)}"


def date_text(value) -> str:
    """O dia do recebimento como no "Combinado" de hoje: "hoje", "amanhã", "24/11"."""
    from datetime import date

    from .order_closing import day_word

    return day_word(date.fromisoformat(str(value)))


def mode_text(value) -> str:
    from .order_closing import mode_word

    return mode_word(str(value))


def window_text(value) -> str:
    """A janela pela grade da casa ("slot-15" → "a partir das 15h"); ref que a grade não conhece não vaza."""
    from shopman.shop.services.fulfillment_window import window_label

    from .order_closing import window_phrase

    return window_phrase(window_label(str(value), for_customer=True))


def time_text(value) -> str:
    """ "16:00" → "16h", "16:30" → "16h30": a hora como a casa diz (``format_clock``)."""
    from shopman.utils.formatting import format_clock

    return format_clock(str(value))


def money_text(value) -> str:
    """ "R$ 24,00": o dinheiro como a casa escreve (o neutro do pacote é "BRL 24.00")."""
    from collections.abc import Mapping

    from shopman.utils.monetary import format_money

    # O valor do fato chega como ``FrozenMap`` (um ``Mapping``, não um ``dict``).
    if not isinstance(value, Mapping) or "price_minor" not in value:
        raise ValueError("valor sem price_minor")
    return f"R$ {format_money(int(value['price_minor']))}"


def track_text(value) -> str:
    """Onde acompanhar o pedido: a página dele no site, determinística a partir do número (nenhum fato novo)."""
    from .tools import _storefront_base_url

    return f"{_storefront_base_url()}/pedido/{value}/"


def method_text(value) -> str:
    """A forma escolhida como a casa a escreve: "Pix", "Cartão (link seguro)"."""
    from .tools import PAYMENT_LABELS

    if str(value) not in PAYMENT_LABELS:
        raise ValueError("forma de pagamento que a casa não conhece")
    return PAYMENT_LABELS[str(value)]


def payment_options_text(value) -> str:
    """As formas do canal para a pergunta: "Pix ou Cartão (link seguro)".

    Sem os números do fechamento de hoje ("1) Pix; 2) …"): pelo motor, o "1" não é lido como a
    primeira opção (o leitor não vê a pergunta), e lista numerada que não se responde por número
    seria promessa falsa.
    """
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("opções sem lista")
    labels = [method_text(option) for option in value]
    return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} ou {labels[-1]}"


def done_text(value) -> str:
    """O recibo de sucesso dito como a casa diz: "Pronto"."""
    return "Pronto" if str(value) == "success" else str(value)


def items_text(value) -> str:
    """As linhas da sacola como hoje (``tools.render_result``): "2 × “Croissant”: R$ 24,00"."""
    from decimal import Decimal

    from .tools import _display_name

    rows = []
    for line in value:
        quantity = Decimal(str(line["quantity"]))
        shown = int(quantity) if quantity == quantity.to_integral_value() else quantity
        rows.append(f"{shown} × {_display_name(line.get('name') or line['ref'])}: {money_text(line['line_total'])}")
    return "\n".join(rows)


def fulfillment_text(value) -> str:
    """O começo da linha do recebimento: "Retirada" ou "Entrega" (o dia e a janela vêm das condições)."""
    from collections.abc import Mapping

    mode = value.get("mode") if isinstance(value, Mapping) else None
    return {"pickup": "Retirada", "delivery": "Entrega"}.get(str(mode), "")


def _no_address(ref) -> dict:
    """Sem conversa, nenhuma referência de endereço se resolve (o motor segura a mensagem)."""
    from conversational_commerce.reply import UnresolvedReference

    raise UnresolvedReference(str(ref))


def address_resolver(conversation):
    """O endereço da entrega pela referência, SÓ o da sacola desta conversa (spec 06, formatador de referência).

    Devolve o endereço estruturado gravado na sacola; outra referência, sacola sem endereço ou leitura
    que falha levantam ``UnresolvedReference``, e a verificação segura a mensagem. O texto existe só aqui,
    no envio.
    """
    from conversational_commerce.reply import UnresolvedReference

    def resolve(ref) -> dict:
        from shopman.orderman.models import Session

        from shopman.shop.conversational.commerce_read import address_ref

        key = getattr(conversation, "session_key", "") or ""
        if not key or str(ref) != address_ref(key):
            raise UnresolvedReference(str(ref))
        try:
            session = Session.objects.filter(session_key=key).first()
        except Exception as exc:  # noqa: BLE001 - a fonte que falha segura a mensagem
            raise UnresolvedReference(str(ref)) from exc
        data = (session.data if session is not None else None) or {}
        structured = data.get("delivery_address_structured")
        if not isinstance(structured, dict) or not data.get("delivery_address"):
            raise UnresolvedReference(str(ref))
        return {**structured, "formatted_address": str(data["delivery_address"])}

    return resolve


def address_text(resolve):
    """ "Rua das Flores, 120": a rua e o número, como o cliente reconhece o endereço que deu."""
    def text(value) -> str:
        from .tools import _display_text

        found = resolve(value)
        street = ", ".join(part for part in (str(found.get("route") or ""), str(found.get("street_number") or ""))
                           if part)
        return _display_text(street or found["formatted_address"])

    return text


def conditions_text(value, resolve=_no_address) -> str:
    """O resto do recebimento e o pagamento, como no resumo de hoje.

    ": segunda-feira, 23/11, a partir das 15h" (o dia e a janela da grade da casa); na entrega, o
    endereço e a taxa em linhas próprias; e "Pagamento: Pix.". Sem dia, sem o dia.
    """
    from shopman.shop.services.fulfillment_window import window_label

    from .tools import PAYMENT_LABELS, _summary_when

    found = dict(value or {})
    text = ""
    if found.get("fulfillment_date"):
        slot = found.get("fulfillment_window")
        label = window_label(str(slot), for_customer=True) if slot else ""
        text = f": {_summary_when(str(found['fulfillment_date']), label)}"
    if found.get("delivery_address"):
        from .tools import _display_text

        text += f"\n{_display_text(resolve(found['delivery_address'])['formatted_address'])}"
    if found.get("delivery_fee"):
        text += f"\nEntrega: {money_text({'price_minor': int(found['delivery_fee'])})}"
    method = PAYMENT_LABELS.get(str(found.get("payment_method") or ""), "")
    if method:
        text += f"\nPagamento: {method}."
    return text


def nice_formatters(conversation=None) -> dict:
    """Os formatadores da Nice. Com a conversa, os de referência resolvem o endereço DELA (e só dela)."""
    from functools import partial

    from conversational_commerce.engine.format import DEFAULT_FORMATTERS

    money = dict.fromkeys(("price", "price_a", "price_b", "total"), money_text)  # o dinheiro do pacote, em reais
    return {**DEFAULT_FORMATTERS, **money, "track": track_text, "done": done_text, "items": items_text,
            "fulfillment": fulfillment_text, "conditions": conditions_text, "owner": owner_text,
            "deadline": deadline_text,
            "date": date_text,
            "mode": mode_text, "window": window_text, "time": time_text,
            "method": method_text, "payment_method": payment_options_text,
            "delivery_address_details": address_words_text, **_address_formatters(conversation, partial)}


def address_words_text(value) -> str:
    """ "o número (ou S/N) e o CEP": o que falta no endereço, como a pergunta de hoje (``address.question``)."""
    from shopman.shop.services.delivery_fiscal_identity import join_words

    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("lacunas sem lista")
    return join_words([str(word) for word in value])


def _address_formatters(conversation, partial) -> dict:
    resolve = address_resolver(conversation) if conversation is not None else _no_address
    return {"address": address_text(resolve), "conditions": partial(conditions_text, resolve=resolve)}

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
    found.update(_order_templates(package, copy_message))
    for template_id, key, today_slot, slot in PAYMENT_TEMPLATES:
        text = (copy_message(key) or "").strip()
        if today_slot not in text:
            continue
        try:
            base = package[template_id]
            found[template_id] = Template(template_id, f"nice:{key}", base.move, text.replace(today_slot, slot),
                                          dict(base.slots))
        except (KeyError, ValueError):
            logger.warning("concierge.turn_framework.template_refused template=%s key=%s", template_id, key)
    return found


def _order_templates(package, copy_message) -> dict[str, Template]:
    """Os moldes do pedido com a frase de hoje. Copy que não vira molde válido fica fora (e o turno, no caminho de hoje).

    O molde da casa tem os MESMOS espaços do pacote (``Engine.__post_init__``). Por isso o "total
    mudou" de hoje, que não diz o total, não vira molde: o do pacote mostra ``{total}``.
    """
    import re

    found: dict[str, Template] = {}
    noted = (copy_message(FULFILLMENT_COPY) or "").strip()
    for template_id, (how, when) in FULFILLMENT_TEMPLATES.items():
        base = package.get(template_id)
        text = re.sub(r"\s+([.,])", r"\1", noted.replace("{how}", how).replace("{when}", when)).strip()
        if base is None or "{how}" not in noted or "{when}" not in noted:
            continue
        try:
            found[template_id] = Template(template_id, f"nice:{FULFILLMENT_COPY}", base.move, text, dict(base.slots))
        except ValueError:
            logger.warning("concierge.turn_framework.template_refused template=%s key=%s", template_id, FULFILLMENT_COPY)
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
                  house_templates=nice_templates(), bodies=bodies, formatters=nice_formatters(conversation),
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


#: O aviso de prazo vencido sai pelos moldes ``wait.*`` (``Engine.tick``, ``only=("wait",)``).
TICK_MOVE = "wait"


def tick_templates_missing() -> tuple[str, ...]:
    """Os moldes do aviso de prazo sem frase da Nice. Enquanto houver um, o tick não fala."""
    approved = set(NICE_TEMPLATE_COPY)
    return tuple(sorted(t.template_id for t in templates().values()
                        if t.move == TICK_MOVE and t.template_id not in approved))


def _due_conversations(ctx: TrustedContext) -> list[int]:
    """As conversas com compromisso do motor aberto e vencido, no inquilino e ambiente do turno vivo."""
    from conversational_commerce.contracts import Commitment
    from django.utils import timezone

    from shopman.shop.conversational.store import _scope, instant
    from shopman.shop.models import Conversation, ConversationalCommitment, ConversationalEpisode

    from .ports import SUBJECT_PREFIX

    now = instant(timezone.now())
    episodes = set()
    for row in ConversationalCommitment.objects.filter(**_scope(ctx), is_open=True).exclude(episode_id=""):
        deadline = getattr(Commitment.from_document(row.commitment).deadline, "at", None)
        if deadline and str(deadline) <= now:
            episodes.add(row.episode_id)
    subjects = set(ConversationalEpisode.objects.filter(**_scope(ctx), episode_id__in=episodes)
                   .values_list("subject", flat=True))
    pks = sorted({int(s[len(SUBJECT_PREFIX):]) for s in subjects
                  if s.startswith(SUBJECT_PREFIX) and s[len(SUBJECT_PREFIX):].isdigit()})
    return list(Conversation.objects.filter(pk__in=pks).values_list("pk", flat=True))


def _only_this_conversation(engine, conversation) -> None:
    """O livro do motor carrega todo compromisso aberto do inquilino; o tick desta conversa só vê os dela."""
    from shopman.shop.conversational.store import _scope
    from shopman.shop.models import ConversationalEpisode

    from .ports import subject_of

    ctx = engine.ports.clock.ctx
    mine = set(ConversationalEpisode.objects.filter(**_scope(ctx), subject=subject_of(conversation.pk))
               .values_list("episode_id", flat=True))
    ledger = engine.commitments
    ledger.entries = {cid: entry for cid, entry in ledger.entries.items() if entry.commitment.episode_id in mine}


def tick(*, channel=None) -> dict:
    """Os prazos do motor vencidos, conversa a conversa: avisa o cliente UMA vez (K22), pelo envio de hoje.

    Roda no ``maintenance_worker`` (``concierge_engine_tick``). Não faz nada com as classes
    desligadas, nem enquanto algum molde do aviso (``wait.*``) não tem frase da Nice: aviso em
    frase genérica do pacote nunca sai (condição 1 da decisão de 22/11/2026). Cada conversa tem
    o próprio motor, com o contexto e o envio dela; a falha numa não derruba as outras.
    """
    from shopman.shop.models import Conversation

    counts = {"conversations": 0, "notices": 0, "failed": 0, "skipped": ""}
    if not live_classes():
        counts["skipped"] = "classes_off"
        return counts
    missing = tick_templates_missing()
    if missing:
        counts["skipped"] = f"no_nice_template:{','.join(missing)}"
        return counts
    from .profile import build_profile

    profile = build_profile(environment=ENVIRONMENT)
    for pk in _due_conversations(TrustedContext(tenant=profile.tenant, environment=ENVIRONMENT, subject="")):
        conversation = Conversation.objects.filter(pk=pk).first()
        if conversation is None:
            continue
        counts["conversations"] += 1
        try:
            engine = build_engine(conversation, environment=ENVIRONMENT, channel=channel)
            if engine is None:
                continue
            _only_this_conversation(engine, conversation)
            results = engine.tick(engine.ports.clock.ctx)
            counts["notices"] += sum(1 for result in results if getattr(result, "reply", None) is not None)
        except Exception:  # noqa: BLE001 — uma conversa que falha não derruba o tick das outras
            counts["failed"] += 1
            logger.warning("concierge.turn_framework.tick_failed conversation=%s", pk, exc_info=True)
    return counts
