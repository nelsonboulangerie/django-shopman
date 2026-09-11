"""Thin idempotency helpers for remote surface mutations."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import IdempotencyKey

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


def idempotency_key_from_request(request: Any, *, fallback: str) -> str:
    """Resolve an idempotency key from HTTP headers/body with a safe fallback."""

    header_key = ""
    try:
        header_key = str(request.headers.get("Idempotency-Key") or "").strip()
    except Exception:
        logger.debug("remote_mutations.idempotency_key_from_request degraded; using fallback", exc_info=True)
        header_key = ""

    body_key = ""
    try:
        data = request.data if hasattr(request, "data") else {}
        body_key = str((data or {}).get("idempotency_key") or "").strip()
    except Exception:
        logger.debug("remote_mutations.idempotency_key_from_request degraded; using fallback", exc_info=True)
        body_key = ""

    return _normalize_key(header_key or body_key or fallback)


def run_idempotent_mutation(
    *,
    scope: str,
    key: str,
    execute: Callable[[], tuple[dict[str, Any], int]],
    cache_response: Callable[[dict[str, Any], int], bool] | None = None,
    fingerprint: str | None = None,
) -> RemoteMutationResult:
    """Run ``execute`` once for ``scope``/``key`` and replay cached responses."""

    if fingerprint is not None:
        if cache_response is not None:
            raise ValueError("Local mutations always retain their result")
        return _run_local_mutation(scope=scope, key=key, fingerprint=fingerprint, execute=execute)

    idem = _acquire(scope=scope, key=key)
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
        if idem.status == "in_progress" and (idem.expires_at is None or idem.expires_at > timezone.now()):
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
    return _local_result(idem, fingerprint)


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
