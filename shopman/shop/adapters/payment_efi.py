"""
EFI PIX payment adapter — Pix payments via Efi (Gerencianet).

Persists via PaymentService (DB) + communicates with Efi API.
Docs: https://dev.efipay.com.br/docs/api-pix
"""

from __future__ import annotations

import hashlib
import json
import logging
import ssl
import time
import uuid
from base64 import b64encode
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult

logger = logging.getLogger(__name__)

SANDBOX_URL = "https://pix-h.api.efipay.com.br"
PRODUCTION_URL = "https://pix.api.efipay.com.br"

_EFI_TOKEN_CACHE_KEY_PREFIX = "efi_access_token"
_EFI_TOKEN_TTL = 3300  # 55 min — EFI tokens last 1h
_EFI_TOKEN_LOCK_TTL = 35
_EFI_TOKEN_LOCK_WAIT_SECONDS = 31.0
_EFI_TOKEN_LOCK_POLL_SECONDS = 0.05


def _brl_to_q(amount: str | float) -> int:
    """Converte o decimal da EFI ("4.35") em centavos (canônico em utils)."""
    from shopman.utils.monetary import brl_to_q

    return brl_to_q(amount)


def _get_config() -> dict:
    """Read EFI configuration from settings."""
    return getattr(settings, "SHOPMAN_EFI", {})


def _base_url(config: dict) -> str:
    return SANDBOX_URL if config.get("sandbox", True) else PRODUCTION_URL


def _get_base_url() -> str:
    return _base_url(_get_config())


class EfiNotConfigured(RuntimeError):
    """Gateway Pix sem credencial — não há como cobrar, e não se finge."""


def _require_credentials(config: dict) -> tuple[str, str]:
    """Credenciais presentes, ou levanta ANTES de qualquer chamada de rede.

    Mesma regra do Stripe (``payment_stripe._get_stripe``): faltando gateway, o
    pedido para com erro visível — ``payment.initiate`` grava o erro e o
    acompanhamento mostra o degrau de falha. Antes daqui um ``client_id`` vazio
    virava uma tentativa de autenticação contra a Efí com credencial em branco,
    e um ``KeyError`` cru quando a chave nem existia.
    """
    client_id = str(config.get("client_id") or "").strip()
    client_secret = str(config.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise EfiNotConfigured(
            "Pix está apontado para a Efí, mas EFI_CLIENT_ID/EFI_CLIENT_SECRET "
            "estão vazios. Configure as credenciais do ambiente."
        )
    return client_id, client_secret


def _certificate_identity(certificate_path: str) -> str:
    """Stable, non-secret identity for the certificate used by this client.

    The DigitalOcean runtime materializes an inline certificate at the same path
    after every rotation.  Hashing the file contents means a rotated certificate
    cannot accidentally reuse the old token, while neither the private key nor
    its filesystem path becomes part of the cache key.
    """
    try:
        certificate = Path(certificate_path).read_bytes()
    except OSError:
        # ``load_cert_chain`` remains the owner of the actionable certificate
        # error.  The fallback only keeps construction of the cache key total.
        certificate = certificate_path.encode("utf-8")
    return hashlib.sha256(certificate).hexdigest()


def _token_cache_key(config: dict) -> str:
    client_id, _ = _require_credentials(config)
    identity = "\0".join(
        (
            _base_url(config),
            client_id,
            _certificate_identity(str(config.get("certificate_path") or "")),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"{_EFI_TOKEN_CACHE_KEY_PREFIX}:{digest}"


def _request_access_token(config: dict) -> str:
    """Obtain one token from Efí; caching and single-flight live above."""
    client_id, client_secret = _require_credentials(config)
    certificate_path = config["certificate_path"]

    auth = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    context = ssl.create_default_context()
    context.load_cert_chain(certificate_path)
    data = urlencode({"grant_type": "client_credentials"}).encode()

    request = Request(
        f"{_base_url(config)}/oauth/token",
        data=data,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urlopen(request, context=context, timeout=30) as response:
        result = json.loads(response.read().decode())
        return result["access_token"]


def _get_access_token() -> str:
    """Obtain or renew an environment-scoped access token.

    The cache key is bound to the base URL, client id and certificate identity,
    so a sandbox/production flip or credential rotation never reuses a token
    issued for the previous context.  ``cache.add`` is an atomic, cross-worker
    best-effort single-flight on the production Redis backend; waiters reuse the
    winner's token instead of stampeding the OAuth endpoint.
    """
    config = _get_config()
    cache_key = _token_cache_key(config)
    token = cache.get(cache_key)
    if token:
        return token

    lock_key = f"{cache_key}:lock"
    lock_owner = uuid.uuid4().hex
    acquired = cache.add(lock_key, lock_owner, timeout=_EFI_TOKEN_LOCK_TTL)
    if not acquired:
        deadline = time.monotonic() + _EFI_TOKEN_LOCK_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(_EFI_TOKEN_LOCK_POLL_SECONDS)
            token = cache.get(cache_key)
            if token:
                return token
            if cache.add(lock_key, lock_owner, timeout=_EFI_TOKEN_LOCK_TTL):
                acquired = True
                break
        if not acquired:
            raise RuntimeError("Efí OAuth token renewal is already in progress")

    try:
        # The token may have appeared between the first read and lock acquisition.
        token = cache.get(cache_key)
        if token:
            return token
        token = _request_access_token(config)
        cache.set(cache_key, token, timeout=_EFI_TOKEN_TTL)
        return token
    finally:
        # The TTL is longer than the network timeout.  The owner check prevents a
        # delayed worker from deleting a successor's lock after an expiry.
        if cache.get(lock_key) == lock_owner:
            cache.delete(lock_key)


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    """Make authenticated request to Efi API."""
    config = _get_config()
    token = _get_access_token()

    context = ssl.create_default_context()
    context.load_cert_chain(config["certificate_path"])

    data = json.dumps(payload).encode() if payload else None

    request = Request(
        f"{_get_base_url()}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )

    try:
        with urlopen(request, context=context, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        # Keep the structured provider body available to recovery policy. Efí
        # reports an absent cobrança as HTTP 400, so status code alone cannot
        # distinguish safe same-txid recreation from a fail-closed 400.
        e.efi_error_body = error_body
        logger.error("Efi API error: %s - %s", e.code, error_body)
        raise


def _merge_intent_gateway_state(
    db_intent,
    *,
    updates: dict,
    gateway_id: str = "",
    remove_keys: tuple[str, ...] = (),
) -> dict:
    """Merge remote progress without erasing a concurrent webhook update.

    Efí may deliver the paid callback immediately after the Cob ``PUT``.  Every
    later QR/recovery write therefore takes the same Payman row lock used by
    authorize/capture and merges the current database value instead of saving a
    stale model snapshot.
    """

    def apply(target) -> dict:
        merged = {**(target.gateway_data or {}), **updates}
        for key in remove_keys:
            merged.pop(key, None)
        target.gateway_data = merged
        update_fields = ["gateway_data"]
        if gateway_id and target.gateway_id != gateway_id:
            target.gateway_id = gateway_id
            update_fields.append("gateway_id")
        target.save(update_fields=update_fields)
        return merged

    # Adapter unit tests use a lightweight intent double.  Production Payman
    # models always have ``pk`` and take the locked branch.
    if getattr(db_intent, "pk", None) is None:
        return apply(db_intent)

    with transaction.atomic():
        locked = type(db_intent).objects.select_for_update().get(pk=db_intent.pk)
        merged = apply(locked)
    db_intent.refresh_from_db()
    return merged


def _charge_definitively_not_created(exc: Exception, *, stage: str, remote_charge_created: bool) -> bool:
    """Whether retry may safely burn this attempt and use a new txid.

    Timeouts and 5xx responses around the Cob PUT are ambiguous, so they keep
    the intent pending for a same-txid retry.  Local credential/certificate
    failures and explicit 4xx rejections happen before a charge can exist.
    """
    if remote_charge_created or stage != "charge_create":
        return False
    if isinstance(exc, (EfiNotConfigured, KeyError, FileNotFoundError, ssl.SSLError)):
        return True
    # 408/429 are transport/back-pressure outcomes: the request may have been
    # accepted before the response was lost or throttled.  Just like 409, they
    # must retain the same txid and be reconciled before any new charge exists.
    return isinstance(exc, HTTPError) and 400 <= int(exc.code) < 500 and int(exc.code) not in {408, 409, 429}


def _charge_location(response: dict) -> tuple[object | None, str]:
    loc = response.get("loc") or {}
    location_id = loc.get("id") if isinstance(loc, dict) else loc
    return location_id, str(response.get("location") or "")


def _charge_definitively_absent(exc: HTTPError) -> bool:
    if int(exc.code) == 404:
        return True
    if int(exc.code) != 400:
        return False
    body = str(getattr(exc, "efi_error_body", "") or "")
    if not body and getattr(exc, "fp", None):
        try:
            raw = exc.read()
            body = raw.decode() if isinstance(raw, bytes) else str(raw or "")
        except Exception:
            logger.debug("Efi charge lookup error body could not be read", exc_info=True)
            body = ""
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        parsed = {}
    return str(parsed.get("nome") or "").strip().lower() == "cobranca_nao_encontrada"


def create_intent(
    *,
    order_ref: str,
    amount_q: int,
    currency: str = "BRL",
    method: str = "pix",
    metadata: dict | None = None,
    **config,
) -> PaymentIntent:
    """Create a PIX charge via Efi gateway + persist via PaymentService."""
    if method != "pix":
        raise ValueError("EFI adapter only supports PIX")

    from shopman.shop.services.pix_policy import enforce_pix_test_amount_limit

    # Homologação Efí confirma automaticamente apenas até R$ 10,00.  Recusar
    # aqui, antes do livro e antes da rede, impede uma cobrança > R$ 10,00 de
    # ficar ATIVA para sempre sem webhook.
    enforce_pix_test_amount_limit(amount_q, adapter_path=__name__)

    from shopman.payman import PaymentService

    metadata = metadata or {}
    idempotency_key = config.get("idempotency_key") or metadata.get("idempotency_key", "")
    efi_config = _get_config()
    pix_timeout_minutes = config.get("pix_timeout_minutes")
    if pix_timeout_minutes:
        pix_expiry_seconds = int(pix_timeout_minutes) * 60
    else:
        pix_expiry_seconds = getattr(settings, "SHOPMAN_PIX_EXPIRY_SECONDS", 3600)
    expires_at = timezone.now() + timedelta(seconds=pix_expiry_seconds)

    candidate_txid = (
        uuid.uuid5(uuid.NAMESPACE_URL, f"shopman-efi:{idempotency_key}").hex
        if idempotency_key
        else uuid.uuid4().hex[:35]
    )
    provider_environment = "sandbox" if efi_config.get("sandbox", True) else "production"
    confirmation_mode = "provider_simulated" if provider_environment == "sandbox" else "provider_live"
    gateway_metadata = {
        **metadata,
        "txid": candidate_txid,
        "provider_environment": provider_environment,
        "confirmation_mode": confirmation_mode,
        "efi_creation_phase": "intent_persisted",
    }
    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method="pix",
        gateway="efi",
        gateway_id=candidate_txid,
        gateway_data=gateway_metadata,
        expires_at=expires_at,
        idempotency_key=idempotency_key,
    )
    persisted_environment = str(
        (db_intent.gateway_data or {}).get("provider_environment") or ""
    ).strip().lower()
    if persisted_environment != provider_environment:
        raise RuntimeError(
            "Cobrança Pix pertence a outro ambiente Efí; reconcilie no ambiente de origem."
        )
    # Idempotent retries inherit the original commercial deadline. Extending
    # it on every QR fetch would keep an old charge apparently payable forever.
    expires_at = db_intent.expires_at or expires_at
    if db_intent.gateway_id and db_intent.gateway_data.get("client_secret"):
        return _intent_from_db(db_intent, currency=currency)

    # ``create_intent`` can return a legacy or partially-created row for the same
    # idempotency key.  Remote progress wins over fresh caller metadata: it is
    # the durable resume cursor after a timeout or process restart.
    txid = db_intent.gateway_id or candidate_txid
    gateway_data = {
        **gateway_metadata,
        **(db_intent.gateway_data or {}),
        "txid": txid,
        "provider_environment": provider_environment,
        "confirmation_mode": confirmation_mode,
    }
    if db_intent.gateway_id != txid or db_intent.gateway_data != gateway_data:
        gateway_data = _merge_intent_gateway_state(
            db_intent,
            updates=gateway_data,
            gateway_id=txid,
        )

    # The txid is durable before the PUT.  Efí may deliver a paid webhook as
    # soon as the charge is created, before the QR request returns.
    # A chave "valor" é do contrato da EFI; a variável é nossa.
    amount = f"{amount_q / 100:.2f}"

    payload = {
        "calendario": {"expiracao": pix_expiry_seconds},
        "valor": {"original": amount},
        "chave": efi_config.get("pix_key"),
        "infoAdicionais": [
            {"nome": "Referência", "valor": order_ref},
        ],
    }

    stage = "charge_create"
    remote_charge_created = bool(gateway_data.get("efi_location_id"))
    try:
        location_id = gateway_data.get("efi_location_id")
        if location_id:
            response = {"location": gateway_data.get("location", "")}
        else:
            response = {}
            # A timeout around PUT is ambiguous: before issuing any second PUT,
            # ask Efí by the durable txid. If it exists, recover its location
            # and continue directly to the QR GET.
            if gateway_data.get("efi_remote_state") == "unknown":
                stage = "charge_recovery"
                try:
                    response = _request("GET", f"/v2/cob/{txid}")
                except HTTPError as probe_error:
                    if not _charge_definitively_absent(probe_error):
                        raise
                    response = {}
                if response:
                    remote_charge_created = True
                    location_id, _location = _charge_location(response)
                    if not location_id:
                        raise RuntimeError("Cobrança Efí encontrada sem localização para recuperar QR.")

            if not location_id:
                stage = "charge_create"
                try:
                    response = _request("PUT", f"/v2/cob/{txid}", payload)
                except HTTPError as put_error:
                    if int(put_error.code) != 409:
                        raise
                    # txid already in use means 'possibly created', never
                    # 'definitively not created'. Resolve that exact txid.
                    remote_charge_created = True
                    stage = "charge_recovery"
                    response = _request("GET", f"/v2/cob/{txid}")
                location_id, _location = _charge_location(response)
                if not location_id:
                    raise RuntimeError("Resposta Efí sem localização da cobrança Pix.")
            remote_charge_created = True
            gateway_data = {
                **gateway_data,
                "location": response.get("location", "") or gateway_data.get("location", ""),
                "efi_location_id": location_id,
                "efi_creation_phase": "charge_created",
                "efi_remote_state": "created",
            }
            # This save is deliberately before the QR request.  If that request
            # fails, retry resumes from the persisted loc id and never PUTs a
            # second charge.
            gateway_data = _merge_intent_gateway_state(
                db_intent,
                updates=gateway_data,
                remove_keys=("efi_last_error_stage", "efi_last_error_type"),
            )

        stage = "qr_fetch"
        qr_response = _request("GET", f"/v2/loc/{location_id}/qrcode")

        client_secret = json.dumps(
            {
                "qrcode": qr_response.get("qrcode", ""),
                "imagemQrcode": qr_response.get("imagemQrcode", ""),
                "txid": txid,
            }
        )

        db_intent.gateway_id = txid
        gateway_data = {
            **gateway_data,
            "location": response.get("location", "") or gateway_data.get("location", ""),
            "client_secret": client_secret,
            "efi_creation_phase": "qr_ready",
            "efi_remote_state": "created",
        }
        gateway_data = _merge_intent_gateway_state(
            db_intent,
            updates=gateway_data,
            gateway_id=txid,
            remove_keys=("efi_last_error_stage", "efi_last_error_type"),
        )

        return PaymentIntent(
            intent_ref=db_intent.ref,
            status=db_intent.status,
            amount_q=amount_q,
            currency=currency,
            client_secret=client_secret,
            expires_at=expires_at,
            gateway_id=txid,
            metadata={
                "qrcode": qr_response.get("qrcode", ""),
                "imagemQrcode": qr_response.get("imagemQrcode", ""),
                "txid": txid,
                "provider_environment": provider_environment,
                "confirmation_mode": confirmation_mode,
            },
        )
    except Exception as exc:
        logger.debug("Efi create_intent entered recovery for order %s", order_ref, exc_info=True)
        # A timeout can happen after Efí accepted the PUT.  Marking FAILED here
        # would lie about a still-payable charge and let a caller generate a new
        # one.  Keep the intent pending, persist only non-sensitive diagnostics,
        # and let the same idempotency key/txid resume safely.
        not_created = _charge_definitively_not_created(
            exc,
            stage=stage,
            remote_charge_created=remote_charge_created,
        )
        gateway_data = {
            **gateway_data,
            "efi_last_error_stage": stage,
            "efi_last_error_type": type(exc).__name__,
            "efi_remote_state": (
                "created" if remote_charge_created else ("not_created" if not_created else "unknown")
            ),
        }
        try:
            gateway_data = _merge_intent_gateway_state(
                db_intent,
                updates=gateway_data,
            )
            if not_created:
                PaymentService.fail(
                    db_intent.ref,
                    error_code="gateway_error",
                    message="A Efí recusou a criação da cobrança antes de gerar o Pix.",
                )
        except Exception:
            logger.warning("Efi create_intent: could not persist recovery state for order %s", order_ref, exc_info=True)
        if not_created:
            logger.exception("Efi create_intent failed before remote charge for order %s", order_ref)
        else:
            logger.exception("Efi create_intent remote state uncertain for order %s", order_ref)
        raise


def _intent_from_db(intent, *, currency: str = "BRL") -> PaymentIntent:
    client_secret = (intent.gateway_data or {}).get("client_secret")
    metadata = dict(intent.gateway_data or {})
    if client_secret:
        try:
            parsed = json.loads(client_secret)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            metadata.update(parsed)
    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=currency or intent.currency,
        client_secret=client_secret,
        expires_at=intent.expires_at,
        gateway_id=intent.gateway_id,
        metadata=metadata,
    )


def capture(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    **config,
) -> PaymentResult:
    """Check PIX payment status and capture if paid.

    PIX is auto-captured when paid — this verifies status at the gateway.
    The `amount_q` argument is accepted for contract uniformity but ignored:
    PIX captures the full charge amount as defined at create_intent time.
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message=f"Intent {intent_ref} não encontrado",
        )

    try:
        response = _request("GET", f"/v2/cob/{txid}")
        status = response.get("status", "")

        if status == "CONCLUIDA":
            amount_q = _brl_to_q(response["valor"]["original"])
            # ⚠️ O Pix JÁ ENTROU. Daqui para baixo, tudo o que falhar é
            # divergência entre o dinheiro real e o livro — nunca "não pagou".
            #
            # Duas coisas mudaram aqui, e as duas eram a mesma meia-correção. A
            # primeira: o `reconcile_gateway_status` era chamado solto, e um
            # `PaymentError` dele caía no `except Exception` lá embaixo como se
            # fosse falha de rede — `success=False`, `logger.warning`, dinheiro
            # recebido e ninguém avisado. A segunda: logo abaixo vinha um
            # `authorize` com `except PaymentError: pass` que NUNCA podia dar
            # certo — o `reconcile` acima já leva o intent de `pending` a
            # `captured` e já anuncia `payment_authorized`. Era um handler mudo
            # guardando uma chamada morta, e o `success=True` do retorno parecia
            # afirmar algo sobre ela. O Core já resolvia; sobrou o ruído.
            try:
                PaymentService.reconcile_gateway_status(
                    intent_ref,
                    gateway_status="captured",
                    amount_q=amount_q,
                    captured_q=amount_q,
                    refunded_q=0,
                    gateway_id=txid,
                    capture_gateway_id=txid,
                    gateway_data={"efi_status": status},
                )
            except PaymentError as exc:
                from shopman.shop.services import observability

                logger.error(
                    "payment_efi.capture: Pix CONCLUIDA de %sq sem registro no Payman "
                    "intent=%s txid=%s code=%s",
                    amount_q, intent_ref, txid, exc.code,
                    exc_info=True,
                )
                observability.record_payment_reconciliation_failure(
                    gateway="efi",
                    intent_ref=intent_ref,
                    order_ref=str(getattr(intent, "order_ref", "") or ""),
                    code=exc.code,
                    context={**(exc.context or {}), "txid": txid, "amount_q": amount_q},
                    exc=exc,
                )
                return PaymentResult(
                    success=False,
                    error_code="reconciliation_failed",
                    message=(
                        "Pix confirmado na Efí e NÃO registrado no Payman. "
                        "Concilie antes de cobrar de novo."
                    ),
                )
            return PaymentResult(
                success=True,
                transaction_id=txid,
                amount_q=amount_q,
            )
        return PaymentResult(
            success=False,
            error_code=status.lower() if status else "pending",
            message=f"Status: {status}",
        )
    except Exception as e:
        logger.warning("capture check failed for intent %s: %s", intent_ref, e, exc_info=True)
        return PaymentResult(
            success=False,
            error_code="error",
            message=str(e),
        )


def refund(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    reason: str = "",
    idempotency_key: str = "",
    **config,
) -> PaymentResult:
    """Process PIX refund via Efi gateway + PaymentService.

    Quando ``idempotency_key`` é dado, o ``dev_id`` da devolução EFI é
    DETERMINÍSTICO por chave — a devolução PIX da EFI é idempotente por
    ``{dev_id}`` na URL, então um retry reapresenta a mesma devolução (não
    estorna duas vezes) e o mesmo ``id`` volta como gateway_id p/ o Payman.
    """
    import hashlib

    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message=f"Intent {intent_ref} não encontrado",
        )

    try:
        cob = _request("GET", f"/v2/cob/{txid}")

        if cob.get("status") != "CONCLUIDA":
            return PaymentResult(
                success=False,
                error_code="not_paid",
                message="Cobrança não foi paga",
            )

        pix_list = cob.get("pix", [])
        if not pix_list:
            return PaymentResult(
                success=False,
                error_code="no_payment",
                message="Pagamento não encontrado",
            )

        e2eid = pix_list[0].get("endToEndId", "")
        amount = f"{amount_q / 100:.2f}" if amount_q else cob["valor"]["original"]
        if idempotency_key:
            dev_id = hashlib.sha256(idempotency_key.encode()).hexdigest()[:35]
        else:
            dev_id = uuid.uuid4().hex[:35]

        response = _request("PUT", f"/v2/pix/{e2eid}/devolucao/{dev_id}", {"valor": amount})

        refund_amount = _brl_to_q(amount)
        try:
            PaymentService.refund(
                intent_ref,
                amount_q=refund_amount,
                reason=reason,
                gateway_id=response.get("id", dev_id),
            )
        except PaymentError as exc:
            # O dinheiro JÁ saiu no gateway. Sem o registro local, o Payman
            # continua mostrando saldo reembolsável e um trigger futuro faria
            # um SEGUNDO refund real — falha tem que ser visível, nunca muda.
            logger.error(
                "payment_efi.refund: gateway devolveu %sq mas o registro local falhou (%s) intent=%s",
                refund_amount, exc, intent_ref,
            )
            from shopman.shop.services.observability import create_operator_alert

            create_operator_alert(
                type="payment_ledger_drift",
                severity="critical",
                message=(
                    f"Refund PIX de {refund_amount} centavos executado no gateway "
                    f"mas NÃO registrado no Payman (intent {intent_ref}). "
                    "Conciliar manualmente antes de qualquer novo estorno."
                ),
                dedupe_key=f"refund_drift:{intent_ref}",
                intent_ref=intent_ref,
                gateway_refund_id=response.get("id", dev_id),
            )

        return PaymentResult(
            success=True,
            transaction_id=response.get("id", dev_id),
            amount_q=refund_amount,
        )
    except Exception as e:
        logger.exception("Efi refund error for intent %s", intent_ref)
        # A timeout/transport error or 5xx around the idempotent PUT is
        # ambiguous: Efí may already have accepted the refund. Propagate so the
        # orchestration retry presents the exact same deterministic dev_id.
        # Explicit 4xx responses remain terminal adapter failures.
        if _refund_error_is_transient(e):
            raise
        return PaymentResult(
            success=False,
            error_code="error",
            message=str(e),
        )


def _refund_error_is_transient(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return int(exc.code) >= 500 or int(exc.code) in {408, 429}
    return isinstance(exc, (TimeoutError, ConnectionError, URLError))


def _record_cancel_drift(intent_ref: str, exc, *, txid: str) -> None:
    """A cobrança morreu na Efí e o Payman não acompanhou.

    Espelha o que ``refund`` já fazia neste mesmo arquivo — dinheiro SAINDO
    alertava, o resto se calava. Um intent já cancelado é o retry benigno e não
    vira alerta; qualquer outro estado é divergência que precisa de gente.
    """
    from shopman.payman import PaymentError, PaymentService

    from shopman.shop.services import observability

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        intent = None
    local_status = str(getattr(intent, "status", "") or "")
    if local_status == "cancelled":
        observability.operational_event(
            "efi.cancel_already_cancelled", intent_ref=intent_ref, txid=txid,
        )
        return

    logger.error(
        "payment_efi.cancel: cobrança removida na Efí sem baixa no Payman "
        "intent=%s txid=%s local_status=%s code=%s",
        intent_ref, txid, local_status or "-", getattr(exc, "code", ""),
        exc_info=True,
    )
    observability.record_payment_reconciliation_failure(
        gateway="efi",
        intent_ref=intent_ref,
        order_ref=str(getattr(intent, "order_ref", "") or ""),
        code=getattr(exc, "code", "") or exc.__class__.__name__,
        context={
            **(getattr(exc, "context", None) or {}),
            "operation": "cancel",
            "txid": txid,
            "local_status": local_status,
        },
        exc=exc,
    )


def cancel(intent_ref: str, **config) -> PaymentResult:
    """Cancel a PIX charge via Efi gateway + PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return PaymentResult(
            success=False,
            error_code="intent_not_found",
            message="Intent não encontrado",
        )

    try:
        payload = {"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"}
        _request("PATCH", f"/v2/cob/{txid}", payload)

        # A cobrança JÁ morreu na Efí. Sem a baixa local, o Payman segue com um
        # intent de pé que ninguém mais consegue pagar — e o `success=True`
        # abaixo jurava que os dois lados estavam alinhados.
        try:
            PaymentService.cancel(intent_ref, reason=str(config.get("reason") or ""))
        except PaymentError as exc:
            _record_cancel_drift(intent_ref, exc, txid=txid)

        return PaymentResult(success=True)
    except Exception as e:
        logger.warning("cancel failed for intent %s: %s", intent_ref, e, exc_info=True)
        return PaymentResult(
            success=False,
            error_code="error",
            message=str(e),
        )


def get_status(intent_ref: str, **config) -> dict:
    """
    Get payment status from PaymentService (source of truth).

    Returns:
        {"intent_ref": str, "status": str, "amount_q": int,
         "captured_q": int, "refunded_q": int, "currency": str}
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        captured_q = PaymentService.captured_total(intent_ref)
        refunded_q = PaymentService.refunded_total(intent_ref)

        return {
            "intent_ref": intent_ref,
            "status": intent.status,
            "amount_q": intent.amount_q,
            "captured_q": captured_q,
            "refunded_q": refunded_q,
            "currency": intent.currency,
        }
    except PaymentError:
        return {
            "intent_ref": intent_ref,
            "status": "error",
            "amount_q": 0,
            "captured_q": 0,
            "refunded_q": 0,
            "currency": "BRL",
        }


def check_gateway_status(intent_ref: str) -> str:
    """
    Check status directly at the Efi gateway (bypasses DB).

    Used as safety check before cancelling expired intents — é o verbo de LEITURA
    que ``shop.services.payment.settle_from_gateway`` consulta.

    Devolve ``captured``, ``pending``, ``cancelled``, ``not_found`` ou ``error``.
    ``not_found`` e ``error`` são respostas diferentes de propósito: intent que
    nunca existiu é ausência de pagamento (cancelar é certo), gateway mudo é
    incerteza (esperar é certo).
    """
    from shopman.payman import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        txid = intent.gateway_id
    except PaymentError:
        return "not_found"

    try:
        cob = _request("GET", f"/v2/cob/{txid}")
        status_map = {
            "ATIVA": "pending",
            "CONCLUIDA": "captured",
            "REMOVIDA_PELO_USUARIO_RECEBEDOR": "cancelled",
            "REMOVIDA_PELO_PSP": "cancelled",
        }
        return status_map.get(cob["status"], cob["status"])
    except Exception as e:
        logger.warning("check_gateway_status failed for %s: %s", intent_ref, e)
        return "error"
