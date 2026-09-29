"""Camada HTTP única das chamadas ao iFood: retry, classificação da recusa e forense.

Por que existe (medido em 19/09/2026)
-------------------------------------

O polling publicado na DigitalOcean recebe ``HTTP 403`` com página HTML
``Access Denied`` em ~42% das tentativas: em uma hora de log, **um único token**
(renovado uma vez, na subida do worker) produziu 21 respostas boas e 15 recusas,
intercaladas. Do IP local, o mesmo código, a mesma rota e o mesmo tipo de token
responderam ``204`` em 24 de 24 tentativas.

Um token sem permissão não alterna entre `204` e `403` de minuto a minuto. A
recusa é do **edge** (Akamai), decidida por origem da conexão — o app na
DigitalOcean sai por um conjunto compartilhado de IPs de NAT, e parte desses IPs
é recusada. Não é escopo do token nem rota errada.

Deste diagnóstico saem as duas responsabilidades deste módulo:

1. **Retry com backoff.** Uma recusa de edge é sorteada por tentativa: com ~58%
   de sucesso em cada uma, três tentativas levam a falha de 42% para ~7%.
2. **Forense.** A página do Akamai traz um ``Reference #`` — o identificador que
   o suporte do iFood usa para achar a regra que bloqueou e o IP que eles viram.
   O log anterior cortava a resposta em 200 caracteres, exatamente antes dessa
   linha; foi por isso que o chamado 33298264 seguiu sem a prova que o resolveria.

Como ler a recusa (classificar, extrair a referência, esperar) mora em
``ifood_edge``, e não aqui: a chamada de token leva a mesma recusa e precisa do
mesmo remédio, sem que os dois módulos possam se chamar — ver o cabeçalho de
``ifood_edge``.

Segurança do retry em chamadas de efeito
----------------------------------------

Retentar ``confirmar``/``despachar``/``cancelar``/``ACK`` seria perigoso se a
requisição pudesse ter chegado ao iFood. **Não pode**: a recusa de edge é
devolvida pelo Akamai, que não encaminha a requisição à origem. Por isso o retry
de recusa de edge é seguro para qualquer verbo, e é o único retry aplicado por
padrão a chamadas de escrita. Falha de transporte e ``5xx`` são ambíguas (a
origem pode ter processado), então só são retentadas quando quem chama declara
``idempotent=True``.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth, ifood_edge
from shopman.shop.services.ifood_edge import API, EDGE, denial_kind, edge_reference

logger = logging.getLogger(__name__)

_DEFAULT_ATTEMPTS = 3
_DEFAULT_BACKOFF = 0.75  # segundos; dobra a cada tentativa, com jitter
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def _timeout() -> int:
    return int(_cfg().get("timeout") or 30)


def _attempts() -> int:
    return max(1, int(_cfg().get("retry_attempts") or _DEFAULT_ATTEMPTS))


def _backoff() -> float:
    return max(0.0, float(_cfg().get("retry_backoff") or _DEFAULT_BACKOFF))


def request(
    method: str,
    path: str,
    *,
    label: str,
    extra_headers: dict | None = None,
    idempotent: bool = False,
    attempts: int | None = None,
    **kwargs,
) -> requests.Response | None:
    """Chama a API do iFood com retry de recusa de edge. ``None`` sem token/desistência.

    ``label`` identifica a operação no log (ex.: ``"poll"``, ``"acknowledge"``).
    ``idempotent=True`` autoriza também o retry de ``5xx``/transporte, que são
    ambíguos para chamadas de efeito — ver o cabeçalho do módulo.
    """
    total = attempts if attempts is not None else _attempts()
    url = f"{base_url()}{path}"
    backoff = _backoff()
    last: requests.Response | None = None

    for attempt in range(1, total + 1):
        headers, reason = ifood_auth.headers_with_reason(extra_headers)
        if not headers:
            # A razão vem do ``ifood_auth`` porque "sem token" tem três causas
            # distintas (sem credencial, transporte, recusa) e o remédio de cada
            # uma é outro. A forense da recusa já foi registrada lá.
            logger.warning(
                "ifood_http.%s: %s — nada enviado", label, ifood_auth.failure_message(reason)
            )
            return None

        try:
            # Despacho por verbo (``requests.get``/``requests.post``) e não
            # ``requests.request``: é assim que a suíte intercepta as chamadas
            # ao iFood, e trocar o ponto de entrada cegaria os testes existentes.
            send = getattr(requests, method.lower())
            resp = send(url, headers=headers, timeout=_timeout(), **kwargs)
        except requests.RequestException as exc:
            # Transporte: só retenta quando a chamada é idempotente, porque a
            # origem pode ter processado antes de a conexão cair.
            if idempotent and attempt < total:
                ifood_edge.sleep_backoff(backoff, attempt)
                continue
            logger.warning("ifood_http.%s: transporte falhou (%s)", label, type(exc).__name__)
            return None

        last = resp
        if resp.status_code < 400:
            if attempt > 1:
                logger.info("ifood_http.%s: recuperado na tentativa %s de %s", label, attempt, total)
            return resp

        if resp.status_code == 401:
            # Token expirado/revogado: renova uma vez e repete. Não é o caso do
            # 403 de edge, que não tem nada a ver com o token.
            if attempt < total:
                ifood_auth.get_access_token(force=True)
                continue

        if resp.status_code == 403 and denial_kind(resp) == EDGE:
            # O Akamai recusou antes da origem: a requisição não teve efeito
            # nenhum, então repetir é seguro inclusive para escrita.
            if attempt < total:
                ifood_edge.sleep_backoff(backoff, attempt)
                continue
            logger.warning(
                "ifood_http.%s: recusado pelo edge do iFood em %s tentativas — %s",
                label, total, ifood_edge.forensics(resp),
            )
            return None

        if resp.status_code in _RETRYABLE_STATUS and idempotent and attempt < total:
            ifood_edge.sleep_backoff(backoff, attempt)
            continue

        logger.warning("ifood_http.%s: %s", label, ifood_edge.forensics(resp))
        return resp

    if last is not None:
        logger.warning("ifood_http.%s: esgotou %s tentativas — %s", label, total, ifood_edge.forensics(last))
    return None


__all__ = ["request", "denial_kind", "edge_reference", "base_url", "EDGE", "API"]
