#!/usr/bin/env python3
"""Gate dos compromissos: o que o repo deve tem ID, dono, prazo e prova.

O defeito que isto fecha (medido em 12/11/2026): o #2298 deixou dois itens reais
em "Seguimento (fora deste PR)", sem ID, dono ou data. O merge apaga o endereço
e o item fica invisível para `gh pr list`, para as outras sessões e para o dono.

O ledger é um arquivo por entrada: `docs/coordination/commitments/DEV-AAAA-NNN.json`.
A tabela única de antes (`COMMITMENTS.md`) fazia todo PR escrever a linha no mesmo
lugar, e cada merge deixava os PRs seguintes CONFLICTING (medido em 18/11/2026: oito
PRs saíram da fila num dia). Com um arquivo por ID, dois PRs nunca tocam o mesmo
arquivo. O índice legível não se versiona: sai de `--format table` na hora.

Este script:

1. valida o ledger (ID único, estado conhecido, dono, `revisar_em` para item
   aberto, prova para item terminal);
2. lista o que venceu, incluindo as decisões legadas de `DECISIONS.md`;
3. com `--pr-body`, reprova PR novo sem a linha `Compromisso: DEV-...` (ou
   `Compromisso: #2300`). O gate do que ficou de fora é `check_ficou_de_fora.py`;
   este script não o duplica;
4. com `--add`, registra a fala do dono e devolve o ID para o PR. O ID novo pula
   os que já estão em voo (PRs abertos, branches locais, worktrees); sem `gh`,
   falha em vez de chutar um ID que talvez já tenha dono.

Sem Django e sem dependência externa: roda antes do install.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = Path("docs/coordination/commitments")
# DEPRECATED(remove by 2026-11-25): a tabela única congelada. Os PRs abertos em
# 18/11/2026 ainda trazem linha nela; até a data, o gate lê as linhas que não têm
# arquivo e reprova linha nova (criado a partir de LEGACY_TABLE_FROZEN). A limpeza
# roda `--migrate-legacy`, apaga a tabela e tudo o que tem esta marca.
LEGACY_TABLE = Path("docs/coordination/COMMITMENTS.md")
LEGACY_TABLE_FROZEN = dt.date(2026, 11, 19)
LEGACY = Path("docs/coordination/DECISIONS.md")
START = "<!-- commitments:start -->"
END = "<!-- commitments:end -->"

COLUMNS = (
    "id",
    "tipo",
    "origem",
    "compromisso",
    "dono",
    "criado",
    "revisar_em",
    "gatilho",
    "estado",
    "prova",
)
TYPES = {"solicitacao", "compromisso", "decisao", "achado"}
STATES = {"ABERTO", "EM_EXECUCAO", "BLOQUEADO", "FEITO", "DESCARTADO", "SUPERSEDIDO"}
TERMINAL = {"FEITO", "DESCARTADO", "SUPERSEDIDO"}
EMPTY_OWNERS = {"", "-", "—", "ninguem", "ninguém", "a definir", "tbd", "n/a"}
ID_RE = re.compile(r"^DEV-\d{4}-\d{3}$")
REF_RE = re.compile(r"\bDEV-\d{4}-\d{3}\b")
ISSUE_NUM_RE = re.compile(r"#(\d{3,})")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMMITMENT_LINE_RE = re.compile(
    r"^\s*Compromisso:\s*(?P<value>(?:DEV-\d{4}-\d{3}|#\d{3,})"
    r"(?:\s*,\s*(?:DEV-\d{4}-\d{3}|#\d{3,}))*|nenhum)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
DEFERRAL_WORDS = re.compile(
    r"fora deste pr|fora do escopo|pend[eê]ncia|fica para|ficou para|adiado|"
    r"limita[cç][oõ]es|seguimento|ficou de fora",
    re.IGNORECASE,
)
NO_DEFERRAL_RE = re.compile(
    r"^\s*[-*]\s+(nenhum|nada|n/a|não se aplica)\b", re.IGNORECASE
)

# PRs anteriores a esta data são a migração: o corpo deles não tinha a linha
# `Compromisso:`. A partir dela, PR novo sem compromisso reprova. Remover a data quando a
# migração fechar (não antes: os PRs de 12/11 ainda estão abertos).
COMMITMENT_GATE_START = dt.date(2026, 11, 13)
BOT_LOGINS = {"app/dependabot", "dependabot[bot]"}
ISSUE_LABELS = ("ficou-de-fora", "helpdesk", "dev", "decisao", "achado")


@dataclass(frozen=True)
class Entry:
    id: str
    tipo: str
    origem: str
    compromisso: str
    dono: str
    criado: str
    revisar_em: str
    gatilho: str
    estado: str
    prova: str

    @property
    def terminal(self) -> bool:
        return self.estado in TERMINAL


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _date(value: str) -> dt.date | None:
    if not DATE_RE.match(value or ""):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


# ── Arquivo por entrada ───────────────────────────────────────────────


def parse_entry_file(path: Path) -> tuple[Entry | None, list[str]]:
    """Lê `DEV-AAAA-NNN.json`: um objeto com exatamente as colunas, todas texto."""
    where = f"{LEDGER_DIR.name}/{path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{where}: json inválido ({exc})"]
    if not isinstance(data, dict):
        return None, [f"{where}: esperado um objeto com as colunas"]
    missing = [column for column in COLUMNS if column not in data]
    extra = sorted(set(data) - set(COLUMNS))
    errors: list[str] = []
    if missing:
        errors.append(f"{where}: faltam campos {', '.join(missing)}")
    if extra:
        errors.append(f"{where}: campos desconhecidos {', '.join(extra)}")
    if errors:
        return None, errors
    bad = [column for column in COLUMNS if not isinstance(data[column], str)]
    if bad:
        return None, [f"{where}: campos que não são texto: {', '.join(bad)}"]
    entry = Entry(**{column: data[column] for column in COLUMNS})
    if entry.id != path.stem:
        errors.append(f"{where}: id '{entry.id}' diferente do nome do arquivo")
    return entry, errors


def load_entry_files(root: Path = ROOT) -> tuple[list[Entry], list[str]]:
    directory = root / LEDGER_DIR
    if not directory.is_dir():
        return [], [f"{LEDGER_DIR} não existe"]
    entries: list[Entry] = []
    errors: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith(".") or path.name == "README.md":
            continue
        if path.suffix != ".json":
            errors.append(f"{LEDGER_DIR.name}/{path.name}: aqui só entra DEV-AAAA-NNN.json")
            continue
        entry, entry_errors = parse_entry_file(path)
        errors += entry_errors
        if entry is not None:
            entries.append(entry)
    return entries, errors


def entry_json(entry: Entry) -> str:
    payload = {column: getattr(entry, column) for column in COLUMNS}
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_entry(root: Path, entry: Entry) -> Path:
    directory = root / LEDGER_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{entry.id}.json"
    # "x": nunca sobrescreve. Se o arquivo existe, o ID já tem dono.
    with path.open("x", encoding="utf-8") as handle:
        handle.write(entry_json(entry))
    return path


# ── Tabela congelada (transição) ──────────────────────────────────────


def parse_ledger(text: str) -> tuple[list[Entry], list[str]]:
    """Lê a tabela entre os marcadores. Devolve (entradas, erros de forma)."""
    if START not in text or END not in text:
        return [], [f"ledger sem os marcadores {START} / {END}"]
    body = text.split(START, 1)[1].split(END, 1)[0]
    lines = [line for line in body.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return [], ["ledger sem cabeçalho, separador e linhas"]
    header = _cells(lines[0])
    if tuple(header) != COLUMNS:
        return [], [
            "cabeçalho do ledger divergente: esperado "
            + " | ".join(COLUMNS)
            + ", lido "
            + " | ".join(header)
        ]
    entries: list[Entry] = []
    errors: list[str] = []
    for line in lines[2:]:
        cells = _cells(line)
        if len(cells) != len(COLUMNS):
            errors.append(
                f"linha com {len(cells)} colunas (esperado {len(COLUMNS)}): {line[:90]}"
            )
            continue
        entries.append(Entry(**dict(zip(COLUMNS, cells, strict=True))))
    return entries, errors


# DEPRECATED(remove by 2026-11-25): leitura da tabela congelada.
def load_legacy_table(root: Path = ROOT) -> tuple[list[Entry], list[str]]:
    path = root / LEGACY_TABLE
    if not path.exists():
        return [], []
    text = path.read_text(encoding="utf-8")
    if START not in text and END not in text:
        return [], []
    return parse_ledger(text)


def _same_commitment(a: Entry, b: Entry) -> bool:
    return " ".join(a.compromisso.split()) == " ".join(b.compromisso.split())


def load_ledger(root: Path = ROOT) -> tuple[list[Entry], list[str]]:
    """Arquivos por entrada + linhas da tabela congelada que ainda não têm arquivo.

    O arquivo é a verdade. Linha da tabela com o mesmo ID e o mesmo compromisso é
    a cópia da migração (ou um PR antigo mudando o estado: vira aviso em
    `legacy_warnings`). Mesmo ID com compromisso diferente é colisão: erro.
    """
    files, errors = load_entry_files(root)
    legacy, legacy_errors = load_legacy_table(root)
    errors += [f"{LEGACY_TABLE.name}: {error}" for error in legacy_errors]
    by_id = {entry.id: entry for entry in files}
    merged = list(files)
    for row in legacy:
        current = by_id.get(row.id)
        if current is None:
            created = _date(row.criado)
            if created is not None and created >= LEGACY_TABLE_FROZEN:
                errors.append(
                    f"{row.id}: linha nova no {LEGACY_TABLE.name}, congelado desde "
                    f"{LEGACY_TABLE_FROZEN.isoformat()}; registre com `make intake` "
                    f"(vira {LEDGER_DIR}/{row.id}.json)"
                )
            merged.append(row)
        elif not _same_commitment(current, row):
            errors.append(
                f"{row.id}: o mesmo ID tem um compromisso no arquivo e outro no "
                f"{LEGACY_TABLE.name}; renumere a linha da tabela com `make intake`"
            )
    return merged, errors


# DEPRECATED(remove by 2026-11-25): avisos da transição.
def legacy_warnings(root: Path = ROOT) -> list[str]:
    files, _ = load_entry_files(root)
    legacy, _ = load_legacy_table(root)
    by_id = {entry.id: entry for entry in files}
    warnings: list[str] = []
    pending = [row.id for row in legacy if row.id not in by_id]
    if pending:
        warnings.append(
            f"{len(pending)} linha(s) só no {LEGACY_TABLE.name} congelado "
            f"({', '.join(pending)}); `--migrate-legacy` cria o arquivo de cada uma"
        )
    for row in legacy:
        current = by_id.get(row.id)
        if current is not None and _same_commitment(current, row) and current != row:
            fields = [
                column
                for column in COLUMNS
                if getattr(current, column) != getattr(row, column)
            ]
            warnings.append(
                f"{row.id}: a tabela congelada diverge do arquivo em {', '.join(fields)}; "
                f"vale o arquivo ({LEDGER_DIR}/{row.id}.json), copie a mudança para lá"
            )
    return warnings


# DEPRECATED(remove by 2026-11-25): a migração da tabela para arquivos.
def migrate_legacy(root: Path = ROOT) -> list[str]:
    """Cria o arquivo de cada linha da tabela que ainda não tem. Devolve os IDs."""
    legacy, errors = load_legacy_table(root)
    if errors:
        raise SystemExit("tabela congelada inválida:\n  " + "\n  ".join(errors))
    files, _ = load_entry_files(root)
    existing = {entry.id for entry in files}
    counts: dict[str, int] = {}
    for row in legacy:
        counts[row.id] = counts.get(row.id, 0) + 1
    repeated = sorted(ref for ref, count in counts.items() if count > 1)
    if repeated:
        raise SystemExit(
            "IDs repetidos na tabela; renumere antes de migrar: " + ", ".join(repeated)
        )
    created: list[str] = []
    for row in legacy:
        if row.id in existing:
            continue
        write_entry(root, row)
        created.append(row.id)
    return created


# ── Validação ─────────────────────────────────────────────────────────


def validate(entries: list[Entry], today: dt.date) -> list[str]:
    errors: list[str] = []
    seen: dict[str, Entry] = {}
    ids = {entry.id for entry in entries}
    for entry in entries:
        where = entry.id or entry.compromisso[:40] or "linha sem id"
        if not ID_RE.match(entry.id):
            errors.append(f"{where}: id fora do formato DEV-AAAA-NNN")
        elif entry.id in seen:
            errors.append(f"{entry.id}: id duplicado")
        else:
            seen[entry.id] = entry

        if entry.tipo not in TYPES:
            errors.append(
                f"{where}: tipo '{entry.tipo}' fora do vocabulário "
                f"({', '.join(sorted(TYPES))})"
            )
        if not entry.origem.strip():
            errors.append(f"{where}: origem vazia (PR, doc ou 'chat')")
        if len(entry.compromisso.strip()) < 8:
            errors.append(f"{where}: compromisso curto demais para ser verificável")
        owner = entry.dono.strip().lower()
        if owner in EMPTY_OWNERS or "ninguém" in owner or "ninguem" in owner:
            errors.append(f"{where}: dono não nomeado ('{entry.dono}')")

        created = _date(entry.criado)
        if created is None:
            errors.append(f"{where}: criado '{entry.criado}' não é YYYY-MM-DD")

        if entry.estado not in STATES:
            errors.append(
                f"{where}: estado '{entry.estado}' fora do vocabulário "
                f"({', '.join(sorted(STATES))})"
            )

        review = _date(entry.revisar_em) if entry.revisar_em not in {"", "-"} else None
        if entry.revisar_em not in {"", "-"} and review is None:
            errors.append(f"{where}: revisar_em '{entry.revisar_em}' não é YYYY-MM-DD")
        if entry.estado in {"ABERTO", "EM_EXECUCAO", "BLOQUEADO"} and review is None:
            errors.append(f"{where}: item aberto sem revisar_em (a data é a trava)")
        if review is not None and created is not None and review < created:
            errors.append(f"{where}: revisar_em anterior ao criado")

        if entry.estado in {"FEITO", "DESCARTADO"} and entry.prova.strip() in {"", "-"}:
            errors.append(
                f"{where}: {entry.estado} exige prova (PR, commit ou quem decidiu e por quê)"
            )
        if entry.estado == "SUPERSEDIDO":
            refs = [ref for ref in REF_RE.findall(entry.prova) if ref != entry.id]
            if not refs:
                errors.append(f"{where}: SUPERSEDIDO exige o ID que o substituiu na prova")
            for ref in refs:
                if ref not in ids:
                    errors.append(f"{where}: SUPERSEDIDO aponta {ref}, que não existe")
    return errors


def overdue(entries: list[Entry], today: dt.date) -> list[Entry]:
    found = []
    for entry in entries:
        if entry.terminal:
            continue
        review = _date(entry.revisar_em)
        if review is not None and review < today:
            found.append(entry)
    return sorted(found, key=lambda entry: entry.revisar_em)


def legacy_overdue(root: Path = ROOT, today: dt.date | None = None) -> list[dict[str, str]]:
    """Decisões antigas de DECISIONS.md, só para o relatório. Não valida o legado."""
    today = today or dt.date.today()
    path = root / LEGACY
    if not path.exists():
        return []
    found: list[dict[str, str]] = []
    for block in re.split(r"\n## ", path.read_text(encoding="utf-8"))[1:]:
        title = block.split("\n", 1)[0].strip()
        match = re.match(r"((?:D|B)-\d{3})", title)
        if not match:
            continue
        state = re.search(r"\*\*Estado:\*\*\s*`([A-Z_]+)`", block)
        review = re.search(r"\*\*revisar_em:\*\*\s*(\d{4}-\d{2}-\d{2})", block)
        if not state or state.group(1) in {"EXECUTADA", "SUPERSEDIDA"}:
            continue
        if not review or review.group(1) >= today.isoformat():
            continue
        owner = re.search(r"\*\*Dono:\*\*\s*([^\n*]+)", block)
        found.append(
            {
                "id": match.group(1),
                "venceu": review.group(1),
                "dono": (owner.group(1).strip().rstrip("·").strip() if owner else "?"),
                "o_que": title[match.end() :].lstrip(" ·-").strip(),
                "origem": "DECISIONS.md",
            }
        )
    return found


def fetch_issues(labels: tuple[str, ...] = ISSUE_LABELS) -> tuple[list[dict], list[str]]:
    """Issues abertas com os labels do ledger. Só relatório; nunca derruba o gate."""
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--limit",
                "200",
                "--json",
                "number,title,createdAt,url,labels",
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return [], ["gh não encontrado; issues não foram conferidas"]
    if result.returncode != 0:
        return [], [f"gh issue list: {result.stderr.strip()[:160]}"]
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [], [f"gh issue list: json inválido ({exc})"]
    wanted = set(labels)
    found = [
        issue
        for issue in issues
        if wanted & {label["name"] for label in issue.get("labels", [])}
    ]
    return sorted(found, key=lambda issue: issue["number"]), []


def orphan_issues(root: Path, issues: list[dict]) -> list[dict]:
    """Issue aberta com label que nenhuma entrada do ledger cita por #numero."""
    entries, _ = load_ledger(root)
    text = "\n".join(" ".join(getattr(entry, c) for c in COLUMNS) for entry in entries)
    candidate = root / LEGACY
    if candidate.exists():
        text += candidate.read_text(encoding="utf-8")
    return [issue for issue in issues if not re.search(rf"#{issue['number']}\b", text)]


def _check_refs(
    refs: list[str],
    issues: list[int],
    known: set[str],
    known_issues: set[int] | None,
    where: str,
) -> list[str]:
    errors: list[str] = []
    for ref in refs:
        if ref not in known:
            errors.append(f"{ref} citado em '{where}' não existe no ledger")
    if known_issues is not None:
        for number in issues:
            if number not in known_issues:
                errors.append(
                    f"issue #{number} citada em '{where}' não está aberta com label "
                    "(ficou-de-fora, helpdesk, dev, decisao ou achado)"
                )
    return errors


def check_pr_body(
    body: str,
    entries: list[Entry],
    *,
    created: dt.date | None = None,
    author: str = "",
    known_issues: set[int] | None = None,
) -> list[str]:
    """Gate do compromisso: PR novo cita a solicitação do dono (DEV- ou issue com label).

    A declaração do que ficou de fora é outro gate (`Ficou de fora declarado`);
    este aqui não a duplica.
    """
    errors: list[str] = []
    known = {entry.id for entry in entries}
    if author in BOT_LOGINS:
        return errors
    if created is not None and created < COMMITMENT_GATE_START:
        return errors  # migração: PR aberto antes da regra
    match = COMMITMENT_LINE_RE.search(body)
    if not match:
        errors.append(
            "PR sem a linha 'Compromisso: DEV-AAAA-NNN' (ou 'Compromisso: #2300'), ou "
            "'Compromisso: nenhum'; a solicitação do dono é registrada antes do trabalho"
        )
        return errors
    value = match.group("value").strip()
    if value.lower() == "nenhum":
        return errors
    refs = REF_RE.findall(value)
    issues = [int(number) for number in ISSUE_NUM_RE.findall(value)]
    errors += _check_refs(refs, issues, known, known_issues, "Compromisso")
    return errors


# ── ID novo sem colisão com o que está em voo ─────────────────────────


def next_id(entries: list[Entry], year: int, taken: set[str] | None = None) -> str:
    prefix = f"DEV-{year}-"
    ids = {entry.id for entry in entries} | set(taken or ())
    numbers = [
        int(ref.rsplit("-", 1)[1])
        for ref in ids
        if ref.startswith(prefix) and ref.rsplit("-", 1)[1].isdigit()
    ]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


class InflightError(RuntimeError):
    """Não deu para saber o que está em voo; o ID novo poderia colidir."""


_FILE_ID_RE = re.compile(r"(DEV-\d{4}-\d{3})\.json")
_ROW_ID_RE = re.compile(r"^\|\s*(DEV-\d{4}-\d{3})\s*\|")


def _git(root: Path, *args: str, run=subprocess.run):
    return run(["git", "-C", str(root), *args], capture_output=True, text=True)


def ids_in_refs(root: Path, refs: list[str], run=subprocess.run) -> set[str]:
    """IDs dos arquivos por entrada e da tabela congelada em cada ref.

    Duas chamadas de `git grep` cobrem todas as refs de uma vez; é o que mantém o
    intake rápido com dezenas de PRs abertos.
    """
    found: set[str] = set()
    if not refs:
        return found
    for pattern, path in (('"id"', str(LEDGER_DIR)), ("| DEV-", str(LEGACY_TABLE))):
        result = _git(root, "grep", "-I", "-F", "-e", pattern, *refs, "--", path, run=run)
        if result.returncode not in (0, 1):
            raise InflightError(f"git grep: {result.stderr.strip()[:160]}")
        for line in result.stdout.splitlines():
            # formato: <ref>:<caminho>:<conteúdo>
            if path == str(LEDGER_DIR):
                match = _FILE_ID_RE.search(line)
                if match:
                    found.add(match.group(1))
                continue
            marker = f"{LEGACY_TABLE}:"
            content = line.split(marker, 1)[1] if marker in line else line
            match = _ROW_ID_RE.match(content)
            if match:
                found.add(match.group(1))
    return found


def ids_in_worktrees(root: Path, run=subprocess.run) -> set[str]:
    """Arquivo criado e ainda não commitado em qualquer worktree deste clone."""
    found: set[str] = set()
    result = _git(root, "worktree", "list", "--porcelain", run=run)
    if result.returncode != 0:
        return found
    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        directory = Path(line[len("worktree ") :]) / LEDGER_DIR
        if directory.is_dir():
            for path in directory.glob("DEV-*.json"):
                match = _FILE_ID_RE.fullmatch(path.name)
                if match:
                    found.add(match.group(1))
    return found


def open_pr_heads(root: Path, run=subprocess.run) -> list[str]:
    try:
        result = run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--limit",
                "300",
                "--json",
                "headRefName",
                "-q",
                ".[].headRefName",
            ],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
    except FileNotFoundError as exc:
        raise InflightError("gh não encontrado") from exc
    if result.returncode != 0:
        raise InflightError(f"gh pr list: {result.stderr.strip()[:160]}")
    return sorted({head for head in result.stdout.split() if head})


def inflight_ids(root: Path, *, offline: bool = False, run=subprocess.run) -> set[str]:
    """IDs já usados fora do `main` local: PRs abertos, branches locais e worktrees.

    O defeito (18/11/2026): `make intake` olhava só o `main`, e dois PRs abertos
    nasceram com o mesmo DEV-2026-051. Sem `gh` ou sem rede, falha alto: um ID
    chutado custa mais que um intake que pede para rodar de novo.
    """
    refs: list[str] = []
    local = _git(root, "for-each-ref", "--format=%(refname)", "refs/heads", run=run)
    if local.returncode == 0:
        refs += [ref for ref in local.stdout.split() if ref]
    if not offline:
        heads = sorted(set(open_pr_heads(root, run=run)) | {"main"})
        fetched = _git(
            root,
            "fetch",
            "--quiet",
            "--no-tags",
            "origin",
            *[f"+refs/heads/{head}:refs/remotes/origin/{head}" for head in heads],
            run=run,
        )
        if fetched.returncode != 0:
            raise InflightError(f"git fetch: {fetched.stderr.strip()[:160]}")
        refs += [f"refs/remotes/origin/{head}" for head in heads]
    return ids_in_refs(root, refs, run=run) | ids_in_worktrees(root, run=run)


def _clean(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def append_entry(
    root: Path,
    *,
    quote: str,
    tipo: str,
    dono: str,
    origem: str,
    revisar_em: str,
    gatilho: str = "-",
    compromisso: str = "",
    estado: str = "ABERTO",
    prova: str = "-",
    taken: set[str] | None = None,
) -> Entry:
    """Cria `commitments/DEV-AAAA-NNN.json`. `taken`: IDs em voo, que o novo pula."""
    entries, errors = load_ledger(root)
    if errors:
        raise SystemExit("ledger inválido, conserte antes de adicionar:\n  " + "\n  ".join(errors))
    today = dt.date.today()
    entry = Entry(
        id=next_id(entries, today.year, taken),
        tipo=tipo,
        origem=_clean(origem),
        compromisso=_clean(compromisso or quote),
        dono=_clean(dono),
        criado=today.isoformat(),
        revisar_em=revisar_em,
        gatilho=_clean(gatilho),
        estado=estado,
        prova=_clean(prova),
    )
    write_entry(root, entry)
    return entry


# ── Relatórios ────────────────────────────────────────────────────────


def _report_table(entries: list[Entry]) -> str:
    """O índice legível, gerado na hora. Nunca é commitado: arquivo único é conflito."""
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for entry in sorted(entries, key=lambda entry: entry.id):
        lines.append(
            "| " + " | ".join(_clean(getattr(entry, column)) for column in COLUMNS) + " |"
        )
    return "\n".join(lines) + "\n"


def _report_issue(
    entries: list[Entry],
    legacy: list[dict[str, str]],
    orphans: list[dict],
    today: dt.date,
) -> str:
    lines = [
        f"<!-- commitments-overdue: {len(entries) + len(legacy) + len(orphans)} -->",
        f"## Compromissos vencidos em {today.isoformat()}",
        "",
        "Itens abertos cuja data de revisão passou. Isto não bloqueia merge; é a lista",
        "de trabalho da semana. Fechar um item exige prova (PR, commit ou decisão de",
        f"quem descartou), escrita no arquivo do item em `{LEDGER_DIR}/`.",
        "",
        "| id | venceu em | dono | o que é | origem |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        lines.append(
            f"| {entry.id} | {entry.revisar_em} | {entry.dono} | "
            f"{_clean(entry.compromisso)} | {_clean(entry.origem)} |"
        )
    for item in legacy:
        lines.append(
            f"| {item['id']} (legado) | {item['venceu']} | {item['dono']} | "
            f"{item['o_que']} | {item['origem']} |"
        )
    if not entries and not legacy:
        lines.append("| - | - | - | Nada vencido. | - |")
    if orphans:
        lines += [
            "",
            "### Issues abertas com label e sem entrada no ledger",
            "",
            "| issue | criada em | título |",
            "|---|---|---|",
        ]
        for issue in orphans:
            lines.append(
                f"| [#{issue['number']}]({issue.get('url', '')}) | "
                f"{issue.get('createdAt', '')[:10]} | {issue.get('title', '')} |"
            )
    lines += [
        "",
        "O job semanal atualiza esta issue. Quando a lista zera, ela fecha sozinha.",
    ]
    return "\n".join(lines) + "\n"


def _report_text(
    entries: list[Entry],
    errors: list[str],
    legacy,
    orphans,
    today,
    *,
    show_overdue: bool = True,
) -> str:
    open_count = len([entry for entry in entries if not entry.terminal])
    lines = [
        f"ledger: {len(entries)} entradas, {open_count} abertas, "
        f"{len(overdue(entries, today))} vencidas"
    ]
    for error in errors:
        lines.append(f"[FAIL] {error}")
    if not errors:
        lines.append("[OK] ledger válido")
    if show_overdue and legacy:
        plural = (
            "decisão legada vencida"
            if len(legacy) == 1
            else "decisões legadas vencidas"
        )
        lines.append(f"[WARN] {len(legacy)} {plural} em DECISIONS.md")
    expired = overdue(entries, today)
    if show_overdue and (expired or legacy):
        lines.append("")
        lines.append("VENCIDOS:")
        for entry in expired:
            lines.append(
                f"  {entry.id}  venceu {entry.revisar_em}  {entry.dono}  "
                f"{entry.compromisso}  ({entry.origem})"
            )
        for item in legacy:
            lines.append(
                f"  {item['id']}  venceu {item['venceu']}  {item['dono']}  "
                f"{item['o_que']}  (legado)"
            )
    if show_overdue and orphans:
        lines.append("")
        lines.append("ISSUES ABERTAS COM LABEL E SEM ENTRADA NO LEDGER:")
        for issue in orphans:
            lines.append(
                f"  #{issue['number']}  {issue.get('createdAt', '')[:10]}  "
                f"{issue.get('title', '')}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="raiz do repo")
    parser.add_argument("--today", help="data de referência (YYYY-MM-DD), para teste")
    parser.add_argument("--pr-body", type=Path, help="arquivo com o corpo do PR")
    parser.add_argument("--pr-body-env", action="store_true", help="lê o corpo de PR_BODY")
    parser.add_argument("--pr-created", help="data de criação do PR (YYYY-MM-DD)")
    parser.add_argument("--author", default="", help="login do autor do PR")
    parser.add_argument(
        "--known-issues",
        default="",
        help="números de issue abertas com label, separados por vírgula (teste local)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "issue", "table"),
        default="text",
        help="table: o índice legível de todas as entradas (gerado, nunca commitado)",
    )
    parser.add_argument("--no-fail-overdue", action="store_true")
    parser.add_argument(
        "--with-issues",
        action="store_true",
        help="inclui issues abertas com label (gh) e aponta as que não têm entrada",
    )
    parser.add_argument("--add", action="store_true", help="registra uma entrada e imprime o ID")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="com --add: não consulta PRs abertos (só branches locais e worktrees). "
        "Risco de colisão com PR em voo",
    )
    parser.add_argument(
        "--migrate-legacy",
        action="store_true",
        help="DEPRECATED(remove by 2026-11-25): cria o arquivo de cada linha da tabela congelada",
    )
    parser.add_argument("--quote", default="", help="fala literal do dono")
    parser.add_argument("--compromisso", default="", help="resumo de uma linha (default: a fala)")
    parser.add_argument("--tipo", default="solicitacao", choices=sorted(TYPES))
    parser.add_argument("--dono", default="Engenharia")
    parser.add_argument("--origem", default="chat")
    parser.add_argument("--gatilho", default="-")
    parser.add_argument("--estado", default="ABERTO", choices=sorted(STATES))
    parser.add_argument("--prova", default="-")
    parser.add_argument("--revisar-em", help="YYYY-MM-DD (default: hoje + 7)")
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    root = args.root

    if args.migrate_legacy:
        created = migrate_legacy(root)
        print(f"{len(created)} arquivo(s) criado(s) em {LEDGER_DIR}: {', '.join(created) or '-'}")
        return 0

    if args.add:
        if not args.quote.strip():
            parser.error("--add exige --quote com a fala do dono")
        try:
            taken = inflight_ids(root, offline=args.offline)
        except InflightError as exc:
            print(
                f"[FAIL] não deu para ver os IDs em voo ({exc}).\n"
                "O ID novo poderia ser o mesmo de um PR aberto (foi o DEV-2026-051 em "
                "18/11/2026). Rode de novo com rede e `gh auth status` ok, ou, sabendo "
                "do risco, `make intake ... offline=1`.",
                file=sys.stderr,
            )
            return 2
        review = args.revisar_em or (today + dt.timedelta(days=7)).isoformat()
        entry = append_entry(
            root,
            quote=args.quote,
            tipo=args.tipo,
            dono=args.dono,
            origem=args.origem,
            revisar_em=review,
            gatilho=args.gatilho,
            compromisso=args.compromisso,
            estado=args.estado,
            prova=args.prova,
            taken=taken,
        )
        print(entry.id)
        label = "Compromisso" if entry.tipo in {"solicitacao", "compromisso"} else "Referência"
        print(f"{label}: {entry.id}")
        print(f"arquivo: {LEDGER_DIR}/{entry.id}.json", file=sys.stderr)
        return 0

    entries, errors = load_ledger(root)
    errors += validate(entries, today)
    warnings = legacy_warnings(root)
    legacy = legacy_overdue(root, today)
    orphans: list[dict] = []
    issue_errors: list[str] = []
    known_issues: set[int] | None = None
    if args.with_issues:
        issues, issue_errors = fetch_issues()
        orphans = orphan_issues(root, issues)
        if not issue_errors:
            known_issues = {issue["number"] for issue in issues}
    if args.known_issues:
        known_issues = {
            int(number) for number in args.known_issues.split(",") if number.strip()
        }

    body = None
    if args.pr_body_env:
        body = os.environ.get("PR_BODY", "")
    elif args.pr_body:
        if not args.pr_body.exists():
            errors.append(f"corpo de PR não encontrado: {args.pr_body}")
        else:
            body = args.pr_body.read_text(encoding="utf-8")
    if body is not None:
        created = (
            dt.date.fromisoformat(args.pr_created[:10]) if args.pr_created else None
        )
        errors += check_pr_body(
            body,
            entries,
            created=created,
            author=args.author,
            known_issues=known_issues,
        )

    expired = overdue(entries, today)
    if args.format == "json":
        payload = {
            "entries": [entry.__dict__ for entry in entries],
            "errors": errors,
            "warnings": warnings,
            "overdue": [entry.__dict__ for entry in expired],
            "legacy_overdue": legacy,
            "orphan_issues": orphans,
            "issue_errors": issue_errors,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.format == "issue":
        print(_report_issue(expired, legacy, orphans, today), end="")
    elif args.format == "table":
        print(_report_table(entries), end="")
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
    else:
        print(
            _report_text(
                entries, errors, legacy, orphans, today, show_overdue=body is None
            ),
            end="",
        )
        for warning in warnings:
            print(f"[WARN] {warning}")

    for error in issue_errors:
        print(f"[WARN] {error}")
    if errors:
        return 1
    if (expired or legacy) and not args.no_fail_overdue:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
