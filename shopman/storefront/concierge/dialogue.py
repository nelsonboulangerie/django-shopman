"""Memória da conversa: o estado explícito que resolve "sim", "o segundo", "mais 2".

Fatia "Memória" (bloco 2) de ``docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md``. O modelo
nunca "lembra": a casa guarda, em ``Conversation.flags["dialogue"]``, um estado pequeno
e explícito, e o código resolve a referência contra ele, sem rede e sem modelo:

- ``pending``: a pergunta que a casa deixou no ar e o que um "sim"/"não" faria;
- ``listed``: a última lista numerada que a casa mostrou ("o segundo", "essas opções");
- ``focus``: o produto em foco ("mais 2", "ele tem quantas fatias?");
- ``order``: o pedido em foco (o pedido em si, e o histórico, vêm do sistema);
- ``last_change``: a última mudança na sacola, para "não, era o outro";
- ``parts``: as partes da última mensagem lida pelas intenções no plural e o que houve
  com cada uma, para "você não respondeu" / "e a minha pergunta?" (``asks_again``).

Regra do dono (03/10/2026): **a memória vence pelo que acontece, não pelo relógio.**

- A pergunta pendente vale enquanto o assunto dela existir: o orçamento ainda é o
  mesmo, o pedido ainda está aberto, o dia de que se fala ainda não passou.
- Lista e foco valem até o fim do PRÓXIMO dia de funcionamento da loja (pelo
  calendário da casa, ``business_calendar``): sexta à noite, segunda de manhã ainda vale.
- Pedido entregue ou cancelado deixa de ser "pedido aberto" (não recebe mais item),
  mas segue como "pedido recente" por ``recent_order_days`` (7 por padrão) ou até o
  próximo pedido, o que vier primeiro.
- Quando a equipe devolve a conversa, a memória zera (``forget``).
- Estado vencido nunca vira suposição: "sim" ou "mais 2" sem referente viram pergunta.

O módulo tem duas metades. A pura (``effective``, ``resolve``, ``next_state``,
``memo_of``) recebe tudo por argumento e é o que o placar (``dialogue_eval``) mede. A
de banco (``for_turn``, ``save_turn``, ``forget``) lê o sistema ao vivo e grava na
mesma transação da resposta, conferindo o ``turn_fence``: turno revogado não grava.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

FLAG_KEY = "dialogue"
VERSION = 1
MAX_LISTED = 5
DEFAULT_RECENT_ORDER_DAYS = 7

#: Status em que o pedido ainda recebe conversa de "pedido aberto".
OPEN_ORDER_STATUSES = frozenset({"new", "accepted", "preparing", "ready", "dispatched"})
#: Quando cada status fechado aconteceu (campo do ``Order``).
CLOSED_AT_FIELDS = (
    ("delivered", "delivered_at"),
    ("completed", "completed_at"),
    ("cancelled", "cancelled_at"),
    ("returned", "returned_at"),
)
CLOSED_STATUS_LABEL = {
    "delivered": "entregue",
    "completed": "entregue",
    "cancelled": "cancelado",
    "returned": "devolvido",
}

# Tipos fechados de pergunta pendente.
OFFER_TEAM = "offer_team"  # "Posso chamar a equipe."
CHOOSE = "choose"  # "Qual deles você prefere?" (opções = a lista mostrada)
CONFIRM_ORDER = "confirm_order"  # resumo pronto, "Responda 'confirmo'"
ASK_ADDRESS = "ask_address"  # set_fulfillment devolveu o que falta do endereço
ASK_SLOT = "ask_slot"  # horários mostrados
CHOOSE_ORDER = "choose_order"  # "acrescentar ao pedido X (1) ou pedido novo (2)?"
CONFIRM_NEW = "confirm_new"  # "o pedido X já foi entregue; quer um pedido novo?"
CONFIRM_ADD = "confirm_add"  # "Acrescento 4 croissant ao pedido X? Total novo R$ Y. sim/não" (``order_addition``)

# Copy da casa (registro ``OmotenashiCopy``, editável no Admin).
ASK_WHAT_KEY = "CONCIERGE_MEMORY_ASK_WHAT"
ASK_WHICH_KEY = "CONCIERGE_MEMORY_ASK_WHICH"
ASK_PRODUCT_KEY = "CONCIERGE_MEMORY_ASK_PRODUCT"
ASK_QTY_PRODUCT_KEY = "CONCIERGE_MEMORY_ASK_QTY_PRODUCT"
ASK_ORDER_OR_NEW_KEY = "CONCIERGE_MEMORY_ASK_ORDER_OR_NEW"
ASK_NEW_AFTER_CLOSED_KEY = "CONCIERGE_MEMORY_ASK_NEW_AFTER_CLOSED"
DECLINED_KEY = "CONCIERGE_MEMORY_DECLINED"
ARRIVED_THANKS_KEY = "CONCIERGE_MEMORY_ARRIVED_THANKS"
ORDER_THANKS_KEY = "CONCIERGE_MEMORY_ORDER_THANKS"
COPY_KEYS = (
    ASK_WHAT_KEY,
    ASK_WHICH_KEY,
    ASK_PRODUCT_KEY,
    ASK_QTY_PRODUCT_KEY,
    ASK_ORDER_OR_NEW_KEY,
    ASK_NEW_AFTER_CLOSED_KEY,
    DECLINED_KEY,
    ARRIVED_THANKS_KEY,
    ORDER_THANKS_KEY,
)


# ── Fatos do sistema (lidos ao vivo a cada turno) ─────────────────────


@dataclass(frozen=True)
class OrderFact:
    ref: str
    status: str
    label: str  # "pedido ABC, retirada hoje a partir das 15h": dados do sistema
    fulfillment_type: str = ""
    closed_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_ORDER_STATUSES


@dataclass
class Facts:
    """O que o sistema sabe agora. A memória só aponta; a verdade mora aqui."""

    now: datetime
    quote_token: str = ""
    cart: dict = field(default_factory=dict)  # sku -> {"name", "qty"}
    open_order: OrderFact | None = None  # o pedido aberto mais recente do cliente
    recent_order: OrderFact | None = None  # o último pedido, fechado há pouco
    order_status: dict = field(default_factory=dict)  # ref -> status, dos pedidos lidos


# ── Vencimento ────────────────────────────────────────────────────────


def horizon(now: datetime, *, shop=None) -> datetime:
    """Fim do próximo dia de funcionamento depois do dia de ``now``.

    Pelo calendário da casa (grade semanal + exceções). Sem grade, o calendário
    degrada para "aberto todo dia" e o horizonte é o fim do dia seguinte.
    """
    from shopman.shop.services import business_calendar

    local = timezone.localtime(now)
    for offset in range(1, 16):
        day = local.date() + timedelta(days=offset)
        try:
            if not business_calendar.is_open_on(day, shop=shop):
                continue
            window = business_calendar.selling_hours_for(day, shop=shop)
        except Exception:
            logger.debug("concierge.dialogue horizon degraded", exc_info=True)
            window = None
        closes = window[1] if window else time(23, 59, 59)
        return datetime.combine(day, closes, tzinfo=local.tzinfo)
    return datetime.combine(local.date() + timedelta(days=1), time(23, 59, 59), tzinfo=local.tzinfo)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _parse_day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def effective(state: dict | None, facts: Facts) -> dict:
    """O estado que ainda vale agora, pelo que aconteceu desde que foi escrito."""
    if not isinstance(state, dict) or state.get("v") != VERSION:
        return {}
    out = {key: value for key, value in state.items() if key in {"v", "fence", "at", "valid_until"}}
    valid_until = _parse_dt(state.get("valid_until"))
    alive = bool(valid_until and facts.now <= valid_until)

    order = state.get("order") if isinstance(state.get("order"), dict) else None
    order_closed_since = False
    if order:
        status = facts.order_status.get(order.get("ref"), "")
        if order.get("open") and status and status not in OPEN_ORDER_STATUSES:
            # Entregue ou cancelado: a memória da conversa sobre ele fecha. O
            # pedido segue como "pedido recente", mas isso vem do sistema.
            order_closed_since = True
        out["order"] = order

    if alive and not order_closed_since:
        for key in ("listed", "focus", "last_change", "parts"):
            if state.get(key):
                out[key] = state[key]

    pending = state.get("pending") if isinstance(state.get("pending"), dict) else None
    if pending and _pending_alive(pending, facts, alive=alive, order_closed=order_closed_since):
        out["pending"] = pending
    return out


def _pending_alive(pending: dict, facts: Facts, *, alive: bool, order_closed: bool) -> bool:
    kind = pending.get("kind")
    if kind == CONFIRM_ORDER:
        # O assunto é o orçamento: vale enquanto for o mesmo.
        return bool(pending.get("token")) and pending.get("token") == facts.quote_token
    if pending.get("order_ref"):
        status = facts.order_status.get(pending["order_ref"], "")
        if kind == CHOOSE_ORDER:
            return status in OPEN_ORDER_STATUSES and alive
        if kind == CONFIRM_NEW:
            return alive
        if kind == CONFIRM_ADD:
            # Pedido que fechou não recebe o "sim"; quem confere a porta de novo
            # no "sim" é o serviço de edição.
            return status in OPEN_ORDER_STATUSES and alive
    if order_closed:
        return False
    day = _parse_day(pending.get("day"))
    if day is not None and timezone.localtime(facts.now).date() > day:
        return False
    return alive


# ── Leitura da fala ───────────────────────────────────────────────────


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold()) if not unicodedata.combining(char)
    )


def words(text: str) -> list[str]:
    """Palavras dobradas, sem pontuação, com letra repetida colapsada ("issoooo" → "isso")."""
    folded = re.sub(r"[^a-z0-9]+", " ", _fold(text))
    return [re.sub(r"([a-z])\1{2,}", r"\1", word) for word in folded.split()]


_YES_STRONG = {
    "sim", "s", "ss", "isso", "exato", "exatamente", "pode", "quero", "claro", "confirmo",
    "confirmado", "confirma", "fechado", "bora", "manda", "aham", "uhum", "yes", "positivo",
}
_YES_WEAK = {"ok", "okay", "certo", "beleza", "blz", "perfeito", "otimo", "combinado", "ta", "bom", "ah", "tudo", "bem"}
_YES_FILLER = {"mesmo", "ser", "sim", "favor", "por", "pfv", "pf", "entao", "isso", "com", "certeza", "pode", "quero", "e", "ai", "ver"}
_NO = {"nao", "n", "nem", "negativo", "deixa", "agora", "obrigado", "obrigada", "pra", "la", "para", "precisa", "nada"}


def answer_kind(tokens: list[str]) -> str:
    """``yes``/``weak_yes``/``no`` quando a fala é SÓ isso; vazio quando tem conteúdo."""
    if not tokens:
        return ""
    if tokens[0] in {"nao", "n", "negativo"} and all(t in _NO for t in tokens):
        return "no"
    if tokens == ["deixa"] or tokens[:2] == ["deixa", "pra"]:
        return "no"
    if any(t in _YES_STRONG for t in tokens) and all(t in _YES_STRONG | _YES_FILLER | _YES_WEAK for t in tokens):
        return "yes"
    if all(t in _YES_WEAK | {"e", "entao", "sim"} for t in tokens):
        return "weak_yes"
    return ""


def leading_yes(tokens: list[str]) -> bool:
    """"sim, já tinha confirmado!": o sim vem primeiro e o resto comenta."""
    return bool(tokens) and tokens[0] in {"sim", "s", "isso", "confirmo", "pode", "claro", "quero"} and len(tokens) > 1


_ORDINALS = {
    "primeiro": 1, "primeira": 1, "segundo": 2, "segunda": 2, "terceiro": 3, "terceira": 3,
    "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5,
}
_NUMBER_WORDS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "meia": 6, "duzia": 12,
}
_SELECT_FILLER = {"o", "a", "os", "as", "opcao", "numero", "n", "quero", "esse", "essa", "e", "pode", "ser", "vou", "querer", "do", "da", "de"}


def selection(tokens: list[str], size: int) -> int:
    """Índice (1..size) quando a fala só escolhe da lista: "o segundo", "o 2", "o último"."""
    if not tokens or size <= 0:
        return 0
    picks = []
    previous = ""
    for token in tokens:
        if token in _ORDINALS:
            picks.append(_ORDINALS[token])
        elif token in {"ultimo", "ultima"}:
            picks.append(size)
        elif token.isdigit() and len(token) <= 2:
            # "o 2" escolhe; "quero 2" é quantidade: o número só escolhe sozinho
            # ou depois de artigo.
            if len(tokens) > 1 and previous not in {"o", "a", "opcao", "numero", "n"}:
                return 0
            picks.append(int(token))
        elif token not in _SELECT_FILLER:
            return 0
        previous = token
    if len(picks) != 1 or not 1 <= picks[0] <= size:
        return 0
    return picks[0]


_QTY_FILLER = {
    "quero", "queria", "manda", "mande", "pode", "ser", "entao", "por", "favor", "e", "me", "da", "de",
    "mais", "outro", "outros", "outra", "outras", "so", "uns", "umas", "coloca", "poe", "bota", "acrescenta",
    "adiciona", "separa", "separar", "reserva", "reservar", "pra", "mim", "tambem", "ai",
}


def quantity_request(tokens: list[str]) -> tuple[int, bool, list[str]] | None:
    """``(qtd, relativa, resto)`` para "mais 2", "quero 2 então", "mais 4 croissant".

    ``resto`` são as palavras que sobram (o produto, quando o cliente disse qual).
    Só reconhece fala curta, de pedido: com pergunta ou frase longa, devolve None.
    """
    if not tokens or len(tokens) > 6:
        return None
    qty = 0
    rest = []
    relative = "mais" in tokens or "outro" in tokens or "outros" in tokens or tokens[:1] == ["+"]
    for token in tokens:
        if token.isdigit() and not qty and len(token) <= 3:
            qty = int(token)
        elif token in _NUMBER_WORDS and not qty:
            qty = _NUMBER_WORDS[token]
        elif token not in _QTY_FILLER:
            rest.append(token)
    if not qty:
        return None
    if not relative and not ({"quero", "manda", "mande", "entao", "pode", "coloca", "poe", "bota"} & set(tokens)):
        return None
    return qty, relative, rest


_CORRECTION = {"outro", "outra"}
_CORRECTION_FILLER = {"nao", "n", "era", "o", "a", "esse", "essa", "quero", "queria", "na", "verdade", "e", "eu", "disse", "falei", "foi"}


def is_correction(tokens: list[str]) -> bool:
    """"não, era o outro", "o outro"."""
    return bool(tokens) and bool(_CORRECTION & set(tokens)) and all(t in _CORRECTION | _CORRECTION_FILLER for t in tokens)


_SINGULAR = {"ele", "ela", "dele", "dela", "nele", "nela"}
_PLURAL = {"eles", "elas", "deles", "delas", "neles", "nelas", "essas", "esses", "estas", "estes"}
_DEMONSTRATIVE = {"esse", "essa", "este", "esta"}  # "isso" é concordância, não referência
#: Palavras que não são produto: perguntas sobre o item em foco ("tem quantas
#: fatias?", "ele tem glúten?") cabem; sobrou outra palavra, a fala nomeia outra
#: coisa e a memória não a reescreve.
_FUNCTION = {
    "e", "ou", "o", "a", "os", "as", "um", "uma", "tem", "tinha", "ter", "vem", "vcs", "voces", "voce", "vc",
    "quanto", "quantos", "quantas", "custa", "sai", "fica", "qual", "quais", "como", "hoje", "agora", "amanha",
    "disponivel", "disponiveis", "opcao", "opcoes", "ai", "aqui", "de", "do", "da", "com", "sem", "pra", "para",
    "eh", "mesmo", "tambem", "algo", "assim", "mais", "menos", "muito", "pouco", "por", "favor", "que",
    "pago", "pagar", "paga", "reais", "real", "preco", "valor", "fatias", "fatia", "gramas", "g", "kg", "peso",
    "tamanho", "sabor", "recheio", "gluten", "lactose", "leite", "ovo", "ovos", "castanha", "castanhas",
    "acucar", "vegano", "vegana", "alergia", "cabe", "serve", "pessoas", "ainda", "ja", "so", "dar", "pode", "posso", "quero", "queria", "reservar", "separar", "ver", "saber", "contem", "leva",
}


def pronoun_reference(tokens: list[str]) -> str:
    """``singular``/``plural`` quando a fala aponta para algo dito antes e não nomeia outra coisa."""
    if not tokens:
        return ""
    has_singular = bool(_SINGULAR & set(tokens))
    has_plural = bool(_PLURAL & set(tokens))
    has_demo = bool(_DEMONSTRATIVE & set(tokens)) and (tokens[0] == "e" or len(tokens) <= 3)
    if not (has_singular or has_plural or has_demo):
        return ""
    leftover = [t for t in tokens if t not in _FUNCTION | _SINGULAR | _PLURAL | _DEMONSTRATIVE and not t.isdigit()]
    if leftover:
        return ""
    return "plural" if has_plural else "singular"


_ARRIVED = {"chegou", "chegaram", "recebi", "recebemos", "recebido", "chegando"}
_THANKS = {"obrigado", "obrigada", "obg", "brigado", "brigada", "valeu", "vlw", "agradeco", "grato", "grata"}
_THANKS_FILLER = {
    "ok", "certo", "beleza", "perfeito", "otimo", "combinado", "ta", "bom", "tudo", "muito", "mt", "mto",
    "ja", "aqui", "e", "sim", "entao", "pela", "pelo", "ajuda", "atendimento", "demais", "mesmo", "gente",
    "pessoal", "certinho", "bem", "ai", "de", "novo",
}


def courtesy_event(tokens: list[str]) -> str:
    """``arrived`` ("obrigado, chegou!") ou ``thanks`` ("ok obrigada") quando é só isso."""
    if not tokens or not (_THANKS & set(tokens)):
        return ""
    allowed = _THANKS | _THANKS_FILLER | _ARRIVED
    if not all(t in allowed for t in tokens):
        return ""
    return "arrived" if _ARRIVED & set(tokens) else "thanks"


# ── Pergunta repetida ─────────────────────────────────────────────────
#
# Decisão da coordenação (03/10/2026, óbvio de omotenashi): "você não respondeu",
# "e a minha pergunta?" é a pergunta repetida, não reclamação. A Concierge responde
# o que ficou pendente (``parts`` da memória) em vez de mandar para a equipe. Só é
# reclamação quando há queixa explícita na mesma fala.

_NUDGE_RE = re.compile(
    r"(?:\b(?:voce|vc|voces|vcs|ninguem)\s+(?:ainda\s+)?)?\bnao\s+(?:me\s+|nos\s+)?respond\w*"
    r"|\brespond\w*\s+(?:nao|nada)\b"
    r"|\b(?:e|cade|e\s+ai)\s+(?:a\s+)?(?:minha|a)\s+(?:pergunta|duvida|resposta)\b"
    r"|\b(?:minha|minhas)\s+(?:pergunta|perguntas|duvida|duvidas)\b(?:\s+(?:ficou|ficaram|sem)\b[\w\s]{0,20})?"
    r"|\b(?:ficou|ficaram|fiquei|continuo|to|estou)\s+sem\s+resposta\b"
    r"|\bcade\s+(?:a\s+)?resposta\b"
    r"|\besqueceu\s+(?:de\s+)?(?:responder|me\s+responder|da\s+minha\s+pergunta)\b"
    r"|\bficou\s+faltando\b"
)
#: Queixa explícita: com ela, a fala é reclamação mesmo trazendo "não respondeu".
_EXPLICIT_COMPLAINT_RE = re.compile(
    r"\b(?:absurd\w*|descaso|pessim\w*|horrivel|ridicul\w*|vergonh\w*|desrespeit\w*|falta\s+de\s+respeito|"
    r"decepcion\w*|irritad\w*|indignad\w*|inaceitavel|palhacada|ofendid\w*|demor\w*|reclam\w*|"
    r"lamentavel|que\s+raiva|pouco\s+caso)\b"
)
#: O que sobra de um trecho de cobrança sem conteúdo próprio ("você ainda não me respondeu, ok?").
_NUDGE_FILLER = {
    "voce", "vc", "voces", "vcs", "ainda", "me", "ok", "oi", "ola", "ei", "e", "ai", "entao", "moca",
    "moco", "nada", "por", "favor", "pf", "pfv", "a", "o", "isso", "aqui", "ate", "agora", "hein", "ne", "ta", "gente",
}


def asks_again(text: str) -> bool:
    """A fala cobra uma resposta que não veio, sem queixa explícita."""
    from .handoff import classify_handoff_request

    folded = _fold(text)
    if not _NUDGE_RE.search(folded):
        return False
    return not (_EXPLICIT_COMPLAINT_RE.search(folded) or classify_handoff_request(text) == "complaint")


def without_nudge(text: str) -> str:
    """A fala sem o trecho de cobrança: o que sobra é pergunta nova (pode ser vazio).

    Divide por frase; a frase de cobrança sai inteira quando só tem a cobrança, e
    perde só a cobrança quando traz conteúdo ("você não respondeu se tem croissant").
    O que sobra volta dobrado (sem acento): a leitura e a busca dobram de qualquer jeito.
    """
    pieces = re.split(r"([?!.:;\n]+)", str(text or ""))
    out: list[str] = []
    for index in range(0, len(pieces), 2):
        sentence = pieces[index]
        delimiter = pieces[index + 1] if index + 1 < len(pieces) else ""
        folded = _fold(sentence)
        if _NUDGE_RE.search(folded):
            rest = _NUDGE_RE.sub(" ", folded)
            rest = re.sub(r"^\W*(?:se|sobre|de|do|da)\b", " ", rest.strip())
            if not [word for word in words(rest) if word not in _NUDGE_FILLER]:
                continue
            sentence = rest
        if sentence.strip():
            out.append(sentence.strip() + (delimiter.strip()[:1] if delimiter.strip()[:1] in {"?", "!", "."} else ""))
    return " ".join(out).strip()


# ── Resolução ─────────────────────────────────────────────────────────


@dataclass
class Resolution:
    """O que a memória fez com a fala.

    ``outcome``: ``pass`` (a fala segue como veio), ``resolved`` (a fala segue
    reescrita e/ou com a nota do que ela responde), ``ask`` (a casa pergunta, sem
    modelo), ``handoff`` (o "sim" aceitou a equipe), ``courtesy`` (agradecimento
    que reconhece o evento recente).
    """

    outcome: str = "pass"
    text: str = ""  # a fala reescrita, quando ``resolved``
    reply: str = ""  # a resposta da casa, quando ``ask``/``courtesy``
    note: str = ""  # para o prompt do agente
    reason: str = ""  # código para o placar e os testes
    refs: tuple[str, ...] = ()
    handoff_reason: str = ""
    memo: dict = field(default_factory=dict)  # o que a resolução grava no estado
    #: Acrescentar a pedido já feito (``order_addition``): ``{order_ref, add | sku+qty, item}``.
    #: ``add_preview`` (o cliente pediu: a casa pergunta com os dados do sistema) e
    #: ``add_apply`` (o "sim" à pergunta) são executados pelo agente, sem modelo.
    request: dict = field(default_factory=dict)

    @property
    def answers_without_model(self) -> bool:
        return self.outcome in {"ask", "handoff", "courtesy", "add_preview", "add_apply"}


_TIME_RE = re.compile(r"\b(\d{1,2})\s*(?:[:h]\s*(\d{2}))?\b")


def _slot_by_time(text: str, options: list[dict]) -> int:
    """"14:30" escolhe o horário que começa às 14:30 (só quando um único bate)."""
    match = _TIME_RE.search(str(text or ""))
    if not match:
        return 0
    wanted = f"{int(match.group(1)):02d}:{match.group(2) or '00'}"
    hits = [index for index, option in enumerate(options, 1) if str(option.get("name", "")).startswith(wanted)]
    return hits[0] if len(hits) == 1 else 0


def _fill(template: str, **values) -> str:
    out = template or ""
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out.strip()


def _options_text(options: list[dict]) -> str:
    return "; ".join(f"{item['n']}) {item.get('name') or item.get('ref')}" for item in options[:MAX_LISTED])


def resolve(text: str, memory: dict, facts: Facts, *, copy=None) -> Resolution:
    """A fala contra o estado que vale agora. Determinístico, sem rede."""
    if copy is None:
        from .service import copy_message as copy

    tokens = words(text)
    if not tokens:
        return Resolution()
    pending = memory.get("pending") or {}
    listed = list(memory.get("listed") or [])
    focus = memory.get("focus") or {}
    kind = pending.get("kind", "")
    answer = answer_kind(tokens)

    # 1. Cortesia que reconhece o evento recente (dado do sistema, nunca inventado).
    event = courtesy_event(tokens)
    if event:
        return _courtesy(event, memory, facts, copy=copy)

    # 2. A resposta à pergunta que a casa deixou no ar.
    if kind == CHOOSE_ORDER:
        picked = selection(tokens, 2)
        wants_new = picked == 2 or "novo" in tokens
        wants_order = picked == 1 or (
            not wants_new and bool({"pedido", "nele", "mesmo", "acrescenta", "acrescentar", "junto"} & set(tokens))
        )
        if wants_order:
            # Acrescentar a pedido já feito (dono, 03/10/2026): pelo mesmo serviço
            # do PDV, depois de uma pergunta de uma linha (``order_addition``).
            ref = pending.get("order_ref", "")
            item = pending.get("item", "")
            if pending.get("sku") and pending.get("qty"):
                return Resolution(
                    outcome="add_preview", reason="add_to_open_order", refs=(ref,),
                    request={"order_ref": ref, "add": [{"sku": pending["sku"], "qty": pending["qty"]}], "item": item},
                    memo={"pending": None},
                )
            return Resolution(
                outcome="resolved", reason="add_to_open_order", refs=(ref,), text=item,
                note=(
                    f"O cliente quer acrescentar {item} ao pedido {ref}, que já foi feito. Ache o produto "
                    f"(search_storefront) e chame add_to_order com order_ref {ref}. Não use set_item."
                ),
                memo={"pending": None},
            )
        if wants_new:
            item = pending.get("item", "")
            return Resolution(
                outcome="resolved",
                text=item,
                reason="new_order",
                note=f"O cliente quer um pedido NOVO com {item}; não mexa no pedido {pending.get('order_ref', '')}.",
                memo={"pending": None},
            )
        if answer in {"yes", "weak_yes"}:
            # "sim" para uma pergunta de duas saídas não escolhe nenhuma.
            options = [{"n": 1, "name": f"acrescentar ao {pending.get('order_ref', 'pedido')}"}, {"n": 2, "name": "pedido novo"}]
            return Resolution(outcome="ask", reply=_fill(copy(ASK_WHICH_KEY), options=_options_text(options)), reason="ask_which")
    if kind == CONFIRM_ADD:
        if answer in {"yes", "weak_yes"} or leading_yes(tokens):
            return Resolution(
                outcome="add_apply", reason="add_confirmed", refs=(pending.get("order_ref", ""),),
                request=dict(pending), memo={"pending": None},
            )
        if answer == "no":
            return Resolution(outcome="ask", reply=copy(DECLINED_KEY), reason="declined", memo={"pending": None})
    if kind == CONFIRM_NEW:
        if answer in {"yes", "weak_yes"}:
            item = pending.get("item", "")
            return Resolution(
                outcome="resolved", text=item, reason="new_order",
                note=f"O cliente confirmou um pedido NOVO com {item}.", memo={"pending": None},
            )
        if answer == "no":
            return Resolution(outcome="ask", reply=copy(DECLINED_KEY), reason="declined", memo={"pending": None})
    if kind == OFFER_TEAM:
        if answer == "yes" or leading_yes(tokens):
            return Resolution(outcome="handoff", reason="accepted_team", handoff_reason="o cliente aceitou falar com a equipe")
        if answer == "no":
            return Resolution(outcome="ask", reply=copy(DECLINED_KEY), reason="declined", memo={"pending": None})
    if (kind == CONFIRM_ORDER or (not kind and facts.quote_token)) and (answer in {"yes", "weak_yes"} or leading_yes(tokens)):
        # Sem outra pergunta no ar, o orçamento vigente (do sistema) é a pergunta.
        return Resolution(
            outcome="resolved", reason="confirm_order",
            note="O cliente respondeu SIM ao resumo vigente (quote_token do sistema). Se ele não mudou nada, siga para place_order.",
        )
    if kind == ASK_SLOT and pending.get("options"):
        options = pending["options"]
        picked = selection(tokens, len(options)) or _slot_by_time(text, options)
        if not picked and answer in {"yes", "weak_yes"} and len(options) == 1:
            picked = 1
        if picked:
            option = options[picked - 1]
            return Resolution(
                outcome="resolved", text=option.get("name", ""), reason="slot",
                note=f"O cliente escolheu o horário {option.get('name', '')} ({pending.get('day', '')}).",
            )
        if answer in {"yes", "weak_yes"}:
            return Resolution(outcome="ask", reply=_fill(copy(ASK_WHICH_KEY), options=_options_text(options)), reason="ask_which_slot")
    if kind == ASK_ADDRESS and not answer:
        return Resolution(outcome="resolved", reason="address", note="A fala responde ao que faltava do endereço da entrega: passe só as partes novas a set_fulfillment.", text=text)

    # 3. Escolha na lista mostrada: "o segundo", "o 2".
    if listed:
        picked = selection(tokens, len(listed))
        if picked:
            item = listed[picked - 1]
            return Resolution(
                outcome="resolved", text=item.get("name", ""), reason="ordinal", refs=(item.get("ref", ""),),
                note=f"\"{text.strip()}\" é o item {picked} da última lista: {item.get('name', '')}.",
                memo={"focus": {"ref": item.get("ref", ""), "name": item.get("name", "")}},
            )
    if is_correction(tokens):
        others = [item for item in listed if item.get("ref") != focus.get("ref")]
        if focus and len(others) == 1:
            other = others[0]
            change = memory.get("last_change") or {}
            note = f"Correção: o cliente queria {other.get('name')}, não {focus.get('name')}."
            if change.get("ref") == focus.get("ref"):
                note += f" A sacola recebeu {change.get('qty')} {focus.get('name')} no último passo: troque pelo item certo."
            return Resolution(
                outcome="resolved", text=other.get("name", ""), reason="correction", refs=(other.get("ref", ""),), note=note,
                memo={"focus": {"ref": other.get("ref", ""), "name": other.get("name", "")}},
            )
        if len(others) > 1:
            return Resolution(outcome="ask", reply=_fill(copy(ASK_WHICH_KEY), options=_options_text(others)), reason="ask_which",
                              memo={"pending": {"kind": CHOOSE, "options": others}})
        return Resolution(outcome="ask", reply=copy(ASK_PRODUCT_KEY), reason="no_referent")

    # 4. Quantidade: "mais 2", "quero 2 então", "mais 4 croissant".
    qty_request = quantity_request(tokens)
    if qty_request is not None:
        return _quantity(text, qty_request, memory, facts, copy=copy)

    # 5. "ele", "essas opções".
    reference = pronoun_reference(tokens)
    if reference == "plural" and len(listed) >= 2:
        names = ", ".join(item.get("name", "") for item in listed)
        return Resolution(
            outcome="resolved", text=f"{text} {names}", reason="plural", refs=tuple(i.get("ref", "") for i in listed),
            note=f"\"{text.strip()}\" se refere à última lista: {names}.",
        )
    if reference == "singular" and focus:
        return Resolution(
            outcome="resolved", text=f"{text} {focus.get('name', '')}", reason="pronoun", refs=(focus.get("ref", ""),),
            note=f"\"{text.strip()}\" se refere a {focus.get('name', '')}.",
        )
    if reference == "singular" and len(listed) == 1:
        item = listed[0]
        return Resolution(outcome="resolved", text=f"{text} {item.get('name', '')}", reason="pronoun", refs=(item.get("ref", ""),))
    if reference:
        return Resolution(outcome="ask", reply=copy(ASK_PRODUCT_KEY), reason="no_referent")

    # 6. "sim" que não responde a nada que ainda valha: pergunta, nunca supõe.
    if answer == "yes" and kind == CHOOSE and pending.get("options"):
        return Resolution(outcome="ask", reply=_fill(copy(ASK_WHICH_KEY), options=_options_text(pending["options"])), reason="ask_which")
    if answer in {"yes", "no"} and not kind:
        return Resolution(outcome="ask", reply=copy(ASK_WHAT_KEY), reason="no_pending")
    if answer == "no" and kind == CHOOSE:
        return Resolution(outcome="ask", reply=copy(DECLINED_KEY), reason="declined", memo={"pending": None})
    return Resolution(note=_context_note(memory))


def _quantity(text, qty_request, memory, facts, *, copy) -> Resolution:
    qty, relative, rest = qty_request
    pending = memory.get("pending") or {}
    focus = memory.get("focus") or {}
    product = " ".join(rest)
    target = product or focus.get("name", "")
    target_ref = "" if product else focus.get("ref", "")
    if not target:
        if pending.get("kind") == CHOOSE and pending.get("options"):
            # "quero 2 então" depois de duas opções: qual das duas?
            return Resolution(outcome="ask", reply=_fill(copy(ASK_WHICH_KEY), options=_options_text(pending["options"])), reason="ask_which")
        return Resolution(outcome="ask", reply=_fill(copy(ASK_QTY_PRODUCT_KEY), qty=qty), reason="qty_without_product")
    item = f"{qty} {target}"
    in_cart = facts.cart.get(target_ref) if target_ref else None
    if relative and facts.cart and (in_cart or not facts.open_order):
        note = f"\"{text.strip()}\": mais {qty} de {target} na sacola desta conversa."
        if in_cart:
            note += f" Já há {in_cart.get('qty')}; a quantidade total pedida é {int(in_cart.get('qty') or 0) + qty}."
        return Resolution(outcome="resolved", text=item, reason="relative_cart", refs=(target_ref,) if target_ref else (), note=note)
    if relative and facts.open_order:
        order = facts.open_order
        return Resolution(
            outcome="ask", reason="ask_order_or_new", refs=(order.ref,),
            reply=_fill(copy(ASK_ORDER_OR_NEW_KEY), item=item, order=order.label),
            memo={"pending": {"kind": CHOOSE_ORDER, "order_ref": order.ref, "item": item,
                              **({"sku": target_ref, "qty": qty} if target_ref else {})}},
        )
    if relative and facts.recent_order:
        order = facts.recent_order
        return Resolution(
            outcome="ask", reason="ask_new_after_closed", refs=(order.ref,),
            reply=_fill(copy(ASK_NEW_AFTER_CLOSED_KEY), item=item, order=order.label,
                        status=CLOSED_STATUS_LABEL.get(order.status, "fechado")),
            memo={"pending": {"kind": CONFIRM_NEW, "order_ref": order.ref, "item": item}},
        )
    if not product:
        return Resolution(
            outcome="resolved", text=item, reason="focus_qty", refs=(target_ref,),
            note=f"\"{text.strip()}\" se refere a {target}.",
            memo={"focus": {"ref": target_ref, "name": target, "qty": qty}},
        )
    note = ""
    if relative:
        note = f"O cliente disse \"mais\", mas não há sacola nem pedido aberto: trate {item} como pedido novo."
    return Resolution(outcome="pass", reason="explicit_product", note=note)


def _courtesy(event: str, memory: dict, facts: Facts, *, copy) -> Resolution:
    recent = facts.recent_order
    focus_order = (memory.get("order") or {}).get("ref")
    if event == "arrived":
        order = facts.open_order if facts.open_order and facts.open_order.status == "dispatched" else recent
        if order and order.fulfillment_type == "delivery" and order.status in {"dispatched", "delivered", "completed"}:
            return Resolution(outcome="courtesy", reply=copy(ARRIVED_THANKS_KEY), reason="arrived", refs=(order.ref,))
        return Resolution()
    order = facts.open_order
    if order and order.ref == focus_order:
        return Resolution(
            outcome="courtesy", reply=_fill(copy(ORDER_THANKS_KEY), summary=order.label), reason="order_thanks", refs=(order.ref,)
        )
    return Resolution()


def _context_note(memory: dict) -> str:
    parts = []
    pending = memory.get("pending") or {}
    if pending.get("kind") == CONFIRM_ORDER:
        parts.append("Há um resumo de pedido esperando a confirmação do cliente.")
    if memory.get("focus"):
        parts.append(f"Produto em foco: {memory['focus'].get('name', '')}.")
    if memory.get("listed"):
        parts.append("Última lista mostrada: " + _options_text(memory["listed"]) + ".")
    return " ".join(parts)


# ── Escrita ───────────────────────────────────────────────────────────


def memo_of(name: str, arguments: dict, result: dict) -> dict:
    """O pedaço do resultado de uma ferramenta que a memória guarda (pequeno)."""
    if not isinstance(result, dict) or result.get("ok") is False:
        return {}
    if name == "search_storefront":
        if result.get("found") is False:
            return {"tool": name, "found": False}
        if result.get("overview"):
            return {"tool": name, "collections": [
                {"ref": c.get("ref", ""), "name": c.get("label", "")} for c in result.get("collections", [])[:MAX_LISTED]
            ]}
        return {"tool": name, "items": [
            {"ref": i.get("sku", ""), "name": i.get("name", "")} for i in result.get("items", [])[:MAX_LISTED]
        ]}
    if name == "set_item":
        sku = str(arguments.get("sku") or "")
        line = next((line for line in result.get("lines", []) if line.get("sku") == sku), {})
        return {"tool": name, "ref": sku, "name": line.get("name", sku), "qty": arguments.get("qty")}
    if name == "review_order":
        return {"tool": name, "ready": bool(result.get("ready")), "token": str(result.get("quote_token") or "")}
    if name == "set_fulfillment":
        return {"tool": name, "address_question": bool(result.get("address_question"))}
    if name == "list_fulfillment_slots":
        slots = result.get("pickup_slots", result.get("delivery_slots", []))
        return {"tool": name, "date": result.get("date", ""), "slots": [
            {"ref": s.get("ref", ""), "name": s.get("label", "")} for s in slots if s.get("available", True)
        ][:MAX_LISTED]}
    if name == "place_order":
        return {"tool": name, "order_ref": str(result.get("order_ref") or "")}
    if name == "add_to_order":
        # A pergunta de confirmação (ou a oferta depois da recusa) fica no ar.
        return {"tool": name, "pending": result.get("pending")} if "pending" in result else {}
    if name == "order_status":
        orders = result.get("orders") or []
        return {"tool": name, "order_ref": orders[0].get("order_ref", "")} if orders else {}
    return {}


def _numbered(items: list[dict]) -> list[dict]:
    return [{"n": index, "ref": item.get("ref", ""), "name": item.get("name", "")} for index, item in enumerate(items[:MAX_LISTED], 1)]


def next_state(
    previous: dict, memos: list[dict], *, now: datetime, fence: int, open_order_refs=(), until: datetime | None = None
) -> dict:
    """O estado depois do turno: o que valia, mais o que a casa acabou de mostrar.

    Toda resposta substitui a pergunta pendente (a última pergunta da casa é a que
    está no ar); o resumo pendente sobrevive enquanto o orçamento for o mesmo.
    """
    state = {
        key: value for key, value in (previous or {}).items() if key in {"listed", "focus", "order", "last_change", "parts"}
    }
    old_pending = (previous or {}).get("pending") or {}
    pending = old_pending if old_pending.get("kind") == CONFIRM_ORDER else None
    today = timezone.localtime(now).date().isoformat()
    for memo in memos:
        tool = memo.get("tool")
        if "pending" in memo:
            pending = memo["pending"]
        if memo.get("focus"):
            state["focus"] = memo["focus"]
        if "parts" in memo:
            # As partes do último turno pelas intenções no plural e o que houve com cada
            # uma: a pergunta repetida ("e a minha pergunta?") responde a partir daqui.
            state["parts"] = memo["parts"]
        if tool == "search_storefront":
            if memo.get("found") is False:
                pending = {"kind": OFFER_TEAM, "day": today}
            elif memo.get("collections"):
                state["listed"] = _numbered([{**c, "kind": "collection"} for c in memo["collections"]])
                pending = {"kind": CHOOSE, "options": state["listed"], "day": today}
            elif memo.get("items"):
                state["listed"] = _numbered(memo["items"])
                if len(state["listed"]) == 1:
                    # Um item só: a casa informa, não pergunta. A pergunta do turno
                    # (o resumo, o horário) continua sendo a que está no ar.
                    state["focus"] = {"ref": state["listed"][0]["ref"], "name": state["listed"][0]["name"]}
                else:
                    pending = {"kind": CHOOSE, "options": state["listed"], "day": today}
        elif tool == "set_item":
            state["focus"] = {"ref": memo.get("ref", ""), "name": memo.get("name", ""), "qty": memo.get("qty")}
            state["last_change"] = {"ref": memo.get("ref", ""), "qty": memo.get("qty")}
        elif tool == "review_order":
            pending = {"kind": CONFIRM_ORDER, "token": memo["token"]} if memo.get("ready") and memo.get("token") else None
        elif tool == "set_fulfillment":
            pending = {"kind": ASK_ADDRESS, "day": today} if memo.get("address_question") else None
        elif tool == "list_fulfillment_slots":
            options = _numbered(memo.get("slots") or [])
            pending = {"kind": ASK_SLOT, "options": options, "day": memo.get("date") or today} if options else None
        elif tool in {"place_order", "order_status"} and memo.get("order_ref"):
            ref = memo["order_ref"]
            state["order"] = {"ref": ref, "open": ref in set(open_order_refs) or tool == "place_order"}
            pending = None
    if pending:
        state["pending"] = pending
    if not any(state.get(key) for key in ("listed", "focus", "order", "last_change", "pending", "parts")):
        return {}
    return {
        "v": VERSION,
        "fence": fence,
        "at": now.isoformat(),
        "valid_until": (until or horizon(now)).isoformat(),
        **{key: value for key, value in state.items() if value},
    }


# ── Banco ─────────────────────────────────────────────────────────────


def recent_order_days() -> int:
    from django.conf import settings

    cfg = getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}
    try:
        return max(0, int(cfg.get("recent_order_days", DEFAULT_RECENT_ORDER_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_RECENT_ORDER_DAYS


def _day_phrase(day: date | None, today: date) -> str:
    if day is None:
        return ""
    if day == today:
        return "hoje"
    if day == today + timedelta(days=1):
        return "amanhã"
    return day.strftime("%d/%m")


def order_label(order, *, now: datetime) -> str:
    """"pedido ABC, retirada hoje a partir das 15h", só com dado do pedido."""
    data = order.data or {}
    parts = [f"pedido {order.ref}"]
    kind = str(data.get("fulfillment_type") or "")
    if kind in {"pickup", "delivery"}:
        today = timezone.localtime(now).date()
        day = _parse_day(data.get("delivery_date")) or timezone.localtime(order.created_at).date()
        when = " ".join(
            part
            for part in (
                "retirada" if kind == "pickup" else "entrega",
                _day_phrase(day, today),
                _slot_label(str(data.get("delivery_time_slot") or "")),
            )
            if part
        )
        parts.append(when)
    return ", ".join(parts)


def _slot_label(slot_ref: str) -> str:
    if not slot_ref:
        return ""
    from .tools import _slot_label as label

    text = label("", slot_ref)
    # O rótulo do horário é título ("A partir das 9h"); no meio da frase, minúscula.
    return text[:1].lower() + text[1:]


def _closed_at(order):
    for status, attr in CLOSED_AT_FIELDS:
        if order.status == status:
            return getattr(order, attr, None) or order.updated_at
    return None


def load_facts(conversation, *, now: datetime | None = None, channel_ref: str = "") -> Facts:
    """O que o sistema sabe agora: orçamento, sacola e pedidos do cliente."""
    now = now or timezone.now()
    facts = Facts(now=now, quote_token=str((conversation.quote or {}).get("token") or ""))
    try:
        from shopman.shop.services import cart as cart_service

        if conversation.session_key:
            session = cart_service.get_open_session(
                session_key=conversation.session_key, channel_ref=channel_ref or conversation.channel_ref
            )
            for item in (session.items if session else []) or []:
                sku = str(item.get("sku") or "")
                if sku:
                    facts.cart[sku] = {"name": item.get("name") or sku, "qty": item.get("qty")}
    except Exception:
        logger.debug("concierge.dialogue cart degraded", exc_info=True)
    try:
        from shopman.orderman.models import Order

        from shopman.shop.services.customer_orders import customer_identity_filter

        identity = customer_identity_filter(
            customer_ref=conversation.customer_ref or None, phone=conversation.phone or None
        )
        orders = list(Order.objects.filter(identity).distinct().order_by("-created_at")[:5]) if identity is not None else []
        state = (conversation.flags or {}).get(FLAG_KEY) or {}
        focus_ref = (state.get("order") or {}).get("ref")
        if focus_ref and all(order.ref != focus_ref for order in orders):
            orders.extend(Order.objects.filter(ref=focus_ref)[:1])
        facts.order_status = {order.ref: order.status for order in orders}
        open_orders = [order for order in orders if order.status in OPEN_ORDER_STATUSES]
        if open_orders:
            order = open_orders[0]
            facts.open_order = OrderFact(order.ref, order.status, order_label(order, now=now),
                                         str((order.data or {}).get("fulfillment_type") or ""))
        latest = orders[0] if orders else None
        closed_at = _closed_at(latest) if latest else None
        if latest and closed_at and now - closed_at <= timedelta(days=recent_order_days()):
            facts.recent_order = OrderFact(latest.ref, latest.status, order_label(latest, now=now),
                                           str((latest.data or {}).get("fulfillment_type") or ""), closed_at)
    except Exception:
        logger.debug("concierge.dialogue orders degraded", exc_info=True)
    return facts


@dataclass
class TurnMemory:
    state: dict
    facts: Facts

    def prompt_lines(self) -> str:
        """O estado em prosa curta para o prompt do agente (o modelo lê, não decide)."""
        lines = []
        note = _context_note(self.state)
        if note:
            lines.append(note)
        if self.facts.open_order:
            lines.append(f"Pedido aberto do cliente: {self.facts.open_order.label} ({self.facts.open_order.status}).")
        if self.facts.recent_order:
            order = self.facts.recent_order
            lines.append(
                f"Pedido recente: {order.label}, {CLOSED_STATUS_LABEL.get(order.status, order.status)}. "
                "Não aceita mais item: acréscimo é pedido novo."
            )
        return "\n".join(lines)


def for_turn(conversation, *, now: datetime | None = None, channel_ref: str = "") -> TurnMemory:
    facts = load_facts(conversation, now=now, channel_ref=channel_ref)
    state = effective((conversation.flags or {}).get(FLAG_KEY), facts)
    return TurnMemory(state=state, facts=facts)


def save_turn(conversation, memos: list[dict], *, previous: dict, open_order_refs=(), now: datetime | None = None) -> bool:
    """Grava o novo estado com o mesmo ``turn_fence`` do turno; turno revogado não grava.

    Chamado dentro da transação que prepara a resposta, com a conversa já travada.
    """
    from shopman.shop.models import Conversation

    fence = getattr(conversation, "_turn_fence", None)
    if fence is None:
        return False
    now = now or timezone.now()
    current = Conversation.objects.select_for_update().filter(pk=conversation.pk, turn_fence=fence).first()
    if current is None:
        return False
    state = next_state(previous, memos, now=now, fence=fence, open_order_refs=open_order_refs)
    flags = dict(current.flags or {})
    if state:
        flags[FLAG_KEY] = state
    else:
        flags.pop(FLAG_KEY, None)
    return bool(Conversation.objects.filter(pk=conversation.pk, turn_fence=fence).update(flags=flags))


def forget(conversation_id: int) -> None:
    """A equipe devolveu a conversa: ela falou coisas que o sistema não viu. Zera."""
    from shopman.shop.models import Conversation

    current = Conversation.objects.select_for_update().filter(pk=conversation_id).first()
    if current is None or FLAG_KEY not in (current.flags or {}):
        return
    flags = dict(current.flags or {})
    flags.pop(FLAG_KEY, None)
    Conversation.objects.filter(pk=conversation_id).update(flags=flags)
