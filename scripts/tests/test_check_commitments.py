from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from scripts import check_commitments as guard

TODAY = dt.date(2026, 11, 12)


def _row(
    id: str = "DEV-2026-001",
    tipo: str = "compromisso",
    origem: str = "#1",
    compromisso: str = "corrigir o fluxo de encomenda",
    dono: str = "Engenharia",
    criado: str = "2026-11-01",
    revisar: str = "2026-11-30",
    gatilho: str = "-",
    estado: str = "ABERTO",
    prova: str = "-",
) -> str:
    return (
        f"| {id} | {tipo} | {origem} | {compromisso} | {dono} | {criado} | "
        f"{revisar} | {gatilho} | {estado} | {prova} |"
    )


def _entry(row: str) -> guard.Entry:
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    return guard.Entry(**dict(zip(guard.COLUMNS, cells, strict=True)))


def _repo(tmp_path: Path, rows: list[str] | None = None) -> Path:
    """Repo com um arquivo por entrada (o ledger de verdade)."""
    directory = tmp_path / guard.LEDGER_DIR
    directory.mkdir(parents=True)
    for row in rows or []:
        entry = _entry(row)
        (directory / f"{entry.id}.json").write_text(guard.entry_json(entry), encoding="utf-8")
    return tmp_path


def _legacy(tmp_path: Path, rows: list[str]) -> Path:
    """DEPRECATED(remove by 2026-11-25): a tabela congelada da transição."""
    docs = tmp_path / "docs/coordination"
    docs.mkdir(parents=True, exist_ok=True)
    body = "\n".join(rows)
    (docs / "COMMITMENTS.md").write_text(
        "# COMMITMENTS\n\n"
        f"{guard.START}\n"
        "| id | tipo | origem | compromisso | dono | criado | revisar_em | gatilho | estado | prova |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
        f"{body}\n"
        f"{guard.END}\n",
        encoding="utf-8",
    )
    return tmp_path


def _entries(root: Path) -> list[guard.Entry]:
    entries, errors = guard.load_ledger(root)
    assert errors == []
    return entries


def test_ledger_valido(tmp_path: Path):
    root = _repo(tmp_path, [_row()])

    assert guard.validate(_entries(root), TODAY) == []


def test_rejeita_id_com_dois_compromissos(tmp_path: Path):
    root = _repo(tmp_path, [_row()])
    _legacy(root, [_row(compromisso="outro item verificável")])

    _, errors = guard.load_ledger(root)

    assert any("o mesmo ID tem um compromisso no arquivo e outro" in e for e in errors)


def test_rejeita_id_duplicado_na_tabela_congelada(tmp_path: Path):
    (tmp_path / guard.LEDGER_DIR).mkdir(parents=True)
    _legacy(tmp_path, [_row(), _row(compromisso="outro item verificável")])

    entries, errors = guard.load_ledger(tmp_path)

    assert errors == []
    assert any("id duplicado" in error for error in guard.validate(entries, TODAY))


def test_rejeita_aberto_sem_revisar(tmp_path: Path):
    root = _repo(tmp_path, [_row(revisar="-")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("sem revisar_em" in error for error in errors)


def test_rejeita_feito_sem_prova(tmp_path: Path):
    root = _repo(tmp_path, [_row(estado="FEITO", prova="-")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("FEITO exige prova" in error for error in errors)


def test_rejeita_descartado_sem_motivo(tmp_path: Path):
    root = _repo(tmp_path, [_row(estado="DESCARTADO", prova="")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("DESCARTADO exige prova" in error for error in errors)


def test_rejeita_supersedido_sem_sucessor(tmp_path: Path):
    root = _repo(tmp_path, [_row(estado="SUPERSEDIDO", prova="substituído")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("SUPERSEDIDO exige o ID" in error for error in errors)


def test_rejeita_estado_fora_do_vocabulario(tmp_path: Path):
    root = _repo(tmp_path, [_row(estado="SUPERADA")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("estado 'SUPERADA'" in error for error in errors)


def test_rejeita_dono_vazio(tmp_path: Path):
    root = _repo(tmp_path, [_row(dono="ninguém")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("dono não nomeado" in error for error in errors)


def test_vencido_e_terminal_nao_vencem(tmp_path: Path):
    root = _repo(
        tmp_path,
        [
            _row(revisar="2026-11-10"),
            _row(id="DEV-2026-002", revisar="2026-11-10", estado="FEITO", prova="#99"),
        ],
    )

    expired = guard.overdue(_entries(root), TODAY)

    assert [entry.id for entry in expired] == ["DEV-2026-001"]


def test_pr_novo_sem_compromisso_reprova():
    errors = guard.check_pr_body(
        "## O que muda\n\nnada\n", [], created=dt.date(2026, 11, 13)
    )

    assert any("sem a linha 'Compromisso:" in error for error in errors)


def test_pr_novo_com_compromisso_conhecido_passa():
    entry = _entry(_row())

    errors = guard.check_pr_body(
        "## Compromisso\n\nCompromisso: DEV-2026-001\n",
        [entry],
        created=dt.date(2026, 11, 13),
    )

    assert errors == []


def test_pr_antigo_nao_exige_compromisso():
    errors = guard.check_pr_body(
        "## O que muda\n\nnada\n", [], created=dt.date(2026, 11, 12)
    )

    assert errors == []


def test_pr_de_bot_nao_exige_compromisso():
    errors = guard.check_pr_body(
        "## O que muda\n\nbump\n", [], created=dt.date(2026, 11, 13), author="app/dependabot"
    )

    assert errors == []


def test_next_id_e_append(tmp_path: Path):
    root = _repo(tmp_path, [_row()])

    entry = guard.append_entry(
        root,
        quote="o dono pediu para corrigir o fluxo",
        tipo="solicitacao",
        dono="Engenharia",
        origem="chat 2026-11-12",
        revisar_em="2099-01-01",
    )

    assert entry.id == f"DEV-{dt.date.today().year}-" + (
        "002" if dt.date.today().year == 2026 else "001"
    )
    assert (root / guard.LEDGER_DIR / f"{entry.id}.json").exists()
    entries, errors = guard.load_ledger(root)
    assert errors == []
    assert "o dono pediu para corrigir o fluxo" in {e.compromisso for e in entries}
    assert guard.validate(entries, TODAY) == []


def test_decisoes_legadas_vencidas(tmp_path: Path):
    docs = tmp_path / "docs/coordination"
    docs.mkdir(parents=True)
    (docs / "DECISIONS.md").write_text(
        "# DECISIONS\n\n"
        "## D-004 · Sessão de PDV compartilhada\n\n"
        "- **Estado:** `EM_EXECUCAO`\n"
        "- **Dono:** Pablo (produto)\n"
        "- **Data:** 2026-09-29 · **revisar_em:** 2026-10-15\n",
        encoding="utf-8",
    )

    found = guard.legacy_overdue(tmp_path, TODAY)

    assert [item["id"] for item in found] == ["D-004"]


def test_compromisso_com_issue_conhecida_passa():
    errors = guard.check_pr_body(
        "## Compromisso\n\nCompromisso: #2300\n",
        [],
        created=dt.date(2026, 11, 13),
        known_issues={2300},
    )

    assert errors == []


def test_issue_sem_linha_no_ledger(tmp_path: Path):
    root = _repo(tmp_path, [_row(origem="#2298")])
    issues = [{"number": 2304, "title": "preparo no Catálogo", "createdAt": "2026-11-12", "url": ""}]

    assert [issue["number"] for issue in guard.orphan_issues(root, issues)] == [2304]


def test_issue_citada_na_linha_nao_e_orfa(tmp_path: Path):
    root = _repo(tmp_path, [_row(origem="#2303 / #2304")])
    issues = [{"number": 2304, "title": "preparo no Catálogo", "createdAt": "2026-11-12", "url": ""}]

    assert guard.orphan_issues(root, issues) == []


# ── Um arquivo por entrada: o que tirou o conflito da fila ─────────────


def test_append_nao_toca_arquivo_existente(tmp_path: Path):
    """Dois intakes criam dois arquivos novos; nenhum arquivo existente muda."""
    root = _repo(tmp_path, [_row()])
    directory = root / guard.LEDGER_DIR
    before = {path.name: path.read_text() for path in directory.iterdir()}

    first = guard.append_entry(
        root, quote="primeira fala do dono", tipo="solicitacao", dono="Engenharia",
        origem="chat", revisar_em="2099-01-01",
    )
    second = guard.append_entry(
        root, quote="segunda fala do dono", tipo="solicitacao", dono="Engenharia",
        origem="chat", revisar_em="2099-01-01",
    )

    after = {path.name: path.read_text() for path in directory.iterdir()}
    assert first.id != second.id
    assert {name: after[name] for name in before} == before
    assert set(after) - set(before) == {f"{first.id}.json", f"{second.id}.json"}


def test_next_id_pula_os_ids_em_voo():
    entry = _entry(_row(id="DEV-2026-050"))

    assert guard.next_id([entry], 2026) == "DEV-2026-051"
    assert guard.next_id([entry], 2026, {"DEV-2026-051", "DEV-2026-053"}) == "DEV-2026-054"


def test_arquivo_com_id_diferente_do_nome_reprova(tmp_path: Path):
    directory = tmp_path / guard.LEDGER_DIR
    directory.mkdir(parents=True)
    (directory / "DEV-2026-009.json").write_text(
        guard.entry_json(_entry(_row(id="DEV-2026-001"))), encoding="utf-8"
    )

    _, errors = guard.load_ledger(tmp_path)

    assert any("diferente do nome do arquivo" in error for error in errors)


def test_arquivo_com_campo_faltando_reprova(tmp_path: Path):
    directory = tmp_path / guard.LEDGER_DIR
    directory.mkdir(parents=True)
    (directory / "DEV-2026-001.json").write_text('{"id": "DEV-2026-001"}', encoding="utf-8")

    _, errors = guard.load_ledger(tmp_path)

    assert any("faltam campos" in error for error in errors)


def test_write_entry_nunca_sobrescreve(tmp_path: Path):
    root = _repo(tmp_path, [_row()])

    with pytest.raises(FileExistsError):
        guard.write_entry(root, _entry(_row(compromisso="outra coisa verificável")))


def test_indice_e_gerado_ordenado(tmp_path: Path):
    root = _repo(tmp_path, [_row(id="DEV-2026-010"), _row(id="DEV-2026-002")])
    entries, _ = guard.load_ledger(root)

    table = guard._report_table(entries)

    assert table.index("DEV-2026-002") < table.index("DEV-2026-010")
    assert table.splitlines()[0].startswith("| id | tipo |")


# ── Transição: tabela congelada. DEPRECATED(remove by 2026-11-25) ─────


def test_linha_antiga_so_na_tabela_ainda_vale(tmp_path: Path):
    """PR aberto antes da migração traz a linha na tabela; o gate a conhece."""
    root = _repo(tmp_path, [_row()])
    _legacy(root, [_row(id="DEV-2026-053", criado="2026-11-18", compromisso="pedido em voo")])

    entries, errors = guard.load_ledger(root)

    assert errors == []
    assert "DEV-2026-053" in {entry.id for entry in entries}
    assert (
        guard.check_pr_body(
            "Compromisso: DEV-2026-053\n", entries, created=dt.date(2026, 11, 18)
        )
        == []
    )
    assert any("DEV-2026-053" in warning for warning in guard.legacy_warnings(root))


def test_tabela_congelada_reprova_linha_nova(tmp_path: Path):
    root = _repo(tmp_path, [_row()])
    _legacy(root, [_row(id="DEV-2026-060", criado="2026-11-19", revisar="2026-11-26")])

    _, errors = guard.load_ledger(root)

    assert any("congelado" in error for error in errors)


def test_copia_da_migracao_nao_duplica(tmp_path: Path):
    root = _repo(tmp_path, [_row()])
    _legacy(root, [_row()])

    entries, errors = guard.load_ledger(root)

    assert errors == []
    assert [entry.id for entry in entries] == ["DEV-2026-001"]
    assert guard.validate(entries, TODAY) == []
    assert guard.legacy_warnings(root) == []


def test_tabela_que_mudou_o_estado_vira_aviso(tmp_path: Path):
    root = _repo(tmp_path, [_row()])
    _legacy(root, [_row(estado="FEITO", prova="#2600")])

    entries, errors = guard.load_ledger(root)

    assert errors == []
    assert entries[0].estado == "ABERTO"  # vale o arquivo
    assert any(
        "estado" in warning and "prova" in warning for warning in guard.legacy_warnings(root)
    )


def test_migracao_e_sem_perda(tmp_path: Path):
    (tmp_path / guard.LEDGER_DIR).mkdir(parents=True)
    rows = [
        _row(),
        _row(id="DEV-2026-002", compromisso="fala com 'aspas', acentuação e (parênteses)"),
    ]
    _legacy(tmp_path, rows)
    legacy, _ = guard.load_legacy_table(tmp_path)

    created = guard.migrate_legacy(tmp_path)
    files, errors = guard.load_entry_files(tmp_path)

    assert created == ["DEV-2026-001", "DEV-2026-002"]
    assert errors == []
    assert files == legacy
    assert guard.migrate_legacy(tmp_path) == []  # idempotente


def test_migracao_recusa_id_repetido(tmp_path: Path):
    (tmp_path / guard.LEDGER_DIR).mkdir(parents=True)
    _legacy(tmp_path, [_row(), _row(compromisso="outro item verificável")])

    with pytest.raises(SystemExit, match="DEV-2026-001"):
        guard.migrate_legacy(tmp_path)


# ── IDs em voo ────────────────────────────────────────────────────────


class _Done:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def test_intake_falha_alto_sem_gh(tmp_path: Path):
    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            raise FileNotFoundError("gh")
        return _Done()

    with pytest.raises(guard.InflightError, match="gh"):
        guard.inflight_ids(tmp_path, run=run)


def test_intake_falha_alto_quando_gh_falha(tmp_path: Path):
    def run(cmd, **kwargs):
        if cmd[0] == "gh":
            return _Done(1, stderr="could not resolve host")
        return _Done()

    with pytest.raises(guard.InflightError, match="could not resolve host"):
        guard.inflight_ids(tmp_path, run=run)


def test_main_sem_gh_sai_2_e_nao_cria_arquivo(tmp_path: Path, monkeypatch):
    root = _repo(tmp_path, [_row()])

    def boom(root, *, offline=False, run=None):
        raise guard.InflightError("gh não encontrado")

    monkeypatch.setattr(guard, "inflight_ids", boom)

    code = guard.main(["--root", str(root), "--add", "--quote", "fala do dono aqui"])

    assert code == 2
    assert [path.name for path in (root / guard.LEDGER_DIR).iterdir()] == ["DEV-2026-001.json"]


def test_ids_em_voo_saem_dos_arquivos_e_da_tabela_de_cada_ref(tmp_path: Path):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "gh":
            return _Done(stdout="claude/a\nclaude/b\n")
        if "for-each-ref" in cmd:
            return _Done(stdout="refs/heads/rascunho\n")
        if "grep" in cmd and str(guard.LEDGER_DIR) in cmd:
            return _Done(
                stdout=(
                    "refs/remotes/origin/claude/a:docs/coordination/commitments/"
                    'DEV-2026-055.json:  "id": "DEV-2026-055",\n'
                )
            )
        if "grep" in cmd:
            return _Done(
                stdout=(
                    "refs/remotes/origin/claude/b:docs/coordination/COMMITMENTS.md:"
                    "| DEV-2026-051 | solicitacao | chat | x | Eng | 2026-11-18 |\n"
                    "refs/heads/rascunho:docs/coordination/COMMITMENTS.md:"
                    "texto que cita | DEV-2026-099 | fora de linha de tabela\n"
                )
            )
        return _Done()

    ids = guard.inflight_ids(tmp_path, run=run)

    assert ids == {"DEV-2026-055", "DEV-2026-051"}
    fetch = next(cmd for cmd in calls if "fetch" in cmd)
    assert "+refs/heads/claude/a:refs/remotes/origin/claude/a" in fetch
    assert "+refs/heads/main:refs/remotes/origin/main" in fetch
    greps = [cmd for cmd in calls if "grep" in cmd]
    assert len(greps) == 2  # todas as refs numa chamada só, por caminho
    assert "refs/heads/rascunho" in greps[0]


def test_offline_nao_chama_gh(tmp_path: Path):
    def run(cmd, **kwargs):
        assert cmd[0] != "gh", "offline não consulta PRs"
        return _Done()

    assert guard.inflight_ids(tmp_path, offline=True, run=run) == set()
