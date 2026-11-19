"""O livro dos recibos, que só acrescenta, e o que se faz com cada recibo (v2 4.7).

As quatro combinações e o próximo passo:

| Último recibo | Próximo passo |
|---|---|
| nenhum, primeira tentativa | ``execute`` |
| nenhum, outra tentativa (o trabalhador anterior morreu) | ``reconcile`` antes de repetir (K14) |
| ``success`` | ``done``: responde com o recibo |
| ``failure`` | ``failed``: informa; nova intenção pede nova decisão |
| ``pending`` ou ``unknown`` | ``reconcile`` com a MESMA chave (K08, K10) |
| aberto e prazo de reconciliação vencido | ``to_person`` (``reconciliation_overdue`` no F4) |
| aberto e chave de idempotência vencida | ``locate`` pela chave; sem achar, ``to_person`` (K16) |

Nunca se gera chave nova para o mesmo pedido, nem se executa de novo um efeito
desconhecido. Recibo que chega depois de um terminal é evidência guardada, e não
reabre nada: um recibo atrasado não autoriza.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from conversational_commerce.contracts import ActionCommand, ActionReceipt, DeploymentProfile, Producer
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import EffectGuard, PortError, TrustedContext
from conversational_commerce.profile import read_line

from ..authority.grants import later
from .decisions import LedgerError

RETENTION_LINE = "effect.idempotency_retention_seconds"
DEADLINE_LINE = "effect.reconciliation_deadline_seconds"
PRODUCER = Producer(name="conversational-commerce", version="receipts-1")
OPEN = ("pending", "unknown")

Step = Literal["execute", "reconcile", "locate", "done", "failed", "to_person"]


class ReceiptLedger:
    """Comandos e recibos em ordem de gravação."""

    def __init__(self) -> None:
        self.commands: dict[str, ActionCommand] = {}
        self._keys: dict[tuple[str, str], str] = {}
        self._receipts: dict[str, list[ActionReceipt]] = {}
        self._ids: set[str] = set()

    def register(self, command: ActionCommand) -> ActionCommand:
        """O comando entra uma vez. Mesma chave com outro conteúdo é conflito (N08)."""
        key = (command.idempotency.scope, command.idempotency.key)
        known = self._keys.get(key)
        if known is not None:
            stored = self.commands[known]
            if stored.content_hash != command.content_hash:
                raise LedgerError(f"{ErrorCode.IDEMPOTENCY_CONFLICT.value}: mesma chave, outro conteúdo")
            return stored
        self._keys[key] = command.command_id
        self.commands[command.command_id] = command
        self._receipts[command.command_id] = []
        return command

    def append(self, receipt: ActionReceipt) -> ActionReceipt:
        if receipt.command_id not in self.commands:
            raise LedgerError(f"recibo de comando desconhecido: {receipt.command_id}")
        if receipt.id in self._ids:
            raise LedgerError(f"recibo {receipt.id} já gravado")
        self._ids.add(receipt.id)
        self._receipts[receipt.command_id].append(receipt)
        return receipt

    def history(self, command_id: str) -> tuple[ActionReceipt, ...]:
        return tuple(self._receipts.get(command_id, ()))

    def latest(self, command_id: str) -> ActionReceipt | None:
        """O recibo que vale: o terminal, se existe (recibo atrasado não o desfaz); senão o último."""
        history = self._receipts.get(command_id, [])
        terminal = [r for r in history if r.status not in OPEN]
        if terminal:
            return terminal[0]
        return history[-1] if history else None


def retention_seconds(profile: DeploymentProfile, executor: Any) -> int | None:
    """A retenção da chave: a menor entre a do perfil e a que o executor declara."""
    values = []
    reading = read_line(profile, RETENTION_LINE)
    if reading.usable:
        values.append(reading.value)
    declared = executor.capabilities().guarantees.get("idempotency_retention_seconds")
    if isinstance(declared, int) and not isinstance(declared, bool):
        values.append(declared)
    return min(values) if values else None


def deadline_seconds(profile: DeploymentProfile) -> int | None:
    reading = read_line(profile, DEADLINE_LINE)
    return reading.value if reading.usable else None


def next_step(ledger: ReceiptLedger, command: ActionCommand, *, now: str, retention: int | None,
              attempt: int = 1) -> Step:
    latest = ledger.latest(command.command_id)
    key_expired = retention is None or later(command.occurred_at, retention) <= now
    if latest is None:
        if attempt > 1:
            return "reconcile"
        return "to_person" if key_expired else "execute"
    if latest.status == "success":
        return "done"
    if latest.status == "failure":
        return "failed"
    if now >= latest.reconciliation.deadline:
        return "to_person"
    return "locate" if key_expired else "reconcile"


@dataclass(frozen=True, slots=True)
class Settled:
    step: Step
    receipt: ActionReceipt | None
    conflict: str | None = None

    @property
    def to_person(self) -> bool:
        return self.step == "to_person"


@dataclass
class Settler:
    """Leva um comando ao recibo pelo próximo passo, e grava o que aprendeu no livro."""

    ledger: ReceiptLedger
    executor: Any
    clock: Any
    profile: DeploymentProfile
    on_receipt: Callable[[ActionReceipt], None] | None = None
    log: list[tuple[str, str]] = field(default_factory=list)

    def _unknown(self, ctx: TrustedContext, command: ActionCommand, code: ErrorCode) -> ActionReceipt:
        seconds = deadline_seconds(self.profile) or 1
        return ActionReceipt(
            id=self.clock.new_id("rcp"), tenant=ctx.tenant, environment=ctx.environment,
            trace_id=command.trace_id, cause_id=command.id, episode_id=command.episode_id,
            occurred_at=self.clock.now(), producer=PRODUCER, command_id=command.command_id,
            status="unknown", effect="unknown", error={"code": code.value, "retry": "after_reconcile"},
            reconciliation={"deadline": later(self.clock.now(), seconds), "owner": "core"})

    def _failure(self, ctx: TrustedContext, command: ActionCommand, code: ErrorCode) -> ActionReceipt:
        return ActionReceipt(
            id=self.clock.new_id("rcp"), tenant=ctx.tenant, environment=ctx.environment,
            trace_id=command.trace_id, cause_id=command.id, episode_id=command.episode_id,
            occurred_at=self.clock.now(), producer=PRODUCER, command_id=command.command_id,
            status="failure", effect="not_applied", error={"code": code.value, "retry": "never"})

    def _keep(self, receipt: ActionReceipt) -> ActionReceipt:
        self.ledger.append(receipt)
        if self.on_receipt is not None:
            self.on_receipt(receipt)
        return receipt

    def settle(self, ctx: TrustedContext, command: ActionCommand, guard: EffectGuard | None,
               attempt: int = 1) -> Settled:
        command = self.ledger.register(command)
        step = next_step(self.ledger, command, now=self.clock.now(),
                         retention=retention_seconds(self.profile, self.executor), attempt=attempt)
        self.log.append((command.command_id, step))
        if step in ("done", "failed", "to_person"):
            return Settled(step, self.ledger.latest(command.command_id))
        if step == "locate":
            found = self.executor.locate(ctx, command.idempotency.scope, command.idempotency.key)
            if found is None or found.status in OPEN:
                return Settled("to_person", self.ledger.latest(command.command_id))
            return Settled("locate", self._keep(found))
        if step == "reconcile":
            return Settled(step, self._keep(self.executor.reconcile(ctx, command)))
        if guard is None:
            raise ValueError("executar exige a guarda do ponto de efeito")
        try:
            receipt = self.executor.execute(ctx, command, guard)
        except PortError as error:
            if error.code is ErrorCode.IDEMPOTENCY_CONFLICT:
                return Settled(step, self.ledger.latest(command.command_id), conflict=error.code.value)
            if error.may_have_happened:
                return Settled(step, self._keep(self._unknown(ctx, command, error.code)))
            # Erro de porta que prova que nada foi submetido: falha definitiva, sem efeito.
            return Settled(step, self._keep(self._failure(ctx, command, error.code)))
        return Settled(step, self._keep(receipt))


def work_execution(ctx: TrustedContext, *, store: Any, settler: Settler,
                   guard_for: Callable[[ActionCommand], EffectGuard], lease_seconds: int = 60) -> Settled | None:
    """O trabalhador da caixa de saída: reivindica uma execução e a leva ao recibo.

    Tentativa depois da primeira (o trabalhador anterior morreu segurando o
    trabalho) reconcilia antes de repetir, com a mesma chave (K14).
    """
    claim = store.claim_work(ctx, "execute", lease_seconds)
    if claim is None:
        return None
    command = settler.ledger.commands[claim.work.payload["command_id"]]
    settled = settler.settle(ctx, command, guard_for(command), attempt=claim.attempt)
    if settled.receipt is not None and settled.receipt.status not in OPEN:
        store.complete_work(ctx, claim.work.work_id)
    return settled
