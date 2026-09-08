"""A espera pós-deploy correlaciona por DIGEST, e por isso não tem falso verde.

Duas gerações caíram antes desta:

1. `sleep 420` num job com `timeout-minutes: 5` — 16 runs cancelados, asserção
   nenhuma, nada vermelho.
2. escolha por relógio (`created_at >= fim - 120s`) com sucesso presumido quando
   nada aparecia. Duas portas para verde mentiroso: o deployment do merge
   ANTERIOR entrava pela folga de 120s, e "não vi deployment" era lido como
   "não havia o que ver".

Os testes abaixo são os seis cenários que o contrato exige, e os dois primeiros
existem exatamente porque a geração anterior os reprovava.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "wait_for_do_deployment.py"
_spec = importlib.util.spec_from_file_location("wait_for_do_deployment", SCRIPT)
wait_for_do = importlib.util.module_from_spec(_spec)
sys.modules["wait_for_do_deployment"] = wait_for_do
_spec.loader.exec_module(wait_for_do)

ANTERIOR = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
ATUAL = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
OUTRO = "sha256:3333333333333333333333333333333333333333333333333333333333333333"


def dep(dep_id: str, phase: str, digest: str | None, created: str = "2026-09-08T18:00:00Z") -> dict:
    d = {"id": dep_id, "phase": phase, "created_at": created}
    if digest:
        d["cause_details"] = {
            "type": "DEPLOY_ON_PUSH",
            "docr_push": {"tag": "web", "image_digest": digest},
        }
    return d


# ---------------------------------------------------------------------------
# (a) deployment anterior ACTIVE + o atual ainda ausente
# ---------------------------------------------------------------------------


def test_deployment_anterior_active_nao_satisfaz_o_run_atual():
    """O falso verde da 2ª geração: a folga de 120s deixava o anterior entrar.

    Aqui ele é ACTIVE, é o mais recente, e ainda assim NÃO conta — o digest é
    de outro build.
    """
    deployments = [dep("ant", "ACTIVE", ANTERIOR, "2026-09-08T18:05:00Z")]
    estado, achado = wait_for_do.classify(deployments, {ATUAL})
    assert estado == "AUSENTE"
    assert achado is None


def test_o_anterior_nao_conta_nem_sendo_o_unico_active():
    deployments = [
        dep("ant", "ACTIVE", ANTERIOR),
        dep("atual", "DEPLOYING", ATUAL),
    ]
    estado, achado = wait_for_do.classify(deployments, {ATUAL})
    assert estado == "EM_CURSO"
    assert achado["id"] == "atual"


# ---------------------------------------------------------------------------
# (b) deployment esperado que nunca aparece
# ---------------------------------------------------------------------------


def test_publicacao_esperada_sem_deployment_e_ausente_nao_sucesso():
    estado, _ = wait_for_do.classify([dep("ant", "ACTIVE", ANTERIOR)], {ATUAL})
    assert estado == "AUSENTE"


def test_manifesto_com_componente_exige_deployment(tmp_path, monkeypatch, capsys):
    """Teto esgotado com componente publicado tem de REPROVAR, não presumir."""
    manifesto = tmp_path / "published.json"
    manifesto.write_text(json.dumps({
        "sha": "abc", "components": [{"tag": "web", "digest": ATUAL}],
    }))
    monkeypatch.setenv("DO_TOKEN", "t")
    monkeypatch.setattr(wait_for_do, "_get", lambda path, token: (
        {"apps": [{"id": "app1", "spec": {"name": "shopman-alpha"}}]}
        if path.startswith("/apps?") else {"deployments": [dep("ant", "ACTIVE", ANTERIOR)]}
    ))
    code = wait_for_do.main([
        "--app-name", "shopman-alpha", "--manifest", str(manifesto),
        "--max-seconds", "0", "--interval", "0",
    ])
    assert code == 1
    assert "NÃO está com o que subiu" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# (c) push somente documental — determinístico, não "provavelmente"
# ---------------------------------------------------------------------------


def test_push_documental_pula_a_espera_na_hora(tmp_path, monkeypatch, capsys):
    manifesto = tmp_path / "published.json"
    manifesto.write_text(json.dumps({"sha": "abc", "components": []}))
    monkeypatch.setenv("DO_TOKEN", "t")
    monkeypatch.setattr(wait_for_do, "_get", lambda path, token: (
        {"apps": [{"id": "app1", "spec": {"name": "shopman-alpha"}}]}
    ))
    chamou = []
    monkeypatch.setattr(wait_for_do.time, "sleep", lambda s: chamou.append(s))
    code = wait_for_do.main([
        "--app-name", "shopman-alpha", "--manifest", str(manifesto),
    ])
    assert code == 0
    assert chamou == [], "não pode dormir um segundo sequer"
    assert "não publicou componente nenhum" in capsys.readouterr().out


def test_manifesto_ilegivel_nao_vira_push_documental(tmp_path, monkeypatch, capsys):
    """Upload perdido e 'nada publicado' não podem terminar iguais."""
    manifesto = tmp_path / "published.json"
    manifesto.write_text("{isto não é json")
    monkeypatch.setenv("DO_TOKEN", "t")
    monkeypatch.setattr(wait_for_do, "_get", lambda path, token: (
        {"apps": [{"id": "app1", "spec": {"name": "shopman-alpha"}}]}
    ))
    code = wait_for_do.main([
        "--app-name", "shopman-alpha", "--manifest", str(manifesto),
    ])
    assert code == 2
    assert "ilegível" in capsys.readouterr().err


def test_manifesto_ausente_fora_do_probe_e_erro(monkeypatch, capsys):
    monkeypatch.setenv("DO_TOKEN", "t")
    monkeypatch.setattr(wait_for_do, "_get", lambda path, token: (
        {"apps": [{"id": "app1", "spec": {"name": "shopman-alpha"}}]}
    ))
    code = wait_for_do.main(["--app-name", "shopman-alpha"])
    assert code == 2
    assert "voltaria a adivinhar" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# (d) PENDING_BUILD → DEPLOYING → ACTIVE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fase", ["PENDING_BUILD", "BUILDING", "PENDING_DEPLOY", "DEPLOYING"])
def test_fases_intermediarias_seguem_esperando(fase):
    estado, achado = wait_for_do.classify([dep("atual", fase, ATUAL)], {ATUAL})
    assert estado == "EM_CURSO"
    assert achado["id"] == "atual"


def test_active_do_run_atual_solta():
    estado, achado = wait_for_do.classify([dep("atual", "ACTIVE", ATUAL)], {ATUAL})
    assert estado == "ACTIVE"
    assert achado["id"] == "atual"


# ---------------------------------------------------------------------------
# (e) dois deploys consecutivos
# ---------------------------------------------------------------------------


def test_dois_deploys_consecutivos_nao_se_confundem():
    """Run 1 publicou ANTERIOR; run 2 publicou ATUAL. Cada um vê o seu."""
    deployments = [
        dep("d2", "DEPLOYING", ATUAL, "2026-09-08T18:10:00Z"),
        dep("d1", "ACTIVE", ANTERIOR, "2026-09-08T18:05:00Z"),
    ]
    assert wait_for_do.classify(deployments, {ANTERIOR})[1]["id"] == "d1"
    assert wait_for_do.classify(deployments, {ATUAL})[1]["id"] == "d2"


def test_run_com_varios_componentes_aceita_qualquer_um_deles():
    """Vários componentes geram vários deployments; um ACTIVE nosso basta."""
    deployments = [
        dep("d2", "ACTIVE", ATUAL),
        dep("d1", "SUPERSEDED", OUTRO),
    ]
    estado, achado = wait_for_do.classify(deployments, {ATUAL, OUTRO})
    assert estado == "ACTIVE"
    assert achado["id"] == "d2"


# ---------------------------------------------------------------------------
# (f) ERROR / CANCELED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fase", ["ERROR", "CANCELED"])
def test_deployment_do_run_que_falha_reprova(fase):
    estado, achado = wait_for_do.classify([dep("atual", fase, ATUAL)], {ATUAL})
    assert estado == "FAILED"
    assert achado["id"] == "atual"


def test_falha_do_anterior_nao_reprova_o_run_atual():
    """Reprovar por causa do deployment de outro run seria vermelho mentiroso."""
    estado, _ = wait_for_do.classify([dep("ant", "ERROR", ANTERIOR)], {ATUAL})
    assert estado == "AUSENTE"


# ---------------------------------------------------------------------------
# Correlação e manifesto
# ---------------------------------------------------------------------------


def test_digest_sai_de_cause_details():
    assert wait_for_do.deployment_digest(dep("x", "ACTIVE", ATUAL)) == ATUAL


def test_deployment_sem_cause_details_nao_correlaciona():
    """Deployment feito à mão no painel não pertence a run nenhum."""
    assert wait_for_do.deployment_digest({"id": "manual", "phase": "ACTIVE"}) is None
    assert wait_for_do.classify([{"id": "manual", "phase": "ACTIVE"}], {ATUAL})[0] == "AUSENTE"


def test_componente_sem_digest_reprova_o_manifesto(tmp_path):
    manifesto = tmp_path / "published.json"
    manifesto.write_text(json.dumps({"components": [{"tag": "web"}]}))
    with pytest.raises(ValueError, match="sem digest"):
        wait_for_do.load_manifest(manifesto)


def test_app_id_por_nome_do_spec():
    apps = [
        {"id": "outro", "spec": {"name": "shopman-prod"}},
        {"id": "certo", "spec": {"name": "shopman-alpha"}},
    ]
    assert wait_for_do.find_app_id(apps, "shopman-alpha") == "certo"
    assert wait_for_do.find_app_id(apps, "inexistente") is None


def test_sem_token_para_e_diz_por_que(monkeypatch, capsys):
    monkeypatch.delenv("DO_TOKEN", raising=False)
    assert wait_for_do.main(["--app-name", "shopman-alpha", "--probe"]) == 2
    assert "DIGITALOCEAN_ACCESS_TOKEN ausente" in capsys.readouterr().err


def test_o_script_nao_tem_mais_folga_de_relogio():
    """A folga de 120s era a porta do falso verde; não pode voltar como código."""
    assert not hasattr(wait_for_do, "CLOCK_SKEW_SECONDS")
    assert not hasattr(wait_for_do, "newest_since")
    assert not hasattr(wait_for_do, "_epoch")


def test_data_nao_influencia_a_escolha():
    """O teste comportamental: o anterior é o MAIS NOVO e ainda assim perde.

    Qualquer volta a "o mais recente desde X" reprova aqui, sem depender de o
    código citar `created_at` — citar é permitido, decidir por isso não é.
    """
    deployments = [
        dep("ant", "ACTIVE", ANTERIOR, "2026-09-08T23:59:00Z"),
        dep("atual", "ACTIVE", ATUAL, "2026-09-08T00:00:01Z"),
    ]
    estado, achado = wait_for_do.classify(deployments, {ATUAL})
    assert estado == "ACTIVE"
    assert achado["id"] == "atual", "escolheu por data, não por digest"
