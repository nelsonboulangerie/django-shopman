"""Códigos de inelegibilidade: por que uma ação está fora do conjunto admissível.

Um código é estável e vai para ``DecisionRecord.candidates[].blocked_by``.
Precondição específica de movimento que falha usa o próprio código da
precondição (``catalog/preconditions.py``); precondição que não se pôde avaliar
usa ``<código>_unknown``. Os códigos abaixo são os do perfil e do nível, comuns a
todo movimento.
"""

from __future__ import annotations

from enum import StrEnum


class IneligibilityCode(StrEnum):
    # O perfil não liga o movimento (sem entrada em ``actions``).
    PROFILE_ACTION_ABSENT = "profile_action_absent"
    # A linha de que a ação depende não existe ou está ``absent`` (K39).
    PROFILE_LINE_ABSENT = "profile_line_absent"
    # A linha existe, mas está ``proposed`` ou ``validating``: não vale como aprovada.
    PROFILE_LINE_NOT_APPROVED = "profile_line_not_approved"
    # O perfil não diz que degrau de identidade o canal exige para a ação.
    IDENTITY_RULE_ABSENT = "identity_rule_absent"
    # A identidade da conversa está abaixo do degrau exigido.
    IDENTITY_INSUFFICIENT = "identity_insufficient"
    # Nível A5: proibido à automação.
    AUTHORITY_FORBIDDEN = "authority_forbidden"
    # Ação A3 ou acima com o perfil dispensando confirmação: o perfil não afrouxa o nível.
    CONFIRMATION_WEAKER_THAN_LEVEL = "confirmation_weaker_than_level"
    # A porta não declara a capacidade de que a ação precisa.
    CAPABILITY_MISSING = "capability_missing"
    # O fato de que a ação depende é desconhecido ou venceu.
    FACT_UNAVAILABLE = "fact_unavailable"


def unknown_code(precondition_code: str) -> str:
    """O código de bloqueio de uma precondição que não se pôde avaliar."""
    return f"{precondition_code}_unknown"
