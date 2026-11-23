"""O pedido como a cliente escreve no WhatsApp, lido pela casa sem modelo (DEV-2026-076).

O ensaio do dono (22/11/2026) parou na primeira frase, e a bateria de pedidos
(``tests/test_concierge_bateria_pedidos.py``) mediu o porquê: sem o leitor de IA, o porteiro e a
divisão local não reconheciam pedido sem "quero" ("2 croissant pra amanha, busco 16h"), número
por extenso, dois produtos numa frase, nem nada dito DEPOIS do pedido ("na verdade 3", "tira 1",
"pra amanhã", "melhor às 10h"). Tudo isso virava "vou verificar com a equipe".

Aqui se lê só a forma do pedido, contra o cardápio do canal e a sacola da conversa:

- **itens**: quantidade (algarismo, por extenso, dúzia, meia dúzia) seguida do produto, um ou
  vários ("2 croissants e 2 pain au chocolat"); o produto casa com o NOME do cardápio, no
  singular ou plural, sem acento, e com erro de digitação pequeno ("croisants");
- **correção** do que já está na sacola: "na verdade 3", "não, quero 4", "são 3" (a quantidade
  do item em foco), "tira 1" (um a menos), "tira o croissant", "troca por pain au chocolat";
- **só o quando/como**: dia, hora ou retirada sem produto ("pra amanhã", "vou buscar às 16h"),
  com a sacola já montada.

Pergunta (com "?", tirando o "entendeu?" do fim) não é pedido, e nada aqui escreve: devolve as
partes de pedido (``Act``) que o turno executa pelos caminhos de sempre. Sem nada reconhecido,
devolve ``None`` e a leitura do porteiro segue como estava.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

_NUMBERS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20,
}
_QTY = r"(?:meia duzia|uma duzia|duzia|\d{1,3}|" + "|".join(sorted(_NUMBERS, key=len, reverse=True)) + r")"
#: Onde o nome do produto acaba: o que vem depois já é quando, como ou cortesia.
_STOP = {
    "pra", "para", "p", "pro", "com", "que", "amanha", "hoje", "depois", "as", "a", "ate", "no", "na", "dia",
    "busco", "buscar", "busca", "retiro", "retirar", "retirada", "pego", "pegar", "passo", "vou", "de", "e",
    "por", "favor", "em", "me", "mim", "eu", "ai", "la", "segunda", "terca", "quarta", "quinta", "sexta",
    "sabado", "domingo", "manha", "tarde", "noite", "entrega", "entregar", "delivery", "hora", "horas",
    "ok", "obrigada", "obrigado", "pfv", "pf", "pls", "tb", "tambem",
}
_TAGS = r"\b(?:entendeu|entendesse|ok|certo|ta|beleza|combinado|pode ser)\s*\?+"
_CORRECT_QTY = re.compile(
    rf"^(?:na verdade|alias|melhor|corrigindo|nao|so que|opa|ops|desculpa|errei)?[\s,]*"
    rf"(?:sao|serao|quero|queria|coloca|poe|bota|faz|faca|muda pra|muda para|pode ser)?\s*(?P<qty>{_QTY})"
    rf"(?:\s+(?:unidades?|un|und))?\s*[.!]*$"
)
_LESS = re.compile(rf"\b(?:tira|tire|remove|menos)\s+(?P<qty>{_QTY})\b(?!\s*\w*\s*(?:h|horas?)\b)")
_REMOVE_PRODUCT = re.compile(r"\b(?:tira|tire|retira|remove|cancela|exclui)\s+(?:o|a|os|as)\s+(?P<prod>[a-z ]+)$")
_SWAP = re.compile(r"\btroca\w*\s+(?:(?:o|a|os|as)\s+[a-z ]+?\s+)?(?:por|pelo|pela|pelos|pelas)\s+(?:um |uma |o |a )?(?P<prod>[a-z ]+)$")


@dataclass
class Talk:
    """O que a fala pede à sacola: as partes de pedido, e se só disse o quando/como.

    ``certain``: TODA palavra da fala foi entendida (itens, quantidade, quando/como, cortesia).
    Só aí a casa decide sem o leitor de IA; sobrou palavra ("e o de ontem veio queimado"), a
    fala vai ao leitor, que pode achar o que a casa não vê.
    """

    acts: list = field(default_factory=list)
    fulfillment_only: bool = False
    certain: bool = False


#: Palavras que a casa entende numa fala de pedido, além do produto e da quantidade.
_KNOWN = _STOP | {
    "quero", "queria", "qro", "querer", "gostaria", "ve", "manda", "separa", "reserva", "encomendar", "pedir",
    "coloca", "poe", "bota", "oi", "ola", "opa", "bom", "boa", "tudo", "bem", "valeu", "so", "isso", "pode",
    "ser", "aqui", "loja", "balcao", "casa", "partir", "das", "pelas", "umas", "uns", "h", "unidades",
    "unidade", "un", "und", "o", "os", "um", "uma", "feira", "retira", "busque", "pegue", "buscando",
    "na", "verdade", "alias", "melhor", "corrigindo", "nao", "sao", "serao", "faz", "faca", "muda", "troca",
    "por", "pelo", "pela", "tira", "tire", "remove", "menos", "mais", "deixa", "fica", "pfvr", "obg",
}
_TIME_TOKEN = re.compile(r"\d{1,2}(?:h\d{0,2}|:\d{2})?|\d{1,2}/\d{1,2}")
#: Fala sobre pedido JÁ feito ("os croissants que pedi", "cadê meu pedido"): não é pedido novo.
_PAST_ORDER = re.compile(r"\b(?:pedi|pedimos|encomendei|comprei|cade|chegou|meu pedido|ja paguei|paguei)\b")


def _leftover(tokens: list[str], consumed: set[int]) -> list[str]:
    return [t for n, t in enumerate(tokens) if n not in consumed and t not in _KNOWN and not _TIME_TOKEN.fullmatch(t)]


def _fold(text: str) -> str:
    from .dialogue import _fold as fold

    return fold(text)


def _clean(text: str) -> str:
    folded = re.sub(_TAGS, " ", _fold(text))
    return " ".join(re.sub(r"[^\w\s:/]", " ", folded).split())


def asks(text: str) -> bool:
    """A fala pergunta? O "entendeu?" do fim cobra atenção, não pergunta."""
    return "?" in re.sub(_TAGS, " ", _fold(text))


def _qty(word: str) -> int:
    word = word.strip()
    if word in ("meia duzia",):
        return 6
    if word in ("uma duzia", "duzia"):
        return 12
    if word.isdigit():
        return int(word)
    return _NUMBERS.get(word, 0)


def _singular(token: str) -> str:
    if len(token) > 4 and token.endswith("es") and token[-3] in "rsz":
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _key(text: str) -> str:
    return " ".join(_singular(t) for t in _fold(text).split() if t not in ("de", "do", "da", "com", "e"))


def menu(channel_ref: str) -> list[tuple[str, str]]:
    """(sku, nome) do que está publicado no cardápio do canal."""
    from shopman.offerman.models import ListingItem

    rows = ListingItem.objects.filter(listing__ref=channel_ref, is_published=True).values_list(
        "product__sku", "product__name")
    return [(sku, name) for sku, name in rows]


def match_product(words: str, products: list[tuple[str, str]]) -> tuple[str, str] | None:
    """O produto do cardápio que as palavras citam: nome inteiro, singular/plural, erro pequeno."""
    wanted = _key(words)
    if not wanted:
        return None
    best, best_score = None, 0.0
    for sku, name in products:
        key = _key(name)
        if not key:
            continue
        if wanted == key:
            return sku, name
        score = SequenceMatcher(None, wanted, key).ratio()
        if wanted.startswith(key + " ") or key.startswith(wanted + " "):
            score = max(score, 0.9 if len(wanted.split()) >= len(key.split()) else 0.0)
        if score > best_score:
            best, best_score = (sku, name), score
    return best if best_score >= 0.84 else None


def _items(clean: str, products) -> tuple[list[tuple[int, tuple[str, str], bool]], set[int]]:
    """Os itens da fala ("2 croissants e 2 pain au chocolat"): (quantidade, produto, é a mais), e as
    posições das palavras usadas."""
    found, consumed = [], set()
    tokens = clean.split()
    i = 0
    while i < len(tokens):
        qty_word = None
        for size in (2, 1):
            chunk = " ".join(tokens[i:i + size])
            if re.fullmatch(_QTY, chunk) and not re.fullmatch(r"\d{1,2}(?:h|:)\d*", chunk):
                qty_word = chunk
                break
        if qty_word is None:
            i += 1
            continue
        j = i + len(qty_word.split())
        if j < len(tokens) and tokens[j] == "de":
            j += 1  # "meia dúzia de croissants"
        name_tokens = []
        while j < len(tokens) and len(name_tokens) < 5:
            token = tokens[j]
            if token in _STOP and not (name_tokens and token in ("de", "a", "e") and j + 1 < len(tokens)
                                       and tokens[j + 1] not in _STOP and not re.fullmatch(_QTY, tokens[j + 1])):
                break
            if re.search(r"\d", token):
                break
            name_tokens.append(token)
            j += 1
        product = match_product(" ".join(name_tokens), products) if name_tokens else None
        if product is not None and _qty(qty_word):
            found.append((_qty(qty_word), product, i > 0 and tokens[i - 1] == "mais"))
            consumed.update(range(i, j))
            i = j
        else:
            i += 1
    return found, consumed


def _focus(lines: list[dict]) -> dict | None:
    return lines[-1] if lines else None


def read(text: str, *, channel_ref: str, cart_lines: list[dict]):
    """As partes de pedido da fala, ou ``None`` quando ela não tem a forma de pedido."""
    from . import order_closing
    from .intents import ORDER, Act

    if asks(text):
        return None
    clean = _clean(text)
    if not clean or _PAST_ORDER.search(clean):
        return None
    products = menu(channel_ref)
    focus = _focus(cart_lines)
    tokens = clean.split()

    def everything_understood(consumed=frozenset()) -> bool:
        return not _leftover(tokens, set(consumed))

    swap = _SWAP.search(clean)
    if swap and focus is not None:
        product = match_product(swap.group("prod"), products)
        if product is not None and product[0] != focus.get("sku"):
            qty = int(float(focus.get("qty") or 1))
            # Primeiro o novo, depois sai o antigo: a sacola nunca fica vazia no meio da troca.
            return Talk(acts=[Act(ORDER, span=f"{qty} {product[1]}", product=product[1], qty=qty),
                              Act(ORDER, span=f"tira o {focus.get('name', '')}", product=focus.get("name", ""), qty=0)],
                        certain=everything_understood(range(clean[:swap.start("prod")].count(" "), len(tokens))))
    removal = _REMOVE_PRODUCT.search(clean)
    if removal and not order_closing.fulfillment_cue(clean.replace(removal.group(0), "")):
        product = match_product(removal.group("prod"), products)
        if product is not None:
            return Talk(acts=[Act(ORDER, span=f"tira o {product[1]}", product=product[1], qty=0)],
                        certain=everything_understood(range(clean[:removal.start("prod")].count(" "), len(tokens))))

    items, consumed = _items(clean, products)
    if items:
        return Talk(acts=[Act(ORDER, span=f"{'mais ' if more else ''}{qty} {name}", product=name, qty=qty)
                          for qty, (_, name), more in items],
                    certain=everything_understood(consumed))

    if focus is not None:
        current = int(float(focus.get("qty") or 0))
        name = focus.get("name", "")
        less = _LESS.search(clean)
        if less and _qty(less.group("qty")) and not order_closing.fulfillment_cue(clean):
            target = max(current - _qty(less.group("qty")), 0)
            return Talk(acts=[Act(ORDER, span=f"{target} {name}" if target else f"tira o {name}", product=name, qty=target)],
                        certain=everything_understood())
        correct = _CORRECT_QTY.match(clean)
        if correct and _qty(correct.group("qty")) and not order_closing.read(clean, {}).minutes:
            qty = _qty(correct.group("qty"))
            return Talk(acts=[Act(ORDER, span=f"{qty} {name}", product=name, qty=qty)], certain=True)
        if order_closing.fulfillment_cue(clean) and not re.search(r"\b(?:abre|abrem|fecha|fecham|funciona)\b", clean):
            # Só o quando/como: a sacola fica como está, e o turno aplica o dia, a hora ou o recebimento.
            return Talk(acts=[Act(ORDER, span=f"{current} {name}", product=name, qty=current)], fulfillment_only=True,
                        certain=everything_understood())
    return None
