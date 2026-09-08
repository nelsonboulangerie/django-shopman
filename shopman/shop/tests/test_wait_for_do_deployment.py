"""A espera pós-deploy decide certo — e a decisão é testável fora do runner.

A primeira versão desta espera era Python dentro de shell dentro de um bloco
YAML, e morreu no runner com `syntax error near unexpected token '('` antes de
esperar coisa alguma. Como script, a decisão inteira cabe em testes: qual
deployment conta, qual fase solta, qual fase grita, e o caso em que não há
deployment nenhum a esperar.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "wait_for_do_deployment.py"
_spec = importlib.util.spec_from_file_location("wait_for_do_deployment", SCRIPT)
wait_for_do = importlib.util.module_from_spec(_spec)
sys.modules["wait_for_do_deployment"] = wait_for_do
_spec.loader.exec_module(wait_for_do)


def dep(dep_id: str, created: str, phase: str) -> dict:
    return {"id": dep_id, "created_at": created, "phase": phase}


# ---------------------------------------------------------------------------
# Qual deployment conta
# ---------------------------------------------------------------------------


def test_deployment_anterior_ao_deploy_nao_conta():
    """O verde que atesta o que não subiu nasce exatamente aqui."""
    velho = dep("v", "2026-09-08T14:00:00Z", "ACTIVE")
    since = wait_for_do._epoch("2026-09-08T15:00:00Z")
    assert wait_for_do.newest_since([velho], since) is None


def test_o_mais_recente_ganha():
    a = dep("a", "2026-09-08T15:10:00Z", "ACTIVE")
    b = dep("b", "2026-09-08T15:20:00Z", "DEPLOYING")
    since = wait_for_do._epoch("2026-09-08T15:00:00Z")
    assert wait_for_do.newest_since([a, b], since)["id"] == "b"


def test_sem_instante_de_referencia_aceita_o_corrente():
    """`--since` vazio é o probe: prova o caminho, não a espera."""
    atual = dep("x", "2026-09-01T00:00:00Z", "ACTIVE")
    assert wait_for_do.newest_since([atual], 0)["id"] == "x"


def test_created_at_ilegivel_nao_estoura():
    ruim = dep("?", "não é data", "ACTIVE")
    assert wait_for_do.newest_since([ruim], 10**9) is None


# ---------------------------------------------------------------------------
# Fases
# ---------------------------------------------------------------------------


def test_error_e_canceled_sao_fracasso_terminal():
    """Deploy que não chegou ao alpha tem que ficar VERMELHO, não seguir."""
    assert wait_for_do.FAILED_PHASES == {"ERROR", "CANCELED"}


def test_folga_de_relogio_declarada():
    """A DO nasce o deployment quando VÊ a tag; os relógios não são o mesmo."""
    assert wait_for_do.CLOCK_SKEW_SECONDS == 120


def test_app_id_por_nome_do_spec():
    apps = [
        {"id": "outro", "spec": {"name": "shopman-prod"}},
        {"id": "certo", "spec": {"name": "shopman-alpha"}},
    ]
    assert wait_for_do.find_app_id(apps, "shopman-alpha") == "certo"
    assert wait_for_do.find_app_id(apps, "inexistente") is None


def test_app_sem_spec_nao_estoura():
    assert wait_for_do.find_app_id([{"id": "a"}], "shopman-alpha") is None


# ---------------------------------------------------------------------------
# Uso
# ---------------------------------------------------------------------------


def test_sem_token_para_e_diz_por_que(monkeypatch, capsys):
    monkeypatch.delenv("DO_TOKEN", raising=False)
    code = wait_for_do.main(["--app-name", "shopman-alpha"])
    assert code == 2
    assert "DIGITALOCEAN_ACCESS_TOKEN ausente" in capsys.readouterr().err
