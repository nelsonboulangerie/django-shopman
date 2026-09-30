"""Leitura pública cacheável na borda: estrutura pública, nunca estado de sessão.

A Cloudflare na frente do ``api.`` ignora ``Vary: Cookie``: uma resposta
``public`` é servida a QUALQUER requisição da mesma URL, com ou sem cookie
(medido em 30/09/2026: ``sku-redirects/`` sai ``public`` com ``Vary: Cookie`` e
dá HIT). Por isso a mesma URL não pode ser pública para o anônimo e privada para
o cliente: o corpo de um iria para o outro.

A saída é por URL, não por cabeçalho:

- rota que não lê o request (``site/``, ``legal/``) é pública na própria URL;
- rota que personaliza (home, shell, catálogo) ganha uma GÊMEA em
  ``storefront/public/…`` que RECUSA cookie, credencial e query string. Sem
  cookie não há sessão nem cliente, então o corpo é o do visitante anônimo por
  construção, e é o mesmo para todos. O BFF do storefront manda para a gêmea só
  o GET que chega sem cookie de sessão; quem tem sessão continua na rota
  privada de sempre.

Cachear ``build_catalog`` com sessão foi rejeitado em 01/08/2026
(``docs/plans/completed/STOREFRONT-CATALOG-NPLUS1-PLAN.md``) por vazar preço,
favoritos e sacola entre clientes. A gêmea não cacheia a projeção: cacheia a
resposta de quem não tem sessão.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import ParseError

# TTL curto: a home e o catálogo mostram disponibilidade, preço de horário e se a
# loja está aberta. 30 s na borda, mais 30 s servindo o velho enquanto revalida,
# é o atraso máximo que o anônimo vê; sacola e checkout recalculam no servidor.
# O navegador não guarda nada (max-age=0): quem cacheia é a borda.
PUBLIC_EDGE_CACHE_CONTROL = (
    "public, max-age=0, s-maxage=30, stale-while-revalidate=30, stale-if-error=120"
)
PRIVATE_NO_STORE = "private, no-store"

_CREDENTIAL_HEADERS = (
    "Cookie",
    "Authorization",
    "Proxy-Authorization",
    "X-SSL-Client-Cert",
)


def carries_credentials(request) -> bool:
    """A requisição traz algo que identifica alguém, ou varia a URL por parâmetro?"""
    return any(request.headers.get(name) for name in _CREDENTIAL_HEADERS) or bool(request.GET)


def mark_public(response):
    """Carimba cache de borda, e falha fechado se a resposta não for pública.

    Só 200 vira público. Resposta que define cookie é, por definição, de alguém:
    volta a ser privada em vez de ir para a borda.
    """
    if response.status_code == status.HTTP_200_OK and not response.cookies:
        response["Cache-Control"] = PUBLIC_EDGE_CACHE_CONTROL
    else:
        response["Cache-Control"] = PRIVATE_NO_STORE
    return response


class PublicReadMixin:
    """Rota que não lê o request: pública na própria URL."""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if request.method in ("GET", "HEAD"):
            return mark_public(response)
        return response


class PublicEdgeCacheMixin(PublicReadMixin):
    """Gêmea pública de uma rota que personaliza: recusa credencial, responde cacheável."""

    http_method_names = ["get", "head"]

    def initial(self, request, *args, **kwargs):
        if carries_credentials(request):
            raise ParseError("Esta leitura pública não aceita cookie, credencial nem parâmetros.")
        super().initial(request, *args, **kwargs)
