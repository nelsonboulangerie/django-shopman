"""Projeção "Avaliações do iFood" para o Gestor de pedidos.

Lê o que ``shopman.shop.services.ifood_review`` traz do iFood e devolve o que a
tela precisa ler: nota, comentário, situação em palavras, visibilidade, respostas
e o pedido avaliado. Os campos que o iFood marca como obrigatórios na lista
(``id``, ``status``, ``replies``, ``version``, ``visibility``) aparecem todos, crus
ao lado da palavra, porque são eles que a homologação confere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils.dateparse import parse_datetime
from shopman.utils.formatting import format_local

from shopman.shop.services import ifood_review

#: Política de Avaliações do iFood: link obrigatório na tela (critério de homologação).
POLICY_URL = "https://portal.ifood.com.br/evaluation-policies"

STATUS_LABELS = {
    "CREATED": "Recebida",
    "NOT_REPLIED": "Aguardando resposta",
    "REPLIED": "Respondida",
    "PUBLISHED": "Publicada",
    "DISCARDED": "Descartada pelo iFood",
    "INVALID": "Invalidada pelo iFood",
}
VISIBILITY_LABELS = {"PUBLIC": "Pública", "PRIVATE": "Privada"}
REPLY_FROM_LABELS = {"MERCHANT": "Loja", "CUSTOMER": "Cliente"}


@dataclass(frozen=True)
class ReviewReply:
    text: str
    author: str
    author_label: str
    created_at: str
    created_at_display: str


@dataclass(frozen=True)
class ReviewQuestion:
    title: str
    kind: str
    answers: tuple[str, ...]


@dataclass(frozen=True)
class ReviewProjection:
    id: str
    status: str
    status_label: str
    visibility: str
    visibility_label: str
    version: str
    score: float | None
    score_display: str
    previous_score: float | None
    score_changed: bool
    comment: str
    customer_name: str
    created_at: str
    created_at_display: str
    order_id: str
    order_short_id: str
    order_created_at_display: str
    replies: tuple[ReviewReply, ...]
    questions: tuple[ReviewQuestion, ...] = ()
    survey_id: str = ""
    can_reply: bool = False


@dataclass(frozen=True)
class ReviewListProjection:
    enabled: bool
    policy_url: str = POLICY_URL
    page: int = 1
    page_size: int = ifood_review.DEFAULT_PAGE_SIZE
    total: int | None = None
    page_count: int | None = None
    reviews: tuple[ReviewProjection, ...] = ()
    reply_min_chars: int = ifood_review.REPLY_MIN_CHARS
    reply_max_chars: int = ifood_review.REPLY_MAX_CHARS
    ifood_max_page_size: int = ifood_review.IFOOD_MAX_PAGE_SIZE


def _when(value) -> tuple[str, str]:
    raw = str(value or "")
    parsed: datetime | None = parse_datetime(raw) if raw else None
    return raw, (format_local(parsed, "%d/%m/%Y às {clock}") if parsed else "")


def _score(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _score_display(score: float | None) -> str:
    if score is None:
        return ""
    text = f"{score:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def project_review(raw: dict) -> ReviewProjection:
    status = str(raw.get("status") or "")
    visibility = str(raw.get("visibility") or "")
    created_at, created_display = _when(raw.get("createdAt"))
    order = raw.get("order") if isinstance(raw.get("order"), dict) else {}
    _, order_created_display = _when(order.get("createdAt"))
    replies = []
    for reply in raw.get("replies") or []:
        if not isinstance(reply, dict):
            continue
        author = str(reply.get("from") or "")
        reply_at, reply_display = _when(reply.get("createdAt"))
        replies.append(
            ReviewReply(
                text=str(reply.get("text") or ""),
                author=author,
                author_label=REPLY_FROM_LABELS.get(author, author),
                created_at=reply_at,
                created_at_display=reply_display,
            )
        )
    questions = []
    for question in raw.get("questions") or []:
        if not isinstance(question, dict):
            continue
        answers = tuple(str(a.get("title") or "") for a in question.get("answers") or [] if isinstance(a, dict))
        questions.append(
            ReviewQuestion(
                title=str(question.get("title") or ""), kind=str(question.get("type") or ""), answers=answers
            )
        )
    score = _score(raw.get("score"))
    return ReviewProjection(
        id=str(raw.get("id") or ""),
        status=status,
        status_label=STATUS_LABELS.get(status, status),
        visibility=visibility,
        visibility_label=VISIBILITY_LABELS.get(visibility, visibility),
        version=str(raw.get("version") or ""),
        score=score,
        score_display=_score_display(score),
        previous_score=_score(raw.get("previousScore")),
        score_changed=bool(raw.get("hasScoreChanged")),
        comment=str(raw.get("comment") or ""),
        customer_name=str(raw.get("customerName") or ""),
        created_at=created_at,
        created_at_display=created_display,
        order_id=str(order.get("id") or ""),
        order_short_id=str(order.get("shortId") or ""),
        order_created_at_display=order_created_display,
        replies=tuple(replies),
        questions=tuple(questions),
        survey_id=str(raw.get("surveyId") or ""),
        can_reply=status == ifood_review.REPLYABLE_STATUS,
    )


def build_review_list_projection(
    *,
    page: int = 1,
    page_size: int = ifood_review.DEFAULT_PAGE_SIZE,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> ReviewListProjection:
    """Uma página de avaliações. Recusa do iFood sobe como ``ReviewAPIError``."""
    if not ifood_review.enabled():
        return ReviewListProjection(enabled=False)
    result = ifood_review.list_reviews(page=page, page_size=page_size, date_from=date_from, date_to=date_to)
    return ReviewListProjection(
        enabled=True,
        page=result.page,
        page_size=page_size,
        total=result.total,
        page_count=result.page_count,
        reviews=tuple(project_review(raw) for raw in result.reviews),
    )


def build_summary_projection() -> dict:
    raw = ifood_review.summary()
    score = _score(raw.get("score"))
    return {
        "score": score,
        "score_display": _score_display(score),
        "total_reviews": raw.get("totalReviewsCount"),
        "valid_reviews": raw.get("validReviewsCount"),
    }
