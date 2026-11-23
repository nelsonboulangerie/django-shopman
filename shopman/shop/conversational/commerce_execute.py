"""``CommerceExecutePort`` sobre o Shopman: guarda, efeito e recibo numa transação só (N6).

O contrato de efeito do framework (``spec/08-effect.md``, v2 4.7) pede quatro coisas do
executor, e é assim que o Shopman as cumpre:

- **a guarda no ponto de efeito**: ``execute`` abre UMA transação do PostgreSQL (``durable``:
  ninguém de fora a engole, e o commit dela é o commit de verdade). Dentro dela, nesta
  ordem: a chave de idempotência é reivindicada (``remote_mutations.run_idempotent_mutation``
  com ``local_atomic``), o sítio trava a linha da conversa e o alvo e lê o estado vigente, a
  ``EffectGuard`` confere esse estado, o efeito que já existe roda e o recibo é gravado na
  chave. A trava é a mesma de ``service.mark_handoff`` (``effect_authority`` do N2, #2625):
  com as duas pontas travando a mesma linha, transferência e efeito ficam em fila, e da
  guarda ao commit ninguém muda a posse;
- **mesma chave e mesmo conteúdo devolvem o recibo existente**, sem guarda nem efeito; mesma
  chave com outro conteúdo é ``idempotency_conflict`` e o recibo fica como estava (a
  impressão digital da chave é o ``content_hash`` do comando);
- **recusa é recibo**: guarda ou sítio que recusa grava ``failure / not_applied`` com
  ``retry: never``; o efeito recusado volta ao ponto de salvamento e nada dele fica;
- **resposta que não chegou é ``effect_unknown``**, nunca falha: se o corpo terminou e a
  saída da transação levantou (o commit, ou um gancho de ``on_commit`` depois dele), a
  chave é lida de novo; achou o recibo, ele vale; não achou, ``effect_unknown``.

``locate`` e ``reconcile`` leem pela ``remote_mutations.lookup_idempotent_mutation``. A
``reconcile`` que não acha recibo não chuta: reivindica a chave, o que ESPERA (trava de
linha do banco) qualquer execução da mesma chave ainda em voo; se não havia nada, sela a
chave como "não aplicado", e desde então nenhuma execução atrasada daquele comando acontece.

O que é da superfície fica fora daqui: ``storefront`` importa ``shop``, nunca o contrário
(regra de dependência do ``CLAUDE.md``). Quem sabe travar a conversa e chamar pedido,
desconto, cancelamento e acréscimo é o ``EffectSite``, que a Concierge injeta
(``shopman/storefront/concierge/effect_site.py``).

Retenção: o recibo de sucesso tem impressão digital e fica ``done``, e a limpeza
(``cleanup_idempotency_keys``, ``PERSISTENT_RECEIPTS``) nunca o apaga; o recibo de recusa
(``failed``, 4xx) vence com o ``expires_at`` da chave, 24 h. A garantia declarada é a menor.

Rede não entra aqui: o Pix e o resto do lifecycle rodam em ``on_commit``, depois do commit
desta transação.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from conversational_commerce.contracts import ActionCommand, ActionReceipt, sha256_hash
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import Capabilities, EffectGuard, EffectState, PortError, TrustedContext
from conversational_commerce.ports.commerce_execute import OPERATIONS
from django.db import transaction
from shopman.orderman.models import IdempotencyKey

from shopman.shop.services import remote_mutations

logger = logging.getLogger(__name__)

PORT = "commerce_execute"
PRODUCER = {"name": "shopman-commerce-execute", "version": "1"}
FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
#: Os termos, no Shopman, são a revisão oferecida (o ``quote_token`` da Concierge). O
#: comando leva a revisão confirmada neste parâmetro; o sítio diz qual vigora agora.
TERMS_REF = "terms_ref"
#: O recibo de recusa vence com o ``expires_at`` padrão da chave (24 h).
RETENTION_SECONDS = 24 * 3600
RECEIPT_CONTRACT = "cc-action-receipt-v1"
SCOPE_PREFIX = "cc.execute:"
APPLIED = 200
REFUSED = 409


def instant(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).astimezone(UTC).strftime(FORMAT)


class SystemClock:
    """O relógio de parede. Os testes injetam o ``FakeClock`` do framework."""

    def now(self) -> str:
        return instant()


@dataclass(frozen=True)
class Reading:
    """O estado vigente, lido pelo sítio com as travas do efeito já tomadas."""

    ownership_epoch: int
    versions: Mapping[str, int] = field(default_factory=dict)
    #: A revisão dos termos que vigora agora; ``None`` quando não há termos vigentes.
    terms_ref: str | None = None


@dataclass(frozen=True)
class Done:
    """O que o efeito existente fez: aplicado (com as referências no domínio) ou recusado."""

    applied: bool
    domain_refs: Mapping[str, str] = field(default_factory=dict)
    observed_versions: Mapping[str, int] = field(default_factory=dict)
    #: Código do ``ErrorCode`` quando não aplicou.
    refusal: str = ErrorCode.PROVIDER_UNAVAILABLE.value


class EffectSite(Protocol):
    """Onde o efeito acontece: a superfície trava, lê e chama o executor que já existe.

    ``lock`` roda DENTRO da transação do executor, antes da guarda: trava a linha da
    conversa (e o alvo), confere que o alvo é do sujeito e devolve o estado vigente. Levanta
    ``PortError`` quando o comando não pode nem ser conferido (posse perdida, alvo alheio).
    ``apply`` chama o efeito existente e diz o que ele fez; nunca abre rede fora do
    ``on_commit``.
    """

    actions: tuple[str, ...]

    def lock(self, ctx: TrustedContext, command: ActionCommand) -> Reading: ...

    def apply(self, ctx: TrustedContext, command: ActionCommand) -> Done: ...


def storage_key(ctx: TrustedContext, scope: str, key: str) -> tuple[str, str]:
    """A chave do framework na ``IdempotencyKey`` (escopo de 64, chave de 128 caracteres).

    O inquilino e o ambiente entram no escopo: a mesma chave de outro inquilino é outra linha.
    """
    digest = hashlib.sha256(f"{ctx.tenant}\x1f{ctx.environment}\x1f{scope}".encode()).hexdigest()[:48]
    stored_key = key if len(key) <= 128 else "sha256:" + hashlib.sha256(key.encode()).hexdigest()
    return SCOPE_PREFIX + digest, stored_key


def _fingerprint(content_hash: str) -> dict[str, str]:
    return {"contract": RECEIPT_CONTRACT, "content_hash": content_hash}


def _body(command: ActionCommand, receipt: ActionReceipt) -> dict[str, Any]:
    return {**_fingerprint(command.content_hash), "receipt": receipt.to_document()}


def _receipt_of(body: Mapping[str, Any]) -> ActionReceipt:
    if body.get("contract") != RECEIPT_CONTRACT:
        raise PortError(ErrorCode.IDEMPOTENCY_CONFLICT, "a chave guarda outro contrato")
    return ActionReceipt.from_document(body["receipt"])


@dataclass
class ShopmanCommerceExecute:
    """O executor do contrato de efeito sobre o Shopman, para os efeitos do ``site``."""

    site: EffectSite
    clock: Any = None
    retention_seconds: int = RETENTION_SECONDS

    PORT = PORT

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = SystemClock()

    def capabilities(self) -> Capabilities:
        return Capabilities(port=PORT, operations=OPERATIONS, guarantees={
            "atomic_effect_guard": True, "idempotency_retention_seconds": self.retention_seconds,
            "reconciliation": True, "reconcile_waits_for_in_flight": True})

    # ── execute ──────────────────────────────────────────────────────────────
    def execute(self, ctx: TrustedContext, command: ActionCommand, guard: EffectGuard) -> ActionReceipt:
        self._authorize(ctx, command)
        if command.action not in self.site.actions:
            raise PortError(ErrorCode.CAPABILITY_MISSING, f"o Shopman não executa {command.action}")
        if transaction.get_connection().in_atomic_block:
            # O recibo de sucesso só pode sair depois do commit de verdade.
            raise RuntimeError("o executor é a transação de fora: não o chame dentro de outra")
        scope, key = storage_key(ctx, command.idempotency.scope, command.idempotency.key)
        fingerprint = _fingerprint(command.content_hash)
        body_done = False
        try:
            with transaction.atomic(durable=True):
                result = remote_mutations.run_idempotent_mutation(
                    scope=scope, key=key, payload=fingerprint, local_atomic=True,
                    execute=lambda: self._effect_unit(ctx, command, guard),
                    cache_response=lambda body, code: code == APPLIED)
                body_done = True
        except remote_mutations.RemoteMutationConflict as conflict:
            raise PortError(ErrorCode.IDEMPOTENCY_CONFLICT,
                            "mesma chave com outro conteúdo; o recibo fica como estava") from conflict
        except remote_mutations.RemoteMutationInProgress as running:
            raise PortError(ErrorCode.EFFECT_PENDING, "a mesma chave está em execução") from running
        except PortError:
            raise
        except Exception as error:
            if not body_done:
                # Levantou dentro da transação: o banco desfez tudo, nada foi aplicado.
                logger.warning("conversational.execute: falhou antes do commit command=%s", command.command_id,
                               exc_info=True)
                raise PortError(ErrorCode.PROVIDER_UNAVAILABLE, f"nada aplicado: {type(error).__name__}") from error
            # O corpo terminou e a saída levantou: o commit pode ter acontecido.
            logger.warning("conversational.execute: saída da transação falhou command=%s", command.command_id,
                           exc_info=True)
            found = self._lookup(scope, key, fingerprint)
            if found is not None:
                return found
            raise PortError(ErrorCode.EFFECT_UNKNOWN, "a resposta não chegou; reconcilie com a mesma chave") from error
        return _receipt_of(result.response_body)

    def _effect_unit(self, ctx: TrustedContext, command: ActionCommand, guard: EffectGuard) -> tuple[dict, int]:
        """Trava, guarda, efeito e recibo. Roda dentro da transação de ``execute``."""
        try:
            reading = self.site.lock(ctx, command)
            guard.verify(self._state(command, reading))
        except PortError as refused:
            if refused.may_have_happened:
                raise
            return _body(command, self._failure(ctx, command, refused.code.value)), REFUSED
        with transaction.atomic():
            done = self.site.apply(ctx, command)
            applied = done.applied and bool(done.domain_refs)
            if not applied:
                # Recusa do efeito (ou sucesso que não aponta o efeito): nada dele fica.
                transaction.set_rollback(True)
        if not applied:
            return _body(command, self._failure(ctx, command, _code(done.refusal))), REFUSED
        receipt = self._receipt(ctx, command, status="success", effect="applied", domain_refs=dict(done.domain_refs),
                                observed_versions=dict(done.observed_versions))
        return _body(command, receipt), APPLIED

    def _state(self, command: ActionCommand, reading: Reading) -> EffectState:
        """O estado que a guarda confere. Os termos vigentes são os do comando só se a revisão é a mesma."""
        terms_hash = None
        if command.terms_hash is not None:
            bound = command.parameters.get(TERMS_REF)
            if bound is None:
                # O comando do motor não leva a revisão da casa: os termos dele são selados com a revisão
                # do alvo (``ShopmanCommerceRead.quote``: ``terms_id=<sacola>-r<rev>``, ``version=rev``).
                # Vigoram enquanto o alvo é a mesma revisão; qualquer mudança na sacola sobe a revisão.
                in_force = all(reading.versions.get(target) == expected
                               for target, expected in command.expected_versions.items()) \
                    and bool(command.expected_versions)
            else:
                in_force = reading.terms_ref is not None and bound == reading.terms_ref
            terms_hash = command.terms_hash if in_force else sha256_hash({TERMS_REF: reading.terms_ref})
        return EffectState(now=self.clock.now(), terms_hash=terms_hash, versions=dict(reading.versions),
                           ownership_epoch=reading.ownership_epoch)

    # ── locate e reconcile ───────────────────────────────────────────────────
    def locate(self, ctx: TrustedContext, scope: str, key: str) -> ActionReceipt | None:
        """O recibo guardado pela chave, sem o conteúdo do comando. Só lê; nunca executa."""
        stored_scope, stored_key = storage_key(ctx, scope, key)
        row = IdempotencyKey.objects.filter(scope=stored_scope, key=stored_key).values("response_body").first()
        content_hash = ((row or {}).get("response_body") or {}).get("content_hash")
        if not content_hash:
            return None
        return self._lookup(stored_scope, stored_key, _fingerprint(content_hash))

    def reconcile(self, ctx: TrustedContext, command: ActionCommand) -> ActionReceipt:
        """O que aconteceu com ESTA chave. Nunca executa o efeito.

        Achou recibo: um recibo novo que o substitui, com o mesmo estado e o mesmo efeito.
        Não achou: reivindica a chave, esperando qualquer execução em voo; se não havia
        nada, sela a chave com ``failure / not_applied`` (o banco garante que nada aplicou).
        """
        self._authorize(ctx, command)
        scope, key = storage_key(ctx, command.idempotency.scope, command.idempotency.key)
        fingerprint = _fingerprint(command.content_hash)
        stored = self._lookup(scope, key, fingerprint)
        if stored is None:
            absent = self._failure(ctx, command, ErrorCode.PROVIDER_UNAVAILABLE.value)
            try:
                with transaction.atomic():
                    sealed = remote_mutations.run_idempotent_mutation(
                        scope=scope, key=key, payload=fingerprint, local_atomic=True,
                        execute=lambda: (_body(command, absent), REFUSED),
                        cache_response=lambda body, code: code == APPLIED)
            except remote_mutations.RemoteMutationConflict as conflict:
                raise PortError(ErrorCode.IDEMPOTENCY_CONFLICT, "a chave é de outro conteúdo") from conflict
            if not sealed.replayed:
                return absent
            stored = _receipt_of(sealed.response_body)
        return self._receipt(ctx, command, status=stored.status, effect=stored.effect,
                             domain_refs=dict(stored.domain_refs), observed_versions=dict(stored.observed_versions),
                             error=stored.error, supersedes=stored.id)

    def _lookup(self, scope: str, key: str, fingerprint: Mapping[str, str]) -> ActionReceipt | None:
        try:
            found = remote_mutations.lookup_idempotent_mutation(scope=scope, key=key, payload=dict(fingerprint))
        except remote_mutations.RemoteMutationConflict as conflict:
            raise PortError(ErrorCode.IDEMPOTENCY_CONFLICT, "a chave é de outro conteúdo") from conflict
        except remote_mutations.RemoteMutationInProgress as running:
            raise PortError(ErrorCode.EFFECT_PENDING, "a chave está em execução") from running
        return None if found is None else _receipt_of(found.response_body)

    # ── peças ────────────────────────────────────────────────────────────────
    def _authorize(self, ctx: TrustedContext, command: ActionCommand) -> None:
        if (command.tenant, command.environment) != (ctx.tenant, ctx.environment):
            raise PortError(ErrorCode.OBJECT_FORBIDDEN, "comando de outro inquilino ou ambiente")

    def _receipt(self, ctx: TrustedContext, command: ActionCommand, **fields: Any) -> ActionReceipt:
        return ActionReceipt(
            id=f"rcp-{uuid.uuid4().hex}", tenant=ctx.tenant, environment=ctx.environment, trace_id=command.trace_id,
            cause_id=command.id, episode_id=command.episode_id, occurred_at=self.clock.now(), producer=PRODUCER,
            command_id=command.command_id, **fields)

    def _failure(self, ctx: TrustedContext, command: ActionCommand, code: str) -> ActionReceipt:
        return self._receipt(ctx, command, status="failure", effect="not_applied",
                             error={"code": code, "retry": "never"})


def _code(value: str) -> str:
    try:
        return ErrorCode(value).value
    except ValueError:
        return ErrorCode.PROVIDER_UNAVAILABLE.value
