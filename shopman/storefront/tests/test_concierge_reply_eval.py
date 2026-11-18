"""Placar da Concierge (``concierge_reply_eval``): a régua que prova (WP-02).

- rodada com rede sem ``--paid`` termina com erro antes de criar cliente (zero chamadas);
- com ``--paid``, o teto de gasto (``--budget-usd``, tabela ``LLM_PRICES``) para a rodada,
  e custo desconhecido também para;
- ``--repeat N`` mostra cada medida "em todas as N";
- ``--report`` grava o placar em Markdown.

Nenhum teste chama provedor: o leitor é um cliente falso que conta as chamadas.
"""

from __future__ import annotations

import dataclasses
import io
import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.storefront.concierge import intent_benchmark, intents, reply_eval, triage

pytestmark = pytest.mark.django_db


class ExplodingFactory:
    """Qualquer tentativa de criar cliente de rede conta e falha."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("cliente de rede criado sem --paid")


class FakeReader:
    """Leitor das partes que devolve lista vazia (vale a divisão local) e um ``usage`` com preço."""

    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps({"acts": []}))],
            usage=SimpleNamespace(
                input_tokens=300, output_tokens=40, cache_read_input_tokens=0, cache_creation_input_tokens=0,
            ),
        )


@pytest.fixture
def no_network(monkeypatch):
    factory = ExplodingFactory()
    monkeypatch.setattr(intents, "build_client", factory)
    monkeypatch.setattr(triage, "build_client", factory)
    monkeypatch.setattr(intent_benchmark, "JevContender", factory)
    return factory


@pytest.fixture
def fake_reader(monkeypatch):
    reader = FakeReader()
    monkeypatch.setattr(intents, "build_client", lambda: reader)
    # 300 tokens de entrada e 40 de saída no Haiku: US$ 0,0005 por leitura.
    monkeypatch.setattr(intents, "_model", lambda: "claude-haiku-4-5")
    return reader


def _command(*args) -> str:
    out = io.StringIO()
    call_command("concierge_reply_eval", *args, stdout=out)
    return out.getvalue()


# ── Sem --paid, nenhuma chamada ──────────────────────────────────────


@pytest.mark.parametrize("args", [
    ("--plural", "--reader", "model"),
    ("--classifier", "model"),
    ("--classifier", "jev"),
    ("--plural", "--reader", "model", "--repeat", "3", "--budget-usd", "5"),
])
def test_network_run_without_paid_fails_before_any_client(no_network, args):
    with pytest.raises(CommandError, match="--paid"):
        _command(*args)
    assert no_network.calls == 0


@pytest.mark.parametrize("args", [
    (),
    ("--memory",),
    ("--plural", "--reader", "local"),
    ("--classifier", "jev-shadow"),
])
def test_free_runs_need_no_paid_and_create_no_client(no_network, args):
    out = _command("--limit", "15", *args)
    assert "Nada foi gravado" in out
    assert no_network.calls == 0


def test_network_reason_names_the_argument_that_costs():
    assert reply_eval.network_reason(plural=True, reader="model") == "--reader model"
    assert reply_eval.network_reason(plural=True, reader="local") == ""
    assert reply_eval.network_reason(classifier="model") == "--classifier model"
    assert reply_eval.network_reason(classifier="jev") == "--classifier jev"
    assert reply_eval.network_reason(classifier="rules") == ""
    assert reply_eval.network_reason(classifier="jev-shadow") == ""


# ── Com --paid, o teto vale ──────────────────────────────────────────


def test_paid_run_stops_at_the_budget(fake_reader):
    out = _command("--plural", "--reader", "model", "--paid", "--budget-usd", "0.0009")
    assert fake_reader.calls == 2  # 0,0005 + 0,0005 passa de 0,0009: a terceira leitura não sai
    assert "parou no teto de gasto" in out
    assert "Gasto da rodada: US$ 0.0010 de US$ 0.0009" in out


def test_budget_holds_across_repetitions(fake_reader):
    out = _command("--plural", "--reader", "model", "--paid", "--budget-usd", "0.0009", "--repeat", "3")
    assert fake_reader.calls == 2
    assert "Só 1 de 3 rodadas" in out


def test_unpriced_model_stops_the_paid_run(fake_reader, monkeypatch):
    monkeypatch.setattr(intents, "_model", lambda: "modelo-fora-da-tabela")
    out = _command("--plural", "--reader", "model", "--paid")
    assert fake_reader.calls == 1
    assert "custo desconhecido" in out


def test_budget_must_be_positive(fake_reader):
    with pytest.raises(CommandError, match="maior que zero"):
        _command("--plural", "--reader", "model", "--paid", "--budget-usd", "0")
    assert fake_reader.calls == 0


def test_max_cases_limits_each_repetition(fake_reader):
    report = reply_eval.run(reply_eval.load_golden()[:30], classifier="rules", max_cases=5)
    assert len(report.results) == 5
    assert "--max-cases 5" in report.stopped
    out = _command("--plural", "--reader", "model", "--paid", "--max-cases", "4", "--repeat", "2")
    assert "4 casos medidos em todas" in out
    assert fake_reader.calls <= 8


# ── --repeat: "em todas as N" ────────────────────────────────────────


def test_repeat_three_shows_every_measure_in_all_three(fake_reader):
    out = _command(
        "--plural", "--reader", "model", "--paid", "--budget-usd", "5", "--repeat", "3", "--show-misses", "0",
        "--limit", "60",
    )
    per_run = fake_reader.calls // 3
    assert per_run > 0 and fake_reader.calls == per_run * 3
    assert "Repetição: 3 rodadas" in out
    table = out[out.index("Repetição: 3 rodadas"):]
    for label in (
        "Várias partes, todas achadas", "Todos os casos, todas achadas", "Partes achadas",
        "Equipe achada", "Equipe sem precisar", "Uma parte lida como várias",
    ):
        assert label in table
    assert "em todas as 3" in table


def test_repeat_on_the_single_scoreboard():
    out = _command("--repeat", "3", "--show-misses", "0", "--limit", "40")
    table = out[out.index("Repetição: 3 rodadas"):]
    for label in ("Destino certo", "Equipe e outra mesa achadas", "À equipe sem precisar", "Intenção certa"):
        assert label in table
    assert "em todas as 3" in table


def test_in_all_counts_the_worst_round_for_team():
    """Equipe achada em 2 de 3 rodadas não conta "em todas": é o que a média esconde."""
    cases = reply_eval.load_golden()[:120]
    runs = [reply_eval.run_plural(cases, reader="local") for _ in range(3)]
    sensitive = [r for r in runs[1].results if r.case["expected"]["destination"] != "answer" and r.team_after]
    assert sensitive
    lost = sensitive[0]
    runs[1].results[runs[1].results.index(lost)] = dataclasses.replace(lost, team_after=False)
    found = sum(r.team_after for r in runs[0].results if r.case["expected"]["destination"] != "answer")
    total = sum(1 for r in runs[0].results if r.case["expected"]["destination"] != "answer")

    text = reply_eval.consistency(runs)

    row = next(line for line in text.splitlines() if line.strip().startswith("Equipe achada"))
    assert row.split()[-1] == f"{found - 1}/{total}"
    assert f"perdida em outra: {lost.case['ref']}" in text


def test_in_all_counts_a_wrong_destination_in_any_round():
    cases = reply_eval.load_golden()[:20]
    runs = [reply_eval.run(cases, classifier="rules") for _ in range(2)]
    ok = [r for r in runs[0].results if r.destination_ok]
    runs[0].results[runs[0].results.index(ok[0])] = dataclasses.replace(ok[0], destination="nowhere")

    text = reply_eval.consistency(runs)

    row = next(line for line in text.splitlines() if line.strip().startswith("Destino certo"))
    assert row.split()[-1] == f"{len(ok) - 1}/{len(cases)}"


def test_repeat_is_refused_where_nothing_varies():
    with pytest.raises(CommandError, match="--repeat"):
        _command("--memory", "--repeat", "2")


# ── --report ──────────────────────────────────────────────────────────


def test_report_writes_the_scoreboard_in_markdown(tmp_path):
    path = tmp_path / "placar" / "linha.md"
    out = _command("--limit", "20", "--report", str(path))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Placar da Concierge\n")
    assert "- Comando: `manage.py concierge_reply_eval" in text
    assert "```text\n═══ Placar da Concierge (golden set) ═══" in text
    assert "Destino certo:" in text and text.rstrip().endswith("```")
    assert f"Placar gravado em {path}" in out
