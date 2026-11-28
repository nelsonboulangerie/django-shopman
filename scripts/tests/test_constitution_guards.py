"""Guardas da Constituição: cada uma reprova o caso ruim e deixa passar o bom.

Stdlib + pytest, sem Django (rode com ``-p no:django``). As guardas leem código como texto
(AST), então os casos são fontes pequenas montadas aqui.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load("guard_baseline")
decision = _load("check_decision_authority")
signal = _load("check_signal_on_commit")
ledger = _load("check_ledger_immutability")
refs = _load("check_cross_kernel_refs")
order = _load("check_order_lifecycle_owner")
money = _load("check_money_integer")
lifecycle = _load("check_lifecycle_functional")
readside = _load("check_read_side_immutability")
guard_map = _load("check_guard_map")

SECTIONS = {
    "decision_authority": decision,
    "signal_on_commit": signal,
    "ledger_immutability": ledger,
    "cross_kernel_refs": refs,
    "order_lifecycle_owner": order,
    "money_integer": money,
    "lifecycle_functional": lifecycle,
    "read_side_immutability": readside,
}


def _tree(source: str) -> ast.Module:
    return ast.parse(source)


def _details(findings) -> list[str]:
    return [f.detail for f in findings]


# ── O repositório casa com a baseline versionada ─────────────────────────────


@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_repository_matches_versioned_baseline(section):
    grew, stale = base.compare(SECTIONS[section].collect(), base.load_baseline(section))
    assert grew == [], grew
    assert stale == [], stale


def test_every_baseline_entry_has_class_reason_and_front():
    data = json.loads(base.BASELINE_PATH.read_text())
    for section in SECTIONS:
        for key, entry in data[section].items():
            assert entry["classe"] in base.CLASSES, key
            assert entry["motivo"], key
            if entry["classe"] == "violacao":
                assert entry["frente"], key


# ── Mecânica da baseline: crescer reprova, encolher reprova até apagar ───────


def _finding(key: str) -> base.Finding:
    return base.Finding(key, "x.py:1", "achado")


def test_new_finding_grows_and_fails():
    grew, stale = base.compare([_finding("a"), _finding("b")], {"a": {"count": 1}})
    assert len(grew) == 1 and grew[0].startswith("b ")
    assert stale == []


def test_more_occurrences_than_baseline_fails():
    grew, _ = base.compare([_finding("a"), _finding("a")], {"a": {"count": 1}})
    assert grew and "achado 2" in grew[0]


def test_fixed_finding_leaves_an_obsolete_entry():
    grew, stale = base.compare([], {"a": {"count": 1, "motivo": "removida pela F2"}})
    assert grew == []
    assert stale and "removida pela F2" in stale[0]


def test_baseline_entry_without_front_is_rejected(tmp_path):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"s": {"k": {"classe": "violacao", "motivo": "m"}}}))
    with pytest.raises(SystemExit):
        base.load_baseline("s", path)


def test_strict_mode_ignores_baseline(capsys):
    assert base.run("s", "T", [_finding("a")], ["--strict"], rule="r") == 1
    assert base.run("s", "T", [], ["--strict"], rule="r") == 0


# ── C5: autoridade de decisão ────────────────────────────────────────────────


def test_decision_authority_sees_definition_past_the_first_line():
    """A versão regex só olhava a 1ª linha (``^`` sem MULTILINE) e dava OK falso."""
    source = '"""doc."""\nimport x\n\n\ndef _stock_decision(sku):\n    return 1\n'
    found = decision.findings_for("shopman/shop/services/availability.py", _tree(source))
    assert len(found) == 1
    assert found[0].key == "shopman/shop/services/availability.py::<module>::_stock_decision"


def test_decision_authority_flags_canonical_outside_owner_and_method():
    source = "class A:\n    def promise_for_sku(self):\n        pass\n"
    found = decision.findings_for("shopman/shop/services/x.py", _tree(source))
    assert found and found[0].key.endswith("::A::promise_for_sku")


def test_decision_authority_accepts_canonical_in_owner_and_callers():
    source = "def promise_for_sku(sku):\n    pass\n"
    assert decision.findings_for("packages/stockman/shopman/stockman/services/promise.py", _tree(source)) == []
    caller = "from shopman.stockman import promise_for_sku\nx = promise_for_sku('A')\n"
    assert decision.findings_for("shopman/shop/services/x.py", _tree(caller)) == []


def test_decision_authority_flags_offer_policy_compared_outside_stockman():
    """Comparar a política é decidir "pode pedir" fora da promessa (frente 5 da v7)."""
    source = (
        "def can_order(raw):\n"
        "    if raw.get('availability_policy') == 'demand_ok':\n"
        "        return True\n"
        "    return raw['availability_policy'] in ('stock_only', 'planned_ok')\n"
    )
    found = decision.findings_for("shopman/shop/services/x.py", _tree(source))
    assert sorted(f.key for f in found) == [
        "shopman/shop/services/x.py::can_order::policy:demand_ok",
        "shopman/shop/services/x.py::can_order::policy:planned_ok",
        "shopman/shop/services/x.py::can_order::policy:stock_only",
    ]


def test_decision_authority_accepts_offer_policy_in_stockman_and_as_data():
    owner = "def f(p):\n    return p == 'stock_only'\n"
    assert decision.findings_for("packages/stockman/shopman/stockman/services/availability.py", _tree(owner)) == []
    shown = "def f(raw):\n    return {'policy': raw.get('availability_policy', 'planned_ok')}\n"
    assert decision.findings_for("shopman/shop/services/x.py", _tree(shown)) == []


def test_decision_authority_skips_installed_build_copy(tmp_path):
    copy = tmp_path / "packages/stockman/build/lib/shopman/shop/services/availability.py"
    copy.parent.mkdir(parents=True)
    copy.write_text("def _stock_decision():\n    pass\n")
    assert decision.collect(tmp_path) == []


# ── ADR-025: signal depois do COMMIT ─────────────────────────────────────────


def _signal(source: str) -> list[str]:
    return _details(signal.findings_for("packages/x/shopman/x/s.py", _tree(source), source.splitlines()))


def test_signal_send_inside_transaction_fails():
    assert _signal("def f():\n    thing_changed.send(\n        sender=X,\n        a=1,\n    )\n")


def test_signal_send_deferred_by_lambda_passes():
    assert _signal("def f():\n    transaction.on_commit(lambda: thing_changed.send(sender=X))\n") == []


def test_signal_send_in_function_registered_on_commit_passes():
    source = (
        "def f():\n"
        "    def _emit():\n"
        "        thing_changed.send(sender=X)\n"
        "    transaction.on_commit(_emit)\n"
    )
    assert _signal(source) == []


def test_on_commit_word_nearby_does_not_excuse_the_send():
    """A janela de 8 linhas da versão regex aceitava on_commit em comentário/docstring."""
    source = "def f():\n    # depois vira on_commit\n    thing_changed.send(sender=X)\n"
    assert _signal(source)


def test_coupled_write_declared_with_marker_passes():
    source = "def f():\n    # ADR-025: escrita acoplada (gate de estoque)\n    thing_changed.send(sender=X)\n"
    assert _signal(source) == []


def test_send_inside_directive_handler_passes():
    source = (
        "class H:\n"
        "    def handle(self, *, message, ctx):\n"
        "        self._done()\n"
        "    def _done(self):\n"
        "        nfce_authorized.send(sender=type(self))\n"
    )
    assert _signal(source) == []


def test_non_signal_send_is_ignored():
    assert _signal("def f():\n    mail.send()\n    client.send(payload)\n") == []


# ── C11: ledger imutável no dono ─────────────────────────────────────────────


def _ledger(rel: str, source: str) -> list[str]:
    return _details(ledger.findings_for(rel, _tree(source)))


MOVE = "from shopman.stockman.models import Move\n"


def test_ledger_write_outside_owner_fails():
    assert _ledger("shopman/shop/services/x.py", MOVE + "Move.objects.create(delta=1)\n")


def test_ledger_rewrite_inside_owner_fails():
    rel = "packages/stockman/shopman/stockman/services/x.py"
    assert _ledger(rel, MOVE + "Move.objects.filter(pk=1).update(delta=2)\n")
    assert _ledger(rel, MOVE + "Move.objects.select_for_update().filter(pk=1).delete()\n")


def test_ledger_append_inside_owner_and_bridge_passes():
    assert _ledger("packages/stockman/shopman/stockman/services/x.py", MOVE + "Move.objects.create(delta=1)\n") == []
    bridge = "packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py"
    assert _ledger(bridge, MOVE + "Move.objects.create(delta=1)\n") == []


def test_ledger_name_from_another_module_is_not_the_ledger():
    source = "from shopman.shop.models import Entry\nEntry.objects.filter(pk=1).update(x=1)\n"
    assert _ledger("shopman/shop/services/x.py", source) == []


def test_ledger_read_passes():
    assert _ledger("shopman/shop/services/x.py", MOVE + "list(Move.objects.filter(delta__gt=0))\n") == []


# ── C3: ref entre kernels, nunca FK ─────────────────────────────────────────


LABELS = {"offerman": "offerman", "craftsman_stockman": "craftsman", "stockman": "stockman"}


def _refs(rel: str, source: str) -> list[str]:
    return _details(refs.findings_for(rel, _tree(source), LABELS))


def test_fk_to_other_kernel_by_string_fails():
    source = "class A(models.Model):\n    p = models.ForeignKey('offerman.Product', on_delete=models.PROTECT)\n"
    assert _refs("packages/stockman/shopman/stockman/models/a.py", source)


def test_fk_to_other_kernel_by_imported_name_fails():
    source = (
        "from shopman.offerman.models import Product\n"
        "class A(models.Model):\n    p = models.OneToOneField(to=Product, on_delete=models.CASCADE)\n"
    )
    assert _refs("packages/stockman/shopman/stockman/models/a.py", source)


def test_fk_inside_own_kernel_or_from_orchestrator_passes():
    own = "class A(models.Model):\n    q = models.ForeignKey('stockman.Quant', on_delete=models.CASCADE)\n"
    assert _refs("packages/stockman/shopman/stockman/models/a.py", own) == []
    contrib = "class A(models.Model):\n    q = models.ForeignKey('craftsman_stockman.X', on_delete=models.CASCADE)\n"
    assert _refs("packages/craftsman/shopman/craftsman/models/a.py", contrib) == []
    orchestrator = "class A(models.Model):\n    p = models.ForeignKey('offerman.Product', on_delete=models.CASCADE)\n"
    assert _refs("shopman/shop/models/a.py", orchestrator) == []


def test_label_map_reads_contrib_labels():
    labels = refs.label_map()
    assert labels["craftsman_stockman"] == "craftsman"
    assert labels["customer_loyalty"] == "guestman"


# ── C6: ciclo de Order no Orderman ──────────────────────────────────────────


ORDER = "from shopman.orderman.models import Order\n"


def _order(rel: str, source: str) -> list[str]:
    return _details(order.findings_for(rel, _tree(source)))


def test_order_status_assignment_outside_owner_fails():
    assert _order("shopman/shop/services/x.py", ORDER + "order.status = Order.Status.READY\norder.save()\n")
    assert _order("shopman/shop/services/x.py", ORDER + "setattr(order, 'status', Order.Status.READY)\n")
    assert _order("shopman/shop/services/x.py", ORDER + "Order.objects.filter(pk=1).update(status='ready')\n")


def test_parallel_transition_table_fails():
    source = ORDER + "NEXT = {Order.Status.NEW: Order.Status.CONFIRMED, Order.Status.CONFIRMED: {Order.Status.READY}}\n"
    assert _order("shopman/shop/services/x.py", source)


def test_order_transition_through_owner_and_reads_pass():
    source = ORDER + (
        "order.transition_status(Order.Status.READY, actor='x')\n"
        "order.status = Order.objects.values_list('status', flat=True).get(pk=1)\n"
        "if order.status == Order.Status.READY:\n    pass\n"
        "LABELS = {Order.Status.READY: 'Pronto'}\n"
    )
    assert _order("shopman/shop/services/x.py", source) == []
    assert _order("packages/orderman/shopman/orderman/models/order.py", ORDER + "self.status = Order.Status.READY\n") == []


# ── C2: dinheiro inteiro ─────────────────────────────────────────────────────


def _money(source: str) -> list[str]:
    return _details(money.findings_for("packages/x/shopman/x/models.py", _tree(source)))


def test_money_in_float_or_decimal_fails():
    assert _money("class A(models.Model):\n    unit_cost = models.DecimalField(max_digits=9, decimal_places=2)\n")
    assert _money("class A(models.Model):\n    price_q = models.FloatField()\n")
    source = "from django.db.models import DecimalField\nclass A(Model):\n    total_q = DecimalField()\n"
    assert _money(source)


def test_integer_money_and_fractional_non_money_pass():
    source = (
        "class A(models.Model):\n"
        "    price_q = models.BigIntegerField()\n"
        "    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)\n"
        "    qty = models.DecimalField(max_digits=9, decimal_places=3)\n"
        "    value = models.FloatField()\n"
    )
    assert _money(source) == []


# ── C7: lifecycle funcional ─────────────────────────────────────────────────


def _lifecycle(source: str) -> list[str]:
    return _details(lifecycle.findings_for("shopman/shop/x.py", _tree(source)))


def test_lifecycle_class_or_subclass_fails():
    assert _lifecycle("class NelsonFlow(\n    BaseFlow,\n):\n    pass\n")
    assert _lifecycle("class OrderLifecycle:\n    pass\n")


def test_phase_vocabulary_and_plain_classes_pass():
    source = "class Phase(models.TextChoices):\n    A = 'a'\nclass Workflow2Step:\n    pass\nclass Config:\n    pass\n"
    assert _lifecycle(source) == []


# ── C10: read-side não escreve no kernel ────────────────────────────────────


def _readside(source: str) -> list[str]:
    return _details(readside.findings_for("shopman/backstage/bi/x.py", _tree(source)))


def test_bi_writing_a_kernel_model_fails():
    assert _readside("from shopman.orderman.models import Order\nOrder.objects.filter(pk=1).update(x=1)\n")


def test_bi_materializing_its_own_model_passes():
    source = (
        "from shopman.backstage.models import ImportBatch\n"
        "from shopman.orderman.models import Order\n"
        "ImportBatch.objects.create(source='x')\n"
        "list(Order.objects.filter(status='done'))\n"
    )
    assert _readside(source) == []


# ── Mapa de guardas ─────────────────────────────────────────────────────────


def test_guard_map_is_complete_and_documented():
    assert guard_map.problems() == []


def test_guard_map_flags_unmapped_check_and_undocumented_guard(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check_a.py").write_text("")
    (tmp_path / "scripts/check_b.py").write_text("")
    doc = tmp_path / guard_map.DOC
    doc.parent.mkdir(parents=True)
    doc.write_text("| x | check_zzz.py | make x |\n")
    found = guard_map.problems(tmp_path, {"porta": ["scripts/check_a.py"]})
    assert any("scripts/check_b.py" in f for f in found)
    assert any("não cita: check_a.py" in f for f in found)
    assert any("inexistente: check_zzz.py" in f for f in found)
