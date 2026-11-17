"""iFood Review: as avaliações dos clientes da loja no iFood, lidas e respondidas pelo Gestor.

Contrato (documentação do módulo Review, lida em 17/11/2026):

- ``GET  /review/v2.0/merchants/{merchantId}/reviews`` — lista paginada. Parâmetros
  ``page`` (1 em diante), ``pageSize`` (o iFood aceita **no máximo 50** e devolve 400
  acima disso), ``addCount`` (traz ``total``/``pageCount``), ``dateFrom``/``dateTo`` em
  ISO 8601 com fuso, ``sort`` (``ASC``/``DESC``) e ``sortBy`` (``CREATED_AT``/``ORDER_DATE``).
- ``GET  /review/v2.0/merchants/{merchantId}/reviews/{reviewId}`` — detalhe com
  questionário, respostas e pedido; 404 quando o ID não existe.
- ``POST /review/v2.0/merchants/{merchantId}/reviews/{reviewId}/answers`` — resposta
  ``{"text": ...}`` de 10 a 300 caracteres; só em avaliação ``NOT_REPLIED`` (409 nos
  demais estados), 400 para tamanho inválido, 422 para conteúdo recusado.
- ``GET  /review/v2.0/merchants/{merchantId}/summary`` — nota e contagens.

Ciclo da avaliação: ``CREATED`` → ``NOT_REPLIED`` (nota 1 a 4 com comentário, 5 dias
para responder) ou ``PUBLISHED`` direto (nota 5, ou sem comentário). Respondida, vira
``REPLIED`` por 5 dias e depois ``PUBLISHED``. A moderação do iFood pode levar a
``DISCARDED``/``INVALID``.

⚠️ **O Shopman não valida o que o iFood valida.** Limite de página e tamanho do texto
vão para o iFood como o operador pediu, e a recusa do iFood volta para a tela com a
mensagem dele. Uma regra duplicada aqui envelheceria em silêncio quando o iFood mudar a
dele, e a tela passaria a mentir sobre o motivo da recusa. A tela mostra o contador e
o limite como orientação, não como portão.

Sem persistência: a fonte da verdade é o iFood, e a tela relê a cada gesto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from shopman.shop.services import ifood_http, ifood_merchant

logger = logging.getLogger(__name__)

#: Limite de página documentado pelo iFood (acima disto ele responde 400).
IFOOD_MAX_PAGE_SIZE = 50
#: Limite que o Shopman repassa: acima de 100 nem o teste de homologação pede.
MAX_PAGE_SIZE_FORWARDED = 100
DEFAULT_PAGE_SIZE = 10
#: Tamanho da resposta aceito pelo iFood (orientação da tela; quem decide é ele).
REPLY_MIN_CHARS = 10
REPLY_MAX_CHARS = 300

STATUSES = ("CREATED", "NOT_REPLIED", "REPLIED", "PUBLISHED", "DISCARDED", "INVALID")
#: Única situação em que o iFood aceita resposta.
REPLYABLE_STATUS = "NOT_REPLIED"

_REVIEW_PATH = "/review/v2.0/merchants/{merchant_id}"
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class ReviewUnavailable(Exception):
    """A integração não está configurada (sem client_id ou merchant_id)."""


class ReviewAPIError(Exception):
    """O iFood recusou ou não respondeu.

    ``status`` é o HTTP do iFood (0 quando não houve resposta utilizável) e
    ``ifood_message`` é o texto que ele mandou, sem tradução, para a tela poder
    mostrar a recusa como ela veio.
    """

    def __init__(self, message: str, *, status: int = 0, ifood_message: str = ""):
        super().__init__(message)
        self.status = status
        self.ifood_message = ifood_message

    @property
    def retryable(self) -> bool:
        return self.status == 0 or self.status in _RETRYABLE_STATUS


@dataclass(frozen=True)
class ReviewPage:
    page: int
    size: int
    total: int | None
    page_count: int | None
    reviews: tuple[dict, ...]


def enabled() -> bool:
    """Integração direta configurada: client_id e merchant_id presentes."""
    cfg = ifood_merchant._cfg()
    return bool(str(cfg.get("client_id") or "").strip()) and bool(ifood_merchant.merchant_id())


def _base() -> str:
    if not enabled():
        raise ReviewUnavailable("Integração com o iFood não configurada.")
    return _REVIEW_PATH.format(merchant_id=ifood_merchant.merchant_id())


# ── Leitura da recusa ─────────────────────────────────────────────────────────


def ifood_error_message(resp) -> str:
    """O texto da recusa como o iFood mandou.

    A documentação mostra três formas de corpo de erro, conforme a rota:
    ``{"error": "...", "status": 400}``, ``{"errorType": ..., "errorMessage": ...}`` e
    ``{"error": {"code": ..., "message": ...}}``. Corpo que não é JSON vira o texto cru.
    """
    try:
        body = resp.json()
    except ValueError:
        return (getattr(resp, "text", "") or "").strip()[:300]
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "")[:300]
    for key in ("errorMessage", "message", "detail"):
        if body.get(key):
            return str(body[key])[:300]
    if error:
        return str(error)[:300]
    return str(body.get("errorType") or "")[:300]


#: O que o operador lê, por HTTP do iFood. A mensagem original do iFood vai junto.
_OPERATOR_COPY = {
    400: "O iFood recusou o pedido: algum valor está fora do que ele aceita.",
    401: "O iFood não aceitou a credencial da integração.",
    403: "O iFood não deu acesso às avaliações desta loja.",
    404: "O iFood não encontrou esta avaliação.",
    409: "O iFood só aceita resposta em avaliação que está aguardando resposta.",
    422: "O iFood recusou o texto da resposta.",
    429: "O iFood pediu para esperar: muitas consultas seguidas. Tente de novo em instantes.",
}


def _raise_for(resp, *, label: str):
    if resp is None:
        raise ReviewAPIError("O iFood não respondeu. Tente de novo em instantes.", status=0)
    message = ifood_error_message(resp)
    status = resp.status_code
    copy = _OPERATOR_COPY.get(status) or "O iFood está com problema para responder. Tente de novo em instantes."
    logger.warning("ifood_review.%s: HTTP %s %s", label, status, message)
    raise ReviewAPIError(copy, status=status, ifood_message=message)


def _json(resp) -> dict:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


# ── Chamadas ──────────────────────────────────────────────────────────────────


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    # ISO 8601 com fuso, como a documentação pede (o ``Z`` de UTC também serve).
    return value.isoformat(timespec="seconds")


def list_reviews(
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "DESC",
    sort_by: str = "CREATED_AT",
) -> ReviewPage:
    params: dict[str, object] = {
        "page": max(1, int(page)),
        "pageSize": int(page_size),
        "addCount": "true",
        "sort": sort,
        "sortBy": sort_by,
    }
    if date_from is not None:
        params["dateFrom"] = _iso(date_from)
    if date_to is not None:
        params["dateTo"] = _iso(date_to)
    resp = ifood_http.request("GET", f"{_base()}/reviews", label="review_list", idempotent=True, params=params)
    if resp is None or resp.status_code != 200:
        _raise_for(resp, label="review_list")
    body = _json(resp)
    reviews = body.get("reviews") if isinstance(body.get("reviews"), list) else []
    return ReviewPage(
        page=int(body.get("page") or params["page"]),
        size=int(body.get("size") if body.get("size") is not None else len(reviews)),
        total=body.get("total"),
        page_count=body.get("pageCount"),
        reviews=tuple(r for r in reviews if isinstance(r, dict)),
    )


def get_review(review_id: str) -> dict:
    review_id = str(review_id or "").strip()
    resp = ifood_http.request("GET", f"{_base()}/reviews/{review_id}", label="review_detail", idempotent=True)
    if resp is None or resp.status_code != 200:
        _raise_for(resp, label="review_detail")
    return _json(resp)


def reply(review_id: str, text: str, *, actor: str = "") -> dict:
    """Responde a avaliação. Não é idempotente: falha ambígua não é repetida."""
    review_id = str(review_id or "").strip()
    resp = ifood_http.request(
        "POST",
        f"{_base()}/reviews/{review_id}/answers",
        label="review_reply",
        json={"text": text},
    )
    if resp is None or resp.status_code not in (200, 201):
        _raise_for(resp, label="review_reply")
    logger.info("ifood_review.reply: avaliação %s respondida por %s", review_id, actor or "?")
    return _json(resp)


def summary() -> dict:
    resp = ifood_http.request("GET", f"{_base()}/summary", label="review_summary", idempotent=True)
    if resp is None or resp.status_code != 200:
        _raise_for(resp, label="review_summary")
    return _json(resp)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "IFOOD_MAX_PAGE_SIZE",
    "MAX_PAGE_SIZE_FORWARDED",
    "REPLYABLE_STATUS",
    "REPLY_MAX_CHARS",
    "REPLY_MIN_CHARS",
    "ReviewAPIError",
    "ReviewPage",
    "ReviewUnavailable",
    "enabled",
    "get_review",
    "ifood_error_message",
    "list_reviews",
    "reply",
    "summary",
]
