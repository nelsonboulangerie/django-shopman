"""Dataclass → TypeScript contract rendering for the operator surfaces.

The Nuxt operator apps used to hand-sync the projection shapes in TypeScript —
a fragile manual mirror where a renamed dataclass field broke nothing at build
time. Following the ``export_pos_schema`` pattern, the ``export_*_schema``
management commands render the projection dataclasses into generated
TypeScript modules that the surfaces import, and a drift test per contract
regenerates the file in-memory and compares it to disk (``--check``).

This module holds the shared, deterministic rendering: Python type hints are
mapped structurally to TypeScript (``str``→``string``, ``tuple[X, ...]``→
``X[]``, ``X | None``→``X | null``, ``dict``→``Record``). Narrowings that only
the surface knows (e.g. timer-class unions) live in each app's ``types/``
module, layered on top of the generated interfaces.
"""

from __future__ import annotations

import datetime
import json
import types
import typing
from dataclasses import fields, is_dataclass
from pathlib import Path

from django.conf import settings

_SCALAR_TS = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    # ``projection_data`` serializa date/datetime como string ISO.
    datetime.date: "string",
    datetime.datetime: "string",
    typing.Any: "unknown",
}


def _ts_type(tp: object, known: frozenset[str]) -> str:
    """Map one Python type annotation to its TypeScript source text."""
    if tp is type(None):
        return "null"
    if tp in _SCALAR_TS:
        return _SCALAR_TS[tp]  # type: ignore[index]

    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    if origin in (typing.Union, types.UnionType):
        # Render "X | null" with null last, deterministically.
        members = [a for a in args if a is not type(None)]
        rendered = [_ts_type(a, known) for a in members]
        if len(members) < len(args):
            rendered.append("null")
        return " | ".join(rendered)

    if origin is typing.Literal:
        return " | ".join(json.dumps(value, ensure_ascii=False) for value in args)

    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return _ts_array(_ts_type(args[0], known))
        raise TypeError(f"Unsupported fixed-length tuple in contract: {tp!r}")

    if origin is list:
        return _ts_array(_ts_type(args[0], known)) if args else "unknown[]"

    if origin is dict:
        if args:
            return f"Record<{_ts_type(args[0], known)}, {_ts_type(args[1], known)}>"
        return "Record<string, unknown>"
    if tp is dict:
        return "Record<string, unknown>"

    if is_dataclass(tp):
        name = tp.__name__  # type: ignore[union-attr]
        if name not in known:
            raise TypeError(
                f"Dataclass {name} referenced but not exported — add it to the "
                "contract's dataclass list (before its first reference)."
            )
        return name

    raise TypeError(f"Unsupported type in contract rendering: {tp!r}")


def _ts_array(inner: str) -> str:
    if " | " in inner:
        return f"({inner})[]"
    return f"{inner}[]"


def render_ts_interface(dc: type, known: frozenset[str]) -> str:
    """Render one projection dataclass as an exported TypeScript interface."""
    hints = typing.get_type_hints(dc)
    doc = (dc.__doc__ or "").strip().splitlines()[0].strip() if dc.__doc__ else ""
    lines: list[str] = []
    if doc:
        lines.append(f"/** {doc} */")
    lines.append(f"export interface {dc.__name__} {{")
    for field in fields(dc):
        lines.append(f"  {field.name}: {_ts_type(hints[field.name], known)};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_contract_module(
    *,
    source: str,
    command: str,
    dataclasses: tuple[type, ...],
    extra_blocks: tuple[str, ...] = (),
) -> str:
    """Render a generated TypeScript contract module (deterministic).

    ``dataclasses`` must list every exported projection, with each dataclass
    appearing no later than its first reference by another one.
    """
    known = frozenset(dc.__name__ for dc in dataclasses)
    blocks = [
        "// AUTO-GENERATED — do not edit by hand.",
        f"// Source of truth: {source}",
        f"// Regenerate with: python manage.py {command}",
        "",
    ]
    blocks.extend(render_ts_interface(dc, known) for dc in dataclasses)
    blocks.extend(extra_blocks)
    return "\n".join(blocks).rstrip() + "\n"


def render_serializer_interfaces(
    serializers: tuple[tuple[str, type], ...],
) -> str:
    """Render DRF Serializer fields as closed TypeScript request interfaces."""
    from rest_framework import serializers as drf

    names = {serializer: name for name, serializer in serializers}

    def field_type(field) -> str:
        if isinstance(field, drf.ListSerializer):
            child_name = names.get(type(field.child))
            if child_name is None:
                raise TypeError(
                    f"Nested serializer {type(field.child).__name__} is not exported"
                )
            rendered = f"{child_name}[]"
        elif isinstance(field, drf.ChoiceField):
            rendered = " | ".join(
                json.dumps(str(value), ensure_ascii=False)
                for value in field.choices
            )
        elif isinstance(field, drf.DecimalField):
            # JSON transports exact quantities as decimal strings.
            rendered = "string"
        elif isinstance(field, (drf.IntegerField, drf.FloatField)):
            rendered = "number"
        elif isinstance(field, drf.BooleanField):
            rendered = "boolean"
        elif isinstance(field, (drf.DateField, drf.DateTimeField, drf.CharField)):
            rendered = "string"
        else:
            raise TypeError(
                f"Unsupported serializer field in production contract: {type(field).__name__}"
            )
        if getattr(field, "allow_null", False):
            rendered += " | null"
        return rendered

    blocks: list[str] = []
    for name, serializer_class in serializers:
        instance = serializer_class()
        lines = [f"export interface {name} {{"]
        for field_name, field in instance.fields.items():
            optional = "" if field.required else "?"
            lines.append(f"  {field_name}{optional}: {field_type(field)};")
        lines.append("}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def render_action_client(specs: tuple[object, ...]) -> str:
    """Render one Nuxt mutation client from canonical backend action specs."""
    lines = [
        "/** Generated production writer. Errors use the envelopes above. */",
        "async function postProductionMutation<T>(href: string, body: unknown): Promise<T> {",
        "  const post = $fetch as unknown as (",
        "    request: string,",
        '    options: { method: "POST"; body: unknown },',
        "  ) => Promise<T>;",
        '  return post(href, { method: "POST", body });',
        "}",
        "",
    ]
    for spec in specs:
        response_name = spec.response.__name__
        if spec.work_order_path:
            signature = f"workOrderId: number, body: {spec.request_name}"
            href = "`" + spec.href.replace("{workOrderId}", "${workOrderId}") + "`"
        else:
            signature = f"body: {spec.request_name}"
            href = json.dumps(spec.href)
        lines.extend(
            [
                f"export function {spec.function_name}({signature}): Promise<{response_name}> {{",
                f"  return postProductionMutation<{response_name}>({href}, body);",
                "}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run_contract_export(command, *, relative_path: Path, rendered: str, check: bool) -> None:
    """Shared ``handle()`` body for the export_*_schema commands.

    Mirrors ``export_pos_schema``: ``--check`` exits non-zero when the file on
    disk diverges from the in-memory render; otherwise the file is (re)written.
    """
    path = Path(settings.BASE_DIR) / relative_path
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if check:
        if current != rendered:
            command.stderr.write(
                command.style.ERROR(
                    f"{relative_path} is stale. Run: python manage.py {command_name(command)}"
                )
            )
            raise SystemExit(1)
        command.stdout.write(command.style.SUCCESS(f"{relative_path} is up to date."))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    command.stdout.write(command.style.SUCCESS(f"Wrote {relative_path}"))


def command_name(command) -> str:
    return type(command).__module__.rsplit(".", 1)[-1]
