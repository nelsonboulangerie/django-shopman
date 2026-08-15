"""Injeta o histórico de clima por dia (CSV ou JSON, sem rede).

    python manage.py import_weather --file londrina-2024-2026.csv

Colunas/chaves aceitas (só ``date`` é obrigatória, o resto entra se vier):
``date`` (YYYY-MM-DD), ``temp_min``, ``temp_max``, ``temp_avg``, ``rain_mm``.
Nomes alternativos: ``temperature_2m_min``/``max``/``mean`` e
``precipitation_sum`` — os cabeçalhos de arquivos de série histórica costumam
vir assim, e reescrever cabeçalho na mão é convite a erro.

Dois anos de temperatura carregados de uma vez tornam o histórico do Yooga
cruzável por clima. O comando é idempotente: recarregar corrige e não duplica.

Célula vazia é ausência, não zero: fica nula, e o dia sai das leituras por
temperatura em vez de entrar como um dia de 0 °C.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.backstage.models import DayContext

FIELD_ALIASES = {
    "temp_min_c": ("temp_min", "temp_min_c", "temperature_2m_min", "tmin"),
    "temp_max_c": ("temp_max", "temp_max_c", "temperature_2m_max", "tmax"),
    "temp_avg_c": ("temp_avg", "temp_avg_c", "temperature_2m_mean", "tmean", "temp_media"),
    "rain_mm": ("rain_mm", "precipitation_sum", "chuva_mm", "precip"),
}


class Command(BaseCommand):
    help = "Injeta o histórico diário de clima (CSV ou JSON)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Arquivo .csv ou .json")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        rows = _read_rows(path)
        if not rows:
            raise CommandError("Arquivo sem linhas — nada a carregar.")

        parsed = _parse(rows)
        days = sorted(parsed)
        with_temp = sum(1 for values in parsed.values() if values.get("temp_max_c") is not None)
        self.stdout.write(
            f"{len(parsed)} dias de {days[0]} a {days[-1]} "
            f"({with_temp} com temperatura máxima)"
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry-run: nada gravado."))
            return

        with transaction.atomic():
            for day, values in parsed.items():
                context, _ = DayContext.objects.get_or_create(date=day)
                for field, value in values.items():
                    setattr(context, field, value)
                context.sources = {**(context.sources or {}), "weather": path.name}
                context.save()

        self.stdout.write(
            self.style.SUCCESS(f"✓ clima gravado para {len(parsed)} dias")
        )


def _read_rows(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        return list(data)
    return list(csv.DictReader(text.splitlines()))


def _parse(rows: list[dict]) -> dict:
    out: dict = {}
    for index, row in enumerate(rows, start=1):
        lowered = {str(k).strip().lower(): v for k, v in row.items() if k}
        raw_date = str(lowered.get("date") or lowered.get("data") or "").strip()
        if not raw_date:
            raise CommandError(f"linha {index}: sem data.")
        try:
            day = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
        except ValueError as exc:
            raise CommandError(f"linha {index}: data {raw_date!r} não é YYYY-MM-DD.") from exc

        values = {}
        for field, aliases in FIELD_ALIASES.items():
            values[field] = _decimal(lowered, aliases, index=index, field=field)
        out[day] = values
    return out


def _decimal(row: dict, aliases: tuple[str, ...], *, index: int, field: str):
    """Número ou None. Vazio é ausência de medição, nunca zero."""
    for alias in aliases:
        if alias not in row:
            continue
        raw = str(row[alias]).strip().replace(",", ".")
        if raw == "" or raw.lower() in {"na", "n/a", "null", "none", "-"}:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation as exc:
            raise CommandError(
                f"linha {index}: {field} = {row[alias]!r} não é número."
            ) from exc
    return None
