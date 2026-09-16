"""Thin idempotency helpers for remote surface mutations."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import IdempotencyKey

from shopman.shop.services.observability import current_operational_context, operational_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoteMutationResult:
    """Result of an idempotent remote mutation execution."""

    response_body: dict[str, Any]
    response_code: int
    replayed: bool = False


class RemoteMutationConflict(Exception):
    """A chave já pertence a outra intenção; nada deve ser executado."""


class RemoteMutationInProgress(Exception):
    """Raised when the same idempotency key is already running."""


def _payload_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def fingerprint(payload: Any) -> str:
    """Stable digest for the legacy surface-mutation contract."""
    return _payload_fingerprint(payload)


def mutation_scope(*parts: str) -> str:
    """Bound scopes to the existing 64-character column without losing identity."""
    return fingerprint(parts)


def idempotency_key_from_request(request: Any, *, fallback: str) -> str:
    """Resolve an idempotency key from HTTP headers/body with a safe fallback."""

    headers = request.headers
    data = getattr(request, "data", {})
    data = data if isinstance(data, dict) else {}
    values = [
        headers.get("Idempotency-Key"),
        headers.get("X-Idempotency-Key"),
        data.get("idempotency_key"),
    ]
    keys = []
    for value in values:
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise RemoteMutationConflict("Chave de tentativa inválida.")
        if value.strip():
            keys.append(_normalize_key(value))
    if len(set(keys)) > 1:
        raise RemoteMutationConflict("As chaves da tentativa divergem. Nenhuma ação foi aplicada.")
    return keys[0] if keys else _normalize_key(fallback)


def run_idempotent_mutation(
    *,
    scope: str,
    key: str,
    execute: Callable[[], tuple[dict[str, Any], int]],
    cache_response: Callable[[dict[str, Any], int], bool] | None = None,
    fingerprint: str | None = None,
    payload: Any = None,
    local_atomic: bool = False,
) -> RemoteMutationResult:
    """Run ``execute`` once for ``scope``/``key`` and replay cached responses."""

    if fingerprint is not None:
        if cache_response is not None or payload is not None or local_atomic:
            raise ValueError("Local mutations always retain their result")
        try:
            result = _run_local_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)
        except (RemoteMutationConflict, RemoteMutationInProgress) as exc:
            if current_operational_context():
                operational_event(
                    "operator.command.blocked",
                    intention_digest=hashlib.sha256(key.encode()).hexdigest(),
                    reason=type(exc).__name__,
                )
            raise
        _observe_local_result(result, key=key, event="operator.command.local_result")
        return result

    # Opt-in only: callers with remote effects retain provider reconciliation semantics.
    with transaction.atomic() if local_atomic else nullcontext():
        idem = _acquire(scope=scope, key=key)
        digest = _payload_fingerprint(payload) if payload is not None else ""
        if digest and idem.request_fingerprint != digest:
            if idem.request_fingerprint or idem.status == "done":
                raise RemoteMutationConflict(
                    "Esta tentativa pertence a outra escolha ou a um recibo legado. Confira antes de continuar."
                )
            idem.request_fingerprint = digest
            idem.save(update_fields=["request_fingerprint"])
        if idem.status == "done" and idem.response_body is not None:
            return RemoteMutationResult(
                response_body=idem.response_body,
                response_code=idem.response_code or 200,
                replayed=True,
            )

        try:
            response_body, response_code = execute()
        except Exception:
            idem.status = "failed"
            idem.save(update_fields=["status"])
            raise

        should_cache = cache_response(response_body, response_code) if cache_response else response_code < 500
        if should_cache:
            idem.status = "done"
            idem.response_body = response_body
            idem.response_code = response_code
            idem.save(update_fields=["status", "response_body", "response_code"])
        else:
            idem.status = "failed"
            idem.save(update_fields=["status"])
        return RemoteMutationResult(
            response_body=response_body,
            response_code=response_code,
            replayed=False,
        )


def _acquire(*, scope: str, key: str) -> IdempotencyKey:
    expires_at = timezone.now() + timedelta(hours=24)
    with transaction.atomic():
        idem, created = IdempotencyKey.objects.select_for_update().get_or_create(
            scope=scope,
            key=key,
            defaults={"status": "in_progress", "expires_at": expires_at},
        )
        if created:
            return idem
        if idem.status == "done" and idem.response_body is not None:
            return idem
        if idem.status == "in_progress" and (
            idem.request_fingerprint or idem.expires_at is None or idem.expires_at > timezone.now()
        ):
            raise RemoteMutationInProgress(f"Mutation already in progress for {scope}:{key}")
        idem.status = "in_progress"
        idem.expires_at = expires_at
        idem.save(update_fields=["status", "expires_at"])
        return idem


def _normalize_key(value: str) -> str:
    key = value.strip()
    if len(key) <= 128:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


_LOCAL_CONTRACT = "local-mutation-v1"


def mutation_fingerprint(payload: dict[str, Any]) -> str:
    """Digest determinístico; callers normalizam inputs e incluem ator/base/versão."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _local_result(idem: IdempotencyKey, fingerprint: str | None = None) -> RemoteMutationResult:
    envelope = idem.response_body or {}
    if envelope.get("contract") != _LOCAL_CONTRACT:
        raise RemoteMutationConflict("Scope belongs to a different mutation contract")
    if fingerprint is not None and envelope.get("fingerprint") != fingerprint:
        raise RemoteMutationConflict("Idempotency key belongs to a different intention")
    return RemoteMutationResult(envelope["result"], idem.response_code or 200, replayed=True)


def lookup_local_mutation(*, scope: str, key: str, fingerprint: str | None = None) -> RemoteMutationResult | None:
    """Consulta pura; caller autoriza a pessoa e constrói seu escopo antes de chamar.

    Nenhum resgate de gateway, criação de chave ou reset por expiração nesta leitura.
    Uma intenção local não commitada ainda não é visível: ausência NÃO autoriza nova
    chave; o cliente conserva a intenção e pode repetir a mesma chamada.
    """
    idem = IdempotencyKey.objects.filter(scope=scope, key=key).first()
    if idem is None:
        return None
    if idem.status != "done":
        raise RemoteMutationInProgress("Mutation has no committed result")
    result = _local_result(idem, fingerprint)
    _observe_local_result(result, key=key, event="operator.command.receipt")
    return result


def _run_local_mutation(*, scope: str, key: str, fingerprint: str, execute) -> RemoteMutationResult:
    """Efeito local + resultado atômicos. Rede pertence a Directive, fora deste lock."""
    if not key or not fingerprint:
        raise ValueError("Local mutation requires key and fingerprint")
    with transaction.atomic():
        idem = _acquire(scope=scope, key=key)
        if idem.status == "done":
            return _local_result(idem, fingerprint)
        # Savepoint separado: uma recusa não pode confirmar escrita parcial do executor.
        with transaction.atomic():
            body, code = execute()
            if code >= 400:
                transaction.set_rollback(True)
        if code >= 500:
            # Sem resposta definitiva, também não confirmar uma chave sem resultado.
            transaction.set_rollback(True)
            return RemoteMutationResult(body, code)
        idem.status = "done"
        idem.response_body = {"contract": _LOCAL_CONTRACT, "fingerprint": fingerprint, "result": body}
        idem.response_code = code
        idem.save(update_fields=["status", "response_body", "response_code"])
        return RemoteMutationResult(body, code)


def _observe_local_result(result: RemoteMutationResult, *, key: str, event: str):
    context = current_operational_context()
    if not context:
        return
    body = result.response_body
    outcome = body.get("outcome")
    outcome = outcome if outcome in {"applied", "not_applied", "unknown", "in_progress"} else "unclassified"
    fields = {
        **context,
        "intention_digest": hashlib.sha256(key.encode()).hexdigest(),
        "response_status": result.response_code,
        "outcome": outcome,
        "replayed": result.replayed,
    }
    for name in ("directive_id", "shift_id", "cash_entry_id"):
        value = body.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            fields[name] = value
    ids = body.get("directive_ids")
    if isinstance(ids, list) and all(isinstance(value, int) and not isinstance(value, bool) for value in ids):
        fields["directive_ids"] = ids
    # Um outer atomic ainda pode reverter o comando: só logar commit confirmado.
    transaction.on_commit(lambda: operational_event(event, **fields), robust=True)
