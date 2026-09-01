"""Importa um arquivo do cofre de volta para o banco — dry-run por padrão.

Sem ``--apply`` nada é escrito: o comando relata, aba por aba, o que SERIA
criado, atualizado e mantido, e toda linha inválida com o erro dela. Com
``--apply`` tudo entra numa transação única: qualquer erro desfaz o arquivo
inteiro — restore pela metade não existe.

O comando falha fechado em três fronteiras:

- aba que o cofre não conhece é erro (arquivo de outra versão ou digitação);
- cabeçalho diferente do que o resource exporta é erro (coluna renomeada no
  Sheets seria silenciosamente ignorada pelo import-export — aqui ela grita);
- em produção, ``--apply`` exige ``--force`` (o mesmo contrato do ``seed``).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.shop.backup import registry, workbook

#: Quantos erros de linha mostrar por aba antes de resumir.
_MAX_ROW_ERRORS = 10


class Command(BaseCommand):
    help = "Importa um backup de dados curados (dry-run por padrão; --apply escreve)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Arquivo .xlsx ou diretório de CSVs do export_backup.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Escreve de verdade (sem isso, só relata o que aconteceria).",
        )
        parser.add_argument(
            "--only",
            default="",
            help="Entidades específicas, separadas por vírgula (ex.: products,recipes).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Obrigatório para --apply em produção.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        if (
            apply
            and getattr(settings, "SHOPMAN_ENVIRONMENT", "") == "production"
            and not options["force"]
        ):
            raise CommandError(
                "Ambiente de produção: import_backup --apply exige --force explícito."
            )

        path = Path(options["path"])
        if path.is_dir():
            datasets = workbook.read_csv_dir(path)
        elif path.is_file():
            datasets = workbook.read_xlsx(path)
        else:
            raise CommandError(f"Arquivo não encontrado: {path}")

        only = {n.strip() for n in options["only"].split(",") if n.strip()}
        if only:
            unknown_only = only - {e.name for e in registry.entries()}
            if unknown_only:
                raise CommandError(f"Entidade desconhecida em --only: {', '.join(sorted(unknown_only))}")
            datasets = {n: d for n, d in datasets.items() if n in only}

        self._validate_shape(datasets)

        plan = [e for e in registry.entries() if e.name in datasets]
        if not plan:
            raise CommandError("Nenhuma entidade do cofre encontrada no arquivo.")

        if apply:
            with transaction.atomic():
                failed = self._run(plan, datasets, dry_run=False)
                if failed:
                    raise CommandError(
                        "Erros de importação — transação desfeita, nada foi escrito."
                    )
            self.stdout.write(self.style.SUCCESS("Importação aplicada."))
        else:
            failed = self._run(plan, datasets, dry_run=True)
            if failed:
                raise CommandError("Dry-run com erros — corrija a planilha antes do --apply.")
            self.stdout.write(
                self.style.SUCCESS("Dry-run limpo. Rode de novo com --apply para escrever.")
            )

    def _validate_shape(self, datasets) -> None:
        """Aba desconhecida ou cabeçalho divergente derruba antes de qualquer linha."""
        problems = []
        for name, dataset in datasets.items():
            entry = registry.get(name)
            if entry is None:
                problems.append(f"aba desconhecida: {name!r}")
                continue
            if entry.read_only:
                problems.append(
                    f"{name}: aba somente-leitura (transacional) — não importável; "
                    "restaurar transacional é papel do backup do banco. Para importar "
                    "só a curadoria deste arquivo, use --only com as abas curadas."
                )
                continue
            expected = set(entry.resource_class().get_export_headers())
            got = set(dataset.headers or [])
            missing = expected - got
            extra = got - expected
            if missing:
                problems.append(f"{name}: coluna(s) faltando: {', '.join(sorted(missing))}")
            if extra:
                problems.append(f"{name}: coluna(s) desconhecida(s): {', '.join(sorted(extra))}")
        if problems:
            raise CommandError("Arquivo incompatível com o cofre:\n  " + "\n  ".join(problems))

    def _run(self, plan, datasets, *, dry_run: bool) -> bool:
        failed = False
        for entry in plan:
            dataset = datasets[entry.name]
            resource = entry.resource_class()
            result = resource.import_data(
                dataset,
                dry_run=dry_run,
                use_transactions=False,
                raise_errors=False,
                collect_failed_rows=True,
            )
            totals = result.totals
            self.stdout.write(
                f"  {entry.name}: {totals.get('new', 0)} nova(s), "
                f"{totals.get('update', 0)} atualizada(s), "
                f"{totals.get('skip', 0)} sem mudança, "
                f"{totals.get('error', 0) + totals.get('invalid', 0)} com erro"
            )
            if result.has_errors() or result.has_validation_errors():
                failed = True
                self._print_errors(entry.name, result)
        return failed

    def _print_errors(self, name: str, result) -> None:
        shown = 0
        for row_number, errors in result.row_errors():
            for error in errors:
                if shown >= _MAX_ROW_ERRORS:
                    self.stderr.write(f"    ... e mais erros em {name} (mostrei {shown}).")
                    return
                self.stderr.write(f"    {name} linha {row_number}: {error.error!r}")
                shown += 1
        for invalid in result.invalid_rows:
            if shown >= _MAX_ROW_ERRORS:
                self.stderr.write(f"    ... e mais erros em {name} (mostrei {shown}).")
                return
            self.stderr.write(
                f"    {name} linha {invalid.number}: {invalid.error_dict}"
            )
            shown += 1
