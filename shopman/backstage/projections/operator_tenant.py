"""OperatorTenantProjection — o nome da casa que os apps de operador mostram.

Os PWAs de operador se chamam ``"<casa> · <app>"`` ("Nelson · PDV"). O ``<casa>`` é
dado do tenant, não código: vem de ``Shop.short_name`` ("nome curto (PWA)", editável
no Admin). Esta projection é a única leitura dele para as superfícies de operador; o
BFF do ``operator-kit`` a consome para montar o ``/manifest.webmanifest`` e o título
da janela.

Sem fallback para a marca longa: ``short_name`` vazio volta vazio, e a superfície
mostra só o nome do app. Trocar para outro campo em silêncio seria uma segunda fonte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopman.shop.models import Shop


@dataclass(frozen=True)
class OperatorTenantProjection:
    short_name: str


def build_operator_tenant(shop: Shop | None) -> OperatorTenantProjection:
    short_name = (shop.short_name if shop is not None else "") or ""
    return OperatorTenantProjection(short_name=short_name.strip())
