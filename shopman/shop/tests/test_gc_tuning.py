"""Ajuste de coleta de lixo do processo web (config/gc_tuning.py).

No ar, o ``gc;dur`` do Server-Timing tinha picos de 265–325 ms: coletas completas
percorrendo os objetos do boot. O ``gc.freeze()`` depois do boot tira esses objetos
da coleta; o limiar fica no padrão do Python salvo env explícita.
"""

from __future__ import annotations

import gc
import importlib
import logging
import sys

import pytest

from config import gc_tuning


@pytest.fixture(autouse=True)
def _restore_gc():
    threshold = gc.get_threshold()
    yield
    gc.unfreeze()
    gc.set_threshold(*threshold)


def test_default_freezes_the_boot_and_keeps_python_thresholds():
    before = gc.get_threshold()

    applied = gc_tuning.tune_gc_after_boot({})

    assert applied["frozen"] > 0
    assert gc.get_freeze_count() == applied["frozen"]
    assert gc.get_threshold() == before
    assert applied["threshold"] is None


def test_freeze_loads_the_urlconf_first(monkeypatch):
    calls = []
    monkeypatch.setattr(gc_tuning, "_warm_urlconf", lambda: calls.append("urls"))

    gc_tuning.tune_gc_after_boot({})

    assert calls == ["urls"]


@pytest.mark.parametrize("off", ["0", "false", "off", "no", " OFF "])
def test_freeze_can_be_turned_off(off):
    gc.unfreeze()

    applied = gc_tuning.tune_gc_after_boot({"SHOPMAN_GC_FREEZE": off})

    assert applied["frozen"] == 0
    assert gc.get_freeze_count() == 0


def test_explicit_threshold_is_applied():
    applied = gc_tuning.tune_gc_after_boot({"SHOPMAN_GC_FREEZE": "0", "SHOPMAN_GC_THRESHOLD": "5000, 10, 10"})

    assert gc.get_threshold() == (5000, 10, 10)
    assert applied["threshold"] == (5000, 10, 10)


@pytest.mark.parametrize("bad", ["abc", "1,2,3,4", "-1", "700,x"])
def test_invalid_threshold_keeps_the_current_one_and_warns(bad, caplog):
    before = gc.get_threshold()

    with caplog.at_level(logging.WARNING, logger="config.gc_tuning"):
        gc_tuning.tune_gc_after_boot({"SHOPMAN_GC_FREEZE": "0", "SHOPMAN_GC_THRESHOLD": bad})

    assert gc.get_threshold() == before
    assert "SHOPMAN_GC_THRESHOLD" in caplog.text


def test_a_broken_urlconf_does_not_break_the_boot(monkeypatch, caplog):
    def boom():
        raise RuntimeError("urlconf")

    monkeypatch.setattr(gc_tuning, "_warm_urlconf", boom)

    with caplog.at_level(logging.WARNING, logger="config.gc_tuning"):
        applied = gc_tuning.tune_gc_after_boot({})

    assert applied["frozen"] > 0
    assert "URLconf" in caplog.text


def test_the_asgi_entrypoint_tunes_gc_after_building_the_application(monkeypatch):
    calls = []
    monkeypatch.setattr(gc_tuning, "tune_gc_after_boot", lambda: calls.append("tuned"))

    module = sys.modules.get("config.asgi")
    module = importlib.reload(module) if module else importlib.import_module("config.asgi")

    assert calls == ["tuned"]
    assert module.application is not None
