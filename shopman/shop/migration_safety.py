"""A trava entre o deploy e o ``migrate`` — backup antes de migração destrutiva.

O job ``release`` (PRE_DEPLOY) roda ``migrate --noinput`` contra o banco real a
cada merge no ``main``. Para migração **aditiva** isso é seguro: o rollback é
redeploy da versão anterior e a coluna nova fica órfã e inofensiva. Para
migração **destrutiva** (contract) não há rollback barato — a recuperação é
restore do banco, e o runbook ``docs/runbooks/backup-e-restore.md`` exige que o
ponto de restauração tenha sido **anotado antes** do deploy.

Este módulo é a metade mecânica dessa exigência: ele responde, sem opinião,
duas perguntas que o release job precisa fazer antes de migrar:

1. Quais migrações estão **pendentes** neste banco?
2. Alguma delas contém operação destrutiva (``RemoveField``, ``DeleteModel``,
   ``RenameField``, ``RenameModel``, ``AlterField`` — a mesma lista do ADR-015,
   em ``docs/decisions/adr-015-backward-compat-policy-post-prod.md``)?

Quando a política do ADR-015 está armada e a resposta da 2 é "sim", o deploy só
passa se quem apertou o botão tiver declarado o ponto de restauração em
``SHOPMAN_MIGRATION_BACKUP_REF``. Sem isso, a trava recusa — porque o backup que
ninguém anotou é o backup que ninguém acha às 3h da manhã.

**Armar a política** (a mesma ordem do ``scripts/check_adr015.py``, mais o sinal
que funciona dentro do contêiner):

1. ``SHOPMAN_ADR015_FORCE`` (``1``/``0``) — simulação local e testes;
2. ``SHOPMAN_GO_LIVE`` (booleano) — o sinal do ambiente de deploy. A imagem do
   app **não carrega o ``.git``**, então a tag não é legível lá dentro: no
   cutover, o spec declara ``SHOPMAN_GO_LIVE=true`` (item do
   ``docs/runbooks/go-live-cutover.md``);
3. a tag ``go-live-v1`` no repositório local — vale na máquina de dev e na CI.

Antes do go-live a trava é um relato honesto e verde: ela **mostra** a migração
destrutiva pendente e deixa passar. A política do ADR-015 só vale a partir da
tag, e fingir o contrário seria inventar uma regra que o projeto não tomou.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: Operações que removem ou reescrevem algo de que o código ainda em voo pode
#: depender. Lista idêntica à de ``scripts/check_adr015.py`` — o teste
#: ``test_migration_safety.py::test_lista_destrutiva_igual_a_do_gate_adr015``
#: trava as duas juntas, para que uma não ande sem a outra.
DESTRUCTIVE_OPERATION_NAMES = frozenset(
    {"RemoveField", "DeleteModel", "RenameField", "RenameModel", "AlterField"}
)

GO_LIVE_TAG = "go-live-v1"

#: Onde quem deu o deploy declara o ponto de restauração. Conteúdo livre e
#: legível por gente: o instante do PITR anotado no runbook, o nome do backup
#: ou do fork de ensaio. O que a trava exige é que exista e diga alguma coisa.
BACKUP_REF_ENV = "SHOPMAN_MIGRATION_BACKUP_REF"

#: Valores que parecem uma declaração mas não são — placeholder deixado no spec.
_EMPTY_BACKUP_REFS = frozenset({"", "-", "n/a", "na", "none", "null", "todo", "tbd"})

#: Quantas migrações aditivas o relato humano lista antes de resumir o resto.
#: Num banco vazio o plano tem centenas delas; no deploy real, poucas.
ADDITIVE_LIST_LIMIT = 15

_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSE_VALUES = frozenset({"0", "false", "f", "no", "n", "off"})

HOWTO = (
    "Migração destrutiva pendente e nenhum ponto de restauração declarado.\n"
    "\n"
    "Antes de deixar este deploy migrar o banco:\n"
    "  1. Anote o ponto de restauração (docs/runbooks/backup-e-restore.md).\n"
    f"  2. Declare-o em {BACKUP_REF_ENV} no ambiente que roda o release\n"
    "     (ex.: SHOPMAN_MIGRATION_BACKUP_REF='PITR 2026-09-23T14:05:00Z — shopman-headless-postgres').\n"
    "  3. Redeploy.\n"
    "\n"
    "Migração destrutiva (contract) não tem rollback barato: a recuperação é\n"
    "restore do banco. O ponto de restauração precisa existir ANTES, não depois."
)


def _env(name: str) -> str:
    return (os.environ.get(name, "") or "").strip()


def _env_bool(name: str) -> bool | None:
    """``True``/``False`` quando a env se declara; ``None`` quando cala."""
    raw = _env(name).lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return None


def _git_tag_present(repo_root: Path | None = None) -> bool:
    try:
        result = subprocess.run(
            ["git", "tag", "--list", GO_LIVE_TAG],
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        # Sem git no contêiner do app. Não é sinal de nada: quem responde lá é
        # SHOPMAN_GO_LIVE.
        return False
    return result.returncode == 0 and GO_LIVE_TAG in result.stdout.split()


def go_live_active(repo_root: Path | None = None) -> tuple[bool, str]:
    """A política do ADR-015 está armada? Devolve ``(armada, por quê)``."""
    forced = _env_bool("SHOPMAN_ADR015_FORCE")
    if forced is not None:
        return forced, f"SHOPMAN_ADR015_FORCE={_env('SHOPMAN_ADR015_FORCE')}"
    declared = _env_bool("SHOPMAN_GO_LIVE")
    if declared is not None:
        return declared, f"SHOPMAN_GO_LIVE={_env('SHOPMAN_GO_LIVE')}"
    if _git_tag_present(repo_root):
        return True, f"tag {GO_LIVE_TAG} presente no repositório local"
    return False, f"tag {GO_LIVE_TAG} ausente e SHOPMAN_GO_LIVE não declarada"


def backup_reference() -> str:
    """O ponto de restauração declarado, ou string vazia se não houver."""
    raw = _env(BACKUP_REF_ENV)
    if raw.lower() in _EMPTY_BACKUP_REFS:
        return ""
    return raw


def destructive_operation_names(migration) -> list[str]:
    """Nomes das operações destrutivas de uma ``Migration`` já carregada."""
    return sorted(
        {
            type(operation).__name__
            for operation in getattr(migration, "operations", [])
            if type(operation).__name__ in DESTRUCTIVE_OPERATION_NAMES
        }
    )


@dataclass(frozen=True)
class PendingMigration:
    app_label: str
    name: str
    destructive_operations: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.app_label}.{self.name}"

    @property
    def destructive(self) -> bool:
        return bool(self.destructive_operations)

    def as_dict(self) -> dict[str, object]:
        return {
            "migration": self.label,
            "destructive": self.destructive,
            "operations": list(self.destructive_operations),
        }


@dataclass(frozen=True)
class SafetyReport:
    """O que a trava mediu, e o que ela decidiu a partir disso."""

    pending: tuple[PendingMigration, ...] = ()
    go_live: bool = False
    go_live_reason: str = ""
    backup_ref: str = ""
    error: str = ""
    connection_alias: str = "default"
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def destructive(self) -> tuple[PendingMigration, ...]:
        return tuple(item for item in self.pending if item.destructive)

    @property
    def blocking(self) -> bool:
        """Recusa o deploy?

        Três formas de recusar, todas fechadas:

        - não deu para ler o plano de migração (``error``) — um portão que não
          enxerga não pode dizer "pode passar";
        - política armada + destrutiva pendente + nenhum ponto de restauração.
        """
        if self.error:
            return True
        if not self.go_live:
            return False
        return bool(self.destructive) and not self.backup_ref

    @property
    def status(self) -> str:
        if self.blocking:
            return "blocked"
        return "clear"

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "status": self.status,
            "go_live": self.go_live,
            "go_live_reason": self.go_live_reason,
            "connection": self.connection_alias,
            "pending_count": len(self.pending),
            "destructive_count": len(self.destructive),
            "backup_ref_declared": bool(self.backup_ref),
            "pending": [item.as_dict() for item in self.pending],
        }
        if self.error:
            data["error"] = self.error
        if self.extra:
            data["extra"] = self.extra
        return data


def collect_pending(connection) -> list[PendingMigration]:
    """As migrações ainda não aplicadas neste banco, na ordem do plano.

    Usa o mesmo executor que o ``migrate`` usa — o plano é o que o deploy vai
    de fato executar daqui a alguns segundos, não uma leitura paralela de
    arquivos.
    """
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    pending: list[PendingMigration] = []
    for migration, backwards in executor.migration_plan(targets):
        if backwards:  # o deploy nunca desfaz; se aparecer, é sinal a relatar
            continue
        pending.append(
            PendingMigration(
                app_label=migration.app_label,
                name=migration.name,
                destructive_operations=tuple(destructive_operation_names(migration)),
            )
        )
    return pending


def build_report(connection=None, repo_root: Path | None = None) -> SafetyReport:
    go_live, reason = go_live_active(repo_root)
    backup_ref = backup_reference()
    if connection is None:
        from django.db import connection as default_connection

        connection = default_connection
    alias = getattr(connection, "alias", "default")
    # Qualquer falha ao ler o plano (banco fora, credencial vencida, grafo
    # quebrado) vira recusa E log. Nada é engolido: a causa vai para o log do
    # release e para o Sentry, e volta no relatório — sem ela, quem lê o deploy
    # vermelho não sabe de qual das três coisas se trata.
    try:
        pending = collect_pending(connection)
    except Exception as exc:  # noqa: BLE001 — portão cego recusa, não libera
        logger.error("migration_safety: não foi possível ler o plano de migração: %s", exc)
        return SafetyReport(
            go_live=go_live,
            go_live_reason=reason,
            backup_ref=backup_ref,
            connection_alias=alias,
            error=f"{type(exc).__name__}: {exc}",
        )
    return SafetyReport(
        pending=tuple(pending),
        go_live=go_live,
        go_live_reason=reason,
        backup_ref=backup_ref,
        connection_alias=alias,
    )


def human_lines(report: SafetyReport) -> list[str]:
    """O relato que sai no log do release job — legível sem abrir o código."""
    lines = [f"migration-safety: {report.status}"]
    lines.append(
        "política ADR-015: "
        + ("ARMADA" if report.go_live else "inativa (pré-go-live)")
        + f" — {report.go_live_reason}"
    )
    if report.error:
        lines.append(f"- [FAIL] não foi possível ler o plano de migração: {report.error}")
        lines.append(
            "  A trava recusa o deploy quando não consegue enxergar o plano: "
            "um portão cego não libera passagem."
        )
        return lines

    lines.append(
        f"banco '{report.connection_alias}': {len(report.pending)} migração(ões) pendente(s), "
        f"{len(report.destructive)} com operação destrutiva."
    )
    # Toda destrutiva aparece pelo nome — é sobre elas que a decisão é tomada.
    # A lista aditiva é cortada porque num banco vazio ela tem centenas de
    # linhas e afogaria justamente o que importa no log do deploy.
    listed_additive = 0
    omitted_additive = 0
    for item in report.pending:
        if item.destructive:
            lines.append(f"  [DESTRUTIVA] {item.label} ({', '.join(item.destructive_operations)})")
            continue
        if listed_additive < ADDITIVE_LIST_LIMIT:
            lines.append(f"  [aditiva   ] {item.label}")
            listed_additive += 1
        else:
            omitted_additive += 1
    if omitted_additive:
        lines.append(f"  … e mais {omitted_additive} aditiva(s), não listadas.")

    if not report.destructive:
        return lines

    if report.backup_ref:
        lines.append(f"ponto de restauração declarado: {report.backup_ref}")
    elif report.go_live:
        lines.append("")
        lines.extend(HOWTO.splitlines())
    else:
        lines.append(
            f"Nenhum ponto de restauração em {BACKUP_REF_ENV}. Pré-go-live isto não "
            "segura o deploy — a partir da tag go-live-v1, segura."
        )
    return lines
