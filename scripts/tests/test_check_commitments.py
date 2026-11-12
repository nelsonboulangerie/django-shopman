from __future__ import annotations

import datetime as dt
from pathlib import Path

from scripts import check_commitments as guard

TODAY = dt.date(2026, 11, 12)


def _repo(tmp_path: Path, rows: list[str] | None = None) -> Path:
    docs = tmp_path / "docs/coordination"
    docs.mkdir(parents=True)
    body = "\n".join(rows or [])
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


def _entries(root: Path) -> list[guard.Entry]:
    entries, errors = guard.load_ledger(root)
    assert errors == []
    return entries


def test_ledger_valido(tmp_path: Path):
    root = _repo(tmp_path, [_row()])

    assert guard.validate(_entries(root), TODAY) == []


def test_rejeita_id_duplicado(tmp_path: Path):
    root = _repo(tmp_path, [_row(), _row(compromisso="outro item verificável")])

    errors = guard.validate(_entries(root), TODAY)

    assert any("id duplicado" in error for error in errors)


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


def test_pr_novo_sem_pedido_reprova():
    errors = guard.check_pr_body(
        "## O que muda\n\nnada\n", [], created=dt.date(2026, 11, 13)
    )

    assert any("sem a linha 'Pedido:" in error for error in errors)


def test_pr_novo_com_pedido_conhecido_passa():
    entry = _entry(_row())

    errors = guard.check_pr_body(
        "## Pedido\n\nPedido: DEV-2026-001\n",
        [entry],
        created=dt.date(2026, 11, 13),
    )

    assert errors == []


def test_pr_antigo_nao_exige_pedido():
    errors = guard.check_pr_body(
        "## O que muda\n\nnada\n", [], created=dt.date(2026, 11, 12)
    )

    assert errors == []


def test_pr_de_bot_nao_exige_pedido():
    errors = guard.check_pr_body(
        "## O que muda\n\nbump\n", [], created=dt.date(2026, 11, 13), author="app/dependabot"
    )

    assert errors == []


def test_next_id_e_append(tmp_path: Path):
    root = _repo(tmp_path, [_row()])

    entry = guard.append_entry(
        root,
        quote="o dono pediu para corrigir o fluxo",
        tipo="pedido",
        dono="Engenharia",
        origem="chat 2026-11-12",
        revisar_em="2026-11-19",
    )

    assert entry.id == "DEV-2026-002"
    entries, errors = guard.load_ledger(root)
    assert errors == []
    assert entries[-1].compromisso == "o dono pediu para corrigir o fluxo"
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


def test_pedido_com_issue_conhecida_passa():
    errors = guard.check_pr_body(
        "## Pedido\n\nPedido: #2300\n",
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
