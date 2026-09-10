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
    fingerprint: str = "",
    atomic_effect: bool = False,
) -> RemoteMutationResult:
    """Run ``execute`` once for ``scope``/``key`` and replay cached responses."""

    if atomic_effect:
        return _run_atomic_mutation(scope=scope, key=key, execute=execute,
            cache_response=cache_response, fingerprint=fingerprint)
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


class RemoteMutationConflict(Exception):
    """A chave já identifica outro conteúdo ou uma evidência legada."""


def mutation_fingerprint(payload: dict) -> str:
    """Hash determinístico sem persistir credenciais nem dados pessoais brutos."""
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()
                    if k not in {"pin", "token", "badge", "password", "client_request_id"}}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(clean(payload), sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _run_atomic_mutation(*, scope, key, execute, cache_response, fingerprint):
    # Só efeitos internos: rollback deve alcançar o owner do efeito. Não usar
    # este modo para um provider HTTP, e-mail, fiscal ou hardware.
    with transaction.atomic():
        idem, created = IdempotencyKey.objects.select_for_update().get_or_create(
            scope=scope, key=key, defaults={"status": "in_progress",
                "expires_at": timezone.now() + timedelta(days=1),
                "response_body": {"version": 1, "fingerprint": fingerprint}},
        )
        envelope = idem.response_body or {}
        if envelope.get("version") != 1 or envelope.get("fingerprint") != fingerprint:
            raise RemoteMutationConflict()
        if not created:
            if idem.status == "done":
                return RemoteMutationResult(envelope["result"], idem.response_code or 200, True)
            # Expiração é retenção, nunca autorização para repetir dinheiro.
            raise RemoteMutationInProgress()
        body, code = execute()
        if cache_response(body, code) if cache_response else code < 300:
            idem.status = "done"
            idem.response_code = code
            idem.response_body = {**envelope, "result": body}
            idem.save(update_fields=["status", "response_body", "response_code"])
        else:
            # Uma resposta recusada também pode ter sido montada depois de um
            # efeito parcial: desfazer tudo, inclusive a tentativa, antes de sair.
            transaction.set_rollback(True)
        return RemoteMutationResult(body, code)
