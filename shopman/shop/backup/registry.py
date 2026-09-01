"""Registro das entidades do cofre — quem entra, com que nome, em que ordem.

O registro é a costura de extensibilidade do cofre: um app novo (ou uma entidade
nova) entra com UMA chamada de ``register()`` no seu ``AppConfig.ready()``, e os
comandos ``export_backup``/``import_backup`` passam a cobri-la sem mudança.

O ``tier`` é a ordem de import (menor primeiro): uma entidade só pode referenciar
por chave natural entidades de tier menor. Export usa a mesma ordem, então o
arquivo lê na ordem em que restaura.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BackupEntry:
    """Uma entidade do cofre: nome da aba, resource e tier de dependência.

    ``read_only`` marca as abas de conferência (transacionais): entram no
    export sob demanda e o import as RECUSA — restaurar transacional é papel
    do backup do banco, nunca de planilha.
    """

    name: str
    resource_class: type
    tier: int
    read_only: bool = False
    order: int = field(compare=False, default=0)


_entries: dict[str, BackupEntry] = {}

#: Limite do XLSX: nome de aba tem no máximo 31 caracteres.
_MAX_SHEET_NAME = 31


def register(name: str, resource_class: type, *, tier: int, read_only: bool = False) -> None:
    """Registra uma entidade no cofre. Nome duplicado é erro de programação."""
    if name in _entries:
        raise ValueError(f"Entidade de backup já registrada: {name!r}")
    if len(name) > _MAX_SHEET_NAME:
        raise ValueError(f"Nome de aba excede {_MAX_SHEET_NAME} caracteres: {name!r}")
    _entries[name] = BackupEntry(
        name=name,
        resource_class=resource_class,
        tier=tier,
        read_only=read_only,
        order=len(_entries),
    )


def entries() -> list[BackupEntry]:
    """Entidades registradas, na ordem de import (tier, depois registro)."""
    return sorted(_entries.values(), key=lambda e: (e.tier, e.order))


def get(name: str) -> BackupEntry | None:
    return _entries.get(name)
