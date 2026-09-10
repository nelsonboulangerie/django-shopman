"""Server-owned preparation label composition and durable relay delivery."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from shopman.backstage.models import PrintAgentCredential, PrintAttempt, PrintJob
from shopman.backstage.services.receipt_escpos import production_label_run

MAX_PAYLOAD_BYTES = 512 * 1024
MAX_LABELS_PER_JOB = 50
LEASE_SECONDS = 45
JOB_LIFETIME = timedelta(hours=2)
RENDERER_VERSION = 1


class PrintJobError(Exception):
    def __init__(self, message: str, *, code: str = "print_job_error", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PrinterConfig:
    enabled: bool
    roll_width_mm: int
    columns: int
    cut_mode: str
    role: str
    problem: str = ""

    @property
    def accepts_preparation(self) -> bool:
        return self.enabled and self.role == "preparation" and not self.problem

    @classmethod
    def from_terminal(cls, terminal) -> PrinterConfig:
        metadata = terminal.metadata if isinstance(terminal.metadata, dict) else {}
        hardware = metadata.get("hardware") if isinstance(metadata.get("hardware"), dict) else {}
        raw = hardware.get("printer") if isinstance(hardware.get("printer"), dict) else {}
        if not raw or raw.get("enabled") is False:
            return cls(False, 0, 0, "", "")
        try:
            roll = int(raw.get("roll_width_mm"))
            columns = int(raw.get("columns"))
        except (TypeError, ValueError):
            return cls(True, 0, 0, "", "", "Informe rolo e colunas da impressora.")
        cut_mode = str(raw.get("cut_mode") or "").strip()
        role = str(raw.get("role") or "").strip()
        problem = ""
        if roll != 80 or columns != 48:
            problem = "Etiquetas de preparação exigem rolo de 80 mm e 48 colunas."
        elif cut_mode not in {"partial", "none"}:
            problem = "Escolha corte parcial ou sem corte."
        elif role != "preparation":
            problem = "A impressora não está marcada para preparação."
        return cls(True, roll, columns, cut_mode, role, problem)


@dataclass(frozen=True)
class PrintDestination:
    terminal: object | None
    label: str
    status_label: str
    available: bool
    problem: str = ""


def _terminal_label(terminal) -> str:
    return "Este dispositivo" if terminal is None else str(terminal.label or terminal.ref)


def resolve_destination(*, station_ref: str = "") -> PrintDestination:
    """Resolve the printer server-side; never accept a target from the tablet."""
    from shopman.cashman.models import Terminal

    station = Terminal.objects.filter(ref=station_ref, is_active=True).first() if station_ref else None
    if station is not None:
        station_meta = station.metadata if isinstance(station.metadata, dict) else {}
        station_cfg = station_meta.get("station") if isinstance(station_meta.get("station"), dict) else {}
        target_ref = str(station_cfg.get("print_target_ref") or "").strip()
        if target_ref:
            target = Terminal.objects.filter(ref=target_ref, is_active=True).first()
            if target is None:
                return PrintDestination(None, "", "Destino não encontrado", False, "Destino de impressão inativo.")
            config = PrinterConfig.from_terminal(target)
            if not config.accepts_preparation:
                return PrintDestination(
                    target, _terminal_label(target), "Configuração incompleta", False, config.problem
                )
            return _destination_health(target)

        own_config = PrinterConfig.from_terminal(station)
        if own_config.accepts_preparation:
            return _destination_health(station)

    candidates = []
    invalid = []
    for terminal in Terminal.objects.filter(is_active=True).order_by("ref"):
        config = PrinterConfig.from_terminal(terminal)
        if config.accepts_preparation:
            candidates.append(terminal)
        elif config.enabled and config.role == "preparation":
            invalid.append((terminal, config.problem))
    if len(candidates) == 1:
        return _destination_health(candidates[0])
    if len(candidates) > 1:
        return PrintDestination(
            None,
            "",
            "Escolha a impressora da estação",
            False,
            "Há mais de uma impressora de preparação e a estação não define print_target_ref.",
        )
    if invalid:
        terminal, problem = invalid[0]
        return PrintDestination(terminal, _terminal_label(terminal), "Configuração incompleta", False, problem)
    return PrintDestination(None, "", "Impressora não configurada", False, "Configure uma impressora de preparação.")


def _destination_health(terminal) -> PrintDestination:
    credential = (
        PrintAgentCredential.objects.filter(terminal=terminal, is_active=True).order_by("-last_seen_at", "-pk").first()
    )
    paired = credential is not None
    recently_seen = bool(
        credential
        and credential.last_seen_at
        and credential.last_seen_at >= timezone.now() - timedelta(seconds=LEASE_SECONDS)
    )
    return PrintDestination(
        terminal,
        _terminal_label(terminal),
        "Pronta" if recently_seen else ("Aguardando estação" if paired else "Relay não pareado"),
        paired,
        "" if paired else "Emita uma credencial para o relay deste terminal.",
    )


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def projection_digest(source_revision: str) -> str:
    try:
        algorithm, digest, _rest = str(source_revision).split(":", 2)
    except ValueError:
        return ""
    return digest if algorithm == "sha256" else ""


def _decimal_fact(value) -> str | None:
    if value is None:
        return None
    from decimal import Decimal

    return format(Decimal(str(value)).normalize(), "f")


def _ticket_document(ticket, *, mode: str) -> dict:
    ingredients = [
        {
            "name": str(ingredient.name),
            "sku": str(ingredient.sku),
            "quantity_display": str(ingredient.quantity_display),
            "target_display": str(ingredient.target_display),
            "annotation": str(ingredient.annotation),
            "theoretical_g": _decimal_fact(ingredient.theoretical_g),
            "target_g": _decimal_fact(ingredient.target_g),
            "rounding_delta_g": _decimal_fact(ingredient.rounding_delta_g),
            "accepted_min_g": _decimal_fact(ingredient.accepted_min_g),
            "accepted_max_g": _decimal_fact(ingredient.accepted_max_g),
        }
        for ingredient in ticket.ingredients
    ]
    common = {
        "ticket_ref": ticket.ticket_ref,
        "blind_code": ticket.blind_code,
        "made_display": ticket.made_display,
    }
    if mode == "blind":
        # Keep this allow-list deliberately small.  Adding a field here can
        # pierce blind weighing even when the renderer itself looks harmless.
        return {**common, "ingredients": ingredients}
    return {
        **common,
        "expiry_display": ticket.expiry_display,
        "name": ticket.name,
        "recipe_ref": ticket.recipe_ref,
        "output_sku": ticket.output_sku,
        "output_quantity_display": ticket.output_quantity_display,
        "total_weight_display": ticket.total_weight_display,
        "theoretical_total_g": _decimal_fact(ticket.theoretical_total_g),
        "target_total_g": _decimal_fact(ticket.target_total_g),
        "rounding_delta_total_g": _decimal_fact(ticket.rounding_delta_total_g),
        "sources_display": ticket.sources_display,
        "validity_configured": bool(ticket.validity_configured),
        "validity_source": ticket.validity_source,
    }


def compose_document(projection, *, mode: str, ticket_refs: list[str]) -> dict:
    if mode not in {"blind", "explicit"}:
        raise PrintJobError("Escolha pesagem cega ou etiqueta de preparo.", code="invalid_mode")
    refs = [str(ref).strip() for ref in ticket_refs if str(ref).strip()]
    if not refs or len(refs) > MAX_LABELS_PER_JOB or len(set(refs)) != len(refs):
        raise PrintJobError(
            f"Escolha entre 1 e {MAX_LABELS_PER_JOB} etiquetas distintas.",
            code="invalid_ticket_selection",
        )
    by_ref = {ticket.ticket_ref: ticket for ticket in projection.tickets}
    if any(ref not in by_ref for ref in refs):
        raise PrintJobError(
            "Uma etiqueta não pertence mais a esta pesagem. Atualize a tela.", code="stale_projection", status_code=409
        )

    if mode == "blind":
        by_code: dict[str, set[str]] = {}
        for ticket in projection.tickets:
            by_code.setdefault(ticket.blind_code, set()).add(ticket.ticket_ref)
        ambiguous = sorted(code for code, mapped in by_code.items() if len(mapped) > 1)
        if ambiguous:
            raise PrintJobError(
                "O mesmo código cego identifica preparos congelados diferentes. Corrija o planejamento antes de imprimir.",
                code="ambiguous_blind_code",
                status_code=409,
            )
    selected_documents = [_ticket_document(by_ref[ref], mode=mode) for ref in refs]
    if mode == "blind":
        # One physical label per ingredient.  A ticket_ref selects a preparo;
        # the frozen print document expands that intent before hashing so both
        # label_count and every reprint retain the exact physical cardinality.
        labels = [
            {**ticket, "ingredients": [ingredient]}
            for ticket in selected_documents
            for ingredient in ticket["ingredients"]
        ]
    else:
        missing_validity = [
            ticket["name"]
            for ticket in selected_documents
            if not ticket["validity_configured"] or not ticket["expiry_display"]
        ]
        if missing_validity:
            names = ", ".join(missing_validity[:3])
            suffix = "…" if len(missing_validity) > 3 else ""
            raise PrintJobError(
                "A etiqueta interna não pode presumir validade. "
                f"Defina a validade na ficha técnica de: {names}{suffix}.",
                code="preparation_validity_missing",
                status_code=409,
            )
        labels = selected_documents
    if not labels or len(labels) > MAX_LABELS_PER_JOB:
        raise PrintJobError(
            f"A seleção gera {len(labels)} etiquetas; o limite por lote é {MAX_LABELS_PER_JOB}.",
            code="label_limit_exceeded",
        )
    return {
        "contract_version": 2,
        "mode": mode,
        "purpose": "internal_weighing" if mode == "blind" else "internal_preparation",
        "legal_scope": "internal_only_not_for_sale",
        "date_basis": "planned_production_date",
        "selected_date": projection.selected_date,
        "scale_precision_g": str(projection.scale_precision_g),
        "scale_precision_display": projection.scale_precision_display,
        "scale_rounding_note": projection.scale_rounding_note,
        "tickets": labels,
    }


def _render(document: dict, *, config: PrinterConfig, copy_number: int) -> tuple[bytes, str, str]:
    document_bytes = _canonical(document)
    payload = production_label_run(
        document,
        copy_number=copy_number,
        columns=config.columns,
        cut_mode=config.cut_mode,
    )
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise PrintJobError("O lote excede 512 KiB. Imprima em grupos menores.", code="payload_too_large")
    return payload, _sha256(document_bytes), _sha256(payload)


def _request_digest(value: dict) -> str:
    return _sha256(_canonical(value))


def create_job(
    *,
    projection,
    mode: str,
    ticket_refs: list[str],
    transport: str,
    actor,
    station_ref: str,
    source_revision: str,
    idempotency_key: str,
) -> PrintJob:
    if transport not in {PrintJob.Transport.RELAY, PrintJob.Transport.BROWSER}:
        raise PrintJobError("Transporte de impressão inválido.", code="invalid_transport")
    destination = resolve_destination(station_ref=station_ref)
    if transport == PrintJob.Transport.RELAY:
        if not destination.available or destination.terminal is None:
            raise PrintJobError(
                destination.problem or destination.status_label, code="printer_unavailable", status_code=409
            )
        target_terminal = destination.terminal
        config = PrinterConfig.from_terminal(target_terminal)
    else:
        # Browser means exactly this device. Keep the physical relay target
        # null; requested_station_ref already preserves the trusted origin for
        # authorization/audit without pretending a server-side destination.
        target_terminal = None
        config = PrinterConfig(True, 80, 48, "partial", "preparation")
    document = compose_document(projection, mode=mode, ticket_refs=ticket_refs)
    payload, document_hash, payload_hash = _render(document, config=config, copy_number=1)
    attempt = {
        "actor_id": actor.pk,
        "station_ref": station_ref,
        "source_revision": source_revision,
        "mode": mode,
        "transport": transport,
        "ticket_refs": ticket_refs,
        "target_terminal_ref": target_terminal.ref if target_terminal is not None else "",
        "document_sha256": document_hash,
    }
    digest = _request_digest(attempt)
    scope = f"backstage:print:create:{actor.pk}"
    key = str(idempotency_key).strip()

    for _ in range(3):
        try:
            with transaction.atomic():
                from shopman.orderman.models import IdempotencyKey

                receipt = IdempotencyKey.objects.select_for_update().filter(scope=scope, key=key).first()
                if receipt is not None:
                    body = dict(receipt.response_body or {})
                    if body.get("request_digest") != digest:
                        raise PrintJobError(
                            "Esta chave pertence a outra impressão.", code="idempotency_conflict", status_code=409
                        )
                    job = PrintJob.objects.filter(ref=body.get("job_ref")).first()
                    if job is None:
                        raise PrintJobError(
                            "Recibo idempotente sem trabalho de impressão.", code="idempotency_broken", status_code=409
                        )
                    return job
                receipt = IdempotencyKey.objects.create(scope=scope, key=key, status="in_progress")
                job = PrintJob.objects.create(
                    kind=(
                        PrintJob.Kind.PRODUCTION_WEIGHING if mode == "blind" else PrintJob.Kind.PRODUCTION_PREPARATION
                    ),
                    transport=transport,
                    status=PrintJob.Status.QUEUED
                    if transport == PrintJob.Transport.RELAY
                    else PrintJob.Status.PREPARED,
                    target_terminal=target_terminal,
                    requested_by=actor,
                    requested_by_ref=actor.get_username(),
                    requested_station_ref=station_ref,
                    source_revision=source_revision,
                    document=document,
                    document_sha256=document_hash,
                    renderer_version=RENDERER_VERSION,
                    payload=payload,
                    payload_sha256=payload_hash,
                    payload_size=len(payload),
                    label_count=len(document["tickets"]),
                    expires_at=timezone.now() + JOB_LIFETIME,
                )
                receipt.status = "done"
                receipt.response_code = 201
                receipt.response_body = {"request_digest": digest, "job_ref": str(job.ref)}
                receipt.save(update_fields=("status", "response_code", "response_body"))
                return job
        except IntegrityError:
            continue
    raise PrintJobError("Não foi possível adquirir a chave de impressão.", code="idempotency_race", status_code=409)


def _idempotent_job_action(*, job: PrintJob, action: str, key: str, request_body: dict, mutate) -> PrintJob:
    scope = f"backstage:print:{action}:{job.pk}"
    digest = _request_digest(request_body)
    for _ in range(3):
        try:
            with transaction.atomic():
                from shopman.orderman.models import IdempotencyKey

                locked = PrintJob.objects.select_for_update().get(pk=job.pk)
                receipt = IdempotencyKey.objects.select_for_update().filter(scope=scope, key=key).first()
                if receipt is not None:
                    body = dict(receipt.response_body or {})
                    if body.get("request_digest") != digest:
                        raise PrintJobError(
                            "Esta chave pertence a outra ação.", code="idempotency_conflict", status_code=409
                        )
                    result = PrintJob.objects.filter(ref=body.get("job_ref")).first()
                    if result is None:
                        raise PrintJobError(
                            "Recibo idempotente inconsistente.", code="idempotency_broken", status_code=409
                        )
                    return result
                receipt = IdempotencyKey.objects.create(scope=scope, key=key, status="in_progress")
                result = mutate(locked)
                receipt.status = "done"
                receipt.response_code = 200
                receipt.response_body = {"request_digest": digest, "job_ref": str(result.ref)}
                receipt.save(update_fields=("status", "response_code", "response_body"))
                return result
        except IntegrityError:
            continue
    raise PrintJobError("Não foi possível adquirir a chave da ação.", code="idempotency_race", status_code=409)


def retry_job(*, job: PrintJob, actor, idempotency_key: str) -> PrintJob:
    def mutate(locked):
        if locked.confirmation or locked.status not in {PrintJob.Status.FAILED, PrintJob.Status.EXPIRED}:
            raise PrintJobError(
                "Somente uma falha comprovada pode voltar à fila.", code="retry_not_allowed", status_code=409
            )
        locked.status = (
            PrintJob.Status.QUEUED if locked.transport == PrintJob.Transport.RELAY else PrintJob.Status.PREPARED
        )
        locked.confirmation = ""
        locked.confirmation_detail = ""
        locked.confirmed_by = None
        locked.confirmed_by_ref = ""
        locked.confirmed_at = None
        locked.expires_at = timezone.now() + JOB_LIFETIME
        locked.save(
            update_fields=(
                "status",
                "confirmation",
                "confirmation_detail",
                "confirmed_by",
                "confirmed_by_ref",
                "confirmed_at",
                "expires_at",
                "updated_at",
            )
        )
        return locked

    return _idempotent_job_action(
        job=job,
        action="retry",
        key=idempotency_key,
        request_body={"actor_id": actor.pk, "job_ref": str(job.ref)},
        mutate=mutate,
    )


def reprint_job(*, job: PrintJob, actor, station_ref: str, transport: str, idempotency_key: str) -> PrintJob:
    if transport not in {PrintJob.Transport.RELAY, PrintJob.Transport.BROWSER}:
        raise PrintJobError("Transporte de impressão inválido.", code="invalid_transport")

    def mutate(locked):
        if locked.status not in {
            PrintJob.Status.SPOOLED,
            PrintJob.Status.AWAITING_CONFIRMATION,
            PrintJob.Status.CONFIRMED,
            PrintJob.Status.UNCERTAIN,
            PrintJob.Status.FAILED,
        }:
            raise PrintJobError(
                "Esta impressão ainda não admite nova via.", code="reprint_not_allowed", status_code=409
            )
        series_jobs = PrintJob.objects.select_for_update().filter(series_ref=locked.series_ref)
        copy_number = int(series_jobs.aggregate(value=Max("copy_number"))["value"] or 0) + 1
        if transport == PrintJob.Transport.RELAY:
            destination = resolve_destination(station_ref=station_ref)
            if not destination.available or destination.terminal is None:
                raise PrintJobError(
                    destination.problem or destination.status_label, code="printer_unavailable", status_code=409
                )
            target_terminal = destination.terminal
            config = PrinterConfig.from_terminal(target_terminal)
        else:
            target_terminal = None
            config = PrinterConfig(True, 80, 48, "partial", "preparation")
        payload, document_hash, payload_hash = _render(locked.document, config=config, copy_number=copy_number)
        return PrintJob.objects.create(
            kind=locked.kind,
            transport=transport,
            status=PrintJob.Status.QUEUED if transport == PrintJob.Transport.RELAY else PrintJob.Status.PREPARED,
            target_terminal=target_terminal,
            requested_by=actor,
            requested_by_ref=actor.get_username(),
            requested_station_ref=station_ref,
            source_revision=locked.source_revision,
            document=locked.document,
            document_sha256=document_hash,
            renderer_version=RENDERER_VERSION,
            payload=payload,
            payload_sha256=payload_hash,
            payload_size=len(payload),
            label_count=locked.label_count,
            series_ref=locked.series_ref,
            copy_number=copy_number,
            reprint_of=locked,
            expires_at=timezone.now() + JOB_LIFETIME,
        )

    return _idempotent_job_action(
        job=job,
        action="reprint",
        key=idempotency_key,
        request_body={
            "actor_id": actor.pk,
            "station_ref": station_ref,
            "job_ref": str(job.ref),
            "transport": transport,
        },
        mutate=mutate,
    )


def confirm_job(*, job: PrintJob, actor, result: str, detail: str, idempotency_key: str) -> PrintJob:
    # ``failed`` is the transitional wire alias used by the tablet's single
    # negative button.  Once paper may have emerged, the honest fact is an
    # incomplete run and recovery is always a visibly marked new copy.
    normalized = "incomplete" if result == "failed" else result

    def mutate(locked):
        if locked.status not in {
            PrintJob.Status.SPOOLED,
            PrintJob.Status.AWAITING_CONFIRMATION,
            PrintJob.Status.UNCERTAIN,
        }:
            raise PrintJobError(
                "Esta impressão não aguarda confirmação.", code="confirmation_not_allowed", status_code=409
            )
        locked.confirmation = normalized
        locked.confirmation_detail = detail
        locked.confirmed_by = actor
        locked.confirmed_by_ref = actor.get_username()
        locked.confirmed_at = timezone.now()
        locked.status = PrintJob.Status.CONFIRMED if normalized == "confirmed" else PrintJob.Status.FAILED
        locked.save(
            update_fields=(
                "confirmation",
                "confirmation_detail",
                "confirmed_by",
                "confirmed_by_ref",
                "confirmed_at",
                "status",
                "updated_at",
            )
        )
        return locked

    return _idempotent_job_action(
        job=job,
        action="confirm",
        key=idempotency_key,
        request_body={"actor_id": actor.pk, "job_ref": str(job.ref), "result": normalized, "detail": detail},
        mutate=mutate,
    )


def record_browser_result(*, job: PrintJob, actor, result: str, idempotency_key: str) -> PrintJob:
    def mutate(locked):
        if (
            locked.confirmation
            or locked.transport != PrintJob.Transport.BROWSER
            or locked.status
            not in {
                PrintJob.Status.PREPARED,
                PrintJob.Status.FAILED,
            }
        ):
            raise PrintJobError(
                "O trabalho já foi assumido pelo relay.", code="browser_fallback_not_allowed", status_code=409
            )
        sequence = int(locked.attempts.aggregate(value=Max("sequence"))["value"] or 0) + 1
        opened = result == "dialog_opened"
        PrintAttempt.objects.create(
            job=locked,
            sequence=sequence,
            status=PrintAttempt.Status.BROWSER_OPENED if opened else PrintAttempt.Status.BROWSER_UNAVAILABLE,
            acknowledged_at=timezone.now(),
            detail="Fallback confirmado pelo navegador; o diálogo não prova papel impresso.",
        )
        locked.status = PrintJob.Status.AWAITING_CONFIRMATION if opened else PrintJob.Status.FAILED
        locked.save(update_fields=("status", "updated_at"))
        return locked

    return _idempotent_job_action(
        job=job,
        action="browser",
        key=idempotency_key,
        request_body={"actor_id": actor.pk, "job_ref": str(job.ref), "result": result},
        mutate=mutate,
    )


def _lease_digest(token: str) -> str:
    return hmac.new(str(settings.SECRET_KEY).encode(), token.encode(), hashlib.sha256).hexdigest()


def claim_next_job(*, credential: PrintAgentCredential, telemetry: dict) -> tuple[PrintJob, PrintAttempt, str] | None:
    now = timezone.now()
    with transaction.atomic():
        PrintJob.objects.filter(
            target_terminal=credential.terminal,
            status=PrintJob.Status.QUEUED,
            expires_at__lte=now,
        ).update(status=PrintJob.Status.EXPIRED, updated_at=now)
        stale = list(
            PrintAttempt.objects.select_for_update()
            .filter(
                credential__terminal=credential.terminal,
                status=PrintAttempt.Status.LEASED,
                lease_expires_at__lte=now,
                job__status=PrintJob.Status.LEASED,
            )
            .select_related("job")
        )
        for attempt in stale:
            attempt.status = PrintAttempt.Status.EXPIRED
            attempt.detail = "Lease expirou sem ACK; não reenviar automaticamente."
            attempt.save(update_fields=("status", "detail"))
            attempt.job.status = PrintJob.Status.UNCERTAIN
            attempt.job.save(update_fields=("status", "updated_at"))

        credential.last_seen_at = now
        credential.last_build = str(telemetry.get("build") or "")[:120]
        credential.save(update_fields=("last_seen_at", "last_build"))
        job = (
            PrintJob.objects.select_for_update(skip_locked=True)
            .filter(
                target_terminal=credential.terminal,
                transport=PrintJob.Transport.RELAY,
                status=PrintJob.Status.QUEUED,
                expires_at__gt=now,
            )
            .order_by("created_at", "pk")
            .first()
        )
        if job is None:
            return None
        sequence = int(job.attempts.aggregate(value=Max("sequence"))["value"] or 0) + 1
        lease_token = secrets.token_urlsafe(32)
        attempt = PrintAttempt.objects.create(
            job=job,
            sequence=sequence,
            credential=credential,
            lease_token_digest=_lease_digest(lease_token),
            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
            agent_version=str(telemetry.get("version") or "")[:80],
            agent_build=str(telemetry.get("build") or "")[:120],
            queue_name=str(telemetry.get("queue") or "")[:160],
            health=str(telemetry.get("health") or "")[:40],
        )
        job.status = PrintJob.Status.LEASED
        job.save(update_fields=("status", "updated_at"))
        return job, attempt, lease_token


def claimed_job_data(job: PrintJob, attempt: PrintAttempt, lease_token: str) -> dict:
    payload = bytes(job.payload)
    return {
        "job_ref": str(job.ref),
        "attempt": attempt.sequence,
        "kind": job.kind,
        "copy_number": job.copy_number,
        "label_count": job.label_count,
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "payload_sha256": job.payload_sha256,
        "content_sha256": job.document_sha256,
        "payload_size": job.payload_size,
        "lease_token": lease_token,
        "lease_expires_at": attempt.lease_expires_at.isoformat(),
    }


def acknowledge_job(
    *,
    credential: PrintAgentCredential,
    job_ref,
    status: str,
    spooler_job_id: str,
    detail: str,
    payload_sha256: str,
    lease_token: str,
    telemetry: dict,
) -> PrintJob:
    if status == "spooled" and not str(spooler_job_id).strip():
        raise PrintJobError("ACK spooled exige spooler_job_id.", code="invalid_ack")
    request_digest = _request_digest(
        {
            "status": status,
            "spooler_job_id": spooler_job_id,
            "detail": detail,
            "payload_sha256": payload_sha256,
            "lease_token": lease_token,
        }
    )
    digest = _lease_digest(lease_token)
    with transaction.atomic():
        job = (
            PrintJob.objects.select_for_update()
            .filter(
                ref=job_ref,
                target_terminal=credential.terminal,
            )
            .first()
        )
        if job is None:
            raise PrintJobError("Trabalho não encontrado para este agente.", code="job_not_found", status_code=404)
        attempt = (
            PrintAttempt.objects.select_for_update()
            .filter(
                job=job,
                credential=credential,
                lease_token_digest=digest,
            )
            .first()
        )
        if attempt is None:
            raise PrintJobError("Lease inválido para este agente.", code="invalid_lease", status_code=409)
        if payload_sha256 != job.payload_sha256:
            raise PrintJobError(
                "Hash do payload diverge; nada foi confirmado.", code="payload_hash_mismatch", status_code=409
            )
        if attempt.ack_digest:
            if attempt.ack_digest == request_digest:
                return job
            raise PrintJobError("Este lease já recebeu um ACK diferente.", code="ack_conflict", status_code=409)
        active_lease = attempt.status == PrintAttempt.Status.LEASED and job.status == PrintJob.Status.LEASED
        late_ack = attempt.status == PrintAttempt.Status.EXPIRED and job.status == PrintJob.Status.UNCERTAIN
        if not (active_lease or late_ack):
            raise PrintJobError("Este lease não está mais ativo.", code="lease_inactive", status_code=409)

        mapped_attempt = {
            "spooled": PrintAttempt.Status.SPOOLED,
            "failed": PrintAttempt.Status.FAILED,
            "uncertain": PrintAttempt.Status.UNCERTAIN,
        }[status]
        mapped_job = {
            "spooled": PrintJob.Status.SPOOLED,
            "failed": PrintJob.Status.FAILED,
            "uncertain": PrintJob.Status.UNCERTAIN,
        }[status]
        attempt.status = mapped_attempt
        attempt.spooler_job_id = str(spooler_job_id or "")[:160]
        attempt.detail = str(detail or "")[:500]
        attempt.acknowledged_at = timezone.now()
        attempt.ack_digest = request_digest
        attempt.agent_version = str(telemetry.get("version") or attempt.agent_version)[:80]
        attempt.agent_build = str(telemetry.get("build") or attempt.agent_build)[:120]
        attempt.queue_name = str(telemetry.get("queue") or attempt.queue_name)[:160]
        attempt.health = str(telemetry.get("health") or attempt.health)[:40]
        attempt.save(
            update_fields=(
                "status",
                "spooler_job_id",
                "detail",
                "acknowledged_at",
                "ack_digest",
                "agent_version",
                "agent_build",
                "queue_name",
                "health",
            )
        )
        job.status = mapped_job
        job.save(update_fields=("status", "updated_at"))
        credential.last_seen_at = timezone.now()
        credential.last_build = attempt.agent_build
        credential.save(update_fields=("last_seen_at", "last_build"))
        return job


def reconcile_job_state(job: PrintJob) -> PrintJob:
    """Make polling sufficient to surface a relay that died after claiming."""
    now = timezone.now()
    with transaction.atomic():
        locked = PrintJob.objects.select_for_update().select_related("target_terminal").get(pk=job.pk)
        if locked.status in {PrintJob.Status.QUEUED, PrintJob.Status.PREPARED} and locked.expires_at <= now:
            locked.status = PrintJob.Status.EXPIRED
            locked.save(update_fields=("status", "updated_at"))
        elif locked.status == PrintJob.Status.LEASED:
            attempt = (
                locked.attempts.select_for_update()
                .filter(status=PrintAttempt.Status.LEASED)
                .order_by("-sequence")
                .first()
            )
            if attempt is not None and attempt.lease_expires_at and attempt.lease_expires_at <= now:
                attempt.status = PrintAttempt.Status.EXPIRED
                attempt.detail = "Lease expirou sem ACK; não reenviar automaticamente."
                attempt.save(update_fields=("status", "detail"))
                locked.status = PrintJob.Status.UNCERTAIN
                locked.save(update_fields=("status", "updated_at"))
        return locked


_STATUS_MESSAGES = {
    PrintJob.Status.PREPARED: "Etiqueta preparada; abra o diálogo de impressão do navegador.",
    PrintJob.Status.QUEUED: "Aguardando estação de impressão.",
    PrintJob.Status.LEASED: "O relay está entregando os bytes à impressora.",
    PrintJob.Status.SPOOLED: "A impressora aceitou o trabalho; confirme o papel.",
    PrintJob.Status.AWAITING_CONFIRMATION: "O diálogo abriu; confirme o papel, não apenas a janela.",
    PrintJob.Status.CONFIRMED: "Impressão confirmada pelo operador.",
    PrintJob.Status.FAILED: "A impressão falhou ou ficou incompleta.",
    PrintJob.Status.UNCERTAIN: "O relay pode ter enviado o papel; confira antes de reimprimir.",
    PrintJob.Status.CANCELLED: "Impressão cancelada.",
    PrintJob.Status.EXPIRED: "A impressão expirou antes de ser entregue.",
}


def job_data(job: PrintJob, *, include_document: bool = False) -> dict:
    data = {
        "ref": str(job.ref),
        "status": job.status,
        "status_label": job.get_status_display(),
        "message": _STATUS_MESSAGES[job.status],
        "target_label": _terminal_label(job.target_terminal),
        "label_count": job.label_count,
        "copy_number": job.copy_number,
        "can_retry": not job.confirmation and job.status in {PrintJob.Status.FAILED, PrintJob.Status.EXPIRED},
        "can_reprint": job.status
        in {
            PrintJob.Status.SPOOLED,
            PrintJob.Status.AWAITING_CONFIRMATION,
            PrintJob.Status.CONFIRMED,
            PrintJob.Status.UNCERTAIN,
            PrintJob.Status.FAILED,
        },
        "can_confirm": job.status
        in {
            PrintJob.Status.SPOOLED,
            PrintJob.Status.AWAITING_CONFIRMATION,
            PrintJob.Status.UNCERTAIN,
        },
        "poll_after_ms": 1500 if job.status in {PrintJob.Status.QUEUED, PrintJob.Status.LEASED} else 0,
    }
    if include_document:
        # This is the already-sanitized, frozen renderer input. Browser print
        # must use it instead of rebuilding from the live projection, or a
        # reprint could audit A while putting B on paper.
        data.update(
            print_document=job.document,
            document_sha256=job.document_sha256,
        )
    return data
