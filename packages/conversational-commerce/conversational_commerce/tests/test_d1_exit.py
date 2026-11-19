"""O critério de saída do D1 (plano do framework, F11), como teste.

1. A matriz fecha: os 40 K marcados, cada um com o escopo que o plano exige
   (``matrix --check``). E o teste do teste: a checagem reprova K faltando, K
   sem escopo e escopo diferente do exigido.
2. As seis jornadas rodam juntas, no mesmo núcleo e sobre os mesmos falsos.
3. A especificação está toda ``vigente``.

A rede bloqueada é a fixture ``autouse`` do ``conftest.py`` (vale para este
arquivo também), e o K38 é ``test_k38_no_infrastructure.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conversational_commerce.engine import Engine, Ports
from conversational_commerce.profile.test_profile import build_test_profile
from conversational_commerce.testing.conformance.catalog import K_TESTS
from conversational_commerce.testing.conformance.matrix import PACKAGE_TESTS, main, report, scan
from conversational_commerce.testing.fakes import FakeWorld
from conversational_commerce.testing.journeys import j1, j2, j3, j4, j5, j6
from conversational_commerce.testing.journeys.runner import ScriptedModel, run_journey, script_of
from conversational_commerce.tests.engine.helpers import CTX, WITH_MODEL

SPEC = Path(__file__).resolve().parents[2] / "spec"
JOURNEYS = (("J1", CTX, j1.STEPS), ("J2", CTX, j2.STEPS), ("J3", j3.CTX, j3.STEPS), ("J4", j4.CTX, j4.STEPS),
            ("J5", j5.CTX, j5.STEPS), ("J6", j6.CTX, j6.STEPS))


def test_the_matrix_closes_with_all_forty_and_the_required_scopes(capsys):
    text, problems, missing = report([PACKAGE_TESTS])
    assert problems == [] and missing == []
    assert len(K_TESTS) == 40 and "Marcados: 40 de 40. Faltam: nenhum." in text
    assert main(["--check"]) == 0
    capsys.readouterr()


def test_the_check_fails_on_a_missing_k_a_missing_scope_or_a_wrong_scope(tmp_path, capsys):
    """O teste do teste: sem ele, uma matriz verde não provaria nada."""
    (tmp_path / "test_fake_adapter.py").write_text(
        "from conversational_commerce.testing.conformance import conformance\n\n"
        "@conformance('K01')\n"
        "def test_without_scope(): ...\n\n"
        "@conformance('K13', scope='core')\n"
        "def test_wrong_scope(): ...\n\n"
        "@conformance('K99', scope='core')\n"
        "def test_unknown(): ...\n", encoding="utf-8")
    marked, problems = scan([tmp_path])
    assert {p.message for p in problems} == {"K01 sem escopo válido: None", "K desconhecido: K99"}
    _, problems, missing = report([tmp_path])
    assert any("K13 declara core, o plano exige real_mechanism" in p.message for p in problems)
    assert "K02" in missing and len(missing) == 39
    # Só os testes do pacote, menos um arquivo: o --check reprova pelo K que falta.
    partial = tmp_path / "partial"
    partial.mkdir()
    for path in sorted(PACKAGE_TESTS.rglob("test_*.py")):
        if path.name != "test_k39_profile_lines.py":
            (partial / f"test_{path.parent.name}_{path.name}").write_text(path.read_text(encoding="utf-8"),
                                                                     encoding="utf-8")
    _, problems, missing = report([partial])
    assert problems == [] and missing == ["K39"]
    capsys.readouterr()


def test_the_six_journeys_run_together_on_one_core():
    world = FakeWorld()
    ports = Ports.from_world(world)
    ports.model = ScriptedModel(world.clock, script_of([step for _, _, steps in JOURNEYS for step in steps]))
    engine = Engine(ports, build_test_profile(**WITH_MODEL), subject_of=j4.subject)
    problems, episodes = {}, {}
    for name, ctx, steps in JOURNEYS:
        runs = run_journey(engine, ctx, steps)
        problems[name] = [problem for run in runs for problem in run.problems]
        episodes[name] = {run.result.episode.episode_id for run in runs}
    assert problems == {name: [] for name, _, _ in JOURNEYS}
    # Cada jornada no seu episódio (vínculos de canal diferentes): ninguém se une a outro por texto.
    assert all(len(ids) == 1 for ids in episodes.values())
    assert len(set().union(*episodes.values())) == len(JOURNEYS)


def test_the_specification_is_all_in_force():
    if not SPEC.is_dir():
        pytest.skip("a especificação mora no repositório, não no wheel instalado")
    states = {}
    for path in sorted(SPEC.glob("*.md")):
        match = re.search(r"^> \*\*Estado:\*\* (\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        states[path.name] = match.group(1) if match else None
    assert len(states) == 12
    assert {name: state for name, state in states.items() if state != "vigente"} == {}
