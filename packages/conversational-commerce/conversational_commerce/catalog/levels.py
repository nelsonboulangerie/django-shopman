"""Níveis de autoridade A0 a A5 e a escada de identidade (v2 5.6).

| Nível | O que é | Exemplo genérico |
|---|---|---|
| A0 | informar fato público | horário, preço de vitrine |
| A1 | leitura personalizada | estado do pedido, endereço salvo |
| A2 | mudança reversível | sacola |
| A3 | compromisso vinculante | registrar, cancelar ou alterar pedido |
| A4 | exceção | desconto, compensação |
| A5 | proibido à automação | o que o perfil vedar |

A escada de identidade, do mais fraco ao mais forte: ``anonymous`` <
``transported`` < ``weak_verified`` < ``strong_verified``. O perfil diz, por
canal, que degrau cada ação exige; o catálogo não escolhe degrau.
"""

from __future__ import annotations

from conversational_commerce.contracts.common import AUTHORITY_LEVELS, IDENTITY_LADDER

AUTOMATION_FORBIDDEN = "A5"
# A partir deste nível a ação compromete o cliente e exige confirmação presa ao alvo.
CONFIRMATION_LEVEL = "A3"


def authority_rank(level: str) -> int:
    return AUTHORITY_LEVELS.index(level)


def identity_rank(assurance: str) -> int:
    return IDENTITY_LADDER.index(assurance)


def at_least_identity(actual: str, required: str) -> bool:
    return identity_rank(actual) >= identity_rank(required)


def stricter_authority(first: str, second: str) -> str:
    return first if authority_rank(first) >= authority_rank(second) else second


def requires_confirmation(level: str) -> bool:
    return authority_rank(level) >= authority_rank(CONFIRMATION_LEVEL)
