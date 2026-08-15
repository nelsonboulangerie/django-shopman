"""Injeta o calendário de feriados de um ano (uma vez por ano, por arquivo).

    python manage.py import_holidays --file calendario-2026.json
    python manage.py import_holidays --file feriados.csv

Aceita JSON (lista de objetos) ou CSV com cabeçalho. Colunas/chaves:
``date`` (YYYY-MM-DD), ``name``, ``scope`` (national|state|city, opcional).

O comando marca também **véspera** e **volta** de feriado, porque é isso que
muda o movimento de uma padaria: o dia antes enche, o dia depois esvazia.

Idempotente: recarregar o mesmo ano corrige o que mudou e não duplica nada. O
ano inteiro é reescrito a partir do arquivo, então feriado removido do arquivo
some do banco — o arquivo é a verdade daquele ano.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.backstage.models import DayContext, HolidayScope

VALID_SCOPES = {choice.value for choice in HolidayScope}


class Command(BaseCommand):
    help = "Injeta o calendário anual de feriados (JSON ou CSV)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Arquivo .json ou .csv")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Lê e valida sem gravar — mostra o que entraria.",
        )

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        rows = _read_rows(path)
        if not rows:
            raise CommandError("Arquivo sem linhas — nada a carregar.")

        holidays = _parse(rows)
        years = sorted({day.year for day in holidays})
        self.stdout.write(
            f"{len(holidays)} feriados em {', '.join(str(y) for y in years)}"
        )
        for day in sorted(holidays):
            name, scope = holidays[day]
            self.stdout.write(f"  {day}  {name}" + (f"  [{scope}]" if scope else ""))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry-run: nada gravado."))
            return

        with transaction.atomic():
            written = _apply(holidays, years, source=path.name)

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ calendário gravado: {written} dias marcados "
                f"({len(holidays)} feriados + vésperas e voltas)"
            )
        )


def _read_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):  # {"2026": [...]} ou {"holidays": [...]}
            data = next((v for v in data.values() if isinstance(v, list)), [])
        return list(data)
    return list(csv.DictReader(text.splitlines()))


def _parse(rows: list[dict]) -> dict[date, tuple[str, str]]:
    """{data: (nome, escopo)} — erro carrega a linha, para o operador se corrigir."""
    out: dict[date, tuple[str, str]] = {}
    for index, row in enumerate(rows, start=1):
        raw_date = str(row.get("date") or row.get("data") or "").strip()
        name = str(row.get("name") or row.get("nome") or "").strip()
        scope = str(row.get("scope") or row.get("abrangencia") or "").strip().lower()
        if not raw_date:
            raise CommandError(f"linha {index}: sem data.")
        if not name:
            raise CommandError(f"linha {index} ({raw_date}): sem nome do feriado.")
        if scope and scope not in VALID_SCOPES:
            raise CommandError(
                f"linha {index} ({raw_date}): abrangência {scope!r} desconhecida. "
                f"Use uma de: {', '.join(sorted(VALID_SCOPES))}."
            )
        try:
            parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"linha {index}: data {raw_date!r} não é YYYY-MM-DD.") from exc
        out[parsed] = (name, scope)
    return out


def _apply(holidays: dict[date, tuple[str, str]], years: list[int], *, source: str) -> int:
    """Reescreve os anos cobertos: o arquivo é a verdade daquele período."""
    written = 0
    for year in years:
        day = date(year, 1, 1)
        end = date(year, 12, 31)
        while day <= end:
            name, scope = holidays.get(day, ("", ""))
            context, _ = DayContext.objects.get_or_create(date=day)
            context.holiday_name = name
            context.holiday_scope = scope
            context.is_holiday_eve = (day + timedelta(days=1)) in holidays
            context.is_post_holiday = (day - timedelta(days=1)) in holidays
            context.has_calendar = True
            context.sources = {**(context.sources or {}), "holiday": source}
            context.save()
            written += 1
            day += timedelta(days=1)
    return written
