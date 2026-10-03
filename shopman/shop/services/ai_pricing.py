"""Preço de modelo de IA para os placares dos pilotos — uma tabela só.

Os pilotos (de-para do B.I. no backstage, intenções da mensageria no
storefront) comparam custo entre concorrentes, e os dois precisam do MESMO
preço por modelo. Mora no orquestrador porque backstage e storefront não se
importam.

Tabela = preço público da Anthropic (24/06/2026; Sonnet 5.5 na tabela de
25/09/2026), em US$ por milhão de tokens (entrada, saída). É só o default do
placar: os comandos aceitam preço por argumento, e modelo fora da tabela sai com
custo zerado e aviso.

O cache de prompt tem preço próprio, derivado da entrada: ler do cache custa um
décimo (``CACHE_READ_FACTOR``) e escrever no cache de 5 minutos custa 1,25 vez
(``CACHE_WRITE_FACTOR``). ``usage_cost`` soma as quatro parcelas; é a conta da
régua da Concierge (``storefront/concierge/metrics.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

LLM_PRICES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-5-5": (4.00, 20.00),
}


@dataclass
class Price:
    """US$ por milhão de tokens."""

    input_per_m: float = 0.0
    output_per_m: float = 0.0

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_m + output_tokens * self.output_per_m) / 1_000_000


#: Fração do preço de entrada cobrada por token lido do cache.
CACHE_READ_FACTOR = 0.10
#: Fração do preço de entrada cobrada por token escrito no cache (TTL de 5 minutos).
CACHE_WRITE_FACTOR = 1.25


def usage_cost(model: str, usage: Mapping) -> float | None:
    """US$ de uma resposta do modelo, com as quatro parcelas do ``usage`` da API.

    ``usage`` tem as chaves da Anthropic (``input_tokens``, ``output_tokens``,
    ``cache_read_input_tokens``, ``cache_creation_input_tokens``); a que faltar
    conta zero. Modelo fora da tabela devolve ``None``: custo desconhecido não é
    custo zero.
    """
    prices = LLM_PRICES.get(model)
    if prices is None:
        return None
    price_in, price_out = prices
    tokens = {key: int(usage.get(key) or 0) for key in (
        "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
    )}
    return (
        tokens["input_tokens"] * price_in
        + tokens["cache_read_input_tokens"] * price_in * CACHE_READ_FACTOR
        + tokens["cache_creation_input_tokens"] * price_in * CACHE_WRITE_FACTOR
        + tokens["output_tokens"] * price_out
    ) / 1_000_000
