"""Piloto do de-para de produto: quem acerta, quanto demora, quanto custa.

Compara três formas de responder "este item do histórico é qual produto do
catálogo?" contra o **gabarito que a casa já deu**: os ``ProductAlias``
confirmados no Admin (com produto, ou confirmados sem produto = extinto / fora
do catálogo). Nada aqui grava alias; o piloto só mede.

- ``fuzzy``: o que o ``suggest_aliases`` faz hoje (``rapidfuzz.token_set_ratio``
  sobre nome normalizado, corte ``DEFAULT_MIN_SCORE``). Custo zero, roda local.
- ``jev``: o modelo de decisão da TypeSafe. Recebe os K candidatos mais
  parecidos (a mesma lista curta do fuzzy) mais a opção ``other`` e devolve
  uma escolha com probabilidade. Cobra só entrada.
- ``llm``: o mesmo pedido ao LLM que o projeto já usa (``AI_ASSIST_*``), com
  resposta em JSON. É a linha de base que o Jev promete bater em custo e tempo.

Os três olham **só o nome**: SKU exato continua ganhando antes de tudo no
sugestor, e não é ali que mora a dúvida. Os dois modelos veem apenas a lista
curta, então o teto deles é a "cobertura da lista curta" que o relatório mostra
— se o produto certo não está entre os K, nenhum dos dois tem como acertar.

Nenhum dado pessoal sai daqui: só nome de produto da origem e nome/SKU do
catálogo.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import time
from dataclasses import dataclass, field

from django.conf import settings

from shopman.backstage.bi.mapping import DEFAULT_MIN_SCORE, normalize_name

logger = logging.getLogger(__name__)

DEFAULT_SHORTLIST = 10
OTHER = "other"


@dataclass(frozen=True)
class CatalogEntry:
    pk: int
    sku: str
    name: str
    normalized: str


@dataclass(frozen=True)
class Case:
    """Uma linha do gabarito: o nome da origem e o produto que a pessoa confirmou."""

    external_name: str
    expected_pk: int | None  # None = confirmado como fora do catálogo


@dataclass
class Verdict:
    product_pk: int | None
    confidence: float  # 0–1
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""


class MatcherNotConfigured(Exception):
    """Falta credencial para este concorrente neste ambiente."""


class MatcherResponseError(Exception):
    """O provedor respondeu algo que não dá para ler como escolha."""


# ── Gabarito e catálogo ─────────────────────────────────────────────────────


def load_catalog() -> list[CatalogEntry]:
    from shopman.offerman.models import Product

    return [
        CatalogEntry(pk=pk, sku=sku, name=name, normalized=normalize_name(name))
        for pk, sku, name in Product.objects.order_by("sku").values_list("id", "sku", "name")
    ]


def gold_cases(source: str, *, limit: int | None = None) -> list[Case]:
    """Os de-paras confirmados da origem que têm nome para comparar."""
    from shopman.backstage.models import ProductAlias

    aliases = (
        ProductAlias.objects.confirmed()
        .filter(source=source)
        .exclude(external_name="")
        .order_by("id")
        .values_list("external_name", "product_id")
    )
    if limit:
        aliases = aliases[:limit]
    return [Case(external_name=name, expected_pk=product_id) for name, product_id in aliases]


def shortlist(name: str, catalog: list[CatalogEntry], k: int) -> list[tuple[CatalogEntry, int]]:
    """Os K produtos de nome mais parecido, com o score do fuzzy (0–100)."""
    from rapidfuzz import fuzz, process

    choices = {index: entry.normalized for index, entry in enumerate(catalog)}
    found = process.extract(normalize_name(name), choices, scorer=fuzz.token_set_ratio, limit=k)
    return [(catalog[index], int(round(score))) for _normalized, score, index in found]


# ── Concorrentes ────────────────────────────────────────────────────────────


class FuzzyMatcher:
    """O sugestor de hoje: o mais parecido, se passar do corte."""

    name = "fuzzy"

    def __init__(self, *, min_score: int = DEFAULT_MIN_SCORE):
        self.min_score = min_score

    def match(self, case: Case, candidates: list[tuple[CatalogEntry, int]]) -> Verdict:
        if not candidates:
            return Verdict(product_pk=None, confidence=0.0)
        entry, score = candidates[0]
        return Verdict(product_pk=entry.pk if score >= self.min_score else None, confidence=score / 100)


def _choice_keys(candidates: list[tuple[CatalogEntry, int]]) -> dict[str, CatalogEntry]:
    return {f"p{position}": entry for position, (entry, _score) in enumerate(candidates, start=1)}


QUESTION = "Qual produto do catálogo é este item do histórico de vendas?"
OTHER_DESCRIPTION = "Nenhum destes: produto fora do catálogo, extinto ou diferente de todos."


class JevMatcher:
    """TypeSafe Jev: uma pergunta de escolha entre os candidatos e ``other``.

    O formato segue a descrição pública da API (``POST /v1/systemone`` com
    ``state`` e ``questions``; pergunta de escolha = chave → descrição, sempre
    com ``other``). A leitura da resposta mora em ``parse_jev_response`` e
    grita com as chaves que recebeu se o formato for outro.
    """

    name = "jev"

    def __init__(self, *, timeout: float = 15.0, session=None):
        self.api_key = (getattr(settings, "JEV_API_KEY", "") or "").strip()
        if not self.api_key:
            raise MatcherNotConfigured("Jev não configurado. Defina JEV_API_KEY.")
        self.url = settings.JEV_API_URL
        self.model = settings.JEV_MODEL
        self.timeout = timeout
        if session is None:
            import requests

            session = requests.Session()
        self.session = session

    def build_request(self, case: Case, keyed: dict[str, CatalogEntry]) -> dict:
        choices = {key: f"{entry.name} (SKU {entry.sku})" for key, entry in keyed.items()}
        choices[OTHER] = OTHER_DESCRIPTION
        return {
            "model": self.model,
            "state": {"sales_history_item": case.external_name},
            "questions": {"product": {"type": "choice", "question": QUESTION, "choices": choices}},
        }

    def match(self, case: Case, candidates: list[tuple[CatalogEntry, int]]) -> Verdict:
        keyed = _choice_keys(candidates)
        started = time.perf_counter()
        response = self.session.post(
            self.url,
            json=self.build_request(case, keyed),
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            raise MatcherResponseError(f"Jev respondeu HTTP {response.status_code}: {response.text[:300]}")
        choice, confidence, input_tokens = parse_jev_response(response.json(), question="product")
        entry = keyed.get(choice)
        if entry is None and choice != OTHER:
            raise MatcherResponseError(f"Jev escolheu {choice!r}, que não estava entre as opções.")
        return Verdict(
            product_pk=entry.pk if entry else None,
            confidence=confidence,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
        )


def parse_jev_response(payload: dict, *, question: str) -> tuple[str, float, int]:
    """(escolha, confiança 0–1, tokens de entrada) de uma resposta do Jev.

    ⚠️ Escrito sem acesso à referência da API: aceita os nomes de campo que a
    documentação pública cita (``answers``, ``answer``/``value``,
    ``confidence``/``probability``/``probabilities``, ``usage``). Se a primeira
    chamada real cair aqui, a mensagem traz as chaves recebidas; ajuste este
    parser e o teste que o fixa.
    """
    answers = payload.get("answers", payload.get("results"))
    if isinstance(answers, list):
        answers = {item.get("id") or item.get("name") or item.get("question"): item for item in answers}
    answer = (answers or {}).get(question)
    if not isinstance(answer, dict):
        raise MatcherResponseError(f"Resposta do Jev sem '{question}'. Chaves recebidas: {sorted(payload)}")

    choice = answer.get("answer", answer.get("value", answer.get("choice")))
    probabilities = answer.get("probabilities") or {}
    if isinstance(choice, dict):  # {"value": "p3", "probability": 0.93}
        choice = choice.get("value", choice.get("key"))
    confidence = answer.get("confidence", answer.get("probability"))
    if confidence is None and isinstance(probabilities, dict) and choice in probabilities:
        confidence = probabilities[choice]
    if not isinstance(choice, str) or confidence is None:
        raise MatcherResponseError(f"Resposta do Jev ilegível para '{question}'. Chaves: {sorted(answer)}")

    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    return choice, float(confidence), input_tokens


_JSON_OBJECT = re.compile(r"\{.*\}", re.S)


class LLMMatcher:
    """O LLM do projeto (``AI_ASSIST_*``) respondendo a mesma escolha em JSON.

    Chama o SDK direto, e não ``copy_assist.suggest``, porque o piloto precisa do
    ``usage`` (tokens) que o transporte de texto descarta.
    """

    name = "llm"

    def __init__(self, *, timeout: float = 60.0, client=None):
        api_key = (getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip()
        if client is None and not api_key:
            raise MatcherNotConfigured("LLM não configurado. Defina AI_ASSIST_API_KEY.")
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.client = client
        self.model = settings.AI_ASSIST_MODEL

    def build_prompt(self, case: Case, keyed: dict[str, CatalogEntry]) -> str:
        options = "\n".join(f"- {key}: {entry.name} (SKU {entry.sku})" for key, entry in keyed.items())
        return (
            f"{QUESTION}\n\nItem do histórico: {case.external_name}\n\nOpções:\n{options}\n"
            f"- {OTHER}: {OTHER_DESCRIPTION}\n\n"
            'Responda só com JSON: {"choice": "<chave>", "confidence": <0 a 1>}'
        )

    def match(self, case: Case, candidates: list[tuple[CatalogEntry, int]]) -> Verdict:
        keyed = _choice_keys(candidates)
        started = time.perf_counter()
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": self.build_prompt(case, keyed)}],
        )
        latency_ms = (time.perf_counter() - started) * 1000
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        found = _JSON_OBJECT.search(text)
        try:
            data = json.loads(found.group(0)) if found else {}
        except json.JSONDecodeError:
            data = {}
        choice, confidence = data.get("choice"), data.get("confidence")
        if not isinstance(choice, str) or not isinstance(confidence, (int, float)):
            raise MatcherResponseError(f"LLM não devolveu escolha em JSON: {text[:200]!r}")
        entry = keyed.get(choice)
        if entry is None and choice != OTHER:
            raise MatcherResponseError(f"LLM escolheu {choice!r}, que não estava entre as opções.")
        usage = getattr(message, "usage", None)
        return Verdict(
            product_pk=entry.pk if entry else None,
            confidence=float(confidence),
            latency_ms=latency_ms,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


# ── Placar ──────────────────────────────────────────────────────────────────


@dataclass
class Price:
    """US$ por milhão de tokens."""

    input_per_m: float = 0.0
    output_per_m: float = 0.0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_m + output_tokens * self.output_per_m) / 1_000_000


@dataclass
class Scoreboard:
    matcher: str
    price: Price
    accept_at: float
    total: int = 0
    correct: int = 0
    accepted: int = 0
    accepted_wrong: int = 0
    errors: int = 0
    latencies: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    rows: list = field(default_factory=list)  # (nome, esperado, escolhido, confiança, certo, erro)

    def add(self, case: Case, verdict: Verdict) -> None:
        self.total += 1
        if verdict.error:
            self.errors += 1
            self.rows.append((case.external_name, case.expected_pk, None, None, False, verdict.error))
            return
        right = verdict.product_pk == case.expected_pk
        self.correct += right
        if verdict.confidence >= self.accept_at:
            self.accepted += 1
            self.accepted_wrong += not right
        if verdict.latency_ms:
            self.latencies.append(verdict.latency_ms)
        self.input_tokens += verdict.input_tokens
        self.output_tokens += verdict.output_tokens
        self.rows.append((case.external_name, case.expected_pk, verdict.product_pk, verdict.confidence, right, ""))

    @property
    def cost_usd(self) -> float:
        return self.price.cost(self.input_tokens, self.output_tokens)

    def latency(self, quantile: float) -> float | None:
        if not self.latencies:
            return None
        if len(self.latencies) == 1:
            return self.latencies[0]
        return statistics.quantiles(self.latencies, n=100, method="inclusive")[int(quantile * 100) - 1]


@dataclass
class BenchmarkResult:
    cases: int
    shortlist_size: int
    shortlist_hits: int  # casos com produto em que o certo estava entre os K
    cases_with_product: int
    boards: list[Scoreboard]


def run(
    cases: list[Case],
    catalog: list[CatalogEntry],
    matchers: list,
    *,
    prices: dict[str, Price],
    shortlist_size: int = DEFAULT_SHORTLIST,
    accept_at: float = 0.9,
) -> BenchmarkResult:
    """Cada caso, para cada concorrente, com a mesma lista curta. Erro de um caso não para o piloto."""
    boards = [Scoreboard(matcher=m.name, price=prices.get(m.name, Price()), accept_at=accept_at) for m in matchers]
    shortlist_hits = cases_with_product = 0
    for case in cases:
        candidates = shortlist(case.external_name, catalog, shortlist_size)
        if case.expected_pk is not None:
            cases_with_product += 1
            shortlist_hits += any(entry.pk == case.expected_pk for entry, _score in candidates)
        for matcher, board in zip(matchers, boards, strict=True):
            try:
                verdict = matcher.match(case, candidates)
            except MatcherResponseError as exc:
                verdict = Verdict(product_pk=None, confidence=0.0, error=str(exc)[:300])
            except Exception as exc:  # rede, timeout: conta como erro do concorrente, não do piloto
                logger.warning("bi.matcher_benchmark: %s falhou num caso: %s", matcher.name, type(exc).__name__)
                verdict = Verdict(product_pk=None, confidence=0.0, error=f"{type(exc).__name__}: {exc}"[:300])
            board.add(case, verdict)
    return BenchmarkResult(
        cases=len(cases),
        shortlist_size=shortlist_size,
        shortlist_hits=shortlist_hits,
        cases_with_product=cases_with_product,
        boards=boards,
    )
