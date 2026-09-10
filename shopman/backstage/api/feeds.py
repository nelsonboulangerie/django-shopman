"""
Backstage Feed API — Feeds (menuboard/Google/Meta) no Gestor.

Read = board dos feeds + coleções disponíveis; write = ligar/pausar e escolher
as coleções que cada feed exibe. Gate: ``shop.manage_catalog``.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.services import feeds as feed_service
from shopman.backstage.services.exceptions import CatalogError


class _FeedBase(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"


class FeedBoardView(_FeedBase):
    def get(self, request):
        from shopman.backstage.projections.feeds import build_feed_board

        return Response({"board": projection_data(build_feed_board())})


class FeedActiveView(_FeedBase):
    def post(self, request):
        ref = (request.data.get("ref") or "").strip()
        is_active = request.data.get("is_active")
        if not ref or not isinstance(is_active, bool):
            return Response({"detail": "ref e is_active (bool) são obrigatórios."}, status=400)
        try:
            feed_service.set_active(ref, is_active)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "ref": ref, "is_active": is_active})


class FeedCollectionsView(_FeedBase):
    def post(self, request):
        ref = (request.data.get("ref") or "").strip()
        collections = request.data.get("collections")
        if not ref or not isinstance(collections, list):
            return Response({"detail": "ref e collections (lista) são obrigatórios."}, status=400)
        try:
            feed_service.set_collections(ref, collections)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "ref": ref})


class FeedRotationView(_FeedBase):
    def post(self, request):
        ref = (request.data.get("ref") or "").strip()
        rotate_seconds = request.data.get("rotate_seconds")
        items_per_page = request.data.get("items_per_page")
        if not ref:
            return Response({"detail": "ref é obrigatório."}, status=400)
        try:
            feed_service.set_rotation(
                ref, rotate_seconds=rotate_seconds, items_per_page=items_per_page
            )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"ok": True, "ref": ref, "rotate_seconds": rotate_seconds, "items_per_page": items_per_page}
        )
