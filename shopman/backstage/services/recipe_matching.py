"""Casar o nome de um ingrediente com um insumo do sistema.

A receita chega como o padeiro (ou o livro) a escreveu: "farine T55", "強力粉",
"eau tiède", "manteiga sem sal", com erro de digitação e em qualquer língua. O
sistema conhece insumos (``Material`` do Buyman) com nome em pt-BR e SKU. Este
módulo devolve, para cada nome, candidatos ranqueados de 0 a 100, e a tela
deixa o padeiro confirmar. Ele sugere; não decide sozinho abaixo de
``best_match(min_score=...)``.

Três etapas, nesta ordem:

1. **Normalizar**: minúsculas, sem acento no alfabeto latino (o japonês fica
   como está), sem pontuação, espaços colapsados.
2. **Traduzir por sinônimo**: uma tabela multilíngue leva o termo da fonte ao
   termo canônico em pt-BR ("farine" e "小麦粉" viram "farinha de trigo") e
   descarta qualificadores que não distinguem insumo ("sem sal", "tiède",
   "fresh"). Sinônimo maior ganha do menor ("farine de seigle" antes de
   "farine").
3. **Ranquear por semelhança** com ``rapidfuzz`` sobre nome e SKU dos insumos
   ativos, mais as ``extra_options`` que o chamador injeta (as saídas das
   receitas-parte, levain e yudane, que este módulo não conhece de propósito).

Por que ``WRatio`` e não ``token_set_ratio``: o ``token_set_ratio`` devolve 100
sempre que os tokens da consulta cabem nos do candidato, então "sal" empata em
100 com "Sal", "Sal grosso" e qualquer nome que contenha a palavra, e o
desempate vira sorte. O ``WRatio`` combina razão simples, parcial e por tokens
com peso pelo tamanho: "manteiga" acha "Manteiga francesa" (parcial, 90) sem
igualar a "Sal", e "trigo farinha" ainda acha "Farinha de trigo" (tokens
reordenados). O que ele não faz sozinho, ignorar "sem sal", a etapa 2 faz antes.

A tabela de papéis (``role_for``) é uma versão mínima da heurística que vai
morar no Craftsman (RECIPE-INVENTORY-PLAN §3/§4); quando a canônica chegar, a
integração aponta para ela e esta some.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from django.db import DatabaseError
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

#: Abaixo disto o candidato não aparece nem como sugestão: é ruído, não opção.
MIN_CANDIDATE_SCORE = 50
DEFAULT_MIN_SCORE = 80

ROLES = ("flour", "liquid", "salt", "yeast", "fat", "sugar", "egg", "dairy", "inclusion", "other")


@dataclass(frozen=True)
class IngredientCandidate:
    sku: str
    name: str
    unit: str
    role: str
    score: int  # 0 a 100


# ── Normalização e sinônimos ────────────────────────────────────────────────

#: Ligaduras e letras que a decomposição Unicode não abre ("œufs" precisa virar "oeufs").
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae", "ß": "ss", "ø": "o", "ł": "l", "đ": "d"})


def normalize_name(name: str) -> str:
    """Minúsculas, sem acento latino, sem pontuação, espaços colapsados.

    Só o alfabeto latino perde o diacrítico: no japonês o dakuten é parte da
    letra (が não é か), então ele fica.
    """
    text = str(name or "").lower().translate(_LIGATURES)
    out: list[str] = []
    for char in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(char) and out and out[-1].isascii():
            continue
        out.append(char)
    text = unicodedata.normalize("NFC", "".join(out))
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


#: Termo canônico em pt-BR → como a fonte pode escrevê-lo. Só o que distingue
#: insumo; qualificador de estado ("fresco", "tiède") mora em ``_QUALIFIERS``.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "farinha de trigo t55": ("farine t55", "farine type 55", "farine de type 55", "type 55", "t55", "flour t55", "farinha t55"),
    "farinha de trigo t65": ("farine t65", "farine type 65", "farine de type 65", "farine de tradition", "type 65", "t65", "flour t65", "farinha t65"),
    "farinha de trigo t45": ("farine t45", "farine type 45", "farine de type 45", "farine de gruau", "type 45", "t45", "flour t45", "farinha t45"),
    "farinha de trigo integral": ("farine complete", "farine de ble complete", "farine integrale", "whole wheat flour", "wholemeal flour", "whole wheat", "wholemeal", "全粒粉", "farinha integral"),
    "farinha de centeio": ("farine de seigle", "seigle", "rye flour", "rye", "ライ麦粉", "ライ麦", "centeio"),
    "farinha de trigo": ("farine de ble", "farine", "bread flour", "all purpose flour", "ap flour", "wheat flour", "plain flour", "strong flour", "flour", "小麦粉", "強力粉", "薄力粉", "中力粉", "粉", "farinha"),
    "agua": ("eau", "water", "水", "お湯", "ぬるま湯"),
    "leite": ("lait", "milk", "牛乳", "ミルク"),
    "manteiga": ("beurre", "butter", "バター"),
    "ovos": ("oeufs", "oeuf", "eggs", "egg", "卵", "玉子", "ovo"),
    "sal": ("sel", "salt", "塩"),
    "acucar": ("sucre", "sugar", "砂糖"),
    "fermento biologico": ("levure de boulanger", "levure fraiche", "levure seche", "levure", "fresh yeast", "dry yeast", "instant yeast", "yeast", "ドライイースト", "イースト", "fermento fresco", "fermento seco", "fermento"),
    "levain": ("sourdough starter", "sourdough", "sauerteig", "levain liquide", "levain dur", "ルヴァン", "サワードウ", "fermento natural"),
    "azeite": ("huile d olive", "olive oil", "オリーブオイル", "azeite de oliva"),
    "creme de leite": ("creme fraiche", "heavy cream", "cream", "creme", "生クリーム"),
    "chocolate": ("chocolat", "チョコレート", "チョコ"),
    "passas": ("raisins secs", "raisins", "レーズン", "uvas passas", "uva passa"),
    "gergelim": ("graines de sesame", "sesame seeds", "sesame", "ごま", "胡麻"),
    "mel": ("miel", "honey", "はちみつ", "蜂蜜"),
    "malte": ("malt diastasique", "diastatic malt", "malt", "モルト"),
}

#: Qualificador que não distingue insumo: some da consulta antes do ranking.
_QUALIFIERS = (
    "sem sal", "com sal", "unsalted", "salted", "doux", "demi sel",
    "fresco", "fresca", "frescos", "frescas", "fresh", "frais", "fraiche",
    "morno", "morna", "tiede", "lukewarm", "warm", "gelado", "gelada", "cold", "froid", "froide",
    "peneirado", "peneirada", "sifted", "tamisee", "temperatura ambiente", "room temperature",
    "a gosto", "q b", "qb", "to taste",
    "grande", "grandes", "large", "medio", "media", "medium", "organico", "organica", "organic", "bio",
)
# "integral", "T55", "sem glúten" NÃO são qualificadores: distinguem insumo, ficam na consulta.


def _has_cjk(text: str) -> bool:
    return any(ord(char) >= 0x2E80 for char in text)


def _pattern(term: str) -> re.Pattern[str]:
    # Latim: palavra inteira. Japonês: não há espaço entre palavras; substring.
    escaped = re.escape(term)
    return re.compile(escaped if _has_cjk(term) else rf"(?<!\w){escaped}(?!\w)")


def _build_synonym_rules() -> tuple[tuple[re.Pattern[str], str], ...]:
    rules: list[tuple[str, str]] = []
    for canonical, aliases in SYNONYMS.items():
        for alias in aliases:
            rules.append((normalize_name(alias), canonical))
    # Maior primeiro: "farine de seigle" precisa ganhar de "farine".
    rules.sort(key=lambda pair: len(pair[0]), reverse=True)
    return tuple((_pattern(alias), canonical) for alias, canonical in rules)


_SYNONYM_RULES = _build_synonym_rules()
_QUALIFIER_RULES = tuple(_pattern(normalize_name(term)) for term in _QUALIFIERS)


def canonical_query(name: str) -> str:
    """O nome da fonte, normalizado, traduzido por sinônimo e sem qualificador."""
    text = normalize_name(name)
    if not text:
        return ""
    # Substituição em duas passadas com marcador: o canônico "farinha de trigo"
    # contém "farinha", que também é sinônimo, e a segunda regra não pode
    # reescrever o que a primeira já traduziu.
    placeholders: list[str] = []

    def _mark(canonical: str) -> str:
        placeholders.append(canonical)
        return f" \x00{len(placeholders) - 1}\x00 "

    for pattern, canonical in _SYNONYM_RULES:
        text = pattern.sub(lambda _m, c=canonical: _mark(c), text)
    for pattern in _QUALIFIER_RULES:
        text = pattern.sub(" ", text)
    text = re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)
    return re.sub(r"\s+", " ", text).strip()


# ── Papel do ingrediente ────────────────────────────────────────────────────

#: Ordem importa: o primeiro papel cujo termo aparece no nome ganha ("manteiga"
#: é laticínio, mas na massa é gordura; "creme de leite" é laticínio).
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("flour", ("farinha", "flour", "farine", "centeio", "rye", "seigle", "semolina", "semola", "fuba", "cornmeal", "粉")),
    ("salt", ("sal", "salt", "sel", "塩", "flor de sal")),
    ("yeast", ("fermento", "levure", "yeast", "levain", "sourdough", "poolish", "biga", "イースト", "ルヴァン")),
    ("egg", ("ovo", "ovos", "egg", "eggs", "oeuf", "oeufs", "gema", "gemas", "clara", "claras", "卵")),
    ("fat", ("manteiga", "butter", "beurre", "azeite", "oleo", "oil", "huile", "banha", "lard", "margarina", "gordura", "バター")),
    ("sugar", ("acucar", "sugar", "sucre", "mel", "honey", "miel", "malte", "malt", "glucose", "xarope", "syrup", "砂糖", "はちみつ")),
    ("dairy", ("leite", "milk", "lait", "creme", "cream", "queijo", "cheese", "fromage", "iogurte", "yogurt", "requeijao", "nata", "牛乳", "生クリーム")),
    ("liquid", ("agua", "water", "eau", "cerveja", "beer", "biere", "suco", "juice", "cafe", "coffee", "cha", "tea", "水")),
    ("inclusion", (
        "chocolate", "chocolat", "gotas", "passas", "raisin", "raisins", "nozes", "noz", "castanha", "castanhas",
        "amendoa", "amendoas", "almond", "gergelim", "sesame", "semente", "sementes", "seed", "seeds", "azeitona",
        "azeitonas", "olive", "olives", "fruta", "frutas", "cebola", "bacon", "presunto", "alecrim", "tomilho",
        "canela", "maca", "limao", "milho", "frango", "salsicha", "チョコ", "レーズン", "ごま",
    )),
)
_ROLE_RULES = tuple(
    (role, tuple(_pattern(normalize_name(term)) for term in terms)) for role, terms in _ROLE_KEYWORDS
)


def role_for(name: str, sku: str = "", metadata: dict | None = None) -> str:
    """Papel do insumo na massa. ``metadata["role"]`` manda quando existe; senão, palavra-chave."""
    declared = str((metadata or {}).get("role") or "").strip().lower()
    if declared in ROLES:
        return declared
    haystack = f"{normalize_name(name)} {normalize_name(sku.replace('-', ' '))}".strip()
    for role, patterns in _ROLE_RULES:
        if any(pattern.search(haystack) for pattern in patterns):
            return role
    return "other"


# ── Ranking ─────────────────────────────────────────────────────────────────


def _active_materials() -> list[IngredientCandidate]:
    """Os insumos ativos como candidatos sem nota. Sem tabela ou sem linha, lista vazia."""
    from shopman.craftsman.models import normalize_recipe_item_unit

    try:
        from shopman.buyman.models import Material

        rows = list(
            Material.objects.filter(is_active=True)
            .only("sku", "name", "unit", "metadata")
            .order_by("name", "sku")
        )
    except DatabaseError:
        logger.debug("recipe_matching: insumos indisponíveis", exc_info=True)
        return []
    return [
        IngredientCandidate(
            sku=material.sku,
            name=material.name,
            unit=normalize_recipe_item_unit(material.unit),
            role=role_for(material.name, material.sku, material.metadata or {}),
            score=0,
        )
        for material in rows
    ]


def _score(query: str, option: IngredientCandidate) -> int:
    name_score = fuzz.WRatio(query, normalize_name(option.name))
    sku_score = fuzz.WRatio(query, normalize_name(option.sku.replace("-", " ")))
    return int(round(max(name_score, sku_score)))


def _rank(
    query: str, options: Sequence[IngredientCandidate], *, limit: int, floor: int,
) -> tuple[IngredientCandidate, ...]:
    scored = [
        IngredientCandidate(sku=o.sku, name=o.name, unit=o.unit, role=o.role, score=_score(query, o))
        for o in options
    ]
    # Empate: o nome mais curto é o mais genérico, e o genérico é a aposta segura.
    scored.sort(key=lambda c: (-c.score, len(c.name), c.name))
    return tuple(c for c in scored if c.score >= floor)[:limit]


def candidates_for(
    name: str, *, limit: int = 5, extra_options: Sequence[IngredientCandidate] = (),
) -> tuple[IngredientCandidate, ...]:
    """Candidatos ranqueados para um nome de ingrediente. Vazio quando nada parece."""
    query = canonical_query(name)
    if not query:
        return ()
    options = list(_active_materials()) + list(extra_options)
    if not options:
        return ()
    return _rank(query, options, limit=limit, floor=MIN_CANDIDATE_SCORE)


def best_match(
    name: str, *, min_score: int = DEFAULT_MIN_SCORE, extra_options: Sequence[IngredientCandidate] = (),
) -> IngredientCandidate | None:
    """O melhor candidato quando a nota chega a ``min_score``; senão ``None`` (a tela pergunta)."""
    ranked = candidates_for(name, limit=1, extra_options=extra_options)
    if ranked and ranked[0].score >= min_score:
        return ranked[0]
    return None


def search_ingredients(query: str, *, limit: int = 12) -> tuple[IngredientCandidate, ...]:
    """Autocomplete da tela. Consulta vazia lista os ativos em ordem de nome (nota 0: não houve casamento)."""
    if not (query or "").strip():
        return tuple(_active_materials()[:limit])
    return candidates_for(query, limit=limit)
