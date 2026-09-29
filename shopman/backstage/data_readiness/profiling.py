"""Sanitized, read-only profiling for external data artifacts.

The profiler deliberately emits structure and aggregate counts, never cell or
element values.  That makes its JSON report suitable for review and CI while
the source artifact remains in the private landing area.
"""

from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import sqlite3
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeElementTree

PROFILE_SCHEMA_VERSION = "shopman.data-artifact-profile/v1"
SUPPORTED_SUFFIXES = frozenset({".csv", ".json", ".sqlite", ".sqlite3", ".db", ".xlsx", ".xml"})


class ArtifactProfileError(ValueError):
    """The artifact cannot be profiled safely or does not match the requested selectors."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = (text, text.replace("/", "-"))
    for candidate in candidates:
        if "T" not in candidate and " " not in candidate:
            try:
                return date.fromisoformat(candidate).isoformat()
            except ValueError:  # silêncio-deliberado: tentar o próximo formato de data
                pass
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:  # silêncio-deliberado: tentar o próximo formato de data
            continue
        return _iso(parsed)
    return None


def _selector_map(selectors: Sequence[str]) -> dict[str, tuple[str, ...]]:
    mapped: dict[str, list[str]] = {}
    for selector in selectors:
        scope, separator, field = selector.partition(":")
        if not separator:
            scope, field = "*", scope
        scope, field = scope.strip(), field.strip()
        if not scope or not field:
            raise ArtifactProfileError(f"Seletor inválido: {selector!r}. Use CAMPO ou ESCOPO:CAMPO.")
        mapped.setdefault(scope, []).append(field)
    return {scope: tuple(fields) for scope, fields in mapped.items()}


def _selectors_for(mapping: dict[str, tuple[str, ...]], scope: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*mapping.get("*", ()), *mapping.get(scope, ()))))


def _tabular_profile(
    *,
    name: str,
    headers: Sequence[Any],
    rows: Iterable[Sequence[Any]],
    key_fields: tuple[str, ...],
    date_fields: tuple[str, ...],
) -> dict[str, Any]:
    columns = [str(value or "").strip() for value in headers]
    if not columns or not any(columns):
        raise ArtifactProfileError(f"{name}: cabeçalho vazio.")
    if not all(columns) or len(set(columns)) != len(columns):
        raise ArtifactProfileError(f"{name}: há nomes de coluna vazios ou duplicados.")

    requested = tuple(dict.fromkeys((*key_fields, *date_fields)))
    missing = [field for field in requested if field not in columns]
    if missing:
        raise ArtifactProfileError(f"{name}: campos solicitados ausentes: {', '.join(missing)}.")

    indexes = {field: columns.index(field) for field in requested}
    rows_raw = rows_valid = rows_blank = 0
    null_counts = Counter(dict.fromkeys(requested, 0))
    distinct_keys: set[tuple[str, ...]] = set()
    duplicate_keys = 0
    date_ranges: dict[str, list[str | None]] = {field: [None, None] for field in date_fields}

    for row in rows:
        rows_raw += 1
        values = list(row)
        if not any(value not in (None, "") for value in values):
            rows_blank += 1
            continue
        rows_valid += 1
        for field, index in indexes.items():
            value = values[index] if index < len(values) else None
            if value in (None, ""):
                null_counts[field] += 1

        if key_fields:
            key = tuple(
                str(values[indexes[field]]).strip() if indexes[field] < len(values) else ""
                for field in key_fields
            )
            if all(key):
                if key in distinct_keys:
                    duplicate_keys += 1
                else:
                    distinct_keys.add(key)

        for field in date_fields:
            index = indexes[field]
            normalized = _iso(values[index] if index < len(values) else None)
            if normalized is None:
                continue
            current = date_ranges[field]
            current[0] = min(filter(None, (current[0], normalized)), default=normalized)
            current[1] = max(filter(None, (current[1], normalized)), default=normalized)

    return {
        "name": name,
        "columns": columns,
        "rows_raw": rows_raw,
        "rows_valid": rows_valid,
        "rows_blank": rows_blank,
        "key_fields": list(key_fields),
        "distinct_keys": len(distinct_keys) if key_fields else None,
        "duplicate_keys": duplicate_keys if key_fields else None,
        "null_counts": dict(sorted(null_counts.items())),
        "date_ranges": {
            field: {"min": bounds[0], "max": bounds[1]} for field, bounds in sorted(date_ranges.items())
        },
    }


def _csv_profile(
    path: Path,
    *,
    keys: dict[str, tuple[str, ...]],
    dates: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    encoding = None
    sample = ""
    for candidate in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            sample = path.read_text(encoding=candidate)[:65536]
        except UnicodeDecodeError:
            continue
        encoding = candidate
        break
    if encoding is None:
        raise ArtifactProfileError("CSV sem encoding suportado (utf-8/latin-1).")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, dialect)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ArtifactProfileError("CSV vazio.") from exc
        table = _tabular_profile(
            name="csv",
            headers=headers,
            rows=reader,
            key_fields=_selectors_for(keys, "csv"),
            date_fields=_selectors_for(dates, "csv"),
        )
    return {"encoding": encoding, "delimiter": dialect.delimiter, "tables": [table]}


def _xlsx_profile(
    path: Path,
    *,
    keys: dict[str, tuple[str, ...]],
    dates: dict[str, tuple[str, ...]],
) -> dict[str, Any]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise ArtifactProfileError("openpyxl não está instalado.") from exc

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        tables = []
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            try:
                headers = next(rows)
            except StopIteration:
                tables.append({"name": sheet.title, "columns": [], "rows_raw": 0, "rows_valid": 0, "rows_blank": 0})
                continue
            tables.append(
                _tabular_profile(
                    name=sheet.title,
                    headers=headers,
                    rows=rows,
                    key_fields=_selectors_for(keys, sheet.title),
                    date_fields=_selectors_for(dates, sheet.title),
                )
            )
    finally:
        workbook.close()
    return {"tables": tables}


def _xml_profile(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    try:
        for _event, element in SafeElementTree.iterparse(path, events=("end",)):
            local_name = element.tag.rsplit("}", 1)[-1]
            counts[local_name] += 1
            element.clear()
    except Exception as exc:
        raise ArtifactProfileError(f"XML inseguro ou inválido: {type(exc).__name__}.") from exc
    return {"element_counts": dict(sorted(counts.items())), "elements_total": sum(counts.values())}


def _sqlite_profile(path: Path) -> dict[str, Any]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        tables = []
        for name in names:
            escaped = name.replace('"', '""')
            columns = [
                {"name": row[1], "type": row[2], "not_null": bool(row[3]), "primary_key": bool(row[5])}
                for row in connection.execute(f'PRAGMA table_info("{escaped}")')
            ]
            rows = connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0]
            tables.append({"name": name, "columns": columns, "rows_raw": rows})
    except sqlite3.Error as exc:
        raise ArtifactProfileError(f"SQLite inválido ou ilegível: {exc}.") from exc
    finally:
        if "connection" in locals():
            connection.close()
    return {"tables": tables}


def _json_profile(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactProfileError("JSON inválido ou fora de UTF-8.") from exc
    if isinstance(payload, list):
        object_rows = sum(isinstance(item, dict) for item in payload)
        schemas = Counter(tuple(sorted(item)) for item in payload if isinstance(item, dict))
        return {
            "root_type": "array",
            "rows_raw": len(payload),
            "object_rows": object_rows,
            "schemas": [{"columns": list(columns), "rows": count} for columns, count in sorted(schemas.items())],
        }
    if isinstance(payload, dict):
        return {"root_type": "object", "columns": sorted(payload), "rows_raw": 1}
    return {"root_type": type(payload).__name__, "rows_raw": 1}


def profile_artifact(
    path: str | Path,
    *,
    source: str,
    purpose: str,
    logical_name: str | None = None,
    key_fields: Sequence[str] = (),
    date_fields: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a sanitized manifest without changing the artifact or the database."""

    artifact = Path(path)
    if not artifact.is_file():
        raise ArtifactProfileError("Artefato não encontrado ou não é um arquivo regular.")
    suffix = artifact.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ArtifactProfileError(f"Formato não suportado: {suffix or 'sem extensão'}.")
    source = source.strip()
    purpose = purpose.strip()
    if not source or not purpose:
        raise ArtifactProfileError("source e purpose são obrigatórios.")

    keys = _selector_map(tuple(key_fields))
    dates = _selector_map(tuple(date_fields))
    if suffix == ".csv":
        details = _csv_profile(artifact, keys=keys, dates=dates)
    elif suffix == ".xlsx":
        details = _xlsx_profile(artifact, keys=keys, dates=dates)
    elif suffix == ".xml":
        if keys or dates:
            raise ArtifactProfileError("Seletores de chave/data ainda não se aplicam a XML.")
        details = _xml_profile(artifact)
    elif suffix in {".sqlite", ".sqlite3", ".db"}:
        if keys or dates:
            raise ArtifactProfileError("Seletores de chave/data ainda não se aplicam a SQLite.")
        details = _sqlite_profile(artifact)
    else:
        if keys or dates:
            raise ArtifactProfileError("Seletores de chave/data ainda não se aplicam a JSON.")
        details = _json_profile(artifact)

    stat = artifact.stat()
    manifest = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "source": source,
        "purpose": purpose,
        "logical_name": (logical_name or artifact.name).strip(),
        "sha256": _sha256(artifact),
        "bytes": stat.st_size,
        "format": suffix.removeprefix("."),
        "mime_type": mimetypes.guess_type(artifact.name)[0] or "application/octet-stream",
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace("+00:00", "Z"),
        "profile": details,
    }
    # A report must never reveal where on a person's machine the source lived.
    assert str(artifact.parent) not in json.dumps(manifest, ensure_ascii=False)
    return manifest
