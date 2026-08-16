"""Injeta o calendário de um ano (uma vez por ano, por arquivo).

    python manage.py import_holidays --file calendario-2026.json
    python manage.py import_holidays --file feriados.csv

Aceita JSON (lista de objetos) ou CSV com cabeçalho. Colunas/chaves:
``date`` (YYYY-MM-DD), ``name``, ``scope`` (national|state|city, opcional) e
``kind`` (``feriado`` — o padrão — ou ``comercial``).

**Feriado e data comercial são fatos diferentes.** O feriado pode FECHAR a loja;
a data comercial (dia das mães, Páscoa, dia dos namorados) nunca fecha — ela
enche. Um dia pode ser os dois, e o Natal é.

O comando marca também **véspera** e **volta**, a partir da união dos dois,
porque é isso que muda o movimento de uma padaria: o dia antes enche, o dia
depois esvazia — e a véspera do dia das mães enche tanto quanto a de um feriado.

Idempotente: recarregar o mesmo ano corrige o que mudou e não duplica nada. O
ano inteiro é reescrito a partir do arquivo, então feriado removido do arquivo
some do banco — o arquivo é a verdade daquele ano.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.backstage.models import DayContext, HolidayScope

VALID_SCOPES = {choice.value for choice in HolidayScope}
COMMERCIAL_KINDS = {"comercial", "commercial"}
HOLIDAY_KINDS = {"", "feriado", "holiday"}


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

        entries = _parse(rows)
        years = sorted({day.year for day in entries})
        holidays = sum(1 for entry in entries.values() if entry.holiday_name)
        self.stdout.write(
            f"{holidays} feriados e {len(entries) - holidays} datas comerciais "
            f"em {', '.join(str(y) for y in years)}"
        )
        for day in sorted(entries):
            entry = entries[day]
            tag = "comercial" if entry.commercial else (entry.scope or "feriado")
            self.stdout.write(f"  {day}  {entry.name}  [{tag}]")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry-run: nada gravado."))
            return

        with transaction.atomic():
            written = _apply(entries, years, source=path.name)

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ calendário gravado: {written} dias marcados "
                f"({len(entries)} datas + vésperas e voltas)"
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


@dataclass(frozen=True)
class CalendarEntry:
    """Um dia declarado no arquivo. Pode ser feriado, data comercial ou os dois.

    O Natal é os dois, e por isso os campos coexistem em vez de disputarem o
    mesmo slot: perder qualquer um dos lados perderia uma pergunta inteira (a
    loja abre? / o que esperar do movimento?).
    """

    holiday_name: str = ""
    scope: str = ""
    commercial_name: str = ""

    @property
    def commercial(self) -> bool:
        return bool(self.commercial_name)

    @property
    def name(self) -> str:
        return self.commercial_name or self.holiday_name


def _parse(rows: list[dict]) -> dict[date, CalendarEntry]:
    """{data: entrada} — erro carrega a linha, para o operador se corrigir."""
    out: dict[date, CalendarEntry] = {}
    for index, row in enumerate(rows, start=1):
        raw_date = str(row.get("date") or row.get("data") or "").strip()
        name = str(row.get("name") or row.get("nome") or "").strip()
        scope = str(row.get("scope") or row.get("abrangencia") or "").strip().lower()
        kind = str(row.get("kind") or row.get("tipo") or "").strip().lower()
        if not raw_date:
            raise CommandError(f"linha {index}: sem data.")
        if not name:
            raise CommandError(f"linha {index} ({raw_date}): sem nome da data.")
        if kind not in COMMERCIAL_KINDS | HOLIDAY_KINDS:
            raise CommandError(
                f"linha {index} ({raw_date}): tipo {kind!r} desconhecido. "
                "Use 'feriado' (padrão) ou 'comercial'."
            )
        commercial = kind in COMMERCIAL_KINDS
        if scope and commercial:
            raise CommandError(
                f"linha {index} ({raw_date}): data comercial não tem abrangência — "
                "abrangência é do feriado, que define quem fecha."
            )
        if scope and scope not in VALID_SCOPES:
            raise CommandError(
                f"linha {index} ({raw_date}): abrangência {scope!r} desconhecida. "
                f"Use uma de: {', '.join(sorted(VALID_SCOPES))}."
            )
        try:
            parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"linha {index}: data {raw_date!r} não é YYYY-MM-DD.") from exc
        # Um dia pode ser feriado E data comercial (o Natal é): a segunda linha
        # do mesmo dia COMPLETA a primeira em vez de substituí-la.
        previous = out.get(parsed) or CalendarEntry()
        out[parsed] = CalendarEntry(
            holiday_name=name if not commercial else previous.holiday_name,
            scope=scope or previous.scope,
            commercial_name=name if commercial else previous.commercial_name,
        )
    return out


def _apply(entries: dict[date, CalendarEntry], years: list[int], *, source: str) -> int:
    """Reescreve os anos cobertos: o arquivo é a verdade daquele período."""
    written = 0
    for year in years:
        day = date(year, 1, 1)
        end = date(year, 12, 31)
        while day <= end:
            entry = entries.get(day) or CalendarEntry()
            context, _ = DayContext.objects.get_or_create(date=day)
            context.holiday_name = entry.holiday_name
            context.holiday_scope = entry.scope
            context.commercial_name = entry.commercial_name
            # Véspera e volta saem da UNIÃO: o sábado antes do dia das mães é
            # véspera tanto quanto o dia anterior a um feriado. E a véspera
            # guarda DE QUAL data ela é véspera, porque numa padaria fechada no
            # dia seguinte é nela que o movimento acontece.
            following = entries.get(day + timedelta(days=1))
            context.is_special_eve = following is not None
            context.eve_of = following.name if following else ""
            context.is_post_special = (day - timedelta(days=1)) in entries
            context.has_calendar = True
            context.sources = {**(context.sources or {}), "holiday": source}
            context.save()
            written += 1
            day += timedelta(days=1)
    return written
