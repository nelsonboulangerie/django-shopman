"""Sonda da foto do post do Google: formato, peso e dimensão ANTES de aprovar.

O Google só aceita foto JPEG ou PNG, de 10 KB a 5 MB e com ao menos 250 px de cada
lado (support.google.com/business/answer/6103862, conferido em 25/09/2026). A URL
não basta para saber: a foto de produto da loja é WebP, e um ``.jpg`` pode ser
qualquer coisa. Então a prévia e a aprovação leem o começo do arquivo.

A leitura é contida pela mesma política de mídia do Marketing: só HTTPS em host da
lista de confiança (``marketing_url_policy.validate_media_url``), sem seguir
redirecionamento, com ``Range`` e teto de bytes, e sem credencial. Não serve a
nada além desta conferência.

``SHOPMAN_MARKETING_MEDIA_PROBE_ENABLED`` desliga a sonda onde não há rede (testes
e simulador local); desligada, só a conferência pela URL vale.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.cache import cache

from shopman.shop.services import marketing_google_post as google_post
from shopman.shop.services.marketing_contracts import MarketingContractError

PROBE_BYTES = 256 * 1024
PROBE_TIMEOUT_SECONDS = 6
_CACHE_SECONDS = 600
_CACHE_PREFIX = "marketing:media-probe:v1:"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


_OPENER = build_opener(_NoRedirect)


@dataclass(frozen=True, slots=True)
class PhotoFacts:
    format: str
    total_bytes: int
    width: int
    height: int


def check_google_photo(url: str, *, field: str = "content.image_url") -> PhotoFacts | None:
    """Recusa, com mensagem no campo, a foto que o Google não aceitaria."""

    if not getattr(settings, "SHOPMAN_MARKETING_MEDIA_PROBE_ENABLED", True):
        return None
    absolute = _absolute(url, field=field)
    facts = _cached_probe(absolute, field=field)
    if facts.format not in google_post.PHOTO_FORMATS:
        label = facts.format.upper() if facts.format else "um formato que não é foto"
        _reject(
            "google_media_format_unsupported",
            f"O Google só aceita foto JPEG ou PNG, e esta imagem é {label}.",
            field,
            "Escolha uma imagem JPEG ou PNG.",
        )
    if not facts.width or not facts.height:
        _reject(
            "google_media_unreadable",
            "Não deu para ler as dimensões desta foto, e o Google recusa foto que não "
            "consegue abrir.",
            field,
            "Exporte a foto de novo em JPEG ou PNG.",
        )
    if facts.total_bytes < google_post.PHOTO_MIN_BYTES:
        _reject(
            "google_media_too_light",
            f"O Google recusa foto com menos de 10 KB, e esta tem "
            f"{_kilobytes(facts.total_bytes)}.",
            field,
            "Use uma foto com mais resolução.",
        )
    if facts.total_bytes > google_post.PHOTO_MAX_BYTES:
        _reject(
            "google_media_too_heavy",
            f"O Google recusa foto com mais de 5 MB, e esta tem "
            f"{facts.total_bytes / (1024 * 1024):.1f} MB.".replace(".", ","),
            field,
            "Reduza a foto para até 5 MB.",
        )
    if min(facts.width, facts.height) < google_post.PHOTO_MIN_SIDE_PX:
        _reject(
            "google_media_too_small",
            f"O Google pede ao menos 250 × 250 px, e esta foto tem "
            f"{facts.width} × {facts.height} px.",
            field,
            "Use uma foto maior.",
        )
    return facts


def _absolute(url: str, *, field: str) -> str:
    from shopman.shop.services import marketing_url_policy, storefront_links

    raw = str(url or "").strip()
    if raw.startswith("/") and not raw.startswith("//"):
        base = storefront_links.storefront_base_url()
        if not base.startswith("https://"):
            _reject(
                "google_media_not_public",
                "O Google baixa a foto pela internet, e esta imagem não tem endereço público.",
                field,
                "Use uma imagem com endereço https://.",
            )
        raw = f"{base}{raw}"
    return marketing_url_policy.validate_media_url(raw, field=field)


def _cached_probe(url: str, *, field: str) -> PhotoFacts:
    key = _CACHE_PREFIX + hashlib.sha256(url.encode("utf-8")).hexdigest()
    cached = cache.get(key)
    if isinstance(cached, dict):
        return PhotoFacts(**cached)
    facts = _probe(url, field=field)
    cache.set(
        key,
        {
            "format": facts.format,
            "total_bytes": facts.total_bytes,
            "width": facts.width,
            "height": facts.height,
        },
        _CACHE_SECONDS,
    )
    return facts


def _probe(url: str, *, field: str) -> PhotoFacts:
    request = Request(
        url,
        headers={"Range": f"bytes=0-{PROBE_BYTES - 1}", "User-Agent": "shopman-media-probe"},
        method="GET",
    )
    try:
        with _OPENER.open(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200) or 200)
            headers = response.headers
            head = response.read(PROBE_BYTES)
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            _reject(
                "google_media_redirect",
                "O endereço da imagem redireciona para outro lugar, e o Google precisa "
                "do endereço final.",
                field,
                "Use o endereço final da imagem.",
            )
        _unreachable(field, retryable=exc.code >= 500 or exc.code == 429)
    except (URLError, TimeoutError, OSError, ValueError):
        _unreachable(field, retryable=True)
    total = _total_bytes(status, headers, len(head))
    photo_format = _magic_format(head)
    width, height = _dimensions(head)
    return PhotoFacts(format=photo_format, total_bytes=total, width=width, height=height)


def _total_bytes(status: int, headers, received: int) -> int:
    content_range = str(headers.get("Content-Range") or "")
    if status == 206 and "/" in content_range:
        tail = content_range.rsplit("/", 1)[-1].strip()
        if tail.isdigit():
            return int(tail)
    length = str(headers.get("Content-Length") or "").strip()
    if status == 200 and length.isdigit():
        return int(length)
    return received


def _magic_format(head: bytes) -> str:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "avif"
    if head[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "heic"
    return ""


def _dimensions(head: bytes) -> tuple[int, int]:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(BytesIO(head)) as image:
            return int(image.width), int(image.height)
    except (UnidentifiedImageError, OSError, ValueError):
        return 0, 0


def _kilobytes(value: int) -> str:
    return f"{max(1, round(value / 1024))} KB"


def _unreachable(field: str, *, retryable: bool) -> None:
    raise MarketingContractError(
        code="google_media_unreachable",
        detail=(
            "Não deu para conferir a foto agora, e o Google recusa foto que não "
            "consegue baixar."
        ),
        retryable=retryable,
        field_errors={field: ("Confira o endereço da imagem ou tente de novo.",)},
    )


def _reject(code: str, detail: str, field: str, message: str) -> None:
    raise MarketingContractError(
        code=code,
        detail=detail,
        field_errors={field: (message,)},
    )
