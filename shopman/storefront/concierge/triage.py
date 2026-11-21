"""Triagem do Concierge: toda mensagem ganha intenção, urgência e destino.

Decisão do dono em 02/10/2026 (D32, "aprovo a triagem"). O vocabulário não é
novo: as 12 intenções são as de ``intent_pilot.DEFAULT_INTENTS`` (combinadas com
o dono em 23/09) e as urgências são três, ``now`` (agora), ``today`` (hoje) e
``can_wait`` (pode esperar).

O destino sai de uma tabela fixa, a da proposta aprovada:

- ``answer``: o Concierge responde sozinho (horário e entrega, como funciona a
  casa, dúvida de produto sem alergia, status do pedido e pedido simples, que na
  fase 1 recebe o link da loja);
- ``team``: vai para uma pessoa, com o bot calado naquela conversa (pediu pessoa,
  reclamação, alergia, encomenda especial e o pedido que o chat não fecha);
  **exceção das perguntas de alergia** (dono, 03/10/2026): a pergunta sobre
  alérgeno o Concierge responde com o aviso de produção compartilhada da casa e
  os alérgenos declarados do produto citado (``allergens.py``); alergia sem dizer
  a quê recebe a pergunta "a quê?". Reação alérgica, alérgeno de que as fontes
  não falam e casa sem aviso cadastrado seguem para a equipe;
- ``other_desk``: vaga, parceria e fornecedor. Também cala o bot, mas o aviso
  fica no Admin e não chega ao sino do Gestor de pedidos: não acorda o balcão.

**Quem classifica.** A regra local (expressões, sem rede) roda sempre e é a
garantia: o que ela reconhece como sensível (pessoa, reclamação, alergia,
encomenda especial) escala mesmo que o Jev discorde. Com ``triage_with_model``
ligado, quem propõe a intenção é o Jev (TypeSafe, D-028, a primeira opinião por
decisão do dono): uma pergunta sim/não por intenção, vence a mais provável acima do
corte; urgência e resumo ficam com a tabela e a regra local. Sem aprovação, sem chave
ou com falha, vale a regra local. A triagem não chama modelo de texto (WP-08, corte
C2). Nenhuma categoria nasce aqui: resposta fora das 12 intenções é descartada.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from django.utils import timezone

from . import allergens
from .handoff import classify_handoff_request
from .intent_benchmark import REGEX_TO_INTENT
from .intent_pilot import DEFAULT_INTENTS
from .small_talk import small_talk_kind

#: O que a triagem grava em ``answered_by`` quando a R8 responde (``data-schemas.md``).
IDENTITY_ANSWERED_BY = "identity"


def _answers_identity(text: str) -> bool:
    from .house_rules import answers_identity

    return answers_identity(text)

logger = logging.getLogger(__name__)

INTENTS = tuple(ref for ref, *_rest in DEFAULT_INTENTS)
DEFAULT_LABELS = {ref: name for ref, name, *_rest in DEFAULT_INTENTS}

NOW, TODAY, CAN_WAIT = "now", "today", "can_wait"
URGENCIES = (NOW, TODAY, CAN_WAIT)
URGENCY_LABELS = {NOW: "agora", TODAY: "hoje", CAN_WAIT: "pode esperar"}

ANSWER, TEAM, OTHER_DESK = "answer", "team", "other_desk"
DESTINATION_LABELS = {
    ANSWER: "Respondida pelo Concierge",
    TEAM: "Com a equipe",
    OTHER_DESK: "Outra mesa",
}

#: As que sempre escalam, mesmo que o Jev proponha outra.
SENSITIVE = frozenset({"human", "complaint", "allergy"})

#: intenção → (destino, urgência padrão). A tabela da D32.
ROUTES = {
    "hours_delivery": (ANSWER, TODAY),
    "house_info": (ANSWER, CAN_WAIT),
    "product_question": (ANSWER, TODAY),
    "order_status": (ANSWER, NOW),
    "order": (ANSWER, NOW),
    "human": (TEAM, NOW),
    "complaint": (TEAM, NOW),
    "allergy": (TEAM, NOW),
    "special_order": (TEAM, TODAY),
    "job": (OTHER_DESK, CAN_WAIT),
    "partnership": (OTHER_DESK, CAN_WAIT),
    "supplier_offer": (OTHER_DESK, CAN_WAIT),
}
assert set(ROUTES) == set(INTENTS), "a tabela de destino cobre exatamente as 12 intenções"

#: Quando nada casa e o Jev não propõe, a mensagem segue para a resposta
#: automática como sempre seguiu (saudação, conversa solta). Fica marcada com a
#: fonte ``default`` para a casa saber que ninguém reconheceu a intenção.
FALLBACK_INTENT = "product_question"

SUMMARY_CHARS = 240


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )


# Em ordem: a primeira que casa vence. As sensíveis vêm antes, pela política de
# handoff (``handoff.classify_handoff_request``), que continua sendo a única
# regra local para pessoa, reclamação, encomenda especial e alergia.
_PATTERNS = (
    ("job", (
        r"\b(?:vagas?|emprego|curriculo|estagio|contratando|trabalhar\s+(?:ai|ai com voces|com voces|na padaria|na casa))\b",
    )),
    ("supplier_offer", (
        r"\b(?:fornecedor\w*|fornecemos|representante|distribuidor\w*|proposta comercial|"
        r"apresentar\s+(?:nossa|nosso|meu|minha)\s+(?:empresa|produto|servico|linha))\b",
        # Quem vende para a casa (WP-04): "tenho uma empresa que fornece…", "falar com o setor de compras".
        r"\bempresa\s+(?:que\s+)?(?:fornece|vende|distribui|fabrica|produz)\b",
        r"\b(?:setor|departamento|area|responsavel|encarregad\w*|comprador\w*)\s+(?:de|das|pelas?)\s+compras\b",
    )),
    ("partnership", (
        r"\b(?:parceria|permuta|influenciador\w*|influencer|divulga\w*|imprensa|jornalista|reportagem|"
        r"sessao de fotos|ensaio fotografico|gravacao|gravar\s+(?:um|uma|no|na|ai))\b",
    )),
    ("order_status", (
        r"\bstatus do (?:meu )?pedido\b",
        r"\b(?:meu|o)\s+pedido\b.{0,40}\b(?:saiu|chega|chegou|pronto|andamento|onde esta|ja foi|demora|vai demorar)\b",
    )),
    ("hours_delivery", (
        r"\b(?:horario|que horas|abre|abrem|fecha|fecham|aberto|aberta|funcionam|endereco|onde fica|"
        r"localizacao|retirada|retirar|entrega|entregam|delivery|frete|taxa de entrega)\b",
    )),
    ("house_info", (
        r"\b(?:pet|cachorro|estacionamento|wi-?fi|reserva de mesa|mesa|acessibilidade|cadeirante|"
        r"formas? de pagamento|aceitam?\s+(?:cartao|pix|vale|vr|va|alelo|sodexo|ticket))\b",
    )),
    ("order", (
        r"\b(?:quero|queria|gostaria de|vou querer|pedir|encomendar|reservar|separar|me (?:ve|manda|separa))\b",
    )),
    ("product_question", (
        r"\b(?:tem|teria|tinha|qual|quais|quanto|preco|sabor|ingrediente|tamanho|disponivel|cardapio)\b",
    )),
)


@dataclass(frozen=True)
class Triage:
    intent: str
    urgency: str
    destination: str
    summary: str
    #: ``rules`` (regra local), ``jev`` (Jev), ``intents`` (leitura em partes),
    #: ``default`` (nada casou) ou ``failures`` (duas tentativas sem resposta útil).
    source: str
    #: Por que o destino não é o da tabela, quando não é: ``order_not_closed``
    #: (segundo turno seguido de pedido que o chat não fecha),
    #: ``no_useful_answer`` (duas falhas seguidas da resposta automática),
    #: ``allergy_offer_accepted`` ("sim" à oferta da equipe para alergia grave) ou
    #: ``cancel_order`` (pedido de cancelamento, regra da casa R4).
    escalated_by: str = ""
    #: Por que o Concierge responde uma intenção que a tabela manda para a
    #: equipe (alergia, decisão do dono em 03/10/2026, ``allergens.py``):
    #: ``allergy_notice`` (respondida com o aviso da casa e os alérgenos
    #: declarados), ``allergy_ask_which`` (alergia sem dizer a quê: pergunta) ou
    #: ``allergy_notice_after_ask`` (a resposta a essa pergunta, respondida);
    #: e no cancelamento: ``self_cancel`` (cancelamento que o cliente poderia
    #: fazer pelo site; a Concierge pergunta e cancela) ou ``cancel_answer`` (o
    #: "sim" ou "não" à pergunta de cancelamento).
    answered_by: str = ""
    #: As probabilidades que o Jev deu a cada intenção neste turno (e a de "mais de uma
    #: parte", quando as intenções no plural estão ligadas). Vazio sem Jev. É a primeira
    #: opinião do porteiro das intenções (``intents.gate``).
    jev_scores: dict = field(default_factory=dict)

    @property
    def intent_label(self) -> str:
        return intent_label(self.intent)

    @property
    def urgency_label(self) -> str:
        return URGENCY_LABELS.get(self.urgency, self.urgency)

    @property
    def escalates(self) -> bool:
        return self.destination != ANSWER

    def as_dict(self) -> dict:
        return asdict(self)

    def reason_line(self) -> str:
        """O motivo do handoff, como o Admin mostra: rótulo e urgência."""
        return f"{self.intent_label} · {self.urgency_label}"[:200]


def intent_label(ref: str) -> str:
    """O nome que o dono deu à intenção no Admin; o padrão quando não há linha."""
    try:
        from shopman.storefront.models import IntentCategory

        name = IntentCategory.objects.filter(ref=ref).values_list("name", flat=True).first()
    except Exception:  # banco indisponível não pode derrubar o turno
        logger.warning("concierge.triage.intent_label_failed ref=%s", ref, exc_info=True)
        name = None
    return name or DEFAULT_LABELS.get(ref, ref)


#: O que não é fala: endereço de link e as marcas que a redação deixa no lugar do que apagou.
_NOT_SPEECH = re.compile(r"https?://\S+|www\.\S+|\[[^\[\]]*omitid[oa][^\[\]]*\]", re.IGNORECASE)


def _continued_intent(text: str, context) -> str:
    """A intenção da fala anterior do cliente, quando esta é só um link ou anexo.

    Só para o que é da equipe ou de outra mesa (currículo, reclamação, parceria): um link
    sozinho depois de "posso te mandar um currículo?" é o currículo. Fala com palavra, ou
    fala anterior que a Concierge responde, segue a regra de sempre.
    """
    if re.search(r"[A-Za-zÀ-ÿ0-9]", _NOT_SPEECH.sub(" ", str(text or ""))):
        return ""
    earlier = next((line for who, line in reversed(list(context or ())) if who == "Cliente" and line), "")
    if not earlier:
        return ""
    intent, _source = classify_rules(earlier)
    return intent if ROUTES.get(intent, (ANSWER,))[0] in {TEAM, OTHER_DESK} else ""


def classify_rules(text: str) -> tuple[str, str]:
    """(intenção, fonte) pela regra local. Nunca devolve intenção fora das 12."""
    sensitive = REGEX_TO_INTENT.get(classify_handoff_request(text), "")
    if sensitive:
        return sensitive, "rules"
    folded = _fold(text)
    for intent, patterns in _PATTERNS:
        if any(re.search(pattern, folded) for pattern in patterns):
            return intent, "rules"
    return FALLBACK_INTENT, "default"


def _clip(text: str, limit: int = SUMMARY_CHARS) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


#: O que sai do cartão do operador: documento, número longo (cartão, conta),
#: dado financeiro e segredo, e contatos (``redact_text``). Endereço, alergia e
#: o pedido FICAM: são o que a equipe precisa ler para agir. A redação da
#: observação passiva (``redact_observation_text``) tira justamente isso.
_CARD_REDACTIONS = frozenset({"cpf", "numeric_identifier", "financial"})


def _redacted(text: str) -> str:
    from shopman.shop.telemetry_redaction import redact_text

    from .observation_privacy import _DOMAIN_PATTERNS

    text = str(text or "")
    for category, pattern, replacement in _DOMAIN_PATTERNS:
        if category in _CARD_REDACTIONS:
            text = pattern.sub(replacement, text)
    return redact_text(text)


def rules_summary(intent: str, text: str) -> str:
    """Resumo sem modelo: a intenção e a fala do cliente, redigida e curta."""
    said = _clip(_redacted(text), 180)
    return f"{intent_label(intent)}. O cliente escreveu: \"{said}\"" if said else intent_label(intent)


# ── Jev ───────────────────────────────────────────────────────────────


def jev_enabled() -> bool:
    """A chave ``triage_with_model``: o Jev propõe a intenção (D-028). Desligada, só a regra."""
    from .service import config

    return bool(config().get("triage_with_model"))


def jev_categories() -> list:
    """As 12 intenções, com a descrição que o dono deu no Admin quando houver."""
    from .intent_benchmark import Category, load_categories

    try:
        edited = {category.ref: category for category in load_categories()}
    except Exception:  # banco indisponível: vale a descrição padrão
        logger.warning("concierge.triage.jev_categories_failed", exc_info=True)
        edited = {}
    return [
        edited.get(ref) or Category(ref, name, description, sensitive)
        for ref, name, description, sensitive in DEFAULT_INTENTS
    ]


def jev_scores(text: str, *, contender=None, with_parts: bool = False):
    """A probabilidade de cada uma das 12 intenções pelo Jev (``Prediction``).

    O texto vai REDIGIDO (``redact_observation_text``), o mesmo que o comparador
    manda: a aprovação do dono (D-028) é para texto redigido. Levanta
    ``ContenderNotConfigured`` sem aprovação ou chave, e o erro do provedor como
    veio; quem chama decide se é silêncio.
    """
    from .intent_benchmark import JevContender, Sample
    from .observation_privacy import redact_observation_text

    contender = contender or JevContender(timeout=10.0)
    sample = Sample(0, redact_observation_text(text).text, frozenset())
    categories = jev_categories()
    if with_parts:
        # Uma pergunta a mais na MESMA chamada: "a mensagem traz mais de uma coisa?"
        # (``intents.MULTIPLE_PARTS``). O Jev responde cada pergunta sim/não sozinha.
        from .intent_benchmark import Category
        from .intents import MULTIPLE_PARTS, MULTIPLE_PARTS_DESCRIPTION

        categories = [*categories, Category(MULTIPLE_PARTS, MULTIPLE_PARTS, MULTIPLE_PARTS_DESCRIPTION)]
    return contender.scores(sample, categories)


def best_jev_intent(scores: dict[str, float]) -> str:
    """A intenção mais provável acima do corte, ou vazio quando nenhuma passa."""
    from .intent_benchmark import PRESENT_AT

    ranked = sorted(
        ((p, ref) for ref, p in scores.items() if ref in ROUTES and p >= PRESENT_AT), reverse=True
    )
    return ranked[0][1] if ranked else ""


def classify_with_jev(text: str, *, contender=None, with_parts: bool = False) -> dict | None:
    """Proposta do Jev: a intenção, sem urgência nem resumo; ou None.

    ``scores`` leva todas as probabilidades (para o porteiro das intenções no plural),
    mesmo quando nenhuma intenção passa do corte.
    """
    try:
        prediction = jev_scores(text, contender=contender, with_parts=with_parts)
    except Exception as exc:  # sem aprovação, sem chave, rede, resposta ilegível: vale a regra
        logger.warning("concierge.triage.jev_failed exception_type=%s", type(exc).__name__)
        return None
    scores = prediction.intents
    intent = best_jev_intent(scores)
    rounded = {ref: round(p, 3) for ref, p in scores.items()}
    confidence = getattr(prediction, "confidence", None)
    if confidence is not None:
        # A confiança do Jev na própria escolha: o porteiro lê junto (``intents.gate``).
        from .intents import JEV_CONFIDENCE

        rounded[JEV_CONFIDENCE] = round(confidence, 3)
    return {"intent": intent, "urgency": "", "summary": "", "scores": rounded}


# ── Decisão ───────────────────────────────────────────────────────────


#: Intenções da regra que vencem a resposta de alergia: pessoa, reclamação
#: (inclusive reação alérgica, ``handoff.py``), encomenda especial e outra mesa.
_OVER_ALLERGY = frozenset({"human", "complaint", "special_order", "job", "partnership", "supplier_offer"})


def _allergy_route(text, rules_intent, *, context, previous, channel_ref) -> Triage | None:
    """Alergia (dono, 03/10/2026, ``allergens.py``): quem responde, ou None se não é alergia.

    A concierge responde com o aviso da casa e os alérgenos declarados, ou
    pergunta a que é a alergia. Fica registrado como alergia, sem consultar
    modelo nem Jev. O que ela não pode responder vai para a equipe, agora,
    mesmo que a regra não tenha visto alergia ("sem soja" não casa no
    ``handoff.py``).
    """
    if rules_intent in _OVER_ALLERGY:
        return None
    answered_before = (previous or {}).get("answered_by") or ""
    if answered_before in {allergens.NOTICE, allergens.NOTICE_AFTER_ASK} and allergens.accepts_team_offer(text):
        # "Sim" à oferta da equipe para alergia grave.
        return Triage("allergy", NOW, TEAM, rules_summary("allergy", text), "rules", allergens.OFFER_ACCEPTED)
    if answered_before == allergens.ASK_WHICH:
        earlier = next((said for who, said in reversed(list(context)) if who == "Cliente"), "")
        found = allergens.decision_after_ask(text, earlier=earlier, channel_ref=channel_ref)
        summary_text = f"{earlier} / {text}" if earlier else text
    else:
        found = allergens.decision(text, channel_ref=channel_ref)
        summary_text = text
    if not found:
        return None
    summary = rules_summary("allergy", summary_text)
    if found == allergens.TEAM:
        return Triage("allergy", NOW, TEAM, summary, "rules")
    return Triage("allergy", TODAY, ANSWER, summary, "rules", answered_by=found)


def decide(
    text: str,
    *,
    context: list[tuple[str, str]] = (),
    previous: dict | None = None,
    message_ids=(),
    commercial_authority: bool = False,
    contender=None,
    channel_ref: str = "",
    concierge_answers: str = "",
) -> Triage:
    """Intenção, urgência, destino e resumo de um turno.

    ``previous`` é a triagem anterior da conversa (``Conversation.flags["triage"]``):
    o segundo turno seguido de pedido que o chat não fecha (fase 1, sem
    autoridade comercial) vai para a equipe. Só conta a triagem de OUTRO turno:
    se ela cobre alguma das mensagens de agora (turno revogado por mensagem que
    chegou depois e repetido inteiro), não houve resposta entre as duas.
    """
    if previous and set(previous.get("message_ids") or ()) & set(message_ids):
        previous = None
    if concierge_answers in {"self_cancel", "cancel_answer"}:
        # Cancelamento conforme a etapa (dono, 03/10/2026): quem chamou já
        # conferiu, pela régua do site, que o próprio cliente poderia cancelar
        # (``cancellation.self_cancellable``), ou que a fala responde à pergunta
        # de cancelamento. A Concierge pergunta e cancela; fora disso, R4.
        return Triage("order", NOW, ANSWER, rules_summary("order", text), "rules", answered_by=concierge_answers)
    rules_intent, rules_source = classify_rules(text)
    continued = _continued_intent(text, context)
    if continued:
        # Só um link (ou anexo) depois de "posso te mandar um currículo?": é a continuação
        # da fala anterior, e vai para onde ela foi (#2910, msg-596).
        rules_intent, rules_source = continued, "rules"
    allergy = _allergy_route(text, rules_intent, context=context, previous=previous, channel_ref=channel_ref)
    if allergy is not None and (allergy.destination == ANSWER or allergy.escalated_by):
        return allergy
    # Alergia que a concierge não responde: equipe, agora.
    allergy_to_team = allergy is not None
    if not allergy_to_team and rules_intent not in SENSITIVE and _answers_identity(text):
        # R8 antes da triagem (dono, 20/11/2026): "com quem eu falo?", "é robô?", "é uma
        # pessoa?" recebem a frase fixa de assistente da casa. O Jev não transforma a
        # pergunta de quem atende em pedido de atendimento humano.
        return Triage("house_info", CAN_WAIT, ANSWER, rules_summary("house_info", text), "rules",
                      answered_by=IDENTITY_ANSWERED_BY)
    if small_talk_kind(text):
        # "Bom dia", "obrigado", "tchau": não há intenção a propor, e a concierge
        # responde a cortesia sem ferramenta. O Jev não é consultado.
        proposal = None
    else:
        # O Jev responde também se a mensagem traz mais de uma parte (``intents``).
        proposal = classify_with_jev(text, contender=contender, with_parts=True) if jev_enabled() else None

    scores = dict((proposal or {}).get("scores") or {})
    if proposal is not None and not proposal["intent"]:
        proposal = None  # o Jev não passou do corte em nenhuma: vale a regra (as probabilidades ficam)
    if allergy_to_team:
        intent, source = "allergy", "rules"
    elif rules_intent in SENSITIVE or rules_intent == "special_order":
        intent, source = rules_intent, "rules"
    elif proposal is not None:
        intent, source = proposal["intent"], "jev"
    else:
        intent, source = rules_intent, rules_source
    if intent == "complaint" and source == "jev" and asks_again(text):
        # "Você não respondeu", "e a minha pergunta?": pergunta repetida, não reclamação
        # (decisão da coordenação, 03/10/2026). Sem queixa explícita (a regra local não
        # viu reclamação), vale a regra, e a Concierge responde o que ficou pendente.
        intent, source = rules_intent, rules_source
        proposal = {**proposal, "summary": ""}

    destination, urgency = ROUTES[intent]
    if proposal is not None and proposal["urgency"] and destination != OTHER_DESK and intent not in SENSITIVE:
        urgency = proposal["urgency"]

    escalated_by = ""
    if (
        destination == ANSWER
        and intent not in SENSITIVE
        and classify_handoff_request(text) == "order_cancel"
    ):
        # Regra da casa R4: cancelar pedido que o cliente não poderia cancelar
        # pelo site (preparo já começado, de outra pessoa) é com a equipe.
        intent, destination, urgency, escalated_by = "order", TEAM, NOW, "cancel_order"
    elif (
        intent == "order"
        and not commercial_authority
        and (previous or {}).get("intent") == "order"
        and (previous or {}).get("destination") == ANSWER
    ):
        destination, urgency, escalated_by = TEAM, NOW, "order_not_closed"

    summary = (proposal or {}).get("summary") or rules_summary(intent, text)
    return Triage(intent, urgency, destination, summary, source, escalated_by, jev_scores=scores)


def asks_again(text: str) -> bool:
    from .dialogue import asks_again as nudge

    return nudge(text)


def after_failures(previous: dict | None, text: str) -> Triage:
    """Duas tentativas sem resposta útil: qualquer intenção vai para a equipe, agora."""
    previous = previous or {}
    intent = previous.get("intent") if previous.get("intent") in ROUTES else classify_rules(text)[0]
    summary = previous.get("summary") or rules_summary(intent, text)
    return Triage(intent, NOW, TEAM, summary, "failures", "no_useful_answer")


def record(conversation, inbound, triage: Triage) -> None:
    """Grava a triagem na mensagem, na conversa e no resumo.

    Mensagem: ``envelope["triage"]`` em cada entrada do turno. Conversa:
    ``flags["triage"]`` (a última, que o Admin filtra) e ``summary`` (o resumo
    que o operador lê). O objeto em memória é atualizado junto, porque as
    ferramentas do turno salvam ``flags`` a partir dele.
    """
    from shopman.shop.models import Conversation, ConversationMessage

    stamp = {
        **triage.as_dict(),
        "message_ids": [message.pk for message in inbound],
        "at": timezone.now().isoformat(),
    }
    for message in inbound:
        ConversationMessage.objects.filter(pk=message.pk).update(
            envelope={**(message.envelope or {}), "triage": triage.as_dict()}
        )
    flags = {**(Conversation.objects.filter(pk=conversation.pk).values_list("flags", flat=True).first() or {})}
    flags["triage"] = stamp
    Conversation.objects.filter(pk=conversation.pk).update(flags=flags, summary=triage.summary)
    conversation.flags = {**(conversation.flags or {}), "triage": stamp}
    conversation.summary = triage.summary


def context_for(conversation, *, limit: int = 6) -> list[tuple[str, str]]:
    """As últimas falas legíveis da conversa, para o resumo dizer o que já foi respondido."""
    from shopman.shop.models import ConversationMessage

    rows = list(
        conversation.messages.filter(
            kind__in=[ConversationMessage.Kind.INBOUND, ConversationMessage.Kind.REPLY],
            automation_eligible=True,
            consumed_by__isnull=False,
        )
        .exclude(text="")
        .order_by("-id")
        .values_list("kind", "text")[:limit]
    )
    who = {ConversationMessage.Kind.INBOUND: "Cliente", ConversationMessage.Kind.REPLY: "Casa"}
    return [(who[kind], text) for kind, text in reversed(rows)]


def customer_quote(text: str) -> str:
    """A fala do cliente entre aspas, redigida e curta; vazio sem fala."""
    said = _clip(_redacted(text), 180)
    return f"“{said}”" if said else ""


def handoff_message(conversation) -> str:
    """O cartão de handoff: só o que o cliente escreveu, entre aspas (coordenação, 20/11/2026).

    Quem é e por quê vêm no título, que a projeção do sino escreve pela conversa; onde
    responder, no botão. As mensagens do turno são as da triagem gravada; sem elas, a
    última do cliente.
    """
    from shopman.shop.models import ConversationMessage

    messages = conversation.messages.filter(kind=ConversationMessage.Kind.INBOUND)
    ids = list(((conversation.flags or {}).get("triage") or {}).get("message_ids") or [])
    texts = list(messages.filter(pk__in=ids).order_by("pk").values_list("text", flat=True)) if ids else []
    if not any(texts):
        texts = list(messages.order_by("-pk").values_list("text", flat=True)[:1])
    return customer_quote(" ".join(text for text in texts if text))


def alert_message(conversation, triage: Triage) -> str:
    """O cartão do operador: intenção e urgência, o resumo e onde responder."""
    who = conversation.customer_name or conversation.phone or ""
    lines = [
        f"{triage.intent_label}, urgência: {triage.urgency_label}.",
        triage.summary,
    ]
    if who:
        lines.append(f"Cliente: {who}.")
    if conversation.last_order_ref:
        lines.append(f"Último pedido: {conversation.last_order_ref}.")
    lines.append("Responda pelo Live Chat do ManyChat.")
    return "\n".join(line for line in lines if line)
