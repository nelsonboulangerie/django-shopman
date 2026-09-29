"""Preço de modelo de IA para os placares dos pilotos — uma tabela só.

Os pilotos (de-para do B.I. no backstage, intenções da mensageria no
storefront) comparam custo entre concorrentes, e os dois precisam do MESMO
preço por modelo. Mora no orquestrador porque backstage e storefront não se
importam.

Tabela = preço público da Anthropic de 24/06/2026, em US$ por milhão de tokens
(entrada, saída). É só o default do placar: os comandos aceitam preço por
argumento, e modelo fora da tabela sai com custo zerado e aviso.
"""

from __future__ import annotations

from dataclasses import dataclass

LLM_PRICES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
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
