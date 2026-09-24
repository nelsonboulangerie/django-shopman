"""Orquestra direitos de dados com recibo durável, lock e idempotência."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.shop.models import (
    PrivacyRequestOperation,
    PrivacyRequestReceipt,
    PrivacyRequestState,
)
from shopman.shop.services import manychat_erasure

_CONTRACT_VERSION = "account-privacy.v1"
_HMAC_DOMAIN_VERSION = "shopman-privacy-receipt-hmac.v1"
_FAILED_RETENTION = timedelta(days=90)
_COMPLETED_RETENTION = timedelta(days=365 * 5)
_STALE_IN_PROGRESS = timedelta(minutes=10)


class PrivacyRequestError(Exception):
    code = "privacy_request_failed"


class InvalidIdempotencyKey(PrivacyRequestError):
    code = "invalid_idempotency_key"


class PrivacyRequestConflict(PrivacyRequestError):
    code = "idempotency_conflict"


class PrivacyRequestInProgress(PrivacyRequestError):
    code = "privacy_request_in_progress"


class PrivacyReceiptKeyUnavailable(PrivacyRequestError):
    code = "privacy_receipt_key_unavailable"


class AccountDeletionBlocked(PrivacyRequestError):
    code = "account_deletion_blocked"

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ProviderErasureIncomplete(PrivacyRequestError):
    """O provedor não confirmou o apagamento — e sem confirmação não há "pronto".

    Deliberadamente NÃO é `AccountDeletionBlocked`: bloqueio é pré-condição que
    o cliente resolve (conclua o pedido, espere a mensagem sair). Isto aqui é
    falha nossa com o provedor, e a resposta certa é a mesma de qualquer
    exclusão incompleta — 503, equipe avisada, tente de novo — nunca um pedido
    para o cliente ir falar com alguém.
    """

    code = "account_deletion_incomplete"

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class _ErasurePlan:
    """O que a fase 1 apurou com o `Customer` travado."""

    subscriber_ids: tuple[str, ...] = ()
    resolution_pending: bool = False
    has_footprint: bool = False
    replayed_outcome: DeletionOutcome | None = None


@dataclass(frozen=True)
class DeletionOutcome:
    receipt_ref: str
    replayed: bool


def privacy_requests_available() -> bool:
    """Indica se os recibos obrigatórios podem ser assinados neste processo.

    Exportação e exclusão não devem ser oferecidas quando a chave dedicada está
    ausente ou inválida: o recibo é parte do contrato, não telemetria opcional.
    """

    try:
        keys = _privacy_hmac_keys()
        _ensure_receipt_key_coverage(keys)
    except PrivacyReceiptKeyUnavailable:
        return False
    return True


def subject_receipt_digests(customer_uuid) -> list[str]:
    """Digests versionados para projetar recibos do próprio titular."""

    keys = _privacy_hmac_keys()
    _ensure_receipt_key_coverage(keys)
    return [
        _digest("subject", str(customer_uuid), key_version=version, key=key)
        for version, key in keys.items()
    ]


def delete_account(*, customer, idempotency_key: str, authorized_at) -> DeletionOutcome:
    """Anonimiza uma conta uma única vez ou reproduz seu recibo concluído.

    O recibo nasce em transação própria para sobreviver a qualquer rollback da
    exclusão. A mutação inteira, inclusive o estado concluído do recibo, fecha
    em uma segunda transação atômica.
    """

    normalized_key = _validate_idempotency_key(idempotency_key)
    idempotency_fingerprint = _stable_idempotency_fingerprint(
        PrivacyRequestOperation.DELETION,
        normalized_key,
    )
    request_material = json.dumps(
        {"acknowledged": True, "contract": _CONTRACT_VERSION, "operation": "deletion"},
        sort_keys=True,
        separators=(",", ":"),
    )
    key_version, key = _key_for_idempotency(
        PrivacyRequestOperation.DELETION,
        idempotency_fingerprint,
    )
    subject_digest = _digest(
        "subject",
        str(customer.uuid),
        key_version=key_version,
        key=key,
    )
    idempotency_digest = _digest(
        "idempotency",
        normalized_key,
        key_version=key_version,
        key=key,
    )
    request_digest = _digest(
        "request",
        request_material,
        key_version=key_version,
        key=key,
    )
    receipt, replayed = _acquire_receipt(
        operation=PrivacyRequestOperation.DELETION,
        subject_material=str(customer.uuid),
        subject_digest=subject_digest,
        idempotency_fingerprint=idempotency_fingerprint,
        idempotency_digest=idempotency_digest,
        request_material=request_material,
        request_digest=request_digest,
        authorized_at=authorized_at,
        key_version=key_version,
    )
    if replayed:
        return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)

    # ── Fase 1 — pré-condições e leitura do vínculo, antes de qualquer I/O ──
    #
    # Nada acontece no provedor enquanto a exclusão ainda puder ser recusada por
    # trabalho vivo aqui dentro: limpar o perfil de alguém que continua com a
    # conta de pé seria meia-exclusão ao contrário.
    try:
        plan = _plan_erasure(receipt, customer)
    except AccountDeletionBlocked:
        _mark_failed(receipt.pk, stage="precondition", code="account_deletion_blocked")
        raise
    if plan.replayed_outcome is not None:
        return plan.replayed_outcome

    # ── I/O externo, FORA de transação ──
    #
    # A intenção durável vai primeiro: se o processo morrer no meio, o marcador
    # conta que a casa já pode ter mexido no perfil de lá.
    erasure = manychat_erasure.ErasureOutcome(confirmed=True)
    if plan.has_footprint:
        manychat_erasure.mark_intent(customer.pk)
        erasure = manychat_erasure.run(
            customer_pk=customer.pk,
            ids=plan.subscriber_ids,
            pending=plan.resolution_pending,
        )
    if not erasure.confirmed:
        # Falha fechada: o provedor não confirmou o apagamento, então a casa não
        # diz "pronto" nem manda o cliente pedir para a equipe. O recibo fica
        # incompleto, a operação é chamada, e o titular vê "tente de novo".
        _mark_failed(receipt.pk, stage="provider_erasure", code="account_deletion_incomplete")
        _alert_failed_receipt(receipt.ref)
        raise ProviderErasureIncomplete(erasure.reason)

    # ── Fase 2 — readquirir o Customer e finalizar ──
    try:
        with transaction.atomic():
            receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt.pk)
            if receipt.state == PrivacyRequestState.COMPLETED:
                return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)

            from shopman.shop.services import account as account_service

            locked_customer = account_service.lock_customer_for_privacy(customer.pk)
            if not locked_customer.is_active:
                previous = (
                    PrivacyRequestReceipt.objects.filter(
                        operation=PrivacyRequestOperation.DELETION,
                        subject_digest__in=_all_digests("subject", str(customer.uuid)),
                        state=PrivacyRequestState.COMPLETED,
                    )
                    .exclude(pk=receipt.pk)
                    .first()
                )
                if previous is None:
                    raise AccountDeletionBlocked("account_already_inactive")
                now = timezone.now()
                receipt.state = PrivacyRequestState.COMPLETED
                receipt.completed_at = now
                receipt.failure_stage = ""
                receipt.failure_code = ""
                receipt.outcome_counts = {"accounts": 0, "already_deleted": 1}
                receipt.retention_until = now + _COMPLETED_RETENTION
                receipt.save(
                    update_fields=[
                        "state",
                        "completed_at",
                        "failure_stage",
                        "failure_code",
                        "outcome_counts",
                        "retention_until",
                        "updated_at",
                    ]
                )
                return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)
            blocker = _deletion_blocker(locked_customer)
            if blocker:
                raise AccountDeletionBlocked(blocker)

            # A pegada é RELIDA com o Customer travado. Entre a fase 1 e aqui,
            # um writer pode ter vinculado um assinante NOVO — é a corrida que
            # a matriz descreve: "se o writer vencer, a exclusão espera e
            # precisa alcançar o efeito recém-criado". O que a limpeza não
            # alcançou não pode ser declarado apagado.
            alcancado = set(erasure.subscriber_ids)
            surgiu = set(manychat_erasure.subscriber_ids(locked_customer)) - alcancado
            if surgiu or manychat_erasure.resolution_pending(locked_customer):
                raise ProviderErasureIncomplete("manychat_link_appeared_during_erasure")

            _settle_storefront_records(locked_customer)
            # A lápide nasce JUNTO com a anonimização: se a exclusão rolar para
            # trás, não pode sobrar lápide recusando o sync de uma conta viva.
            manychat_erasure.remember(erasure.subscriber_ids)
            manychat_erasure.clear_intent(locked_customer)
            account_service.anonymize_customer(
                locked_customer,
                correlation_ref=str(receipt.ref),
            )
            now = timezone.now()
            receipt.state = PrivacyRequestState.COMPLETED
            receipt.completed_at = now
            receipt.failure_stage = ""
            receipt.failure_code = ""
            receipt.outcome_counts = {"accounts": 1}
            receipt.retention_until = now + _COMPLETED_RETENTION
            receipt.save(
                update_fields=[
                    "state",
                    "completed_at",
                    "failure_stage",
                    "failure_code",
                    "outcome_counts",
                    "retention_until",
                    "updated_at",
                ]
            )
    except AccountDeletionBlocked:
        _mark_failed(receipt.pk, stage="precondition", code="account_deletion_blocked")
        raise
    except ProviderErasureIncomplete:
        _mark_failed(receipt.pk, stage="provider_erasure", code="account_deletion_incomplete")
        _alert_failed_receipt(receipt.ref)
        raise
    except Exception:
        _mark_failed(receipt.pk, stage="anonymization", code="account_deletion_incomplete")
        _alert_failed_receipt(receipt.ref)
        raise

    # Depois do commit: o que a API do provedor NÃO faz vira tarefa com prazo,
    # em vez de uma pendência que alguém teria que lembrar sozinho.
    manychat_erasure.open_operator_task(erasure.subscriber_ids, receipt_ref=receipt.ref)
    return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=False)


def begin_export(
    *,
    customer_uuid,
    authorized_at,
) -> PrivacyRequestReceipt:
    """Abre evidência durável antes de qualquer leitura/serialização do artefato."""

    now = timezone.now()
    nonce = str(uuid.uuid4())
    key_version, key = _current_privacy_key()
    return PrivacyRequestReceipt.objects.create(
        operation=PrivacyRequestOperation.EXPORT,
        state=PrivacyRequestState.IN_PROGRESS,
        key_version=key_version,
        subject_digest=_digest(
            "subject",
            str(customer_uuid),
            key_version=key_version,
            key=key,
        ),
        idempotency_fingerprint=_stable_idempotency_fingerprint(
            PrivacyRequestOperation.EXPORT,
            nonce,
        ),
        idempotency_digest=_digest(
            "idempotency",
            nonce,
            key_version=key_version,
            key=key,
        ),
        request_digest=_digest(
            "request",
            _CONTRACT_VERSION + ":export",
            key_version=key_version,
            key=key,
        ),
        authorization_method="otp_step_up",
        authorized_at=authorized_at,
        retention_until=now + _FAILED_RETENTION,
    )


def complete_export(receipt_pk: int, *, counts: dict[str, int]) -> PrivacyRequestReceipt:
    now = timezone.now()
    with transaction.atomic():
        receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt_pk)
        receipt.state = PrivacyRequestState.COMPLETED
        receipt.completed_at = now
        receipt.failure_stage = ""
        receipt.failure_code = ""
        receipt.outcome_counts = _safe_counts(counts)
        receipt.retention_until = now + _COMPLETED_RETENTION
        receipt.save(
            update_fields=[
                "state",
                "completed_at",
                "failure_stage",
                "failure_code",
                "outcome_counts",
                "retention_until",
                "updated_at",
            ]
        )
    return receipt


def fail_export(receipt_pk: int, *, stage: str = "artifact") -> None:
    _mark_failed(receipt_pk, stage=stage, code="account_export_incomplete")


def _acquire_receipt(
    *,
    operation: str,
    subject_material: str,
    subject_digest: str,
    idempotency_fingerprint: str,
    idempotency_digest: str,
    request_material: str,
    request_digest: str,
    authorized_at,
    key_version: int,
) -> tuple[PrivacyRequestReceipt, bool]:
    now = timezone.now()
    defaults = {
        "request_digest": request_digest,
        "key_version": key_version,
        "authorization_method": "otp_step_up",
        "authorized_at": authorized_at,
        "retention_until": now + _FAILED_RETENTION,
    }
    try:
        with transaction.atomic():
            receipt, created = PrivacyRequestReceipt.objects.get_or_create(
                operation=operation,
                idempotency_fingerprint=idempotency_fingerprint,
                defaults={
                    **defaults,
                    "subject_digest": subject_digest,
                    "idempotency_digest": idempotency_digest,
                },
            )
    except IntegrityError:
        receipt = PrivacyRequestReceipt.objects.get(
            operation=operation,
            idempotency_fingerprint=idempotency_fingerprint,
        )
        created = False

    if created:
        return receipt, False
    receipt_key = _privacy_hmac_keys().get(receipt.key_version)
    if receipt_key is None:
        raise PrivacyReceiptKeyUnavailable("receipt_key_version_not_configured")
    expected_subject = _digest(
        "subject",
        subject_material,
        key_version=receipt.key_version,
        key=receipt_key,
    )
    expected_request = _digest(
        "request",
        request_material,
        key_version=receipt.key_version,
        key=receipt_key,
    )
    if not hmac.compare_digest(receipt.subject_digest, expected_subject):
        raise PrivacyRequestConflict("idempotency_key_owned_by_another_subject")
    if not hmac.compare_digest(receipt.request_digest, expected_request):
        raise PrivacyRequestConflict("request_digest_mismatch")
    if receipt.state == PrivacyRequestState.COMPLETED:
        return receipt, True

    with transaction.atomic():
        receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt.pk)
        if receipt.state == PrivacyRequestState.COMPLETED:
            return receipt, True
        if receipt.state == PrivacyRequestState.IN_PROGRESS and receipt.updated_at >= now - _STALE_IN_PROGRESS:
            raise PrivacyRequestInProgress("request_already_running")
        receipt.state = PrivacyRequestState.IN_PROGRESS
        receipt.completed_at = None
        receipt.failure_stage = ""
        receipt.failure_code = ""
        receipt.attempt_count += 1
        receipt.started_at = now
        receipt.save(
            update_fields=[
                "state",
                "completed_at",
                "failure_stage",
                "failure_code",
                "attempt_count",
                "started_at",
                "updated_at",
            ]
        )
    return receipt, False


def replay_completed_deletion(idempotency_key: str) -> DeletionOutcome | None:
    """Consulta somente um recibo concluído; nunca inicia ou retoma exclusão."""

    normalized_key = _validate_idempotency_key(idempotency_key)
    fingerprint = _stable_idempotency_fingerprint(
        PrivacyRequestOperation.DELETION,
        normalized_key,
    )
    receipt = (
        PrivacyRequestReceipt.objects.filter(
            operation=PrivacyRequestOperation.DELETION,
            idempotency_fingerprint=fingerprint,
            state=PrivacyRequestState.COMPLETED,
        )
        .order_by("-started_at", "-pk")
        .first()
    )
    if receipt is None:
        return None
    return DeletionOutcome(receipt_ref=str(receipt.ref), replayed=True)


def _mark_failed(receipt_pk: int, *, stage: str, code: str) -> None:
    now = timezone.now()
    with transaction.atomic():
        receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt_pk)
        if receipt.state == PrivacyRequestState.COMPLETED:
            return
        receipt.state = PrivacyRequestState.FAILED
        receipt.completed_at = now
        receipt.failure_stage = stage
        receipt.failure_code = code
        receipt.outcome_counts = {}
        receipt.retention_until = now + _FAILED_RETENTION
        receipt.save(
            update_fields=[
                "state",
                "completed_at",
                "failure_stage",
                "failure_code",
                "outcome_counts",
                "retention_until",
                "updated_at",
            ]
        )


def _plan_erasure(receipt, customer) -> _ErasurePlan:
    """Fase 1: trava, confere tudo que recusa, e lê o vínculo do provedor.

    Sai sem nenhum efeito externo: a única coisa que esta fase muda é nada.
    """
    with transaction.atomic():
        locked_receipt = PrivacyRequestReceipt.objects.select_for_update().get(pk=receipt.pk)
        if locked_receipt.state == PrivacyRequestState.COMPLETED:
            return _ErasurePlan(
                replayed_outcome=DeletionOutcome(receipt_ref=str(locked_receipt.ref), replayed=True),
            )

        from shopman.shop.services import account as account_service

        locked_customer = account_service.lock_customer_for_privacy(customer.pk)
        if not locked_customer.is_active:
            # Conta já inativa não tem provedor a limpar; a fase 2 decide entre
            # reproduzir o recibo anterior e recusar, com o código de sempre.
            return _ErasurePlan()

        blocker = _deletion_blocker(locked_customer)
        if blocker:
            raise AccountDeletionBlocked(blocker)
        in_flight = _storefront_in_flight_blocker(locked_customer)
        if in_flight:
            raise AccountDeletionBlocked(in_flight)

        return _ErasurePlan(
            subscriber_ids=manychat_erasure.subscriber_ids(locked_customer),
            resolution_pending=manychat_erasure.resolution_pending(locked_customer),
            has_footprint=manychat_erasure.has_provider_footprint(locked_customer),
        )


def _storefront_in_flight_blocker(customer) -> str:
    """Gêmeo SÓ DE LEITURA das duas recusas de `_settle_storefront_records`.

    Lá elas moram no meio da revogação da fila, que é onde precisam estar. Aqui
    elas precisam ser perguntadas ANTES do I/O externo: sem esta pergunta, a
    casa limparia o perfil no provedor de alguém cuja exclusão ainda vai ser
    recusada na fase 2, e a pessoa ficaria com a conta de pé e o perfil de lá
    zerado. A varredura aqui é de propósito mais larga que a de lá — numa
    pré-condição, errar para o lado de recusar é o lado certo.
    """
    from shopman.shop.models import AudienceSnapshotMember, DeliveryTarget
    from shopman.storefront.models import StockAlertDelivery, StockAlertSubscription

    subscription_ids = list(
        StockAlertSubscription.objects.filter(customer_ref=customer.ref).values_list("pk", flat=True)
    )
    if subscription_ids and StockAlertDelivery.objects.filter(
        subscription_id__in=subscription_ids,
        status=StockAlertDelivery.Status.CLAIMED,
    ).exists():
        return "stock_alert_delivery_in_flight"

    member_ids = tuple(
        AudienceSnapshotMember.objects.filter(customer=customer).values_list("pk", flat=True)
    )
    if member_ids and DeliveryTarget.objects.filter(
        member_id__in=member_ids,
        state=DeliveryTarget.State.SENDING,
    ).exists():
        return "marketing_delivery_in_flight"
    return ""


def _settle_storefront_records(customer) -> None:
    """Revoga filas futuras e retém somente prova técnica não identificável."""

    from django.db.models import Q

    from shopman.shop.models import AudienceSnapshotMember, DeliveryTarget
    from shopman.storefront.models import (
        CustomerFavorite,
        StockAlertDelivery,
        StockAlertSubscription,
    )
    from shopman.storefront.services.stock_alerts import _revocation_hash

    subscriptions = list(
        StockAlertSubscription.objects.select_for_update()
        .filter(customer_ref=customer.ref)
        .order_by("pk")
    )
    subscription_ids = [subscription.pk for subscription in subscriptions]
    subscription_refs = [subscription.ref for subscription in subscriptions]
    if (
        subscription_ids
        and StockAlertDelivery.objects.filter(
            subscription_id__in=subscription_ids,
            status=StockAlertDelivery.Status.CLAIMED,
        ).exists()
    ):
        raise AccountDeletionBlocked("stock_alert_delivery_in_flight")

    now = timezone.now()
    if subscription_ids:
        StockAlertDelivery.objects.filter(
            subscription_id__in=subscription_ids,
            status__in=(
                StockAlertDelivery.Status.QUEUED,
                StockAlertDelivery.Status.RETRYABLE,
            ),
        ).update(
            status=StockAlertDelivery.Status.SUPPRESSED,
            claimed_at=None,
            last_error_code="subject_deleted",
            updated_at=now,
        )
        for subscription in subscriptions:
            reason = "subject_deleted"
            revoked_at = subscription.revoked_at or now
            revocation_hash = subscription.revocation_evidence_hash or _revocation_hash(
                subscription.ref,
                revoked_at,
                reason,
            )
            StockAlertSubscription.objects.filter(pk=subscription.pk).update(
                customer_ref="",
                contact_phone="",
                target_key=_digest("stock-alert-target", str(subscription.ref)),
                disclosure_text="",
                revoked_at=revoked_at,
                revoke_reason=reason,
                revocation_evidence_hash=revocation_hash,
                dispatch_claimed_at=None,
            )

    # Um member misto pode ter sido produzido ao deduplicar, pelo mesmo
    # telefone, um Customer canônico e uma assinatura ownerless. Essa
    # assinatura não vira propriedade do cadastro atual por coincidência de
    # número: preservamos o target e apenas retiramos o vínculo contaminado.
    owned_members = AudienceSnapshotMember.objects.select_for_update().filter(customer=customer).filter(
        Q(subscription_ref__isnull=True) | Q(subscription_ref__in=subscription_refs)
    )
    owned_member_ids = tuple(owned_members.values_list("pk", flat=True))
    targets = DeliveryTarget.objects.select_for_update().filter(member_id__in=owned_member_ids)
    if targets.filter(state=DeliveryTarget.State.SENDING).exists():
        raise AccountDeletionBlocked("marketing_delivery_in_flight")
    targets.filter(
        state__in=(
            DeliveryTarget.State.PLANNED,
            DeliveryTarget.State.QUEUED,
            DeliveryTarget.State.FAILED_RETRYABLE,
        )
    ).update(
        state=DeliveryTarget.State.CANCELLED,
        lease_owner="",
        lease_until=None,
        last_error_code="subject_deleted",
        settled_at=now,
    )
    owned_members.delete()
    (
        AudienceSnapshotMember.objects.select_for_update()
        .filter(customer=customer, subscription_ref__isnull=False)
        .exclude(subscription_ref__in=subscription_refs)
        .update(customer=None)
    )

    CustomerFavorite.objects.filter(customer_ref=customer.ref).delete()


def _deletion_blocker(customer) -> str:
    from shopman.shop.models import ConversationMessage, OutboundAttempt
    from shopman.shop.services import account as account_service

    otp_blocker = account_service.privacy_otp_deletion_blocker(customer)
    if otp_blocker:
        return otp_blocker

    # O vínculo com o ManyChat NÃO recusa mais a exclusão. Ele deixou de ser
    # pré-condição e virou trabalho: `manychat_erasure` limpa o perfil de lá,
    # grava a lápide que impede a ressurreição pelo webhook e abre a tarefa
    # datada do que a API do provedor não faz. Mandar o cliente "pedir à
    # equipe" era o oposto do direito que a página promete a ele.
    order_blocker = account_service.privacy_order_deletion_blocker(
        customer.ref,
        customer.phone or "",
    )
    if order_blocker:
        return order_blocker
    conversations = account_service._customer_conversations(  # noqa: SLF001
        customer.ref,
        customer.phone or "",
    )
    messages = ConversationMessage.objects.filter(conversation__in=conversations)
    if OutboundAttempt.objects.filter(
        message__in=messages,
        state=OutboundAttempt.State.EXECUTING,
    ).exists():
        return "conversation_delivery_in_flight"
    return ""


def _alert_failed_receipt(receipt_ref) -> None:
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="account_deletion_incomplete",
        severity="critical",
        message=f"Exclusão de conta incompleta. Recibo: {receipt_ref}.",
        dedupe_key=f"privacy-deletion:{receipt_ref}",
    )


def _validate_idempotency_key(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = uuid.UUID(raw)
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidIdempotencyKey("uuid_v4_required") from exc
    if parsed.version != 4 or str(parsed) != raw.lower():
        raise InvalidIdempotencyKey("uuid_v4_required")
    return str(parsed)


def _key_for_idempotency(operation: str, idempotency_fingerprint: str) -> tuple[int, bytes]:
    keys = _privacy_hmac_keys()
    _ensure_receipt_key_coverage(keys)
    existing = (
        PrivacyRequestReceipt.objects.filter(
            operation=operation,
            idempotency_fingerprint=idempotency_fingerprint,
        )
        .order_by("-started_at", "-pk")
        .first()
    )
    if existing is None:
        return _current_privacy_key(keys)
    key = keys.get(existing.key_version)
    if key is None:
        raise PrivacyReceiptKeyUnavailable("receipt_key_version_not_configured")
    return existing.key_version, key


def _stable_idempotency_fingerprint(operation: str, idempotency_key: str) -> str:
    """Identificador irreversível e independente da rotação da chave HMAC.

    A entrada é obrigatoriamente UUIDv4 aleatório e não é persistida. O
    domínio fixo e a operação impedem colisões entre fluxos sem quebrar o
    lookup quando o contrato da solicitação evoluir.
    """

    material = f"shopman-privacy-idempotency.v1\0{operation}\0{idempotency_key}".encode()
    return hashlib.sha256(material).hexdigest()


def _all_digests(purpose: str, value: str) -> list[str]:
    return [_digest(purpose, value, key_version=version, key=key) for version, key in _privacy_hmac_keys().items()]


def _current_privacy_key(keys: dict[int, bytes] | None = None) -> tuple[int, bytes]:
    resolved = keys or _privacy_hmac_keys()
    _ensure_receipt_key_coverage(resolved)
    try:
        version = int(
            getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION", 1)
        )
    except (TypeError, ValueError) as exc:
        raise PrivacyReceiptKeyUnavailable("current_receipt_key_version_invalid") from exc
    key = resolved.get(version)
    if key is None:
        raise PrivacyReceiptKeyUnavailable("current_receipt_key_not_configured")
    return version, key


def _privacy_hmac_keys() -> dict[int, bytes]:
    raw_previous = getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS", {})
    if isinstance(raw_previous, str):
        try:
            raw_previous = json.loads(raw_previous or "{}")
        except (TypeError, ValueError) as exc:
            raise PrivacyReceiptKeyUnavailable("receipt_keyring_invalid") from exc
    if not isinstance(raw_previous, Mapping):
        raise PrivacyReceiptKeyUnavailable("receipt_keyring_invalid")

    keys: dict[int, bytes] = {}
    for raw_version, raw_key in raw_previous.items():
        try:
            version = int(raw_version)
        except (TypeError, ValueError) as exc:
            raise PrivacyReceiptKeyUnavailable("receipt_key_version_invalid") from exc
        key = str(raw_key or "").encode("utf-8")
        if version < 1 or len(key) < 32:
            raise PrivacyReceiptKeyUnavailable("receipt_key_invalid")
        keys[version] = key

    try:
        current_version = int(
            getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION", 1)
        )
    except (TypeError, ValueError) as exc:
        raise PrivacyReceiptKeyUnavailable("current_receipt_key_version_invalid") from exc
    current_key = str(getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY", "") or "").encode("utf-8")
    if current_version < 1 or len(current_key) < 32:
        raise PrivacyReceiptKeyUnavailable("current_receipt_key_invalid")
    previous_current = keys.get(current_version)
    if previous_current is not None and not hmac.compare_digest(
        previous_current,
        current_key,
    ):
        raise PrivacyReceiptKeyUnavailable("receipt_key_version_conflict")
    keys[current_version] = current_key
    return keys


def _ensure_receipt_key_coverage(keys: Mapping[int, bytes]) -> None:
    """Fail closed while any retained receipt cannot be authenticated."""

    if PrivacyRequestReceipt.objects.exclude(key_version__in=tuple(keys)).exists():
        raise PrivacyReceiptKeyUnavailable("retained_receipt_key_not_configured")


def _digest(
    purpose: str,
    value: str,
    *,
    key_version: int | None = None,
    key: bytes | None = None,
) -> str:
    if key_version is None or key is None:
        key_version, key = _current_privacy_key()
    material = f"{_HMAC_DOMAIN_VERSION}\0key:{key_version}\0{purpose}\0{value}".encode()
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _safe_counts(values: dict[str, int]) -> dict[str, int]:
    return {
        str(key)[:48]: max(0, int(value))
        for key, value in values.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
