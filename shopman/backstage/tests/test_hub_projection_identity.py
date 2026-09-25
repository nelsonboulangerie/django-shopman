"""O Shopman Apps e as superfícies chamam cada app pelo MESMO nome.

O dono viu um app com dois nomes: o tile do launcher dizia "Gestor de Pedidos", a barra
de título da janela dizia "Gestor"; a Cozinha era "Cozinha" no rail e "KDS" no título.
A identidade canônica passou a viver em `surfaces/operator-kit/app-identity.json` — é
dela que saem manifesto, barra de título, ícone e rail.

O Django não lê esse arquivo em runtime: o deploy do backend não empacota `surfaces/`,
e um import que só existe no repositório de desenvolvimento seria uma bomba em produção.
Então os dois lados seguem escritos, e é este teste que os mantém iguais — o CI lembra
no lugar de alguém.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopman.backstage.projections.hub import _REGISTRY
from shopman.shop.models.push_subscription import PushSurface
from shopman.shop.services.operator_capacity import SERVICE_LABELS

SURFACES_DIR = Path(__file__).resolve().parents[3] / "surfaces"
IDENTITY_PATH = SURFACES_DIR / "operator-kit" / "app-identity.json"
REGISTRY_PATH = SURFACES_DIR / "registry.json"


def _tile_to_app() -> dict[str, str]:
    """`ref` do tile no launcher → chave do app, lido do registro único das superfícies.

    A Loja não entra: é superfície de cliente, fora da família de operador. Fora do
    repositório (sem `surfaces/`) não há o que comparar.
    """
    if not REGISTRY_PATH.exists():  # pragma: no cover - só fora do repositório
        return {}
    surfaces = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["surfaces"]
    return {s["hub_tile"]: app for app, s in surfaces.items() if s["kind"] == "operator" and s["hub_tile"]}


TILE_TO_APP = _tile_to_app()


def _identity() -> dict:
    if not IDENTITY_PATH.exists():  # pragma: no cover - só fora do repositório
        pytest.skip(f"identidade das superfícies ausente: {IDENTITY_PATH}")
    return json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))["apps"]


@pytest.mark.parametrize(("tile_ref", "app"), sorted(TILE_TO_APP.items()))
def test_tile_label_matches_surface_label(tile_ref: str, app: str) -> None:
    """O nome no tile é o nome na barra de título — letra por letra."""
    spec = next(spec for spec in _REGISTRY if spec.ref == tile_ref)
    assert spec.label == _identity()[app]["label"], (
        f"o tile '{tile_ref}' chama o app de {spec.label!r} e a própria superfície se "
        f"chama {_identity()[app]['label']!r} — um app, um nome"
    )


@pytest.mark.parametrize(("tile_ref", "app"), sorted(TILE_TO_APP.items()))
def test_tile_fallback_icon_matches_surface(tile_ref: str, app: str) -> None:
    """O Lucide de recurso do tile é o mesmo que o rail do app usa quando o PNG falha."""
    spec = next(spec for spec in _REGISTRY if spec.ref == tile_ref)
    assert spec.icon == _identity()[app]["fallbackIcon"]


def test_every_operator_app_has_a_tile() -> None:
    """Superfície nova sem tile é app que ninguém acha; o Shopman Apps é o único launcher."""
    identity = _identity()
    # O Shopman Apps é o próprio launcher: não tem tile dentro de si.
    expected = {app for app in identity if app != "hub"}
    assert set(TILE_TO_APP.values()) == expected


def test_no_tile_label_uses_a_hyphen_as_separator() -> None:
    """Separador de nome nesta casa é o ponto médio, nunca hífen, travessão ou barra."""
    import re

    offenders = [spec.label for spec in _REGISTRY if re.search(r"\s[-–—|]\s", spec.label)]
    assert offenders == []


def test_the_launcher_has_one_name_on_both_sides() -> None:
    """O launcher tem UM nome — inclusive nas telas do Django que falam dele.

    O nome vivia em três lugares do lado Python (o rótulo do serviço na capacidade, a
    superfície de push, e a própria tela) sem nada que os comparasse; bastava consertar
    um para os outros dois envelhecerem calados. O lado TS já lê tudo do
    `app-identity.json`; aqui a string é repetida por necessidade, então é o CI que
    compara.
    """
    name = _identity()["hub"]["label"]
    assert SERVICE_LABELS["hub"] == name
    assert PushSurface.HUB.label == name


# Onde a porta pede outra coisa que o tile — só com motivo escrito. O tile do
# Marketing também aceita `shop.manage_campaigns` na janela de migração do app
# (`permissions.can_manage_campaigns`); a porta pede só `shop.view_marketing`.
TILE_WIDER_THAN_DOOR = {"marketing": "janela de migração de shop.manage_campaigns (can_manage_campaigns)"}


def _door_permission(app: str) -> str:
    """A permissão que o app pede na porta (`const OPERATOR_PERM = "..."` na casca)."""
    import re

    found = {
        match
        for path in (SURFACES_DIR / f"{app}-nuxt" / "app").rglob("*.vue")
        for match in re.findall(r'const OPERATOR_PERM = "([a-z_]+\.[a-z_]+)"', path.read_text(encoding="utf-8"))
    }
    assert len(found) == 1, f"{app}: esperava uma permissão de porta, achei {sorted(found)}"
    return found.pop()


class _UserWith:
    """Usuário de mentira: tem exatamente as permissões dadas (ou todas, menos uma)."""

    is_superuser = False
    is_staff = True

    def __init__(self, *, only: str | None = None, all_but: str | None = None):
        self.only, self.all_but = only, all_but

    def has_perm(self, perm: str) -> bool:
        return perm == self.only if self.only is not None else perm != self.all_but


@pytest.mark.parametrize(("tile_ref", "app"), sorted(TILE_TO_APP.items()))
def test_the_tile_asks_what_the_app_door_asks(tile_ref: str, app: str) -> None:
    """Quem recebe a permissão da porta vê o tile; quem não a tem, não vê.

    Nos dois sentidos o defeito já existiu: o padeiro com `operate_production` via a
    grade VAZIA enquanto o app abria, e quem tinha outra permissão via o tile e
    levava 403 ao clicar. App novo (`make new-surface`) nasce com os dois no mesmo
    predicado; este teste impede que eles se separem depois.
    """
    spec = next(spec for spec in _REGISTRY if spec.ref == tile_ref)
    door = _door_permission(app)
    assert spec.can_access(_UserWith(only=door)), f"{tile_ref}: quem tem {door} abre o app e não vê o tile"
    if app in TILE_WIDER_THAN_DOOR:
        return
    assert not spec.can_access(_UserWith(all_but=door)), f"{tile_ref}: o tile aparece para quem a porta de {app} recusa"
