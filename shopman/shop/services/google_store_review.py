"""O estado, no Google, dos dois recursos da loja física: retirada e disponibilidade na loja.

O Merchant Center revisa à parte dois recursos da loja (issue #2652): a
**retirada no mesmo dia** (``pickup``) e as **páginas de produto com
disponibilidade na loja** (``inStock``). Aprovar ou negar chegava só por e-mail;
a aba Canais do Gestor passa a mostrar o estado.

Quem lê é o próprio app, com a conta de serviço que já faz o envio do catálogo,
só leitura: ``GET /accounts/v1/accounts/{conta}/omnichannelSettings`` (Merchant
API). Cada configuração (uma por país) traz ``pickup.state`` e ``inStock.state``
em ``ACTIVE``, ``FAILED``, ``RUNNING`` ou ``ACTION_REQUIRED``. **O recurso não traz
o motivo da recusa** (referência conferida em 17/11/2026): o motivo mora no
Merchant Center, e a tela leva até lá em vez de inventar texto.

A leitura roda no ``maintenance_worker`` (``sync_platform_catalogs``), no máximo
uma vez por :data:`READ_EVERY`, e fica no cache compartilhado (Redis em
produção) até a próxima. A tela só lê o cache: abrir Canais não chama o Google.
Leitura que falhou é guardada como falha, com a hora: a tela diz que não leu, e
nunca mostra "aprovado" por falta de dado.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY = "shopman:google_store_review"
#: De quanto em quanto tempo o worker pergunta ao Google. A revisão do Google
#: leva dias; uma hora basta para a tela acompanhar.
READ_EVERY = timedelta(hours=1)
#: O cache guarda a leitura por bem mais que a cadência: worker parado por um
#: dia não apaga o último estado, só o envelhece (a tela mostra a hora).
CACHE_TTL_SECONDS = int(timedelta(days=7).total_seconds())

#: País das configurações da loja (``regionCode`` CLDR).
REGION = "BR"

ACTIVE = "ACTIVE"
FAILED = "FAILED"
RUNNING = "RUNNING"
ACTION_REQUIRED = "ACTION_REQUIRED"
#: A conta não tem o recurso pedido (ou não tem configuração para o país).
NOT_REQUESTED = "NOT_REQUESTED"


@dataclass(frozen=True)
class StoreReview:
    """Uma leitura do estado dos dois recursos, com a hora."""

    checked_at: datetime
    #: A leitura deu certo. ``False``: ``error`` diz por quê, e os estados são vazios.
    ok: bool
    pickup: str = ""
    in_stock: str = ""
    error: str = ""


def last_review() -> StoreReview | None:
    """A última leitura guardada, ou ``None`` quando nenhuma foi feita ainda."""
    raw = cache.get(CACHE_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        checked_at = datetime.fromisoformat(str(raw["checked_at"]))
    except (KeyError, ValueError):
        return None
    return StoreReview(
        checked_at=checked_at,
        ok=bool(raw.get("ok")),
        pickup=str(raw.get("pickup") or ""),
        in_stock=str(raw.get("in_stock") or ""),
        error=str(raw.get("error") or ""),
    )


def _store(review: StoreReview) -> None:
    data = asdict(review)
    data["checked_at"] = review.checked_at.isoformat()
    cache.set(CACHE_KEY, data, CACHE_TTL_SECONDS)


def refresh_if_due(*, now: datetime | None = None) -> StoreReview | None:
    """Lê de novo quando a última leitura passou de :data:`READ_EVERY`.

    Sem conta configurada não pergunta nada e devolve ``None``.
    """
    from shopman.shop.adapters import catalog_projection_google as google

    if not google._configured(google._get_config()):
        return None
    now = now or timezone.now()
    previous = last_review()
    if previous is not None and now - previous.checked_at < READ_EVERY:
        return previous
    return refresh(now=now)


def refresh(*, now: datetime | None = None) -> StoreReview:
    """Pergunta ao Google, guarda e devolve a leitura (certa ou falha)."""
    review = read(now=now)
    _store(review)
    return review


def read(*, now: datetime | None = None) -> StoreReview:
    """Uma leitura de ``omnichannelSettings``, só leitura. Não guarda nada."""
    import requests

    from shopman.shop.adapters import catalog_projection_google as google

    now = now or timezone.now()
    cfg = google._get_config()
    if not google._configured(cfg):
        return StoreReview(checked_at=now, ok=False, error="Conta do Google não configurada")
    settings_list: list[dict] = []
    page_token = ""
    try:
        token = google._access_token(cfg)
        while True:
            params = {"pageToken": page_token} if page_token else {}
            resp = requests.get(
                f"{google._base(cfg)}/accounts/v1/{google._account(cfg)}/omnichannelSettings",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=google._timeout(cfg),
            )
            if resp.status_code >= 400:
                return StoreReview(checked_at=now, ok=False, error=google._google_error(resp))
            body = resp.json() if resp.content else {}
            settings_list.extend(body.get("omnichannelSettings") or [])
            page_token = str(body.get("nextPageToken") or "")
            if not page_token:
                break
    except Exception as exc:  # rede, chave recusada, JSON inválido
        logger.warning("google_store_review: leitura falhou", exc_info=True)
        return StoreReview(checked_at=now, ok=False, error=f"A chamada ao Google falhou: {exc}")

    setting = next(
        (item for item in settings_list if str(item.get("regionCode") or "").upper() == REGION),
        None,
    )
    if setting is None:
        return StoreReview(checked_at=now, ok=True, pickup=NOT_REQUESTED, in_stock=NOT_REQUESTED)
    return StoreReview(
        checked_at=now,
        ok=True,
        pickup=_state(setting.get("pickup")),
        in_stock=_state(setting.get("inStock")),
    )


def _state(resource) -> str:
    if not isinstance(resource, dict):
        return NOT_REQUESTED
    state = str(resource.get("state") or "").upper()
    if state in (ACTIVE, FAILED, RUNNING, ACTION_REQUIRED):
        return state
    return NOT_REQUESTED
