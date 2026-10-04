"""OperatorHubProjection — a Central (launcher pós-login, e a home do Shopman).

Read model do "launcher" do operador: uma grade de tiles das superfícies de operador
(PDV · Cozinha · Gestor · Produção · Marketing · Loja), **permission-aware** — o app que o
operador não pode acessar nem aparece. Não hospeda CRUD: no topo, a fila "Precisa de você"
(``projections/hub_queue.py``) leva cada item ao lugar exato no app certo; embaixo, os blocos dos
apps, cada um com uma linha de estado que concorda com a fila (UX-H1). O tile
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
    can_expedite,
    can_manage_campaigns,
    can_operate_kds,
    can_operate_pos,
    can_operate_production,
    can_operate_purchase,
    can_view_bi,
    is_superuser,
)
from shopman.backstage.projections.hub_queue import HubQueueProjection, collect_hub_queue

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
    #: A linha de estado do bloco, que concorda com a fila "Precisa de você" (UX-H1).
    #: ``status_attention`` é o que pede alguém ("1 para aceitar"); ``status_summary`` é o
    #: resto, calmo ("11 ativos"). Vazios quando o app não tem fonte de estado.
    status_attention: str = ""
    status_summary: str = ""
    #: O estado bom e sabido ("Caixa aberto", "Aberta"): o ponto do bloco fica verde
    #: quando nada pede alguém. Vazio quando o app não tem estado positivo a dizer.
    status_positive: str = ""


@dataclass(frozen=True)
class OperatorHubProjection:
    operator_name: str
    tiles: tuple[HubTileProjection, ...]
    #: "Precisa de você": a soma das filas dos papéis do operador (`projections/hub_queue.py`).
    queue: HubQueueProjection


@dataclass(frozen=True)
class _AppSpec:
    ref: str
    label: str
    description: str
    icon: str
    kind: str
    can_access: Callable[[object], bool]
    #: Nome curto, onde o inteiro não cabe ao lado de outra coisa (a coluna do app na fila
    #: "Precisa de você"). Vazio = o próprio ``label``. Espelha ``shortLabel`` de
    #: ``app-identity.json`` (o mesmo teste de identidade compara os dois).
    short_label: str = ""

    @property
    def queue_label(self) -> str:
        return self.short_label or self.label


# Registro declarativo das superfícies (ordem = ordem de exibição). Ícone forte por
# app conforme o design system canônico (DS §6).
#
# ⚠️ O `label` e o `icon` de cada app têm de bater com
# `surfaces/operator-kit/app-identity.json`, a identidade que as próprias superfícies
# publicam (manifesto, barra de título, rail). Um app com dois nomes é o que o dono viu:
# o tile dizia "Gestor de Pedidos", a janela dizia "Gestor". O Python não lê o JSON em
# runtime (o deploy do Django não empacota `surfaces/`); quem compara os dois lados é
# `shopman/backstage/tests/test_hub_projection_identity.py`, que falha no CI se
# divergirem. A Loja fica de fora: é superfície de cliente, com marca própria.
#
# O nome Lucide é o FALLBACK do tile:
# a Central mostra o PNG da família PWA (`surfaces/operator-kit/PWA_ICONS.md`) e só
# cai no Lucide quando a imagem não carrega — por isso os nomes seguem a família
# (Produção usa `tabler:baguette` no PNG; o fallback fica em `croissant`, único
# símbolo próximo que existe no Lucide).
_REGISTRY: tuple[_AppSpec, ...] = (
    _AppSpec("pos", "PDV", "Vender no balcão", "shopping-basket", "launch", can_operate_pos),
    _AppSpec("kds", "Cozinha", "Preparo e saída", "chef-hat", "launch", can_operate_kds),
    _AppSpec("gestor", "Gestor de pedidos", "Fila e acompanhamento", "square-kanban", "launch", can_expedite, "Gestor"),
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
    _AppSpec("production", "Produção", "Produção e lotes", "croissant", "launch", can_operate_production),
    _AppSpec("purchase", "Compras", "Comprar e receber insumos", "package", "launch", can_operate_purchase),
    _AppSpec("marketing", "Marketing", "Divulgar o lote", "megaphone", "launch", can_manage_campaigns),
    _AppSpec("bi", "B.I.", "Números da operação", "chart-no-axes-combined", "launch", can_view_bi),
    _AppSpec("loja", "Loja online", "Abrir a loja do cliente", "store", "external", is_superuser),
)


def _surface_urls() -> dict[str, str]:
    base = DEV_SURFACE_URLS if settings.DEBUG else {}
    override = getattr(settings, "SHOPMAN_SURFACE_URLS", None) or {}
    return {**base, **override}


def accessible_surfaces(user) -> dict[str, tuple[str, str]]:
    """Os apps de operador que ``user`` abre, na ordem do launcher: ``ref → (nome curto, URL)``.

    A mesma pergunta do tile (permissão do app e URL configurada); a Loja fica de fora (é a
    superfície do cliente, não um lugar de trabalho). A busca da suíte
    (``projections/suite_search.py``) só aponta para estes.
    """
    urls = _surface_urls()
    return {
        spec.ref: (spec.queue_label, urls[spec.ref])
        for spec in _REGISTRY
        if spec.kind == "launch" and urls.get(spec.ref) and spec.can_access(user)
    }


def purchase_surface_url(user) -> str:
    """URL do Compras para um atalho vindo de outro app ("Pedir no Compras").

    A mesma pergunta que o tile do launcher faz: quem não opera Compras, ou
    superfície sem URL, recebe vazio, e o atalho não aparece.
    """
    if not can_operate_purchase(user):
        return ""
    return _surface_urls().get("purchase", "")


def _operator_name(user) -> str:
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or getattr(user, "username", "") or "Operador"


def build_operator_hub(user) -> OperatorHubProjection:
    """Monta a Central para `user`: APENAS os tiles que ele pode acessar, e a fila
    "Precisa de você" com os itens em que ele pode agir."""
    urls = _surface_urls()
    visible = [spec for spec in _REGISTRY if spec.can_access(user) and urls.get(spec.ref)]
    # Só app que o operador abre entra na fila: o item leva para dentro dele.
    queue, statuses = collect_hub_queue(
        user,
        urls={spec.ref: urls[spec.ref] for spec in visible},
        labels={spec.ref: spec.queue_label for spec in visible},
    )
    tiles = tuple(
        HubTileProjection(
            ref=spec.ref,
            label=spec.label,
            description=spec.description,
            icon=spec.icon,
            url=urls[spec.ref],
            kind=spec.kind,
            status_attention=statuses[spec.ref].attention if spec.ref in statuses else "",
            status_summary=statuses[spec.ref].summary if spec.ref in statuses else "",
            status_positive=statuses[spec.ref].positive if spec.ref in statuses else "",
        )
        for spec in visible
    )
    return OperatorHubProjection(operator_name=_operator_name(user), tiles=tiles, queue=queue)
