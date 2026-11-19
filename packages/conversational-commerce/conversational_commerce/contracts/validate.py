"""Validação, leitura e escrita de contratos, dirigidas pela anotação de tipo.

Um validador só serve os 17 contratos: ele lê as anotações da dataclass
(``typing.get_type_hints``) e confere cada campo. O que a anotação não diz
(combinações proibidas, ordem de instantes, soma de totais) mora no método
``check()`` de cada contrato.

Tipos que a anotação pode usar, e mais nenhum:

- ``str``, ``int`` (nunca ``bool``), ``bool``;
- ``Literal[...]`` de strings (enum fechado);
- ``Annotated[tipo, Rule.X]`` (``common.Rule``);
- ``X | None`` (opcional ou anulável);
- união de ``Value`` discriminada por um campo ``Literal`` de valor único;
- ``tuple[X, ...]`` (lista imutável) e ``Mapping[str, X]`` (vira ``FrozenMap``);
- uma subclasse de ``Value``.

Na escrita, campo opcional vazio (``None``, lista vazia, mapa vazio) é omitido:
ausente e vazio são o mesmo, e a forma canônica não os carrega. É o que deixa um
MENOR novo (campo opcional a mais) produzir o mesmo hash que o anterior quando o
campo novo está vazio. Um ``JsonValue`` obrigatório pode valer ``null`` e aí
sai ``null``; dentro de um valor livre, ``null`` e vazio são do dono do valor e
ficam.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import re
import types
import typing
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from functools import cache
from typing import Any

from .canonical import MAX_SAFE_INTEGER, FrozenMap, freeze_json, sha256_hash, thaw_json
from .common import ObservationRecord, Record, Rule, StrictRecord, Value
from .errors import ContractError, invalid, unsupported

RESERVED_KEYS = frozenset({"schema", "kind"})

_PATTERNS: dict[Rule, re.Pattern[str]] = {
    Rule.INSTANT: re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"),
    Rule.CURRENCY: re.compile(r"[A-Z]{3}"),
    # Sem zero à esquerda nem à direita; "-0" não existe (o zero é "0").
    Rule.DECIMAL: re.compile(r"(?!-0$)-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?"),
    Rule.HASH: re.compile(r"sha256:[0-9a-f]{64}"),
    Rule.VERSION: re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"),
}

# Exposto para o schema_export: o mesmo padrão, ancorado, para o JSON Schema.
PATTERNS: dict[Rule, str] = {rule: f"^{pattern.pattern}$" for rule, pattern in _PATTERNS.items()}


# ── leitura das anotações ────────────────────────────────────────────────────


@cache
def contract_fields(cls: type) -> tuple[tuple[str, Any, bool], ...]:
    """(nome, anotação, tem_default) de cada campo do contrato, na ordem da classe."""
    hints = typing.get_type_hints(cls, include_extras=True)
    result = []
    for f in dataclasses.fields(cls):
        has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
        result.append((f.name, hints[f.name], has_default))
    return tuple(result)


def split_annotated(tp: Any) -> tuple[Any, tuple[Rule, ...]]:
    if typing.get_origin(tp) is typing.Annotated:
        base, *extras = typing.get_args(tp)
        return base, tuple(extra for extra in extras if isinstance(extra, Rule))
    return tp, ()


def union_args(tp: Any) -> tuple[Any, ...] | None:
    origin = typing.get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        return typing.get_args(tp)
    return None


def is_nullable(tp: Any) -> bool:
    args = union_args(tp)
    return args is not None and type(None) in args


def discriminator(cls: type) -> tuple[str, str]:
    """O campo ``Literal`` de valor único que identifica ``cls`` numa união."""
    for name, tp, _ in contract_fields(cls):
        base, _ = split_annotated(tp)
        if typing.get_origin(base) is typing.Literal and len(typing.get_args(base)) == 1:
            return name, typing.get_args(base)[0]
    raise TypeError(f"{cls.__name__} está numa união sem campo discriminador")


# ── coerção: valor de fio ou de Python → valor do contrato ───────────────────


def coerce(tp: Any, value: Any, path: tuple[str | int, ...]) -> Any:
    base, rules = split_annotated(tp)
    result = _coerce_base(base, value, path)
    for rule in rules:
        _apply_rule(rule, result, path)
    return result


def _coerce_base(tp: Any, value: Any, path: tuple[str | int, ...]) -> Any:
    args = union_args(tp)
    if args is not None:
        options = tuple(arg for arg in args if arg is not type(None))
        if value is None:
            if len(options) < len(args):
                return None
            raise invalid("campo obrigatório é nulo", *path)
        if len(options) == 1:
            return coerce(options[0], value, path)
        return _coerce_tagged_union(options, value, path)

    if value is None and tp is not Any:
        raise invalid("campo obrigatório é nulo", *path)

    if isinstance(value, float):
        raise invalid("número de ponto flutuante não é permitido; use inteiro ou decimal em texto", *path)

    origin = typing.get_origin(tp)
    if origin is typing.Literal:
        allowed = typing.get_args(tp)
        if not isinstance(value, str) or value not in allowed:
            raise invalid(f"valor fora do enum {list(allowed)}: {value!r}", *path)
        return value
    if origin is tuple:
        item_tp = typing.get_args(tp)[0]
        if isinstance(value, str | bytes) or not isinstance(value, collections.abc.Sequence):
            raise invalid("lista esperada", *path)
        return tuple(coerce(item_tp, item, (*path, index)) for index, item in enumerate(value))
    if origin is collections.abc.Mapping:
        _, item_tp = typing.get_args(tp)
        if not isinstance(value, Mapping):
            raise invalid("objeto esperado", *path)
        out = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise invalid("chave de mapa precisa ser texto não vazio", *path)
            out[key] = coerce(item_tp, item, (*path, key))
        return FrozenMap(out)
    if tp is Any:
        return freeze_json(value, path)
    if tp is FrozenMap:
        if not isinstance(value, Mapping):
            raise invalid("objeto esperado", *path)
        return freeze_json(value, path)
    if tp is bool:
        if not isinstance(value, bool):
            raise invalid("booleano esperado", *path)
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise invalid("inteiro esperado", *path)
        if abs(value) > MAX_SAFE_INTEGER:
            raise invalid("inteiro fora da faixa segura ±(2**53 - 1)", *path)
        return value
    if tp is str:
        if not isinstance(value, str):
            raise invalid("texto esperado", *path)
        return value
    if isinstance(tp, type) and issubclass(tp, Value):
        if isinstance(value, tp):
            return value
        if isinstance(value, Mapping):
            return build(tp, value, path)
        raise invalid(f"objeto {tp.__name__} esperado", *path)
    raise TypeError(f"anotação não suportada no contrato: {tp!r}")


def _coerce_tagged_union(options: tuple[Any, ...], value: Any, path: tuple[str | int, ...]) -> Any:
    for option in options:
        if isinstance(value, option):
            return value
    if not isinstance(value, Mapping):
        raise invalid("objeto esperado", *path)
    tags = []
    for option in options:
        key, tag = discriminator(option)
        tags.append(tag)
        if value.get(key) == tag:
            return build(option, value, path)
    raise invalid(f"objeto não corresponde a nenhuma das formas {tags}", *path)


def _apply_rule(rule: Rule, value: Any, path: tuple[str | int, ...]) -> None:
    if rule is Rule.IDENTIFIER or rule is Rule.TEXT:
        if not value or value != value.strip():
            raise invalid("texto vazio ou com espaço nas pontas", *path)
        if rule is Rule.IDENTIFIER and any(ch.isspace() for ch in value):
            raise invalid("identificador não tem espaço", *path)
    elif rule is Rule.NON_NEGATIVE:
        if value < 0:
            raise invalid("inteiro não pode ser negativo", *path)
    elif rule is Rule.POSITIVE:
        if value < 1:
            raise invalid("inteiro precisa ser positivo", *path)
    elif rule in _PATTERNS:
        if not _PATTERNS[rule].fullmatch(value):
            raise invalid(f"formato {rule.value} inválido: {value!r}", *path)
        if rule is Rule.INSTANT:
            try:
                datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError as exc:
                raise invalid(f"instante inexistente: {value!r}", *path) from exc
    # JSON e JSON_OBJECT já foram conferidos na coerção.


# ── construção a partir de mapa ──────────────────────────────────────────────


def build(cls: type, data: Mapping[str, Any], path: tuple[str | int, ...] = ()) -> Any:
    """Monta um ``Value`` estrito a partir de um mapa: campo desconhecido é recusa."""
    known = {name for name, _, _ in contract_fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise invalid(f"campo desconhecido: {unknown}", *path)
    return _construct(cls, data, path, {})


def _construct(cls: type, data: Mapping[str, Any], path: tuple[str | int, ...], extra: dict[str, Any]) -> Any:
    kwargs = dict(extra)
    for name, tp, has_default in contract_fields(cls):
        if name in data:
            kwargs[name] = coerce(tp, data[name], (*path, name))
        elif has_default or name in kwargs:
            continue
        elif is_nullable(tp):
            kwargs[name] = None
        else:
            raise invalid("campo obrigatório ausente", *path, name)
    try:
        return cls(**kwargs)
    except ContractError as exc:
        raise exc.prefixed(*path) from None


# ── validação no construtor ──────────────────────────────────────────────────


def check_instance(obj: Any) -> None:
    """Chamado pelo ``__post_init__`` de todo contrato: normaliza e valida."""
    cls = type(obj)
    if isinstance(obj, Record) and not obj.schema_version:
        object.__setattr__(obj, "schema_version", cls.VERSION)
    for name, tp, _ in contract_fields(cls):
        value = getattr(obj, name)
        coerced = coerce(tp, value, (name,))
        if coerced is not value:
            object.__setattr__(obj, name, coerced)
    if isinstance(obj, Record):
        _check_envelope(obj)
    obj.check()
    if isinstance(obj, Record) and cls.HASH_FIELD is not None:
        stated = getattr(obj, cls.HASH_FIELD)
        if stated is not None and stated != compute_hash(obj):
            raise invalid("hash não confere com o documento", cls.HASH_FIELD)


def _major_minor(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def _check_envelope(record: Record) -> None:
    cls = type(record)
    if not cls.SCHEMA or not cls.KIND:
        raise TypeError(f"{cls.__name__} não declara SCHEMA e KIND")
    version = record.schema_version
    if isinstance(record, StrictRecord):
        if version not in cls.SUPPORTED_VERSIONS:
            raise unsupported(f"{cls.SCHEMA} {version} não suportada (suportadas: {sorted(cls.SUPPORTED_VERSIONS)})",
                              "schema_version")
    elif isinstance(record, ObservationRecord):
        major, minor = _major_minor(version)
        current_major, current_minor = _major_minor(cls.VERSION)
        if major != current_major:
            raise unsupported(f"{cls.SCHEMA} {version}: MAIOR diferente de {current_major}", "schema_version")
        if record.extensions:
            if minor <= current_minor:
                raise invalid(f"campo desconhecido {sorted(record.extensions)} sem MENOR acima de {cls.VERSION}",
                              "extensions")
            clash = sorted(set(record.extensions) & (_field_names(cls) | RESERVED_KEYS))
            if clash:
                raise invalid(f"extensão com nome de campo do contrato: {clash}", "extensions")


def _field_names(cls: type) -> frozenset[str]:
    return frozenset(name for name, _, _ in contract_fields(cls))


# ── leitura de documento ─────────────────────────────────────────────────────


def parse_record(cls: type[Record], document: Mapping[str, Any]) -> Record:
    """Lê ``document`` como ``cls``.

    Ordem das recusas: não é objeto → ``invalid_content``; ``schema`` de outro
    contrato ou versão fora do que o leitor aceita → ``unsupported_schema``;
    ``kind`` errado, campo desconhecido onde não cabe, tipo errado, hash que
    não confere → ``invalid_content``.
    """
    if not isinstance(document, Mapping):
        raise invalid("documento precisa ser um objeto JSON")
    if document.get("schema") != cls.SCHEMA:
        raise unsupported(f"esperado schema {cls.SCHEMA!r}, veio {document.get('schema')!r}", "schema")
    if document.get("kind") != cls.KIND:
        raise invalid(f"esperado kind {cls.KIND!r}, veio {document.get('kind')!r}", "kind")
    version = document.get("schema_version")
    if not isinstance(version, str) or not _PATTERNS[Rule.VERSION].fullmatch(version):
        raise unsupported(f"schema_version ausente ou fora do formato MAIOR.MENOR: {version!r}", "schema_version")

    names = _field_names(cls)
    unknown = {key: value for key, value in document.items() if key not in names and key not in RESERVED_KEYS}
    extra: dict[str, Any] = {}
    if issubclass(cls, StrictRecord):
        if version not in cls.SUPPORTED_VERSIONS:
            raise unsupported(f"{cls.SCHEMA} {version} não suportada", "schema_version")
        if unknown:
            raise invalid(f"campo desconhecido: {sorted(unknown)}")
    else:
        major, minor = _major_minor(version)
        current_major, current_minor = _major_minor(cls.VERSION)
        if major != current_major:
            raise unsupported(f"{cls.SCHEMA} {version}: MAIOR diferente de {current_major}", "schema_version")
        if "extensions" in document:
            raise invalid("extensions não é campo de fio: o desconhecido vem no nível de cima", "extensions")
        if unknown:
            if minor <= current_minor:
                raise invalid(f"campo desconhecido: {sorted(unknown)}")
            extra["extensions"] = freeze_json(unknown)
    if cls.HASH_FIELD is not None and document.get(cls.HASH_FIELD) is None:
        raise invalid("documento com hash precisa trazer o hash", cls.HASH_FIELD)
    return _construct(cls, document, (), extra)


# ── escrita ──────────────────────────────────────────────────────────────────


def encode_value(value: Any) -> Any:
    if isinstance(value, Value | Record):
        out: dict[str, Any] = {}
        for name, tp, has_default in contract_fields(type(value)):
            item = getattr(value, name)
            if name == "extensions":
                continue
            if _omitted(item, tp, has_default):
                continue
            out[name] = encode_value(item)
        return out
    if isinstance(value, FrozenMap | Mapping):
        return {key: encode_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [encode_value(item) for item in value]
    return value


def _omitted(item: Any, tp: Any, has_default: bool) -> bool:
    """Campo opcional no valor vazio (nulo, lista vazia, mapa vazio) não sai no documento."""
    if item is None:
        return has_default or is_nullable(tp)
    if has_default and isinstance(item, tuple | Mapping) and len(item) == 0:
        return True
    return False


def encode_record(record: Record) -> dict[str, Any]:
    """O documento do registro: campos conhecidos, ``schema``, ``kind`` e as extensões no nível de cima."""
    cls = type(record)
    document = {"schema": cls.SCHEMA, "kind": cls.KIND}
    document.update(encode_value(record))
    if isinstance(record, ObservationRecord):
        document.update(thaw_json(record.extensions))
    return document


def hash_input(record: Record) -> dict[str, Any]:
    """O que entra no hash: o documento sem o próprio hash e sem ``recorded_at``."""
    document = encode_record(record)
    document.pop(type(record).HASH_FIELD or "", None)
    document.pop("recorded_at", None)
    return document


def compute_hash(record: Record) -> str:
    return sha256_hash(hash_input(record))


def seal(record: Record) -> Record:
    """Uma cópia de ``record`` com o hash calculado (o produtor chama isto)."""
    field_name = type(record).HASH_FIELD
    if field_name is None:
        raise TypeError(f"{type(record).__name__} não tem campo de hash")
    return dataclasses.replace(record, **{field_name: compute_hash(record)})


# ── ajudas para os check() dos contratos ─────────────────────────────────────


def require_order(earlier: str | None, later: str | None, field_name: str, *, strict: bool = False) -> None:
    """``later`` não pode vir antes de ``earlier`` (instantes no formato canônico comparam como texto)."""
    if earlier is None or later is None:
        return
    if later < earlier or (strict and later == earlier):
        raise invalid(f"{field_name} precisa vir {'depois' if strict else 'no mesmo instante ou depois'} de {earlier}",
                      field_name)


def require_unique(values: typing.Iterable[str], field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise invalid(f"valor repetido: {value!r}", field_name)
        seen.add(value)


def probability(text: str, *path: str | int) -> Decimal:
    """Decimal em texto entre 0 e 1."""
    value = Decimal(text)
    if not (0 <= value <= 1):
        raise invalid(f"probabilidade fora de [0, 1]: {text}", *path)
    return value
