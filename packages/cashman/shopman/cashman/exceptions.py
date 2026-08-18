"""Exceções do Cashman.

Mesmo contrato do restante da suite: ``code`` legível por máquina, ``message``
em português para gente, ``context`` com o que ajuda a diagnosticar.
"""

from __future__ import annotations


class CashError(Exception):
    """
    Base de toda exceção do Cashman.

    Codes:
        SHIFT_ALREADY_OPEN     — operador ou terminal já tem turno aberto
        SHIFT_NOT_OPEN         — a operação exige turno aberto
        SHIFT_NOT_CLOSED       — a operação exige turno fechado (correção de contagem)
        INVALID_AMOUNT         — sinal ou valor incompatível com o tipo do lançamento
        INVALID_KIND           — tipo de lançamento desconhecido
        PARENT_REQUIRED        — o tipo exige o lançamento que ele responde
        PARENT_MISMATCH        — o ``parent`` não é do tipo esperado ou é de outro turno
        APPROVAL_REQUIRED      — o tipo exige segunda assinatura
        IMMUTABLE              — tentativa de editar ou apagar lançamento
    """

    def __init__(self, code: str = "error", message: str = "", context: dict | None = None):
        self.code = code
        self.message = message or code
        self.context = context or {}
        super().__init__(f"[{code}] {self.message}")

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context}
