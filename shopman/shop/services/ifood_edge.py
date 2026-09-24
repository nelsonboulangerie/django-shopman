"""Como se lê uma recusa do iFood: quem recusou, com que referência, quanto esperar.

Por que isto é um módulo, e não um trecho do ``ifood_http``
----------------------------------------------------------

A recusa de borda medida em 19/09/2026 (cabeçalho de ``ifood_http`` e
``docs/reports/IFOOD-SUPORTE-403-2026-09-12.md``) não atinge só as APIs: o
endpoint de autenticação também leva ``403`` do edge. Ou seja, as duas camadas
precisam do mesmo remédio — e **elas não podem se chamar**: ``ifood_http`` pede
o header autorizado a ``ifood_auth``, então ``ifood_auth`` não pode voltar a
pedir o token pelo ``ifood_http``. Seria ciclo.

O que as duas dividem não é a chamada, é o **conhecimento**: distinguir a recusa
do Akamai da recusa da API do iFood, extrair o ``Reference #`` que o suporte
usa, e esperar entre tentativas sem sincronizar retentativas. Esse conhecimento
mora aqui, abaixo das duas; nenhuma delas importa a outra.
"""

from __future__ import annotations

import html
import random
import re
import time

import requests

# A recusa do edge vem como HTML, não JSON. A recusa da própria API do iFood vem
# como JSON e significa outra coisa (escopo/permissão) — remédio diferente.
EDGE = "edge"
API = "api"

_REFERENCE_RE = re.compile(r"Reference\s*#\s*([0-9A-Za-z.\-]+)")
# Cabeçalhos que ajudam a rastrear a recusa; nunca inclui Authorization.
_FORENSIC_HEADERS = ("x-ifood-request-id", "x-request-id", "x-correlation-id", "server", "date")


def denial_kind(resp: requests.Response) -> str:
    """``EDGE`` quando quem recusou foi o Akamai; ``API`` quando foi o iFood.

    A distinção decide o remédio: recusa de edge se resolve com retry e, se
    persistir, com liberação da origem junto ao iFood; recusa de API é escopo do
    token ou permissão do merchant, e retry nenhum resolve.
    """
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "json" in content_type:
        return API
    body = (resp.text or "")[:2000]
    if "Access Denied" in body or "<HTML" in body.upper():
        return EDGE
    return API


def edge_reference(body: str) -> str:
    """O ``Reference #`` da página do Akamai, ou string vazia.

    O corpo vem com entidades HTML (``&#46;`` no lugar do ponto), então o texto
    é desescapado antes da busca — sem isso a referência não casa.
    """
    match = _REFERENCE_RE.search(html.unescape(body or ""))
    return match.group(1) if match else ""


def forensics(resp: requests.Response, *, include_body: bool = True) -> str:
    """Resumo rastreável da recusa, sem segredo nem dado de cliente.

    ``include_body=False`` para a chamada de token: o corpo de uma recusa de
    autenticação pode ecoar o que foi enviado (``clientSecret``), então ali só
    o status, a classificação e os cabeçalhos de rastreio podem ir ao log.
    """
    parts = [f"http={resp.status_code}"]
    kind = denial_kind(resp)
    parts.append(f"recusa={kind}")
    if kind == EDGE:
        reference = edge_reference(resp.text or "")
        parts.append(f"referencia={reference or 'ausente'}")
    elif include_body:
        parts.append(f"corpo={(resp.text or '')[:300]}")
    for header in _FORENSIC_HEADERS:
        value = resp.headers.get(header)
        if value:
            parts.append(f"{header}={value}")
    return " ".join(parts)


def sleep_backoff(backoff: float, attempt: int) -> None:
    """Espera exponencial com jitter, para não sincronizar retentativas."""
    if backoff <= 0:
        return
    delay = backoff * (2 ** (attempt - 1))
    time.sleep(delay * (0.5 + random.random() / 2))


__all__ = ["denial_kind", "edge_reference", "forensics", "sleep_backoff", "EDGE", "API"]
