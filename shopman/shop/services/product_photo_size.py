"""Tamanho da foto de produto, medido uma vez por endereço.

A partir de 31/01/2027 o Google reprova o produto cuja foto tem menos de 500 × 500 px
(aviso do Google ao dono em 05/11/2026; requisito do ``image_link`` em
support.google.com/merchants/answer/6324350). Foto esticada também reprova, então a
saída nunca é ampliar: é trocar a foto.

A foto da casa é imutável por nome (trocar a foto é trocar o nome do arquivo, ver
``config/product_photos.py``), então o tamanho medido vale para sempre: fica no cache
sem prazo, e o envio ao Google não baixa a foto de novo. O upload pelo Catálogo grava
o tamanho na hora, sem rede (``remember``).

A medida usa a sonda do Marketing (só host de confiança, sem seguir redirecionamento,
leitura parcial). Foto fora do host de confiança não se mede aqui: quem reprova foto
fora do host da casa é a prontidão (``catalog.product_image_host``). Sonda desligada
(testes, simulador sem rede) só responde o que já foi gravado.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Lado mínimo da foto de produto no Google (a partir de 31/01/2027).
GOOGLE_MIN_SIDE_PX = 500

_CACHE_PREFIX = "catalog:photo-size:v1:"


def _key(url: str) -> str:
    return _CACHE_PREFIX + hashlib.sha256(url.encode("utf-8")).hexdigest()


def remember(url: str, width: int, height: int) -> None:
    """Grava o tamanho de uma foto já lida, sem prazo (o arquivo não muda)."""
    if url and width and height:
        cache.set(_key(url), [int(width), int(height)], None)


def photo_size(url: str) -> tuple[int, int] | None:
    """``(largura, altura)`` da foto, ou ``None`` quando não deu para medir."""
    from shopman.shop.services import marketing_media_probe
    from shopman.shop.services.marketing_contracts import MarketingContractError

    url = str(url or "").strip()
    if not url:
        return None
    cached = cache.get(_key(url))
    if isinstance(cached, (list, tuple)) and len(cached) == 2:
        return int(cached[0]), int(cached[1])
    if not marketing_media_probe.probe_enabled():
        return None
    try:
        facts = marketing_media_probe.probe_facts(url, field="image_url")
    except MarketingContractError as exc:
        logger.warning("product_photo_size: não deu para medir %s (%s)", url, exc.code)
        return None
    if not facts.width or not facts.height:
        logger.warning("product_photo_size: dimensões ilegíveis em %s", url)
        return None
    remember(url, facts.width, facts.height)
    return facts.width, facts.height


def too_small_for_google(size: tuple[int, int] | None) -> bool:
    return size is not None and min(size) < GOOGLE_MIN_SIDE_PX
