"""OperatorHubProjection — a Central de Apps (launcher pós-login).

Read model do "launcher" do operador: uma grade de tiles das superfícies de operador
(PDV · Cozinha · Gestor · Produção · Marketing · Loja), **permission-aware** — o app que o
operador não pode acessar nem aparece. É só um índice de navegação; não hospeda CRUD. O tile
Loja abre a **loja do cliente** (storefront) em nova aba — fora da zona de operador.

Registry declarativo (tipado aqui; caminho claro p/ configurável no Admin depois). Cada
tile carrega o predicado de permissão canônico de `backstage.permissions` — a mesma regra
que gateia a superfície dedicada e a sidebar. As URLs vêm de `settings.SHOPMAN_SURFACE_URLS`;
em prod são os subdomínios (`pdv.`/`kds.`/`gestor.`/`prod.`) e o apex da loja. Superfície
SEM URL configurada não vira tile (mesma regra de `shop.services.operator_links`: nunca
apontar para link morto) — o fallback 127.0.0.1 abaixo vale só em DEBUG.

Nunca importa de `shopman.backstage.views.*`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings

from shopman.backstage.permissions import (
    can_manage_campaigns,
    can_manage_orders,
    can_operate_kds,
    can_operate_pos,
    can_operate_production,
    can_operate_purchase,
    can_view_bi,
    is_superuser,
)

# URLs de DEV das superfícies — usadas apenas com DEBUG ligado, quando
# `settings.SHOPMAN_SURFACE_URLS` não cobre a superfície. Fora de DEBUG não há
# fallback: superfície sem URL fica fora do launcher.
DEV_SURFACE_URLS: dict[str, str] = {
    "pos": "http://127.0.0.1:3002/",
    "kds": "http://127.0.0.1:3003/",
    "gestor": "http://127.0.0.1:3004/",
    "production": "http://127.0.0.1:3005/",
    "marketing": "http://127.0.0.1:3006/",
    "bi": "http://127.0.0.1:3007/",
    "purchase": "http://127.0.0.1:3008/",
    "loja": "http://127.0.0.1:3000/",
}


@dataclass(frozen=True)
class HubTileProjection:
    """Um tile do launcher — uma superfície de operador que o usuário PODE abrir."""

    ref: str
    label: str
    description: str
    icon: str  # nome Lucide (ícone forte da superfície, DS §6)
    url: str
    kind: str  # "launch" (superfície de operador, mesma aba) | "external" (fora da zona, nova aba)


@dataclass(frozen=True)
class OperatorHubProjection:
    operator_name: str
    tiles: tuple[HubTileProjection, ...]


@dataclass(frozen=True)
class _AppSpec:
    ref: str
    label: str
    description: str
    icon: str
    kind: str
    can_access: Callable[[object], bool]


# Registro declarativo das superfícies (ordem = ordem de exibição). Ícone forte por
# app conforme o design system canônico (DS §6).
_REGISTRY: tuple[_AppSpec, ...] = (
    _AppSpec("pos", "PDV", "Vender no balcão", "banknote", "launch", can_operate_pos),
    _AppSpec("kds", "Cozinha", "Preparo e expedição", "chef-hat", "launch", can_operate_kds),
    _AppSpec("gestor", "Gestor de Pedidos", "Fila e acompanhamento", "clipboard-list", "launch", can_manage_orders),
    # ⚠️ `can_operate_production`, e NÃO `can_access_production`: o tile tem de
    # perguntar a MESMA coisa que o app pergunta na porta. O `can_access_production`
    # exige `shop.manage_production` ou alguma permissão de COLUNA FINA do console
    # Admin — nenhuma das duas é o gate do app.
    #
    # Errava nos dois sentidos. O gerente concede `operate_production` a um padeiro
    # novo; ele abre a Central e a grade vem VAZIA, dizendo "nenhum app liberado —
    # fale com o gerente" — enquanto `prod.boulangerie.com.br` abre normalmente. E
    # quem tem só `view_production_planned` VIA o tile e levava 403 ao clicar.
    #
    # Ninguém no ar hoje é afetado (Cozinha e Gerente têm as duas permissões), mas
    # qualquer grant customizado cai nele na hora — que é o caso normal quando entra
    # gente nova.
    _AppSpec("production", "Produção", "Produção e fornadas", "croissant", "launch", can_operate_production),
    _AppSpec("purchase", "Compras", "Comprar e receber insumos", "package-check", "launch", can_operate_purchase),
    _AppSpec("marketing", "Marketing", "Divulgar a fornada", "megaphone", "launch", can_manage_campaigns),
    _AppSpec("bi", "B.I.", "Números da operação", "chart-line", "launch", can_view_bi),
    _AppSpec("loja", "Loja online", "Abrir a loja do cliente", "store", "external", is_superuser),
)


def _surface_urls() -> dict[str, str]:
    base = DEV_SURFACE_URLS if settings.DEBUG else {}
    override = getattr(settings, "SHOPMAN_SURFACE_URLS", None) or {}
    return {**base, **override}


def _operator_name(user) -> str:
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or getattr(user, "username", "") or "Operador"


def build_operator_hub(user) -> OperatorHubProjection:
    """Monta o launcher para `user`, contendo APENAS os tiles que ele pode acessar."""
    urls = _surface_urls()
    tiles = tuple(
        HubTileProjection(
            ref=spec.ref,
            label=spec.label,
            description=spec.description,
            icon=spec.icon,
            url=urls[spec.ref],
            kind=spec.kind,
        )
        for spec in _REGISTRY
        if spec.can_access(user) and urls.get(spec.ref)
    )
    return OperatorHubProjection(operator_name=_operator_name(user), tiles=tiles)
