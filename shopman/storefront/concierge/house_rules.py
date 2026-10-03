"""Regras da casa: a tabela única do que a Concierge pode dizer e do que nunca diz.

Fatia F3 da arquitetura v2 (``docs/plans/CONCIERGE-ARQUITETURA-ALVO-V2.md``, seção 7;
OBS0310-M). A régua é do dono (03/10/2026): **nunca afirmar algo falso; se não sabe,
diz que vai verificar**, e verificar de verdade. Cada regra aqui tem um
identificador, quando se aplica, o que exige ou proíbe, o que acontece quando é
quebrada, e exemplos que são testes (``test_concierge_house_rules.py`` roda todos).

Por que em código, e não no Admin: regra de segurança precisa de versão, revisão
e teste antes de valer. O que é editável no Admin é a FRASE (Copy Omotenashi),
nunca a regra; e é por isso que as regras de saída valem também sobre a frase da
casa: uma copy editada com travessão, com "obrigado" ou com uma promessa que
ninguém cumpre é pega na saída, como qualquer outra resposta.

**Onde cada regra atua.**

- *Entrada* (R3, R4, R7, R8, R9): decidem quem responde antes do modelo. As de
  equipe moram em ``handoff.py`` e ``triage.py`` (a garantia sem rede), a de
  cortesia em ``small_talk.py``, a de alergia no executor de alergia; as frases
  fixas de R7 e R8 saem daqui (``fixed_reply_for``).
- *Saída* (R1, R2, R3, R5, R6, R8, R10 a R13): toda resposta, inclusive a montada
  pelo sistema, passa por ``review`` antes de ser gravada para envio
  (``service.run_turn`` e ``service._prepare_reply``).
- *Envio* (R14): a janela de 24 h da Meta, no transporte
  (``transport.authorize_response``).

**O que acontece quando uma regra de saída é quebrada** (``Effect``):

- ``REPAIR``: a palavra é trocada e a resposta segue ("esgotado" vira
  "indisponível", "obrigado" vira "obrigada", travessão vira vírgula);
- ``HOLD``: a resposta NÃO sai. A conversa vai para a equipe, e o cliente recebe o
  aviso de atendimento humano, que é verdadeiro porque o atendimento foi de fato
  pedido (o recibo existe). É o "não sei, vou verificar" possível hoje, até a
  fatia F5 trazer a verificação com prazo;
- ``RECORD``: só mede. Vale para a forma (R11) da resposta montada pela casa, que
  hoje é a base: reprovar a base não deixaria nada para mandar no lugar.

**Origem da resposta.** ``HOUSE`` é texto montado pelo código a partir dos dados
(copy da casa, resultado de ferramenta, aviso de alergia); ``MODEL`` é texto
livre de modelo. Hoje nenhum texto do modelo chega ao cliente (``agent.run_agent``
só devolve o resultado canônico das ferramentas), então R1 e R5 são cumpridas
por construção e o verificador delas só reprova texto ``MODEL``: é a trava para a
redação com marcadores (F6) e a régua que o placar aplica às respostas antigas do
alpha, que eram do modelo.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

#: Versão da tabela, gravada no envelope de cada resposta (``data-schemas.md``).
VERSION = 1

# ── Vocabulário ───────────────────────────────────────────────────────

ENTRY, OUTPUT, SEND = "entrada", "saída", "envio"

HOUSE, MODEL = "house", "model"
ORIGINS = (HOUSE, MODEL)


class Effect:
    ROUTE_TEAM = "route_team"  # entrada: a conversa vai para a equipe
    FIXED_REPLY = "fixed_reply"  # entrada: frase fixa da casa, sem modelo nem busca
    REPAIR = "repair"  # saída: troca a palavra e segue
    HOLD = "hold"  # saída: não sai; equipe, com o aviso de handoff
    RECORD = "record"  # saída: só mede
    REFUSE_SEND = "refuse_send"  # envio: o transporte recusa


EFFECT_LABELS = {
    Effect.ROUTE_TEAM: "vai para a equipe",
    Effect.FIXED_REPLY: "frase fixa da casa",
    Effect.REPAIR: "a palavra é corrigida e a resposta segue",
    Effect.HOLD: "a resposta não sai; a conversa vai para a equipe, com o aviso de atendimento humano",
    Effect.RECORD: "só mede (gravado no envelope)",
    Effect.REFUSE_SEND: "o transporte recusa o envio",
}

#: Recibos: o que de fato aconteceu no turno e que autoriza dizer que aconteceu.
TEAM_NOTIFIED = "team_notified"  # um cartão foi criado para a equipe
HANDOFF = "handoff"  # a conversa foi entregue à equipe
CART = "cart"  # a sacola mudou
ORDER = "order"  # o pedido foi registrado
NOTIFY = "notify"  # aviso de disponibilidade registrado
VERIFY = "verify"  # verificação com prazo aberta (fatia F5; ainda não existe)


def fold(text: str) -> str:
    """Minúsculas e sem acento: "Indisponível" e "indisponivel" são a mesma palavra."""
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )


# ── Contexto e resultado ──────────────────────────────────────────────


@dataclass(frozen=True)
class ReplyContext:
    """O que a regra precisa saber sobre a resposta: de onde veio e o que aconteceu."""

    origin: str = HOUSE
    receipts: frozenset[str] = frozenset()
    #: A fala do cliente no turno (R12: emoji só se o cliente usou, para texto do modelo).
    customer_text: str = ""
    #: Telefones e e-mails da própria casa, que podem sair (R13).
    house_contacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Violation:
    rule: str
    effect: str
    found: str

    def as_dict(self) -> dict:
        # O dado pessoal que R13 achou não vai para o envelope: o envelope é lido no Admin.
        found = "[dado pessoal omitido]" if self.rule == "R13" else self.found[:80]
        return {"rule": self.rule, "effect": self.effect, "found": found}


@dataclass
class Review:
    """O que a tabela fez com as respostas de um turno."""

    texts: list[str] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @property
    def held(self) -> list[Violation]:
        return [v for v in self.violations if v.effect == Effect.HOLD]

    @property
    def repaired(self) -> list[Violation]:
        return [v for v in self.violations if v.effect == Effect.REPAIR]

    @property
    def recorded(self) -> list[Violation]:
        return [v for v in self.violations if v.effect == Effect.RECORD]

    def reason_line(self) -> str:
        """O motivo do handoff, como o Admin mostra."""
        ids = list(dict.fromkeys(v.rule for v in self.held))
        titles = "; ".join(f"{rid} {RULES_BY_ID[rid].title}" for rid in ids)
        return f"Regra da casa: {titles}"[:200]

    def as_envelope(self) -> dict:
        """``ConversationMessage.envelope["house_rules"]`` (``data-schemas.md``)."""
        return {
            "version": VERSION,
            "held": sorted({v.rule for v in self.held}),
            "repaired": sorted({v.rule for v in self.repaired}),
            "recorded": sorted({v.rule for v in self.recorded}),
            "violations": [v.as_dict() for v in self.violations],
        }


# ── A regra ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HouseRule:
    id: str
    title: str
    stages: tuple[str, ...]
    #: Quando se aplica.
    when: str
    #: O que exige ou proíbe.
    demands: str
    #: O que acontece se for quebrada, por origem (``HOUSE``/``MODEL``); nas de
    #: entrada e envio, uma só.
    on_violation: dict[str, str]
    #: Quem executa (módulo e função), para a leitura da tabela levar ao código.
    enforced_by: str
    #: Exemplos que PRECISAM disparar e que NÃO podem disparar. ``must_*`` são
    #: respostas (regra de saída, conferidas com a origem ``examples_origin``);
    #: ``entry_*`` são falas do cliente (regra de entrada). Viram teste parametrizado.
    must_flag: tuple[str, ...] = ()
    must_pass: tuple[str, ...] = ()
    entry_flag: tuple[str, ...] = ()
    entry_pass: tuple[str, ...] = ()
    examples_origin: str = HOUSE
    #: Entrada: a fala dispara a regra? Saída: o que a resposta quebra.
    entry_check: Callable[[str], bool] | None = None
    output_check: Callable[[str, ReplyContext], list[str]] | None = None
    #: Saída, ``REPAIR``: devolve o texto consertado.
    repair: Callable[[str, ReplyContext], str] | None = None

    def effect_for(self, origin: str) -> str:
        return self.on_violation.get(origin) or next(iter(self.on_violation.values()))


# ── Ajudantes de texto ────────────────────────────────────────────────

#: Blocos travados (código Pix copia e cola, link): montados pelo código, ficam fora
#: das regras de forma e de dado pessoal. O link não é dado pessoal e o Pix é o
#: bloco que a casa manda separado.
_PIX_RE = re.compile(r"000201\S{20,}")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)


def _without_locked(text: str) -> str:
    return _URL_RE.sub(" ", _PIX_RE.sub(" ", str(text or "")))


def _hits(patterns: Iterable[re.Pattern], text: str) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        found.extend(match.group(0) for match in pattern.finditer(text))
    return found


def _compile(*patterns: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(p) for p in patterns)


def _keep_case(original: str, replacement: str) -> str:
    return replacement[:1].upper() + replacement[1:] if original[:1].isupper() else replacement


# ── R1 e R5: fato e dinheiro só de fonte ──────────────────────────────

_NUMBER_WORDS = (
    r"dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|quatorze|catorze|quinze|"
    r"dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta|cinquenta|sessenta|setenta|"
    r"oitenta|noventa|cem|meia\s+duzia|duzia"
)
_FACT_PATTERNS = _compile(
    r"\d+(?:[.,:h]\d+)*",
    r"r\$",
    r"\breais\b|\bcentavos\b",
    r"https?://\S+|www\.\S+",
    rf"\b(?:{_NUMBER_WORDS})\b",
)


def _check_fact(text: str, ctx: ReplyContext) -> list[str]:
    """Texto do modelo não digita número, preço, horário nem link (só por marcador, F6)."""
    if ctx.origin != MODEL:
        return []
    return _hits(_FACT_PATTERNS, fold(text))


_MONEY_PATTERNS = _compile(
    r"\b(?:total|subtotal|pix|copia e cola|link de pagamento|valor|taxa|frete|desconto|cobranc\w*|"
    r"pagamento|pagar|pague)\b",
)


def _check_money(text: str, ctx: ReplyContext) -> list[str]:
    """Total, Pix, link de pagamento e resumo só em bloco travado, montado pelo código."""
    if ctx.origin != MODEL:
        return []
    return _hits(_MONEY_PATTERNS, fold(text))


# ── R2: "Indisponível", sem motivo ────────────────────────────────────

_UNAVAILABLE_PATTERNS = _compile(
    r"\besgotad[oa]s?\b",
    r"\b(?:sem|fora\s+de)\s+estoque\b",
    r"\bacab(?:ou|aram)\b(?!\s+de\b)",
    # "O atendimento automático está pausado" fala do atendimento, não do produto.
    r"(?<!atendimento automatico esta )(?<!atendimento esta )\bpausad[oa]s?\b",
)


def _check_unavailable(text: str, ctx: ReplyContext) -> list[str]:
    return _hits(_UNAVAILABLE_PATTERNS, fold(text))


def _repair_unavailable(text: str, ctx: ReplyContext) -> str:
    def word(match: re.Match) -> str:
        plural = match.group(0).casefold().endswith("s")
        return _keep_case(match.group(0), "indisponíveis" if plural else "indisponível")

    text = re.sub(r"\besgotad[oa]s?\b", word, text, flags=re.I)
    text = re.sub(r"(?<!atendimento automático está )(?<!atendimento está )\bpausad[oa]s?\b", word, text, flags=re.I)
    text = re.sub(
        r"\b(?:sem|fora\s+de)\s+estoque\b",
        lambda m: _keep_case(m.group(0), "indisponível"),
        text,
        flags=re.I,
    )
    text = re.sub(r"\bacabaram\b(?!\s+de\b)", lambda m: _keep_case(m.group(0), "estão indisponíveis"), text, flags=re.I)
    text = re.sub(r"\bacabou\b(?!\s+de\b)", lambda m: _keep_case(m.group(0), "está indisponível"), text, flags=re.I)
    return text


# ── R3: alergia ───────────────────────────────────────────────────────

_ALLERGEN_WORDS = (
    r"gluten|lactose|leite|ovos?|castanh\w*|nozes|noz|amendoim|amendoas?|avelas?|pistaches?|"
    r"macadamias?|soja|gergelim|sesamo|trigo|frutos\s+do\s+mar|peixes?|camarao|mostarda|crustaceos?"
)
_ALLERGY_CLAIM_PATTERNS = _compile(
    rf"\b(?:sem|livre\s+de|livres\s+de|isent[oa]s?\s+de|zero)\s+(?:{_ALLERGEN_WORDS})\b",
    rf"\bnao\s+(?:tem|temos|contem|leva|levam|possui|possuem|usa|usamos|vai)\s+(?:nada\s+de\s+)?(?:{_ALLERGEN_WORDS})\b",
    r"\bpode(?:m)?\s+comer\b",
    r"\b(?:e|sao|esta|estao|fica)\s+segur[oa]s?\s+para\b",
    r"\bseguro\s+para\s+(?:alergic|celiac|intolerant)\w*",
)


def _check_allergy_claim(text: str, ctx: ReplyContext) -> list[str]:
    """Nunca afirmar ausência de alérgeno, nunca "pode comer"."""
    return _hits(_ALLERGY_CLAIM_PATTERNS, fold(text))


def _entry_allergy(text: str) -> bool:
    from .triage import classify_rules

    return classify_rules(text)[0] == "allergy"


# ── R4: equipe ────────────────────────────────────────────────────────


def _entry_team(text: str) -> bool:
    from .handoff import TEAM_CATEGORIES, classify_handoff_request

    return classify_handoff_request(text) in TEAM_CATEGORIES


# ── R6: promessa só com recibo ────────────────────────────────────────

_WHO = r"(?:equipe|alguem|atendente|atendimento|gerente|responsavel|time|pessoa)"
#: (padrões, recibos que autorizam). A promessa sai só com UM dos recibos do turno.
_PROMISES: tuple[tuple[tuple[re.Pattern, ...], frozenset[str]], ...] = (
    (
        _compile(
            rf"\b(?:ja\s+)?(?:avisei|chamei|acionei|encaminhei|solicitei|notifiquei|passei)\b.{{0,40}}\b{_WHO}\b",
            rf"\bvou\s+(?:avisar|chamar|acionar|encaminhar|notificar|passar)\b.{{0,40}}\b{_WHO}\b",
        ),
        frozenset({TEAM_NOTIFIED, HANDOFF}),
    ),
    (
        _compile(
            r"\b(?:a|nossa)\s+equipe\s+(?:ja\s+)?(?:vai|ira|continua|continuara|segue|seguira|assume|assumira|"
            r"retorna|retornara|responde|respondera|te\s+(?:chama|responde|retorna))\b",
            r"\balguem\s+da\s+equipe\s+(?:ja\s+)?(?:vai|ira|continua|continuara|segue|assume|te\s+\w+)\b",
        ),
        frozenset({HANDOFF}),
    ),
    (
        _compile(
            r"\b(?:ja\s+)?(?:separei|reservei|adicionei|garanti)\b",
            r"\bcoloquei\b.{0,40}\b(?:sacola|carrinho|pedido)\b",
            r"\b(?:deixei|ficou|ficaram|esta|estao)\s+(?:ja\s+)?separad[oa]s?\b",
        ),
        frozenset({CART, ORDER}),
    ),
    (
        _compile(
            r"\bpedido\b(?:\s+\S*\d\S*)?\s+(?:confirmado|registrado|anotado)\b",
            r"\bpedido\b.{0,40}\b(?:esta|foi|ficou)\s+(?:ja\s+)?(?:confirmado|registrado|anotado)\b",
            r"\b(?:anotei|confirmei|registrei)\b",
        ),
        frozenset({ORDER}),
    ),
    (
        _compile(
            r"\bvou\s+(?:verificar|conferir|checar|consultar|perguntar|confirmar\s+(?:com|para|pra))\b",
            r"\b(?:ja\s+)?(?:te|lhe)\s+(?:aviso|retorno|respondo|confirmo)\b",
            r"\bassim\s+que\s+(?:eu\s+)?(?:souber|tiver|confirmar|chegar|voltar)\b",
        ),
        frozenset({VERIFY, HANDOFF, NOTIFY}),
    ),
    (
        # "Confirme com a loja" sem acionar ninguém é não-resposta (teste de campo,
        # PR #1441): mandar o cliente perguntar a outro lugar só com a equipe acionada.
        _compile(
            r"\b(?:confirme|confira|verifique|consulte|pergunte|ligue|fale|entre\s+em\s+contato)\s+"
            r"(?:diretamente\s+)?(?:com|para|na|no)\s+(?:a\s+|o\s+)?(?:loja|equipe|casa|atendimento|balcao|padaria)\b",
        ),
        frozenset({HANDOFF}),
    ),
)


def _check_promise(text: str, ctx: ReplyContext) -> list[str]:
    """Dizer que fez (ou que vai fazer) só quando o executor deixou o recibo."""
    folded = fold(text)
    found: list[str] = []
    for patterns, receipts in _PROMISES:
        if receipts & ctx.receipts:
            continue
        found.extend(_hits(patterns, folded))
    return found


# ── R7: nunca negociar ────────────────────────────────────────────────

_NEGOTIATION_PATTERNS = _compile(
    r"\bdesconto\w*\b",
    r"\b(?:faz|faca|fazer|da\s+para\s+fazer|consegue\s+fazer)\s+(?:um\s+)?(?:preco|precinho|valor)\b",
    r"\b(?:abaixa|baixa|baixar|abaixar|melhora|melhorar)\s+(?:o|esse|um\s+pouco\s+o)?\s*(?:preco|valor)\b",
    r"\b(?:fazer|faz|sai)\s+(?:mais\s+)?barat\w*\b",
    r"\b(?:dono|dona|gerente|nelson|chefe)\s+(?:autorizou|liberou|deixou|prometeu|disse\s+que)\b",
    r"\bchorar\s+(?:o\s+)?preco\b|\bpechinch\w*\b",
)


def asks_negotiation(text: str) -> bool:
    return bool(_hits(_NEGOTIATION_PATTERNS, fold(text)))


# ── R8: assistente da casa ────────────────────────────────────────────

_IDENTITY_PATTERNS = _compile(
    r"\b(?:voce|vc|vcs|voces|tu|e|eh|sera\s+que\s+e|isso\s+e|aqui\s+e|estou\s+falando\s+com|to\s+falando\s+com|"
    r"falo\s+com)\s+(?:um\s+|uma\s+|o\s+|a\s+)?(?:robo|robozinho|bot|chatbot|maquina|ia|inteligencia\s+artificial|"
    r"pessoa(?:\s+de\s+verdade|\s+real)?|humano|humana|gente\s+de\s+verdade|atendente\s+virtual|"
    r"assistente\s+virtual|automatico|automatica|resposta\s+automatica)\b",
    r"\b(?:qual|como)\s+(?:e\s+)?(?:o\s+)?(?:seu|teu)\s+nome\b|\bcomo\s+(?:voce|vc)\s+se\s+chama\b",
)
_DENIAL_PATTERNS = _compile(
    r"\bsou\s+(?:uma?\s+)?(?:pessoa|humana?|atendente\s+de\s+verdade|gente\s+de\s+verdade)\b",
    r"\bnao\s+sou\s+(?:uma?\s+)?(?:robo|bot|maquina|assistente\s+virtual|ia|inteligencia\s+artificial|automatic[oa])\b",
)


def asks_identity(text: str) -> bool:
    return bool(_hits(_IDENTITY_PATTERNS, fold(text)))


def _check_denial(text: str, ctx: ReplyContext) -> list[str]:
    """Nunca negar ser automação."""
    return _hits(_DENIAL_PATTERNS, fold(text))


# ── R9: cortesia ──────────────────────────────────────────────────────


def _entry_courtesy(text: str) -> bool:
    from .small_talk import small_talk_kind

    return bool(small_talk_kind(text))


# ── R10: voz feminina ─────────────────────────────────────────────────

_VOICE_REPAIRS = (
    (re.compile(r"\bobrigad[oa]\s*\(a\)", re.I), "obrigada"),
    (re.compile(r"\bobrigado\b", re.I), "obrigada"),
    (re.compile(r"\bnosso\s+concierge\b", re.I), "nossa concierge"),
    (re.compile(r"\bdo\s+concierge\b", re.I), "da concierge"),
    (re.compile(r"\bo\s+concierge\b", re.I), "a concierge"),
    (re.compile(r"\bum\s+assistente\s+autom[aá]tico\b", re.I), "uma assistente automática"),
    (re.compile(r"\bum\s+assistente\b", re.I), "uma assistente"),
    (re.compile(r"\bsou\s+o\s+assistente\b", re.I), "sou a assistente"),
)


def _check_voice(text: str, ctx: ReplyContext) -> list[str]:
    return [m.group(0) for pattern, _ in _VOICE_REPAIRS for m in pattern.finditer(text)]


def _repair_voice(text: str, ctx: ReplyContext) -> str:
    for pattern, replacement in _VOICE_REPAIRS:
        text = pattern.sub(lambda m, r=replacement: _keep_case(m.group(0), r), text)
    return text


# ── R11: forma ────────────────────────────────────────────────────────

MAX_LINES = 3
MAX_CHARS = 400
MAX_QUESTIONS = 1
MAX_LIST_ITEMS = 3
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•·]|\d+[.)])\s+")


def _check_form(text: str, ctx: ReplyContext) -> list[str]:
    body = _without_locked(text)
    lines = [line for line in body.splitlines() if line.strip()]
    found = []
    if len(lines) > MAX_LINES:
        found.append(f"{len(lines)} linhas")
    if len(body.strip()) > MAX_CHARS:
        found.append(f"{len(body.strip())} caracteres")
    if body.count("?") > MAX_QUESTIONS:
        found.append(f"{body.count('?')} perguntas")
    items = sum(1 for line in lines if _LIST_ITEM_RE.match(line))
    if items > MAX_LIST_ITEMS:
        found.append(f"{items} itens de lista")
    return found


# ── R12: sem travessão, sem markdown, emoji da casa ───────────────────

ALLOWED_EMOJI = frozenset({"💛", "✨", "😊", "😌"})
_DASH_RE = re.compile(r"[—–]")
_MARKDOWN_PATTERNS = (
    re.compile(r"\*\*(.+?)\*\*"),
    re.compile(r"__(.+?)__"),
    re.compile(r"`([^`\n]+)`"),
    re.compile(r"(?<![\w*])\*(\S(?:[^*\n]*?\S)?)\*(?![\w*])"),
    re.compile(r"(?m)^#{1,6}\s+(.*)$"),
)
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿]️?"
)


def _emoji_in(text: str) -> list[str]:
    return [m.group(0).replace("️", "") for m in _EMOJI_RE.finditer(str(text or ""))]


def _disallowed_emoji(text: str, ctx: ReplyContext) -> list[str]:
    used_by_customer = bool(_emoji_in(ctx.customer_text))
    return [
        emoji for emoji in _emoji_in(text)
        if emoji not in ALLOWED_EMOJI or (ctx.origin == MODEL and not used_by_customer)
    ]


def _check_style(text: str, ctx: ReplyContext) -> list[str]:
    found = [m.group(0) for m in _DASH_RE.finditer(text)]
    found.extend(m.group(0) for pattern in _MARKDOWN_PATTERNS for m in pattern.finditer(_without_locked(text)))
    found.extend(_disallowed_emoji(text, ctx))
    return found


def _repair_style(text: str, ctx: ReplyContext) -> str:
    # Travessão: antes de valor vira dois-pontos ("Croissant: R$ 13,00"); no começo
    # da linha some; no meio da frase vira vírgula.
    text = re.sub(r"(?m)^\s*[—–]\s*", "", text)
    text = re.sub(r"\s*[—–]\s*(?=R\$|\d)", ": ", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    for pattern in _MARKDOWN_PATTERNS:
        text = pattern.sub(r"\1", text)
    bad = set(_disallowed_emoji(text, ctx))
    if bad:
        text = _EMOJI_RE.sub(lambda m: "" if m.group(0).replace("️", "") in bad else m.group(0), text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    return text


# ── R13: dado pessoal não sai ─────────────────────────────────────────

_CPF_FORMATTED_RE = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
_ELEVEN_DIGITS_RE = re.compile(r"(?<![\d\w-])\d{11}(?![\d\w-])")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<![\w-])(?:\+?55\s?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]\d{4}(?![\w-])")


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _check_personal_data(text: str, ctx: ReplyContext) -> list[str]:
    from shopman.utils.documents import is_valid_cpf

    body = _without_locked(text)
    found = [m.group(0) for m in _CPF_FORMATTED_RE.finditer(body)]
    found.extend(m.group(0) for m in _ELEVEN_DIGITS_RE.finditer(body) if is_valid_cpf(m.group(0)))
    house = {c.casefold() for c in ctx.house_contacts if "@" in c}
    house_phones = {_digits(c)[-8:] for c in ctx.house_contacts if len(_digits(c)) >= 8}
    found.extend(m.group(0) for m in _EMAIL_RE.finditer(body) if m.group(0).casefold() not in house)
    found.extend(m.group(0) for m in _PHONE_RE.finditer(body) if _digits(m.group(0))[-8:] not in house_phones)
    return found


# ── R14: janela de 24 h ───────────────────────────────────────────────

# Executada no transporte (``transport.ManyChatWhatsAppAdapter.authorize_response``):
# sem evidência da janela, o envio é recusado. O teste da regra prova isso pelo
# próprio adaptador.


# ── A tabela ──────────────────────────────────────────────────────────

RULES: tuple[HouseRule, ...] = (
    HouseRule(
        id="R1",
        title="nunca afirmar fato sem fonte",
        stages=(OUTPUT,),
        when="toda resposta",
        demands=(
            "preço, estoque, horário, prazo, total, taxa e link só vêm dos dados, montados pelo código; "
            "o modelo não digita número nem link"
        ),
        on_violation={HOUSE: Effect.HOLD, MODEL: Effect.HOLD},
        enforced_by="house_rules._check_fact (resposta do modelo); resposta da casa cumpre por construção",
        must_flag=(
            "Tem croissant hoje, sai às 9h.",
            "O pão de forma custa R$ 18,00.",
            "Entregamos em até quarenta minutos.",
            "Peça por aqui: https://exemplo.com/loja",
        ),
        must_pass=(
            "Tem sim, quer que eu mostre as opções?",
            "Posso te ajudar com o cardápio ou com um pedido.",
        ),
        output_check=_check_fact,
        examples_origin=MODEL,
    ),
    HouseRule(
        id="R2",
        title="para o cliente é só \"indisponível\"",
        stages=(OUTPUT,),
        when="produto que não está à venda hoje",
        demands="a palavra é \"indisponível\", sem motivo: nada de esgotado, acabou, pausado, sem estoque",
        on_violation={HOUSE: Effect.REPAIR, MODEL: Effect.REPAIR},
        enforced_by="house_rules._repair_unavailable",
        must_flag=(
            "O croissant está esgotado.",
            "Os pães de queijo acabaram.",
            "Esse item está pausado no canal.",
            "Brioche: sem estoque hoje.",
        ),
        must_pass=(
            "O croissant está indisponível hoje.",
            "A fornada acabou de sair do forno.",
            "O atendimento automático está pausado. Suas escolhas foram preservadas.",
        ),
        output_check=_check_unavailable,
        repair=_repair_unavailable,
    ),
    HouseRule(
        id="R3",
        title="alergia só pelo aviso da casa",
        stages=(ENTRY, OUTPUT),
        when="fala de alergia ou alérgeno; e toda resposta",
        demands=(
            "a resposta é o aviso da casa e os alérgenos declarados (executor de alergia, sem modelo); "
            "nunca afirmar ausência de alérgeno nem \"pode comer\"; alérgeno de que as fontes não falam vai "
            "para a equipe"
        ),
        on_violation={HOUSE: Effect.HOLD, MODEL: Effect.HOLD},
        enforced_by="entrada: triage.decide + executor de alergia; saída: house_rules._check_allergy_claim",
        must_flag=(
            "Esse pão é sem glúten.",
            "Não tem leite na receita, pode ficar tranquila.",
            "Pode comer sim!",
            "O croissant é seguro para celíacos.",
        ),
        must_pass=(
            "Todos os nossos produtos contêm ou podem conter glúten, e não temos como assegurar a ausência dele.",
            "Pão de campanha, alérgenos declarados: glúten.",
        ),
        entry_flag=(
            "Tenho alergia a castanha, o panetone leva castanha?",
            "Sou celíaca, posso comer o croissant?",
            "O brioche tem lactose?",
        ),
        entry_pass=("Tem pão integral hoje?", "Qual o horário de vocês?"),
        entry_check=_entry_allergy,
        output_check=_check_allergy_claim,
    ),
    HouseRule(
        id="R4",
        title="reclamação, reação, cancelamento, pagamento com problema e pedido de pessoa vão para a equipe",
        stages=(ENTRY,),
        when=(
            "reclamação, reação alérgica ou mal-estar, cancelamento de pedido, Pix ou link que não funcionou, "
            "desistência pela taxa de entrega, pedido de pessoa"
        ),
        demands="equipe, agora; a regra local nunca é tirada pelo modelo",
        on_violation={HOUSE: Effect.ROUTE_TEAM},
        enforced_by="handoff.classify_handoff_request → triage.decide",
        entry_flag=(
            "Quero falar com um atendente",
            "Meu pedido veio errado",
            "Quero cancelar meu pedido",
            "O pix não funcionou",
            "O link de pagamento não abre",
            "Não consegui pagar o pedido",
            "Acabei pedindo em outro lugar para compensar a taxa de entrega",
            "Com essa taxa de entrega vou desistir",
        ),
        entry_pass=(
            "Qual a taxa de entrega?",
            "Vocês aceitam pix?",
            "Tem croissant hoje?",
            "Cancela",
        ),
        entry_check=_entry_team,
    ),
    HouseRule(
        id="R5",
        title="dinheiro só em bloco travado",
        stages=(OUTPUT,),
        when="total, Pix, link de pagamento, resumo do pedido",
        demands=(
            "anexado pelo código (resumo, total, Pix, link); o modelo não fala de valor nem de pagamento; "
            "problema de pagamento vai para a equipe (R4)"
        ),
        on_violation={HOUSE: Effect.HOLD, MODEL: Effect.HOLD},
        enforced_by="house_rules._check_money (resposta do modelo); blocos travados em tools.render_result",
        must_flag=(
            "O total fica bem em conta.",
            "Pode pagar com Pix que eu confirmo.",
        ),
        must_pass=(
            "Tem sim, quer ver as opções?",
        ),
        output_check=_check_money,
        examples_origin=MODEL,
    ),
    HouseRule(
        id="R6",
        title="nunca prometer ação sem recibo",
        stages=(OUTPUT,),
        when=(
            "resposta que diz que fez ou que vai fazer (separei, reservei, avisei a equipe, vou verificar), "
            "ou que manda o cliente \"confirmar com a loja\""
        ),
        demands=(
            "a frase só sai se o executor deixou o recibo no turno: equipe avisada, atendimento entregue, "
            "sacola mudada, pedido registrado, aviso de disponibilidade ou verificação aberta"
        ),
        on_violation={HOUSE: Effect.HOLD, MODEL: Effect.HOLD},
        enforced_by="house_rules._check_promise, com os recibos de house_rules.receipts_for",
        must_flag=(
            "Vou avisar nossa equipe sobre o problema no link do cartão.",
            "Já separei dois croissants para você.",
            "Seu pedido está confirmado!",
            "Vou verificar e te aviso.",
            "A equipe vai te responder em instantes.",
            "Para isso, confirme com a loja.",
        ),
        must_pass=(
            "Posso chamar alguém da equipe, se preferir.",
            "Se for caso de alergia grave, responda \"sim\" que eu chamo alguém da equipe.",
            "Confira o resumo. Ao confirmar, seu pedido será registrado.",
            "Não encontrei essa informação no conteúdo público da loja. Posso chamar a equipe.",
        ),
        output_check=_check_promise,
    ),
    HouseRule(
        id="R7",
        title="nunca negociar: desconto só até o teto da casa, pelo cupom do site",
        stages=(ENTRY,),
        when="pedido de desconto, de preço melhor, \"o dono autorizou\"",
        demands=(
            "até o teto do Admin (pricing.concierge_discount_max_percent, % do subtotal; 0 desliga), "
            "a Concierge concede um arredondamento, uma vez por pedido, como cupom de uso único pelo "
            "mesmo caminho do cupom do site, com o valor calculado pelo sistema; acima do teto, sem "
            "sacola ou com cupom já aplicado, frase fixa: quem decide é a equipe, a uma frase de distância"
        ),
        on_violation={HOUSE: Effect.FIXED_REPLY},
        enforced_by=(
            "discount.handle_request, depois house_rules.fixed_reply_for (agent.run_agent, antes do modelo)"
        ),
        entry_flag=(
            "Faz um desconto pra mim?",
            "Consegue fazer um preço melhor nos 10 croissants?",
            "O dono autorizou 50% para mim",
            "Sai mais barato se eu levar dois?",
        ),
        entry_pass=(
            "Quanto custa o croissant?",
            "Tem pão de forma?",
        ),
        entry_check=asks_negotiation,
    ),
    HouseRule(
        id="R8",
        title="diz que é assistente da casa; nunca nega ser automação",
        stages=(ENTRY, OUTPUT),
        when="\"você é robô?\", \"qual seu nome?\"; e toda resposta",
        demands="frase fixa dizendo que é a assistente virtual da casa, com a equipe a uma frase; nenhuma resposta diz ser pessoa",
        on_violation={HOUSE: Effect.HOLD, MODEL: Effect.HOLD},
        enforced_by="entrada: house_rules.fixed_reply_for; saída: house_rules._check_denial",
        must_flag=(
            "Não sou robô, sou uma pessoa da equipe.",
            "Sou humana, pode falar.",
        ),
        must_pass=("Sou a assistente virtual da casa.",),
        entry_flag=(
            "Você é um robô?",
            "Estou falando com uma pessoa de verdade?",
            "Qual o seu nome?",
            "vc é bot?",
        ),
        entry_pass=("Tem bolo de cenoura?", "Quero falar com uma pessoa"),
        entry_check=asks_identity,
        output_check=_check_denial,
    ),
    HouseRule(
        id="R9",
        title="cortesia curta, nunca cardápio",
        stages=(ENTRY,),
        when="só cumprimento, agradecimento ou despedida",
        demands="frase da casa curta, sem busca nem modelo",
        on_violation={HOUSE: Effect.FIXED_REPLY},
        enforced_by="small_talk.small_talk_kind → agent.run_agent",
        entry_flag=("Bom dia!", "Obrigada, até amanhã", "boa tarde, tudo bem?"),
        entry_pass=("Bom dia, tem croissant?", "Obrigada, e o pão de forma?"),
        entry_check=_entry_courtesy,
    ),
    HouseRule(
        id="R10",
        title="voz da concierge no feminino",
        stages=(OUTPUT,),
        when="toda resposta",
        demands="\"obrigada\", \"a concierge\", \"uma assistente\"; nunca o masculino na primeira pessoa da casa",
        on_violation={HOUSE: Effect.REPAIR, MODEL: Effect.REPAIR},
        enforced_by="house_rules._repair_voice",
        must_flag=(
            "Obrigado pela preferência!",
            "Nosso concierge está fora do ar.",
            "Aqui é o concierge da casa, um assistente automático.",
        ),
        must_pass=("Obrigada pela preferência!", "Aqui é a concierge da casa."),
        output_check=_check_voice,
        repair=_repair_voice,
    ),
    HouseRule(
        id="R11",
        title="forma: curta, uma pergunta, lista de até três",
        stages=(OUTPUT,),
        when="toda resposta (fora os blocos travados: Pix e link)",
        demands=(
            f"até {MAX_LINES} linhas e {MAX_CHARS} caracteres, {MAX_QUESTIONS} pergunta, "
            f"até {MAX_LIST_ITEMS} itens por lista"
        ),
        on_violation={HOUSE: Effect.RECORD, MODEL: Effect.HOLD},
        enforced_by="house_rules._check_form (resposta da casa: só mede, é a base de hoje)",
        must_flag=(
            "Linha um.\nLinha dois.\nLinha três.\nLinha quatro.",
            "Quer croissant? Ou prefere pão de queijo?",
            "- a\n- b\n- c\n- d",
        ),
        must_pass=("Tem croissant hoje. Quer que eu mostre as outras opções?",),
        output_check=_check_form,
    ),
    HouseRule(
        id="R12",
        title="sem travessão, sem markdown, emoji só da casa",
        stages=(OUTPUT,),
        when="toda resposta",
        demands="sem travessão, sem markdown; emoji só 💛 ✨ (😊 😌 às vezes), e no texto do modelo só se o cliente usou",
        on_violation={HOUSE: Effect.REPAIR, MODEL: Effect.REPAIR},
        enforced_by="house_rules._repair_style",
        must_flag=(
            "Croissant — R$ 13,00",
            "Total: **R$ 68,00**",
            "Pronto! 🎉",
        ),
        must_pass=("Croissant: R$ 13,00", "Até logo! Quando precisar, é só chamar. 💛"),
        output_check=_check_style,
        repair=_repair_style,
    ),
    HouseRule(
        id="R13",
        title="dado pessoal não sai",
        stages=(OUTPUT,),
        when="toda resposta",
        demands="nenhum CPF, telefone ou e-mail que não seja da própria casa",
        on_violation={HOUSE: Effect.HOLD, MODEL: Effect.HOLD},
        enforced_by="house_rules._check_personal_data",
        must_flag=(
            "O CPF cadastrado é 529.982.247-25.",
            "Falei com a cliente pelo (43) 99876-5432.",
            "O e-mail dela é maria@exemplo.com.",
        ),
        must_pass=(
            "Pedido ORD-20261003-0001 registrado. Total: R$ 52,00.",
            "Retirada: 03/10 das 16:00 às 16:30.",
        ),
        output_check=_check_personal_data,
    ),
    HouseRule(
        id="R14",
        title="fora da janela de 24 h, nada de texto livre",
        stages=(SEND,),
        when="envio de qualquer resposta",
        demands="sem evidência da janela de atendimento da Meta, o envio é recusado",
        on_violation={HOUSE: Effect.REFUSE_SEND},
        enforced_by="transport.ManyChatWhatsAppAdapter.authorize_response",
    ),
)

RULES_BY_ID = {rule.id: rule for rule in RULES}
assert len(RULES) == len(RULES_BY_ID) == 14, "as 14 regras da v2, uma vez cada"


# ── Entrada ───────────────────────────────────────────────────────────

NEGOTIATION_COPY_KEY = "CONCIERGE_PRICE_NEGOTIATION"
IDENTITY_COPY_KEY = "CONCIERGE_IDENTITY"


def fixed_reply_for(customer_text: str, *, shop_name: str = "", copy=None) -> tuple[str, str]:
    """(regra, frase) das regras de entrada com frase fixa (R7, R8); ou ("", "").

    R7 vem antes: "você é robô? faz um desconto" é pedido de desconto.
    """
    if copy is None:
        from .service import copy_message as copy

    for rule_id, matches, key in (
        ("R7", asks_negotiation, NEGOTIATION_COPY_KEY),
        ("R8", asks_identity, IDENTITY_COPY_KEY),
    ):
        if matches(customer_text):
            text = (copy(key) or "").replace("{shop_name}", shop_name or "a casa").strip()
            if text:
                return rule_id, text
    return "", ""


# ── Saída ─────────────────────────────────────────────────────────────


def check(text: str, ctx: ReplyContext = ReplyContext()) -> list[Violation]:
    """Toda regra de saída sobre uma resposta, sem mudar nada."""
    violations: list[Violation] = []
    for rule in RULES:
        if rule.output_check is None:
            continue
        for found in rule.output_check(text, ctx):
            violations.append(Violation(rule.id, rule.effect_for(ctx.origin), found))
    return violations


def review(texts: Iterable[str], ctx: ReplyContext = ReplyContext()) -> Review:
    """Aplica a tabela a cada resposta do turno: conserta o que se conserta, aponta o que segura.

    O que fica em ``held`` não pode sair: quem chama entrega a conversa à equipe.
    O conserto é refeito até estabilizar e conferido de novo; o que o conserto
    não resolveu vira ``HOLD``.
    """
    result = Review()
    for text in texts:
        if not text or not text.strip():
            result.texts.append(text or "")
            continue
        found = check(text, ctx)
        result.violations.extend(found)
        fixed = text
        for rule in RULES:
            if rule.repair is not None and any(v.rule == rule.id for v in found):
                fixed = rule.repair(fixed, ctx)
        if fixed != text:
            for leftover in check(fixed, ctx):
                if leftover.effect == Effect.REPAIR:
                    result.violations.append(Violation(leftover.rule, Effect.HOLD, leftover.found))
        result.texts.append(fixed)
    return result


def receipts_for(outcome=None, *, team_notified: bool = False, handoff: bool = False) -> frozenset[str]:
    """Os recibos do turno, lidos do que os executores fizeram (``AgentOutcome``)."""
    receipts: set[str] = set()
    if team_notified:
        receipts.add(TEAM_NOTIFIED)
    if handoff or getattr(outcome, "handoff", False):
        receipts.update({HANDOFF, TEAM_NOTIFIED})
    if getattr(outcome, "order_ref", ""):
        receipts.add(ORDER)
    for event in getattr(outcome, "tool_events", None) or ():
        if not event.get("ok", True):
            continue
        name = event.get("name")
        if name in {"set_item", "set_fulfillment"}:
            receipts.add(CART)
        elif name == "place_order":
            receipts.add(ORDER)
        elif name == "notify_when_available":
            receipts.add(NOTIFY)
    return frozenset(receipts)


def house_contacts() -> tuple[str, ...]:
    """Telefone e e-mail da casa (``Shop``): podem sair numa resposta (R13)."""
    try:
        from shopman.shop.models import Shop

        shop = Shop.load() if hasattr(Shop, "load") else Shop.objects.first()
    except Exception:  # banco indisponível: nenhum contato liberado, a regra fica mais estrita
        return ()
    if shop is None:
        return ()
    return tuple(value for value in (getattr(shop, "phone", ""), getattr(shop, "email", "")) if value)
