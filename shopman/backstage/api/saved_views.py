"""Leituras salvas (os favoritos do painel de filtros): CRUD por pessoa, por tela.

WP-FASE2-UX-OPERADOR, K4. Cada tela que oferece favoritos se declara em ``SCREENS``:
a permissão de quem lê aquela tela e a gramática do recorte dela. Tela que não está
ali não guarda favorito (a borda recusa), e recorte fora da gramática não salva.

- ``GET  saved-views/?surface=orders&screen=history`` → os seus, fixados primeiro.
- ``POST saved-views/`` ``{surface, screen, name, query, pinned?}`` → salva; o mesmo nome
  na mesma tela atualiza, não duplica.
- ``PATCH saved-views/<id>/`` ``{name?, pinned?}`` → renomeia e/ou fixa.
- ``DELETE saved-views/<id>/`` → apaga.

O favorito alheio não existe para quem pergunta (404), nem para ler nem para apagar.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.parsing import as_bool
from shopman.backstage.projections.bi_explore import ExploreError, validate_config

from .permissions import HasBackstagePermission

NAME_MAX_LENGTH = 80
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_MAX_DIMENSIONS = 20
_MAX_VALUES = 50
_MAX_VALUE_LENGTH = 120
_PERIOD_KEYS = {"preset", "from", "to"}


class QueryError(ValueError):
    """O recorte não cabe na gramática da tela."""


def _text(value, *, field: str) -> str:
    if not isinstance(value, str):
        raise QueryError(f"{field} precisa ser texto.")
    if len(value) > _MAX_VALUE_LENGTH:
        raise QueryError(f"{field} passa de {_MAX_VALUE_LENGTH} caracteres.")
    return value


def screen_query(raw) -> dict:
    """A gramática do recorte de uma lista: filtros por dimensão, período e agrupamento.

    ``{"filters": {"payment": ["pix", "card"]}, "period": {"preset": "7d", "from": "",
    "to": ""}, "group": "channel"}``. Os valores são as chaves que a tela já põe na
    URL; quem os interpreta é a tela (a mesma regra do ``FilterBar``).
    """
    if not isinstance(raw, dict):
        raise QueryError("O recorte precisa ser um objeto.")
    unknown = set(raw) - {"filters", "period", "group"}
    if unknown:
        raise QueryError(f"Chaves desconhecidas no recorte: {', '.join(sorted(unknown))}.")
    filters = raw.get("filters") or {}
    if not isinstance(filters, dict):
        raise QueryError("Os filtros precisam ser um objeto.")
    if len(filters) > _MAX_DIMENSIONS:
        raise QueryError(f"Mais de {_MAX_DIMENSIONS} filtros num favorito.")
    clean_filters: dict[str, list[str]] = {}
    for key, values in filters.items():
        if not isinstance(key, str) or not _KEY.match(key):
            raise QueryError(f"Filtro com nome inválido: {key!r}.")
        if not isinstance(values, list) or len(values) > _MAX_VALUES:
            raise QueryError(f"O filtro {key} precisa ser uma lista de até {_MAX_VALUES} valores.")
        clean_filters[key] = [_text(value, field=f"Valor de {key}") for value in values]
    query: dict = {"filters": clean_filters}
    period = raw.get("period")
    if period not in (None, {}):
        if not isinstance(period, dict) or set(period) - _PERIOD_KEYS:
            raise QueryError("O período aceita só: preset, from, to.")
        query["period"] = {key: _text(period.get(key) or "", field=f"Período ({key})") for key in sorted(_PERIOD_KEYS)}
    group = raw.get("group")
    if group not in (None, ""):
        if not isinstance(group, str) or not _KEY.match(group):
            raise QueryError("Agrupamento com nome inválido.")
        query["group"] = group
    return query


_BI_WINDOW_KEYS = {"preset", "from", "to"}


def bi_explore_query(raw) -> dict:
    """O cenário do explorador do B.I.: ``{metric, by, by2, window}`` pela gramática dele."""
    if not isinstance(raw, dict):
        raise QueryError("A config do cenário precisa ser um objeto.")
    unknown = set(raw) - {"metric", "by", "by2", "window"}
    if unknown:
        raise QueryError(f"Chaves desconhecidas na config: {', '.join(sorted(unknown))}.")
    try:
        validate_config(str(raw.get("metric") or ""), str(raw.get("by") or "time"), str(raw.get("by2") or ""))
    except ExploreError as exc:
        raise QueryError(str(exc)) from exc
    window = raw.get("window") or {}
    if not isinstance(window, dict) or set(window) - _BI_WINDOW_KEYS:
        raise QueryError("Janela do cenário aceita só: preset, from, to.")
    return {
        "metric": raw["metric"],
        "by": raw.get("by") or "time",
        "by2": raw.get("by2") or "",
        "window": {key: str(window[key]) for key in window},
    }


@dataclass(frozen=True)
class Screen:
    permission: str
    validate: Callable[[object], dict]


# As telas que guardam favorito. Nova tela entra aqui com a permissão de quem a lê.
SCREENS: dict[tuple[str, str], Screen] = {
    ("bi", "explore"): Screen("backstage.view_bi", bi_explore_query),
    ("orders", "queue"): Screen("shop.manage_orders", screen_query),
    ("orders", "history"): Screen("shop.manage_orders", screen_query),
    ("orders", "catalog"): Screen("shop.manage_catalog", screen_query),
    ("orders", "customers"): Screen("shop.manage_customers", screen_query),
    # As Encomendas do PDV: o balcão as lê (a lista pede também `shop.manage_orders`,
    # que o grupo Caixa tem; o favorito é do balcão).
    ("pos", "preorders"): Screen("cashman.operate_pos", screen_query),
}


def _payload(view) -> dict:
    return {
        "id": view.pk,
        "surface": view.surface,
        "screen": view.screen,
        "name": view.name,
        "query": view.query,
        "pinned": view.pinned,
    }


def _screen(request, surface: str, screen: str) -> tuple[Screen | None, Response | None]:
    entry = SCREENS.get((surface, screen))
    if entry is None:
        return None, Response(
            {"detail": f"A tela {surface}/{screen} não guarda favoritos.", "field": "screen"}, status=400
        )
    if not request.user.has_perm(entry.permission):
        return None, Response({"detail": "Você não tem acesso a esta tela."}, status=403)
    return entry, None


def _name(raw) -> str:
    return str(raw or "").strip()[:NAME_MAX_LENGTH]


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="List my saved views of a screen",
        responses={200: OpenApiResponse(description="The saved views, pinned first.")},
    ),
    post=extend_schema(
        tags=["backstage"],
        summary="Save the current view of a screen (validated by the screen's grammar)",
        responses={200: OpenApiResponse(description="The saved view.")},
    ),
)
class SavedViewListView(APIView):
    permission_classes = [HasBackstagePermission]

    def get(self, request):
        from shopman.backstage.models import SavedView

        surface = str(request.GET.get("surface") or "")
        screen = str(request.GET.get("screen") or "")
        _entry, refusal = _screen(request, surface, screen)
        if refusal:
            return refusal
        views = SavedView.objects.filter(owner=request.user, surface=surface, screen=screen)
        return Response({"views": [_payload(view) for view in views]})

    def post(self, request):
        from shopman.backstage.models import SavedView

        data = request.data or {}
        surface = str(data.get("surface") or "")
        screen = str(data.get("screen") or "")
        entry, refusal = _screen(request, surface, screen)
        if refusal:
            return refusal
        name = _name(data.get("name"))
        if not name:
            return Response({"detail": "Dê um nome ao favorito.", "field": "name"}, status=400)
        try:
            query = entry.validate(data.get("query"))
        except QueryError as exc:
            return Response({"detail": str(exc), "field": "query"}, status=400)
        defaults = {"query": query}
        if "pinned" in data:
            defaults["pinned"] = as_bool(data, "pinned")
        view, _created = SavedView.objects.update_or_create(
            owner=request.user, surface=surface, screen=screen, name=name, defaults=defaults
        )
        return Response({"ok": True, "view": _payload(view)})


@extend_schema_view(
    patch=extend_schema(
        tags=["backstage"],
        summary="Rename or pin a saved view",
        responses={200: OpenApiResponse(description="The saved view.")},
    ),
    delete=extend_schema(
        tags=["backstage"],
        summary="Delete a saved view",
        responses={200: OpenApiResponse(description="Deleted.")},
    ),
)
class SavedViewDetailView(APIView):
    permission_classes = [HasBackstagePermission]

    def _get(self, request, pk: int):
        from shopman.backstage.models import SavedView

        return SavedView.objects.filter(owner=request.user, pk=pk).first()

    def patch(self, request, pk: int):
        view = self._get(request, pk)
        if view is None:
            return Response({"detail": "Favorito não encontrado."}, status=404)
        data = request.data or {}
        fields: list[str] = []
        if "name" in data:
            name = _name(data.get("name"))
            if not name:
                return Response({"detail": "Dê um nome ao favorito.", "field": "name"}, status=400)
            view.name = name
            fields.append("name")
        if "pinned" in data:
            view.pinned = as_bool(data, "pinned")
            fields.append("pinned")
        if not fields:
            return Response({"detail": "Diga o que muda: name ou pinned."}, status=400)
        try:
            with transaction.atomic():
                view.save(update_fields=[*fields, "updated_at"])
        except IntegrityError:
            return Response(
                {"detail": "Você já tem um favorito com esse nome nesta tela.", "field": "name"}, status=400
            )
        return Response({"ok": True, "view": _payload(view)})

    def delete(self, request, pk: int):
        view = self._get(request, pk)
        if view is None:
            return Response({"detail": "Favorito não encontrado."}, status=404)
        view.delete()
        return Response({"ok": True})
