"""Backstage API — avaliações dos clientes no iFood (módulo Review).

GET  /api/v1/backstage/ifood/reviews/?page=&page_size=&date_from=&date_to=  → uma página
     ...?status=NOT_REPLIED|REPLIED                                     → todas da situação (abas)
GET  /api/v1/backstage/ifood/reviews/summary/                               → nota e contagens
GET  /api/v1/backstage/ifood/reviews/<review_id>/                           → detalhe
POST /api/v1/backstage/ifood/reviews/<review_id>/reply/  {"text": "..."}   → resposta

A recusa do iFood chega à tela no dialeto de erro da casa (``detail``), com o HTTP
e a mensagem original do iFood em ``ifood_status``/``ifood_message``: o operador lê
a frase em português, e a homologação vê a recusa exatamente como o iFood mandou.
O HTTP desta API repete o do iFood nos 4xx (400, 404, 409, 422...); falta de
resposta e 5xx do iFood viram 502.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta

from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.ifood_reviews import (
    STATUS_TAB_DEFAULT_DAYS,
    build_review_list_projection,
    build_summary_projection,
    project_review,
    with_order_refs,
)
from shopman.shop.services import business_calendar, ifood_review

from .permissions import HasBackstagePermission


def _error(exc: ifood_review.ReviewAPIError) -> Response:
    status = exc.status if 400 <= exc.status < 500 else http.HTTP_502_BAD_GATEWAY
    return Response(
        {"detail": str(exc), "ifood_status": exc.status, "ifood_message": exc.ifood_message},
        status=status,
    )


def _unavailable() -> Response:
    return Response(
        {"detail": "A integração com o iFood não está configurada neste ambiente."},
        status=http.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _bad(field: str, message: str) -> Response:
    return Response({"detail": message, "field": field, "errors": {field: [message]}}, status=400)


def _day_bound(raw: str, *, end: bool) -> datetime | None:
    """``AAAA-MM-DD`` da tela vira o início (ou o fim) do dia no fuso da loja."""
    day = date.fromisoformat(raw)
    tz = business_calendar.shop_timezone()
    return datetime.combine(day, time.max.replace(microsecond=0) if end else time.min, tzinfo=tz)


class _ReviewView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"


class IFoodReviewListView(_ReviewView):
    @extend_schema(tags=["backstage"], summary="Avaliações do iFood (uma página)")
    def get(self, request):
        if not ifood_review.enabled():
            return Response(asdict(build_review_list_projection()))
        try:
            page = int(request.query_params.get("page") or 1)
        except ValueError:
            return _bad("page", "A página precisa ser um número.")
        try:
            page_size = int(request.query_params.get("page_size") or ifood_review.DEFAULT_PAGE_SIZE)
        except ValueError:
            return _bad("page_size", "A quantidade por página precisa ser um número.")
        # Até 100 vai para o iFood como foi pedido (ele aceita 50 e recusa o resto,
        # com a mensagem dele); acima disso nem o teste de homologação pede.
        if not 1 <= page_size <= ifood_review.MAX_PAGE_SIZE_FORWARDED:
            return _bad("page_size", f"Escolha de 1 a {ifood_review.MAX_PAGE_SIZE_FORWARDED} por página.")
        try:
            date_from = (
                _day_bound(request.query_params["date_from"], end=False)
                if request.query_params.get("date_from")
                else None
            )
            date_to = (
                _day_bound(request.query_params["date_to"], end=True) if request.query_params.get("date_to") else None
            )
        except ValueError:
            return _bad("date_from", "Data em formato inválido.")
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status not in ifood_review.STATUSES:
            return _bad("status", "Situação desconhecida.")
        if status and date_from is None:
            # A aba por situação olha os últimos dias quando não há período.
            today = datetime.now(business_calendar.shop_timezone()).date()
            date_from = _day_bound((today - timedelta(days=STATUS_TAB_DEFAULT_DAYS)).isoformat(), end=False)
        if date_from and date_to and date_from > date_to:
            return _bad("date_to", "A data final é anterior à inicial.")
        try:
            projection = build_review_list_projection(
                page=page, page_size=page_size, date_from=date_from, date_to=date_to, status=status
            )
        except ifood_review.ReviewAPIError as exc:
            return _error(exc)
        return Response(asdict(projection))


class IFoodReviewSummaryView(_ReviewView):
    @extend_schema(tags=["backstage"], summary="Nota da loja no iFood")
    def get(self, request):
        if not ifood_review.enabled():
            return _unavailable()
        try:
            return Response(build_summary_projection())
        except ifood_review.ReviewAPIError as exc:
            return _error(exc)


class IFoodReviewDetailView(_ReviewView):
    @extend_schema(tags=["backstage"], summary="Uma avaliação do iFood")
    def get(self, request, review_id: str):
        if not ifood_review.enabled():
            return _unavailable()
        try:
            raw = ifood_review.get_review(review_id)
        except ifood_review.ReviewAPIError as exc:
            return _error(exc)
        return Response(asdict(with_order_refs([project_review(raw)])[0]))


class IFoodReviewReplyView(_ReviewView):
    @extend_schema(tags=["backstage"], summary="Responder uma avaliação do iFood")
    def post(self, request, review_id: str):
        if not ifood_review.enabled():
            return _unavailable()
        text = request.data.get("text") if isinstance(request.data, dict) else None
        if not isinstance(text, str):
            return _bad("text", "Escreva a resposta.")
        # O tamanho (10 a 300) é regra do iFood e quem decide é ele: ver o
        # cabeçalho de ``ifood_review``.
        try:
            answer = ifood_review.reply(review_id, text, actor=request.user.get_username())
        except ifood_review.ReviewAPIError as exc:
            return _error(exc)
        return Response(
            {
                "review_id": str(answer.get("reviewId") or review_id),
                "text": str(answer.get("text") or text),
                "created_at": str(answer.get("createdAt") or ""),
            },
            status=http.HTTP_201_CREATED,
        )
