"""A Central e as superfícies chamam cada app pelo MESMO nome.

O dono viu um app com dois nomes: o tile da Central dizia "Gestor de Pedidos", a barra
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

IDENTITY_PATH = (
    Path(__file__).resolve().parents[3] / "surfaces" / "operator-kit" / "app-identity.json"
)

# `ref` do tile na Central → chave do app na identidade das superfícies. A Loja não
# entra: é superfície de cliente, fora da família de operador.
TILE_TO_APP = {
    "pos": "pos",
    "kds": "kds",
    "gestor": "orders",
    "production": "production",
    "purchase": "purchase",
    "marketing": "marketing",
    "bi": "bi",
}


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
    """Superfície nova sem tile é app que ninguém acha; a Central é o único launcher."""
    identity = _identity()
    # A Central é o próprio launcher: não tem tile dentro de si.
    expected = {app for app in identity if app != "hub"}
    assert set(TILE_TO_APP.values()) == expected


def test_no_tile_label_uses_a_hyphen_as_separator() -> None:
    """Separador de nome nesta casa é o ponto médio, nunca hífen, travessão ou barra."""
    import re

    offenders = [spec.label for spec in _REGISTRY if re.search(r"\s[-–—|]\s", spec.label)]
    assert offenders == []
