"""A trava de backup antes do `migrate` — a política roda como código.

Cobre as três decisões que o job `release` toma antes de migrar o banco real:

- a política do ADR-015 está armada? (env explícita > tag no repositório);
- a migração pendente é destrutiva?
- há ponto de restauração declarado?

E o comportamento fechado: portão que não enxerga o plano recusa; placeholder
no lugar do ponto de restauração não conta como declaração.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.db import migrations, models

from shopman.shop import migration_safety

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_adr015.py"
_spec = importlib.util.spec_from_file_location("check_adr015_parity", _SCRIPT)
check_adr015 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_adr015)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Nenhum teste herda o ambiente de quem rodou a suíte."""
    for name in ("SHOPMAN_ADR015_FORCE", "SHOPMAN_GO_LIVE", migration_safety.BACKUP_REF_ENV):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Paridade com o gate irmão
# ---------------------------------------------------------------------------


def test_lista_destrutiva_igual_a_do_gate_adr015():
    """Duas travas, uma definição. Se uma andar sozinha, este teste reprova."""
    assert migration_safety.DESTRUCTIVE_OPERATION_NAMES == check_adr015.DESTRUCTIVE_OPERATIONS
    assert migration_safety.GO_LIVE_TAG == check_adr015.GO_LIVE_TAG


# ---------------------------------------------------------------------------
# Armar a política
# ---------------------------------------------------------------------------


def test_force_arma_a_politica(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADR015_FORCE", "1")
    armed, reason = migration_safety.go_live_active()
    assert armed is True
    assert "SHOPMAN_ADR015_FORCE" in reason


def test_force_desarma_mesmo_com_go_live_declarada(monkeypatch):
    monkeypatch.setenv("SHOPMAN_ADR015_FORCE", "0")
    monkeypatch.setenv("SHOPMAN_GO_LIVE", "true")
    armed, _ = migration_safety.go_live_active()
    assert armed is False


def test_go_live_env_arma_sem_git(monkeypatch):
    """O contêiner do app não carrega o .git — quem responde lá é a env."""
    monkeypatch.setenv("SHOPMAN_GO_LIVE", "true")
    monkeypatch.setattr(migration_safety, "_git_tag_present", lambda *_a, **_k: False)
    armed, reason = migration_safety.go_live_active()
    assert armed is True
    assert "SHOPMAN_GO_LIVE" in reason


def test_sem_env_e_sem_tag_a_politica_fica_inativa(monkeypatch):
    monkeypatch.setattr(migration_safety, "_git_tag_present", lambda *_a, **_k: False)
    armed, reason = migration_safety.go_live_active()
    assert armed is False
    assert migration_safety.GO_LIVE_TAG in reason


def test_tag_presente_arma_a_politica(monkeypatch):
    monkeypatch.setattr(migration_safety, "_git_tag_present", lambda *_a, **_k: True)
    armed, reason = migration_safety.go_live_active()
    assert armed is True
    assert migration_safety.GO_LIVE_TAG in reason


# ---------------------------------------------------------------------------
# Ponto de restauração declarado
# ---------------------------------------------------------------------------


def test_ponto_de_restauracao_declarado(monkeypatch):
    monkeypatch.setenv(migration_safety.BACKUP_REF_ENV, " PITR 2026-09-23T14:05:00Z ")
    assert migration_safety.backup_reference() == "PITR 2026-09-23T14:05:00Z"


@pytest.mark.parametrize("placeholder", ["", "   ", "-", "n/a", "TBD", "none"])
def test_placeholder_nao_conta_como_declaracao(monkeypatch, placeholder):
    monkeypatch.setenv(migration_safety.BACKUP_REF_ENV, placeholder)
    assert migration_safety.backup_reference() == ""


# ---------------------------------------------------------------------------
# Leitura das operações
# ---------------------------------------------------------------------------


def _migration(*operations):
    migration = migrations.Migration("0002_teste", "shop")
    migration.operations = list(operations)
    return migration


def test_operacoes_destrutivas_sao_reconhecidas():
    migration = _migration(
        migrations.RemoveField("order", "note"),
        migrations.AlterField("order", "total_q", models.IntegerField(default=0)),
        migrations.AddField("order", "observation", models.TextField(blank=True, default="")),
    )
    assert migration_safety.destructive_operation_names(migration) == ["AlterField", "RemoveField"]


def test_migracao_aditiva_nao_tem_operacao_destrutiva():
    migration = _migration(
        migrations.AddField("order", "observation", models.TextField(blank=True, default="")),
        migrations.AddIndex("order", models.Index(fields=["ref"], name="idx_order_ref")),
    )
    assert migration_safety.destructive_operation_names(migration) == []


# ---------------------------------------------------------------------------
# A decisão
# ---------------------------------------------------------------------------


def _report(**kwargs):
    defaults = {
        "pending": (
            migration_safety.PendingMigration("shop", "0002_teste", ("RemoveField",)),
        ),
        "go_live": True,
        "go_live_reason": "teste",
        "backup_ref": "",
    }
    defaults.update(kwargs)
    return migration_safety.SafetyReport(**defaults)


def test_armada_destrutiva_sem_backup_recusa():
    report = _report()
    assert report.blocking is True
    assert report.status == "blocked"
    assert migration_safety.BACKUP_REF_ENV in "\n".join(migration_safety.human_lines(report))


def test_armada_destrutiva_com_backup_declarado_passa():
    report = _report(backup_ref="PITR 2026-09-23T14:05:00Z")
    assert report.blocking is False
    assert "PITR 2026-09-23T14:05:00Z" in "\n".join(migration_safety.human_lines(report))


def test_armada_so_com_migracao_aditiva_passa():
    report = _report(pending=(migration_safety.PendingMigration("shop", "0002_teste", ()),))
    assert report.blocking is False


def test_pre_go_live_relata_mas_nao_segura():
    """Antes da tag a política não vale — e a trava diz isso, em vez de fingir."""
    report = _report(go_live=False, go_live_reason="tag ausente")
    assert report.blocking is False
    texto = "\n".join(migration_safety.human_lines(report))
    assert "pré-go-live" in texto
    assert "DESTRUTIVA" in texto


def test_portao_cego_recusa_mesmo_pre_go_live():
    """Não conseguir ler o plano nunca pode ser lido como 'nada pendente'."""
    report = _report(pending=(), go_live=False, error="OperationalError: conexão recusada")
    assert report.blocking is True
    assert "não foi possível ler o plano" in "\n".join(migration_safety.human_lines(report))


def test_relato_lista_toda_destrutiva_e_resume_a_cauda_aditiva():
    """Banco vazio tem centenas de aditivas; elas não podem afogar a destrutiva."""
    pending = [
        migration_safety.PendingMigration("shop", f"{i:04d}_aditiva", ())
        for i in range(migration_safety.ADDITIVE_LIST_LIMIT + 40)
    ]
    pending.append(migration_safety.PendingMigration("shop", "9999_contract", ("RemoveField",)))
    texto = "\n".join(migration_safety.human_lines(_report(pending=tuple(pending))))
    assert "shop.9999_contract (RemoveField)" in texto
    assert "… e mais 40 aditiva(s), não listadas." in texto
    assert texto.count("[aditiva   ]") == migration_safety.ADDITIVE_LIST_LIMIT


def test_json_do_relatorio_nomeia_a_migracao_destrutiva():
    data = _report().as_dict()
    assert data["status"] == "blocked"
    assert data["destructive_count"] == 1
    assert data["backup_ref_declared"] is False
    assert data["pending"][0]["migration"] == "shop.0002_teste"
    assert data["pending"][0]["operations"] == ["RemoveField"]


# ---------------------------------------------------------------------------
# O comando
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_comando_passa_com_o_banco_em_dia(capsys):
    """Banco de teste = grafo inteiro aplicado: nada pendente, nada a segurar."""
    call_command("migration_safety")
    saida = capsys.readouterr().out
    assert "migration-safety: clear" in saida
    assert "0 migração(ões) pendente(s)" in saida


@pytest.mark.django_db
def test_comando_json_e_legivel_por_maquina(capsys):
    call_command("migration_safety", "--json")
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "clear"
    assert data["pending_count"] == 0


@pytest.mark.django_db
def test_comando_recusa_quando_a_trava_recusa(monkeypatch):
    monkeypatch.setattr(migration_safety, "build_report", lambda **_kwargs: _report())
    with pytest.raises(CommandError) as exc:
        call_command("migration_safety")
    assert "backup-e-restore" in str(exc.value)


@pytest.mark.django_db
def test_modo_report_nunca_recusa(monkeypatch, capsys):
    monkeypatch.setattr(migration_safety, "build_report", lambda **_kwargs: _report())
    call_command("migration_safety", "--report")
    assert "migration-safety: blocked" in capsys.readouterr().out


@pytest.mark.django_db
def test_conexao_inexistente_e_erro_de_uso():
    with pytest.raises(CommandError, match="não existe"):
        call_command("migration_safety", "--database", "inexistente")
