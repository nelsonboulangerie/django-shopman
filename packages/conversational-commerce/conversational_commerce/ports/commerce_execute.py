"""Porta de comércio, execução: executar, localizar, reconciliar.

Garantias (v2 4.7, 5.4): o contrato de efeito inteiro. A guarda é chamada na
mesma unidade atômica do efeito; mesma chave e mesmo conteúdo devolvem o recibo
existente; mesma chave com outro conteúdo é ``idempotency_conflict`` e o recibo
não é sobrescrito; resposta que não chegou é ``effect_unknown``, e reconcilia-se
com a MESMA chave.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from conversational_commerce.contracts import ActionCommand, ActionReceipt

from .common import Capabilities, TrustedContext
from .guard import EffectGuard

OPERATIONS = ("execute", "locate", "reconcile")


@runtime_checkable
class CommerceExecutePort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def execute(self, ctx: TrustedContext, command: ActionCommand, guard: EffectGuard) -> ActionReceipt: ...

    def locate(self, ctx: TrustedContext, scope: str, key: str) -> ActionReceipt | None: ...

    def reconcile(self, ctx: TrustedContext, command: ActionCommand) -> ActionReceipt: ...
