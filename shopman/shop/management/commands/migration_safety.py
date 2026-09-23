"""Recusa o deploy quando a migração é destrutiva e ninguém anotou o backup.

Roda **antes** do ``migrate`` no job ``release`` (PRE_DEPLOY). Lê o mesmo plano
de migração que o ``migrate`` executaria e responde uma pergunta só: há
migração destrutiva pendente sem ponto de restauração declarado?

Uso::

    python manage.py migration_safety            # trava (sai != 0 quando recusa)
    python manage.py migration_safety --report   # só relata; nunca recusa
    python manage.py migration_safety --json     # saída legível por máquina

A mecânica, o armar da política e o porquê de cada recusa estão em
``shopman/shop/migration_safety.py``. O procedimento humano — como anotar o
ponto de restauração e como ensaiar um restore — está em
``docs/runbooks/backup-e-restore.md``.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from shopman.shop import migration_safety


class Command(BaseCommand):
    help = (
        "Recusa o deploy quando há migração destrutiva pendente sem ponto de "
        "restauração declarado (ADR-015)."
    )

    #: Sem system checks, de propósito. Este comando roda ANTES do `migrate`,
    #: quando uma tabela nova ainda não existe — e vários checks do Shopman
    #: consultam o banco (catálogo, canais, templates). Deixá-los rodar aqui
    #: trocaria "migração destrutiva sem backup" por um ProgrammingError de
    #: tabela ausente: o portão falaria da coisa errada. O `check --deploy` do
    #: release job continua rodando, logo antes, no comando próprio dele.
    requires_system_checks: list = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            action="store_true",
            help="Só relata o plano pendente; sai 0 mesmo quando a trava recusaria.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Imprime o relatório em JSON.",
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Alias da conexão a inspecionar (padrão: default).",
        )

    def handle(self, *args, **options):
        from django.db import connections
        from django.utils.connection import ConnectionDoesNotExist

        try:
            connection = connections[options["database"]]
        except ConnectionDoesNotExist as exc:
            raise CommandError(
                f"Conexão '{options['database']}' não existe em DATABASES."
            ) from exc

        report = migration_safety.build_report(connection=connection)

        if options["as_json"]:
            self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2))
        else:
            for line in migration_safety.human_lines(report):
                self.stdout.write(line)

        if options["report"] or not report.blocking:
            return

        raise CommandError(
            "migration-safety recusou o deploy: veja o relato acima e "
            "docs/runbooks/backup-e-restore.md."
        )
