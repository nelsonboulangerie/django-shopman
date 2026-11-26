"""O contexto do site que a referência ``NB-XxXx`` traz para o link de acesso.

Um caminho só para quem cria o link a partir da mensagem do WhatsApp: o endpoint do
ManyChat (``AccessLinkCreateView``) e quem mais receber a mesma mensagem (a Concierge
da loja, quando a mensagem chega só a ela). Os dois dobram o estado da referência na
metadata do link do mesmo jeito (destino, sacola, retorno) e liberam a aba do
computador do mesmo jeito. Duas cópias divergiriam em silêncio, e quem paga é a
cliente que tocou em Finalizar e cai no cardápio.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.utils import timezone

from ..conf import get_doorman_settings
from ..models import AccessLink
from ..utils import safe_redirect_url
from .access_link import AccessLinkService

logger = logging.getLogger(__name__)


#: A marca, na metadata do link, da referência que ele consumiu (``code_mark``).
SITE_CODE_KEY = "site_code"


def code_mark(code: str) -> str:
    """A marca de uma referência ``NB-…`` (o código puro ou a mensagem inteira).

    Hash e não o código: o link guarda só a prova de que aquela referência já foi
    atendida, nunca o código que ainda abriria o contexto.
    """
    from .link_state import extract_code

    body = extract_code(code or "")
    return hashlib.sha256(body.encode()).hexdigest()[:24] if body else ""


def already_answered(code: str, customer) -> bool:
    """A referência já virou link para este cliente, por qualquer dos caminhos.

    A mesma mensagem pode chegar ao endpoint do ManyChat e à Concierge da loja. A
    referência é de uso único: quem a consome primeiro cria o link (e a mensagem de
    entrada sai com ele); quem chega depois encontra a marca e não cria o segundo,
    que sairia com o aviso falso de "sua sacola não veio" (#3621).
    """
    mark = code_mark(code)
    if not mark or customer is None:
        return False
    window = timezone.now() - timedelta(seconds=get_doorman_settings().LINK_STATE_TTL_SECONDS + 60)
    return AccessLink.objects.filter(
        customer_id=customer.subject_id, created_at__gte=window, **{f"metadata__{SITE_CODE_KEY}": mark}
    ).exists()


def fold_state(state: dict, metadata: dict, *, request=None, code: str = "") -> tuple[str, str]:
    """Dobra o estado da referência na metadata do link e devolve ``(origin, origin_label)``.

    A sessão de origem não viaja na metadata: ela é o endereço da liberação
    (``release_origin``), não contexto do login. ``next`` passa por ``safe_redirect_url``;
    o resto (ex.: ``cart_session_key``, ``site_return``) viaja opaco, sem sobrescrever o
    que quem pediu o link já pôs. Com ``code``, o link leva a marca da referência
    (``already_answered``).
    """
    state = dict(state)
    mark = code_mark(code)
    if mark:
        metadata[SITE_CODE_KEY] = mark
    origin = str(state.pop("origin", "") or "")
    origin_label = str(state.pop("origin_label", "") or "")
    for key, value in state.items():
        if key == "next":
            if value:
                metadata["next"] = safe_redirect_url(str(value), request)
        elif value is not None and key not in metadata:
            metadata[key] = value
    return origin, origin_label


def release_origin(
    *,
    customer,
    metadata: dict,
    origin: str,
    origin_label: str,
    audience: str = AccessLink.Audience.WEB_GENERAL,
    source: str = AccessLink.Source.MANYCHAT,
) -> bool:
    """Libera a aba do computador que apertou o botão e marca a metadata do link.

    Cria o token da aba de origem e o deixa esperando por ela. É um access link como
    qualquer outro (a aba o troca pelo mesmo caminho do link da mensagem, sem login
    paralelo) e não é entregue a ninguém (sem ``deliver``): só a sessão cuja impressão
    digital é ``origin`` o encontra. Vem ANTES do link da mensagem, porque a mensagem
    sai junto com ele e vai dizer "você já entrou". Devolve se liberou.
    """
    from .link_state import new_revoke_ref, release_to_origin, store_revocation

    if not origin:
        return False
    settings = get_doorman_settings()
    claim_metadata = {key: value for key, value in metadata.items() if key not in ("deliver", "deliver_to")}
    claim_metadata["login_source"] = "site_release"
    claim = AccessLinkService.create_token(
        customer=customer,
        audience=audience,
        source=source,
        ttl_minutes=max(1, -(-settings.LINK_STATE_TTL_SECONDS // 60)),
        metadata=claim_metadata,
    )
    if not claim.success or not claim.token:
        logger.error("access_link.origin_release_failed error=%s", claim.error)
        return False

    revoke_ref = new_revoke_ref()
    release_to_origin(origin, token=claim.token, revoke_ref=revoke_ref)
    store_revocation(revoke_ref, {
        "origin": origin,
        "customer_id": str(customer.subject_id),
        "origin_label": origin_label,
    })
    logger.info("access_link.origin_released")
    metadata["released"] = True
    metadata["revoke_ref"] = revoke_ref
    if origin_label:
        metadata["origin_label"] = origin_label
    return True
