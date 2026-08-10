"""Os flows do ManyChat, por nome — para o operador escolher gente em vez de id.

O `flow_ns` é opaco: `content20240614222050_512341` é a palavra `content`, a data/hora de
criação e um sufixo aleatório. Dá para saber QUANDO o flow nasceu, e nada mais. O que tem
significado é o **nome** ("Teste Webhook API Manychat"), e a API devolve os dois juntos.

Então o Admin oferece a lista por nome e guarda o `ns` atrás. Pedir para alguém colar um
id de 27 caracteres é convidar erro de digitação num campo cuja falha é silenciosa: `ns`
errado não estoura, só faz o envio falhar destinatário por destinatário.

**Cacheado, com degradação explícita.** O Admin renderiza formulário muitas vezes, e uma
chamada de rede por render é lentidão garantida e indisponibilidade eventual. Quando a API
não responde, a lista volta vazia e o formulário cai para texto livre — melhor operador
digitando do que operador travado.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.error import HTTPError, URLError

from django.core.cache import cache

logger = logging.getLogger(__name__)

_FLOWS_URL = "https://api.manychat.com/fb/page/getFlows"
_CACHE_KEY = "shopman.manychat.flows.v1"
#: Cinco minutos: flow novo aparece rápido o bastante para o operador não desconfiar da
#: ferramenta, e a API não é chamada a cada abertura de formulário.
_CACHE_TTL = 300


def list_flows(*, force: bool = False) -> tuple[tuple[str, str], ...]:
    """``((ns, nome), …)`` ordenado por nome. Vazio quando não há como saber.

    Vazio significa "não consegui perguntar", nunca "não existe flow" — e quem consome
    trata os dois igual: cai para entrada livre em vez de afirmar que a conta está vazia.
    """
    if not force:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return tuple(tuple(pair) for pair in cached)

    flows = _fetch()
    cache.set(_CACHE_KEY, [list(pair) for pair in flows], _CACHE_TTL)
    return flows


def flow_name(ns: str) -> str:
    """O nome do flow, ou string vazia se ele não estiver na lista.

    Vazio para um `ns` configurado é sinal de flow **apagado no ManyChat** — o caso que
    faz uma campanha falhar calada.
    """
    if not ns:
        return ""
    for candidate, name in list_flows():
        if candidate == ns:
            return name
    return ""


def _fetch() -> tuple[tuple[str, str], ...]:
    from django.conf import settings

    token = (getattr(settings, "MANYCHAT_API_TOKEN", "") or "").strip()
    if not token:
        # Ambiente sem token (dev local) não é erro: é ausência de configuração, e o
        # formulário cai para texto livre.
        return ()

    request = urllib.request.Request(_FLOWS_URL, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("manychat.flows_http_error status=%s", exc.code)
        return ()
    except URLError as exc:
        logger.warning("manychat.flows_unreachable reason=%s", exc.reason)
        return ()
    except (ValueError, OSError):
        logger.warning("manychat.flows_unreadable", exc_info=True)
        return ()

    data = payload.get("data") or {}
    rows = data.get("flows") if isinstance(data, dict) else data
    pairs = [
        (str(row.get("ns")), str(row.get("name") or row.get("ns")))
        for row in (rows or [])
        if isinstance(row, dict) and row.get("ns")
    ]
    return tuple(sorted(pairs, key=lambda pair: pair[1].lower()))
