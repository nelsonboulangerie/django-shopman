"""Piloto do de-para: gabarito, lista curta, os três concorrentes e o placar.

Nenhum teste chama rede: Jev e LLM recebem transporte falso, e o que se fixa é
o pedido que sai, a leitura do que volta e a conta de acerto/custo.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command
from shopman.offerman.models import Product

from shopman.backstage.bi.matcher_benchmark import (
    OTHER,
    Case,
    EmbeddingMatcher,
    FuzzyMatcher,
    JevMatcher,
    LLMMatcher,
    MatcherNotConfigured,
    MatcherResponseError,
    gold_cases,
    load_catalog,
    parse_jev_response,
    run,
    shortlist,
)
from shopman.backstage.models import AliasStatus, ProductAlias
from shopman.shop.services.ai_pricing import Price


@pytest.fixture
def catalog(db):
    products = {
        sku: Product.objects.create(sku=sku, name=name)
        for sku, name in (
            ("CT", "Croissant Tradicional"),
            ("PC", "Pain au Chocolat"),
            ("BA", "Baguete Tradicional"),
            ("MD", "Madeleine"),
        )
    }
    return products


def _confirmed(name, product=None, status=AliasStatus.CONFIRMED):
    return ProductAlias.objects.create(source="yooga", external_name=name, product=product, status=status)


# ── Gabarito ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_gold_is_only_confirmed_aliases_with_name(catalog):
    _confirmed("CROISSANT TRAD", catalog["CT"])
    _confirmed("Bolo de pote")  # confirmado sem produto = fora do catálogo
    _confirmed("Pão de queijo", catalog["BA"], status=AliasStatus.PROPOSED)  # palpite da máquina não é gabarito
    cases = gold_cases("yooga")
    assert cases == [Case("CROISSANT TRAD", catalog["CT"].pk), Case("Bolo de pote", None)]


@pytest.mark.django_db
def test_shortlist_brings_the_most_similar_first(catalog):
    found = shortlist("pain chocolat", load_catalog(), 2)
    assert found[0][0].sku == "PC"
    assert len(found) == 2


# ── Concorrentes ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_fuzzy_keeps_todays_cut(catalog):
    entries = load_catalog()
    matcher = FuzzyMatcher(min_score=80)
    hit = matcher.match(Case("croissant tradicional", None), shortlist("croissant tradicional", entries, 3))
    assert hit.product_pk == catalog["CT"].pk and hit.confidence == 1.0
    miss = matcher.match(Case("bolo de pote", None), shortlist("bolo de pote", entries, 3))
    assert miss.product_pk is None and miss.confidence < 0.8


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code, self.text = payload, status_code, str(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload, status_code=200):
        self.payload, self.status_code, self.sent = payload, status_code, []

    def post(self, url, *, json, headers, timeout):
        self.sent.append((url, json, headers))
        return _FakeResponse(self.payload, self.status_code)


@pytest.mark.django_db
def test_jev_asks_a_choice_with_other_and_reads_the_answer(catalog, settings):
    settings.JEV_API_KEY = "test-key"
    session = _FakeSession({
        "answers": {"product": {"answer": "p1", "confidence": 0.97}},
        "usage": {"input_tokens": 120},
    })
    matcher = JevMatcher(session=session)
    candidates = shortlist("pain chocolat", load_catalog(), 3)
    verdict = matcher.match(Case("pain chocolat", catalog["PC"].pk), candidates)

    url, body, headers = session.sent[0]
    assert url == settings.JEV_API_URL
    assert headers["Authorization"] == "Bearer test-key"
    choices = body["questions"]["product"]["choices"]
    assert list(choices)[:3] == ["p1", "p2", "p3"] and OTHER in choices
    assert body["state"] == {"sales_history_item": "pain chocolat"}
    assert (verdict.product_pk, verdict.confidence, verdict.input_tokens) == (catalog["PC"].pk, 0.97, 120)


@pytest.mark.django_db
def test_jev_other_means_no_product(catalog, settings):
    settings.JEV_API_KEY = "test-key"
    matcher = JevMatcher(session=_FakeSession({"answers": {"product": {"answer": OTHER, "confidence": 0.9}}}))
    verdict = matcher.match(Case("bolo de pote", None), shortlist("bolo de pote", load_catalog(), 3))
    assert verdict.product_pk is None


def test_jev_without_key_stays_out(settings):
    settings.JEV_API_KEY = ""
    with pytest.raises(MatcherNotConfigured):
        JevMatcher(session=_FakeSession({}))


def test_jev_parser_accepts_probabilities_list_shape_and_names_unknown_shapes():
    choice, confidence, tokens = parse_jev_response(
        {"answers": [{"id": "product", "value": "p2", "probabilities": {"p2": 0.8, "other": 0.2}}]},
        question="product",
    )
    assert (choice, confidence, tokens) == ("p2", 0.8, 0)
    with pytest.raises(MatcherResponseError, match="Chaves recebidas"):
        parse_jev_response({"output": "?"}, question="product")


class _FakeClient:
    def __init__(self, text, usage=(300, 20)):
        message = SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
            stop_reason="end_turn",
        )
        self.calls = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return message

        self.messages = SimpleNamespace(create=create)


@pytest.mark.django_db
def test_llm_reads_json_choice_and_usage(catalog):
    matcher = LLMMatcher(client=_FakeClient('{"choice": "p1", "confidence": 0.85}'))
    verdict = matcher.match(Case("madeleine", catalog["MD"].pk), shortlist("madeleine", load_catalog(), 3))
    assert (verdict.product_pk, verdict.confidence) == (catalog["MD"].pk, 0.85)
    assert (verdict.input_tokens, verdict.output_tokens) == (300, 20)


@pytest.mark.django_db
def test_llm_one_contender_per_model_and_low_effort_only_where_accepted(catalog, settings):
    settings.AI_ASSIST_MODEL = "claude-opus-5"
    candidates = shortlist("madeleine", load_catalog(), 2)
    default = LLMMatcher(client=_FakeClient('{"choice": "p1", "confidence": 0.9}'))
    default.match(Case("madeleine", None), candidates)
    assert default.name == "llm:claude-opus-5"
    assert default.client.calls[0]["output_config"] == {"effort": "low"}

    haiku = LLMMatcher(model="claude-haiku-4-5", client=_FakeClient('{"choice": "p1", "confidence": 0.9}'))
    haiku.match(Case("madeleine", None), candidates)
    assert haiku.name == "llm:claude-haiku-4-5"
    assert "output_config" not in haiku.client.calls[0]  # o Haiku 4.5 recusa o esforço


@pytest.mark.django_db
def test_llm_choice_outside_options_is_an_error(catalog):
    matcher = LLMMatcher(client=_FakeClient('{"choice": "p9", "confidence": 0.9}'))
    with pytest.raises(MatcherResponseError):
        matcher.match(Case("madeleine", None), shortlist("madeleine", load_catalog(), 2))


# ── Embeddings ──────────────────────────────────────────────────────────────

_VECTORS = {
    # Nomes do catálogo (minúsculos) e das consultas, num espaço de brinquedo.
    "croissant tradicional": [1.0, 0.0, 0.0],
    "pain au chocolat": [0.0, 1.0, 0.0],
    "baguete tradicional": [0.0, 0.0, 1.0],
    "madeleine": [0.5, 0.5, 0.5],
    "pao de chocolate": [0.1, 0.99, 0.0],  # o fuzzy não liga a "pain au chocolat"; o sentido liga
    "bolo de pote": [0.7, -0.7, 0.1],
}


def _toy_embed(texts):
    return [_VECTORS[text] for text in texts]


@pytest.mark.django_db
def test_embedding_finds_by_meaning_in_the_whole_catalog(catalog):
    matcher = EmbeddingMatcher(embed=_toy_embed, min_similarity=0.8)
    matcher.prepare(load_catalog())
    hit = matcher.match(Case("Pao de chocolate", catalog["PC"].pk), candidates=[])  # sem lista curta
    assert hit.product_pk == catalog["PC"].pk and hit.confidence > 0.99
    miss = matcher.match(Case("Bolo de pote", None), candidates=[])
    assert miss.product_pk is None and miss.confidence < 0.8


@pytest.mark.django_db
def test_run_prepares_the_embedding_catalog_once(catalog):
    calls = []

    def counting_embed(texts):
        calls.append(len(texts))
        return _toy_embed(texts)

    matcher = EmbeddingMatcher(embed=counting_embed)
    result = run([Case("pao de chocolate", catalog["PC"].pk)], load_catalog(), [matcher], prices={})
    assert calls == [4, 1]  # catálogo uma vez, consulta uma vez
    assert result.boards[0].correct == 1


def test_embedding_without_package_stays_out(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_fastembed(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("sem fastembed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_fastembed)
    with pytest.raises(MatcherNotConfigured, match="pip install fastembed"):
        EmbeddingMatcher()


# ── Placar ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_scoreboard_counts_accepted_errors_cost_and_failures(catalog):
    entries = load_catalog()
    cases = [Case("madeleine", catalog["MD"].pk), Case("bolo de pote", None), Case("baguete", catalog["BA"].pk)]

    class Scripted:
        name = "llm"
        answers = iter([("MD", 0.95), ("CT", 0.95), MatcherResponseError("quebrou")])

        def match(self, case, candidates):
            answer = next(self.answers)
            if isinstance(answer, Exception):
                raise answer
            from shopman.backstage.bi.matcher_benchmark import Verdict

            return Verdict(catalog[answer[0]].pk, answer[1], latency_ms=100, input_tokens=1_000_000, output_tokens=0)

    result = run(cases, entries, [Scripted()], prices={"llm": Price(input_per_m=3.0)}, shortlist_size=3)
    board = result.boards[0]
    assert (board.total, board.correct, board.accepted, board.accepted_wrong, board.errors) == (3, 1, 2, 1, 1)
    assert board.cost_usd == pytest.approx(6.0)
    assert (result.cases_with_product, result.shortlist_hits) == (2, 2)


@pytest.mark.django_db
def test_command_reports_and_refuses_empty_gold(catalog, settings, tmp_path, capsys):
    settings.JEV_API_KEY = ""
    settings.AI_ASSIST_API_KEY = ""
    with pytest.raises(CommandError, match="Gabarito vazio"):
        call_command("benchmark_alias_matchers")

    _confirmed("CROISSANT TRADICIONAL", catalog["CT"])
    _confirmed("Bolo de pote")
    out_csv = tmp_path / "piloto.csv"
    call_command("benchmark_alias_matchers", csv=str(out_csv))
    out = capsys.readouterr().out
    assert "jev: fora do placar" in out and "llm: fora do placar" in out
    assert "2 casos confirmados" in out
    assert "fuzzy" in out and "2/2 (100%)" in out
    assert out_csv.read_text(encoding="utf-8").splitlines()[1].startswith("fuzzy,CROISSANT TRADICIONAL,CT,CT")


def test_command_with_explicit_matcher_without_key_fails(settings, db):
    settings.JEV_API_KEY = ""
    with pytest.raises(CommandError, match="JEV_API_KEY"):
        call_command("benchmark_alias_matchers", matcher=["jev"])


@pytest.mark.django_db
def test_command_prices_each_llm_model_from_the_table(catalog, settings, monkeypatch, capsys):
    from shopman.backstage.bi import matcher_benchmark

    class OfflineLLM(LLMMatcher):
        def __init__(self, *, model=None):
            super().__init__(model=model, client=_FakeClient('{"choice": "p1", "confidence": 0.95}', usage=(1_000_000, 0)))

    monkeypatch.setattr(matcher_benchmark, "LLMMatcher", OfflineLLM)
    _confirmed("CROISSANT TRADICIONAL", catalog["CT"])
    call_command(
        "benchmark_alias_matchers", matcher=["llm"], llm_model=["claude-haiku-4-5", "modelo-sem-preco"],
    )
    out = capsys.readouterr().out
    haiku_line = next(line for line in out.splitlines() if "llm:claude-haiku-4-5" in line)
    assert "1.0000" in haiku_line  # 1M tokens de entrada × US$ 1/M
    assert "Custo de llm:modelo-sem-preco zerado" in out


# ── Medição automática: o placar vai para o Admin ───────────────────────────


@pytest.mark.django_db
def test_measure_waits_for_enough_gold_then_keeps_an_aggregate_report(catalog, settings, monkeypatch):
    from shopman.backstage.bi import matcher_benchmark
    from shopman.backstage.models import AliasBenchmarkReport

    settings.AI_ASSIST_API_KEY = ""
    settings.JEV_API_KEY = ""
    _confirmed("CROISSANT TRADICIONAL", catalog["CT"])
    report, reason = matcher_benchmark.maybe_measure()
    assert report is None and "1 de 20" in reason

    monkeypatch.setattr(matcher_benchmark, "MIN_CONFIRMED_TO_MEASURE", 1)
    report, reason = matcher_benchmark.maybe_measure()
    assert reason == "medido" and report.cases == 1 and report.contenders.startswith("fuzzy")
    assert "llm: " in report.skipped and "jev: " in report.skipped
    assert "■ fuzzy" in report.report and "acertou: 1 de 1" in report.report
    assert "CROISSANT" not in report.report  # só agregado

    again, reason = matcher_benchmark.maybe_measure()
    assert again is None and "próximo sai" in reason  # um por semana
    assert AliasBenchmarkReport.objects.count() == 1


@pytest.mark.django_db
def test_worker_command_is_quiet_until_it_measures(catalog, settings, capsys):
    settings.AI_ASSIST_API_KEY = ""
    call_command("run_alias_benchmark")
    assert capsys.readouterr().out == ""
    _confirmed("CROISSANT TRADICIONAL", catalog["CT"])
    call_command("run_alias_benchmark", now=True)
    assert "placar do de-para: medido" in capsys.readouterr().out


@pytest.mark.django_db
def test_report_is_readable_in_admin_and_read_only(catalog, settings, monkeypatch):
    from django.contrib.auth.models import User
    from django.test import Client
    from django.urls import reverse

    from shopman.backstage.bi import matcher_benchmark
    from shopman.shop.models import Shop

    settings.AI_ASSIST_API_KEY = ""
    Shop.objects.create(name="Test Shop", brand_name="Test", short_name="TS", primary_color="#C5A55A", default_ddd="43")
    User.objects.create_superuser("admin", "admin@test.com", "pass")
    client = Client()
    client.login(username="admin", password="pass")
    monkeypatch.setattr(matcher_benchmark, "MIN_CONFIRMED_TO_MEASURE", 1)
    _confirmed("CROISSANT TRADICIONAL", catalog["CT"])
    report, _reason = matcher_benchmark.maybe_measure()

    page = client.get(reverse("admin:backstage_aliasbenchmarkreport_change", args=[report.pk]))
    assert page.status_code == 200 and "aceitaria sozinho" in page.content.decode()
    assert client.get(reverse("admin:backstage_aliasbenchmarkreport_add")).status_code == 403
