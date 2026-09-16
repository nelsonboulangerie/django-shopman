"""
Manychat Subscriber Resolver — Resolve recipient → subscriber_id.

Usado pelo ManychatBackend (orderman) para converter phone/email/ref
em Manychat subscriber_id para envio de mensagens outbound.

Estratégia de resolução (em ordem):
1. Numérico direto → subscriber_id
2. DB: CustomerIdentifier(MANYCHAT) via phone/email/ref
3. API fallback: GET /fb/subscriber/findByCustomField (WhatsApp ID espelhado)
4. API fallback: GET /fb/subscriber/findBySystemField (phone)
5. API bootstrap: POST /fb/subscriber/createSubscriber (whatsapp_phone)
   → persiste como CustomerIdentifier para próximas chamadas quando houver customer
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from shopman.guestman.models import Customer

logger = logging.getLogger(__name__)

# ManyChat API base URL
_API_BASE = "https://api.manychat.com/fb"
_API_TIMEOUT = 10
_PRIVACY_PENDING_KEY = "manychat_resolution_pending"
_PROVIDER_LOCK_NAMESPACE = 72601
_LOCAL_PROVIDER_LOCKS: dict[int, threading.Lock] = {}
_LOCAL_PROVIDER_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class _ProviderLookupOutcome:
    subscriber_id: int | None = None
    conclusive_absence: bool = False


@dataclass(frozen=True)
class _ProviderCreateOutcome:
    subscriber_id: int | None = None


@contextmanager
def _customer_provider_mutex(customer_pk: int):
    """Serialize provider resolution without keeping a DB transaction open."""
    from django.db import connection

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_lock(%s, %s)",
                [_PROVIDER_LOCK_NAMESPACE, int(customer_pk)],
            )
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    [_PROVIDER_LOCK_NAMESPACE, int(customer_pk)],
                )
        return

    with _LOCAL_PROVIDER_LOCKS_GUARD:
        local_lock = _LOCAL_PROVIDER_LOCKS.setdefault(int(customer_pk), threading.Lock())
    with local_lock:
        yield


def _read_http_error_body(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8", "replace")[:300]
    except Exception:
        return ""


def _subscriber_id(data: dict) -> int | None:
    subscriber = data.get("data") or {}
    if isinstance(subscriber, list):
        subscriber = subscriber[0] if subscriber else {}
    if not isinstance(subscriber, dict):
        return None

    subscriber_id = subscriber.get("id")
    if not subscriber_id:
        return None

    try:
        return int(subscriber_id)
    except (TypeError, ValueError):
        return None


def _manychat_failure_message(data: dict) -> str:
    message = data.get("message") or data.get("error") or data.get("status")
    if message:
        return str(message)[:300]
    return json.dumps(data, ensure_ascii=True)[:300]


def _lookup_phone_values(phone: str) -> tuple[str, ...]:
    values: list[str] = []

    def add(value: str) -> None:
        value = (value or "").strip()
        if value and value not in values:
            values.append(value)
        digits = value.lstrip("+")
        if digits and digits != value and digits not in values:
            values.append(digits)

    add(phone)
    try:
        from shopman.utils.phone import normalize_phone

        add(normalize_phone(phone))
    except Exception:  # silêncio-deliberado: a variante bruta continua válida para o lookup
        logger.debug("Manychat resolver: phone variant normalization failed", exc_info=True)
    return tuple(values)


def _canonical_phone(phone: str) -> str:
    try:
        from shopman.utils.phone import normalize_phone

        return normalize_phone(phone) or phone
    except Exception:  # silêncio-deliberado: o chamador ainda compara o telefone original
        logger.debug("Manychat resolver: phone normalization failed", exc_info=True)
        return phone


@lru_cache(maxsize=16)
def _custom_field_name_by_id(api_token: str, field_id: str) -> str:
    if not api_token or not field_id:
        return ""
    request = Request(f"{_API_BASE}/page/getCustomFields", headers={
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=_API_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") != "success":
                logger.warning(
                    "Manychat resolver: custom fields lookup failed: %s",
                    _manychat_failure_message(data),
                )
                return ""
            for field in data.get("data") or []:
                if str(field.get("id")) == str(field_id):
                    return str(field.get("name") or "").strip()
    except HTTPError as e:
        logger.warning(
            "Manychat resolver: custom fields HTTP error %d: %s",
            e.code,
            _read_http_error_body(e),
        )
    except (URLError, ValueError, Exception):
        logger.warning("Manychat resolver: custom fields lookup failed")
    return ""


class ManychatSubscriberResolver:
    """
    Resolve recipient → Manychat subscriber_id.

    Usa CustomerIdentifier (contrib/identifiers) para mapear
    phone/email/ref → MANYCHAT subscriber_id.

    Se não encontrar no banco, consulta a API do ManyChat via
    findBySystemField (phone) e persiste o resultado.
    """

    @classmethod
    def resolve(cls, recipient: str, *, require_customer: bool = False) -> int | None:
        """
        Resolve subscriber_id a partir do recipient.

        Args:
            recipient: subscriber_id numérico, phone E.164, customer code ou email.

        Returns:
            Manychat subscriber_id (int) ou None se não encontrado.
        """
        recipient = (recipient or "").strip()
        if not recipient:
            return None
        if recipient.isdigit():
            return int(recipient)
        original_recipient = recipient
        if recipient.startswith("+"):
            recipient = _canonical_phone(recipient)

        customer = cls._find_customer(recipient)
        if customer is None and original_recipient != recipient:
            customer = cls._find_customer(original_recipient)

        if customer:
            return cls._resolve_for_customer(customer.pk, recipient)

        # OTP delivery must never bootstrap an ownerless provider contact.  If
        # account deletion won before this lookup, returning None lets the
        # configured delivery chain fall back without recreating external PII.
        if require_customer:
            return None

        # API fallback: lookup subscriber by the mirrored WhatsApp ID before
        # the system phone. WhatsApp-only contacts often do not have ManyChat's
        # generic `phone` field populated, but they do have a WhatsApp ID.
        if recipient.startswith("+"):
            subscriber_id = cls._lookup_by_whatsapp_id_custom_field_api(recipient)
            if subscriber_id is None:
                subscriber_id = cls._lookup_by_phone_api(recipient)
                if subscriber_id is not None:
                    cls._mirror_whatsapp_id_custom_field_api(subscriber_id, recipient)
            if subscriber_id is None:
                subscriber_id = cls._create_whatsapp_subscriber_api(recipient)
            return subscriber_id

        if not customer:
            logger.debug("Manychat resolver: customer not found for %s", recipient[:20])
        return None

    @classmethod
    def resolve_active_customer(cls, recipient: str) -> int | None:
        """OTP-safe one-argument capability: never bootstrap an ownerless contact."""
        return cls.resolve(recipient, require_customer=True)

    @classmethod
    def _resolve_for_customer(cls, customer_pk: int, recipient: str) -> int | None:
        """Resolve under the account's canonical privacy fence.

        The Customer row serializes resolution with account deletion.  Provider
        calls have the resolver's bounded timeout and happen only after the
        active-state recheck.  If an external create/lookup has no conclusive
        local result, a non-PII reconciliation marker remains durable: deletion
        must fail closed instead of claiming that an account was erased while
        the provider may have accepted a contact.
        """
        prepared, subscriber_id = cls._prepare_customer_resolution(customer_pk, recipient)
        if not prepared:
            if subscriber_id is not None and recipient.startswith("+"):
                cls._mirror_whatsapp_id_custom_field_api(subscriber_id, recipient)
            return subscriber_id
        return cls._run_pending_customer_resolution(customer_pk, recipient)

    @classmethod
    def _prepare_customer_resolution(
        cls,
        customer_pk: int,
        recipient: str,
    ) -> tuple[bool, int | None]:
        """Commit the fail-closed intent before any provider mutation."""
        from django.conf import settings
        from django.db import transaction
        from shopman.guestman.models import Customer

        with transaction.atomic(durable=True):
            customer = (
                Customer.objects.select_for_update()
                .filter(pk=customer_pk, is_active=True)
                .first()
            )
            if customer is None:
                return False, None
            subscriber_id = cls._get_manychat_id(customer)
            if subscriber_id is not None:
                return False, subscriber_id
            if not recipient.startswith("+"):
                return False, None
            api_token = str(getattr(settings, "MANYCHAT_API_TOKEN", "") or "").strip()
            if not api_token:
                return False, None

            metadata = dict(customer.metadata or {})
            if metadata.get(_PRIVACY_PENDING_KEY):
                return False, None
            metadata[_PRIVACY_PENDING_KEY] = True
            customer.metadata = metadata
            customer.save(update_fields=["metadata", "updated_at"])
            return True, None

    @classmethod
    def _run_pending_customer_resolution(cls, customer_pk: int, recipient: str) -> int | None:
        """Run bounded I/O only after the durable intent transaction committed."""
        with _customer_provider_mutex(customer_pk):
            subscriber_id = cls._lookup_by_whatsapp_id_custom_field_api(recipient)
            if subscriber_id is None:
                subscriber_id = cls._lookup_by_phone_api(recipient)
                if subscriber_id is not None:
                    cls._mirror_whatsapp_id_custom_field_api(subscriber_id, recipient)
            if subscriber_id is None:
                subscriber_id = cls._create_whatsapp_subscriber_outcome(recipient).subscriber_id
            return cls._finalize_customer_resolution(customer_pk, subscriber_id)

    @classmethod
    def _finalize_customer_resolution(
        cls,
        customer_pk: int,
        subscriber_id: int | None,
    ) -> int | None:
        from django.db import transaction
        from shopman.guestman.models import Customer

        with transaction.atomic(durable=True):
            customer = (
                Customer.objects.select_for_update()
                .filter(pk=customer_pk, is_active=True)
                .first()
            )
            if customer is None:
                return None
            metadata = dict(customer.metadata or {})
            if not metadata.get(_PRIVACY_PENDING_KEY):
                return cls._get_manychat_id(customer)
            if subscriber_id is not None:
                cls._persist_manychat_id(customer, subscriber_id)
                metadata.pop(_PRIVACY_PENDING_KEY, None)
                customer.metadata = metadata
                customer.save(update_fields=["metadata", "updated_at"])
            return subscriber_id

    @classmethod
    def reconcile_pending(cls, customer_pk: int) -> str:
        """Reconcile an uncertain create using a read-only provider lookup.

        Returns ``linked`` when the external subscriber is materialized locally,
        ``absent`` only after the provider gives a successful empty lookup,
        ``uncertain`` when upstream cannot confirm either outcome, and ``clear``
        when no reconciliation was pending.  It never creates or deletes an
        external subscriber.
        """
        with _customer_provider_mutex(customer_pk):
            phone = cls._pending_customer_phone(customer_pk)
            if phone is None:
                return "clear"
            if not phone:
                return "uncertain"
            outcome = cls._lookup_by_phone_api_outcome(phone)
            if outcome.subscriber_id is not None:
                cls._finalize_customer_resolution(customer_pk, outcome.subscriber_id)
                return "linked"
            if outcome.conclusive_absence:
                cls._clear_pending_resolution(customer_pk)
                return "absent"
            return "uncertain"

    @classmethod
    def _pending_customer_phone(cls, customer_pk: int) -> str | None:
        from django.db import transaction
        from shopman.guestman.models import Customer

        with transaction.atomic(durable=True):
            customer = (
                Customer.objects.select_for_update()
                .filter(pk=customer_pk, is_active=True)
                .first()
            )
            if customer is None:
                return None
            if not (customer.metadata or {}).get(_PRIVACY_PENDING_KEY):
                return None
            return _canonical_phone(customer.phone or "")

    @classmethod
    def _clear_pending_resolution(cls, customer_pk: int) -> None:
        from django.db import transaction
        from shopman.guestman.models import Customer

        with transaction.atomic(durable=True):
            customer = (
                Customer.objects.select_for_update()
                .filter(pk=customer_pk, is_active=True)
                .first()
            )
            if customer is None:
                return
            metadata = dict(customer.metadata or {})
            metadata.pop(_PRIVACY_PENDING_KEY, None)
            customer.metadata = metadata
            customer.save(update_fields=["metadata", "updated_at"])

    @classmethod
    def fetch_subscriber_info(cls, subscriber_id: str | int) -> dict | None:
        """O contato como o ManyChat o conhece — ``GET /fb/subscriber/getInfo``.

        Existe porque o `subscriber_id` é a única coisa que um fluxo do ManyChat
        nunca erra, e todo o resto (telefone, texto da última mensagem) tem nome
        e disponibilidade que variam por canal. Buscar na fonte substitui o corpo
        do request adivinhar qual variável usar.

        O que o getInfo devolve, medido num contato real de WhatsApp em 01/09:
        ``whatsapp_phone="+55..."``, ``last_input_text="#menu NB-282SW9"`` — e
        ``phone=None``. O campo sistêmico `phone` é nulo mesmo num contato de
        WhatsApp saudável; foi assumi-lo que quebrou o login por dias.
        """
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        subscriber_id = str(subscriber_id or "").strip()
        if not api_token or not subscriber_id:
            return None

        url = f"{_API_BASE}/subscriber/getInfo?{urlencode({'subscriber_id': subscriber_id})}"
        request = Request(url, headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=_API_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success" and isinstance(data.get("data"), dict):
                return data["data"]
            logger.warning(
                "Manychat resolver: getInfo failed for %s: %s",
                subscriber_id, _manychat_failure_message(data),
            )
        except HTTPError as e:
            logger.warning(
                "Manychat resolver: getInfo HTTP error %d for %s: %s",
                e.code, subscriber_id, _read_http_error_body(e),
            )
        except (URLError, ValueError, Exception):
            logger.warning("Manychat resolver: getInfo call failed")
        return None

    @staticmethod
    def phone_from_subscriber_info(info: dict | None) -> str:
        """O telefone do contato, na ordem em que ele de fato existe.

        ``whatsapp_phone`` primeiro porque é o único preenchido em contato de
        WhatsApp. ``optin_phone`` NÃO entra na cascata: apesar do nome, é booleano.
        """
        if not isinstance(info, dict):
            return ""
        for key in ("whatsapp_phone", "phone"):
            value = info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def _find_customer(cls, recipient: str) -> Customer | None:
        """Busca customer por phone, code ou email."""
        from shopman.guestman.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )
        from shopman.guestman.models import Customer

        if recipient.startswith("+"):
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.PHONE,
                    identifier_value=recipient,
                    customer__is_active=True,
                )
                return ident.customer
            except CustomerIdentifier.DoesNotExist:
                # Also try direct phone field on Customer
                return Customer.objects.filter(
                    phone=recipient, is_active=True,
                ).first()

        if recipient.startswith("MC-"):
            return Customer.objects.filter(
                ref=recipient, is_active=True,
            ).first()

        if "@" in recipient:
            try:
                ident = CustomerIdentifier.objects.select_related("customer").get(
                    identifier_type=IdentifierType.EMAIL,
                    identifier_value=recipient.lower().strip(),
                    customer__is_active=True,
                )
                return ident.customer
            except CustomerIdentifier.DoesNotExist:
                return None

        return None

    @classmethod
    def _get_manychat_id(cls, customer: Customer) -> int | None:
        """Busca Manychat subscriber_id do customer."""
        from shopman.guestman.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )

        try:
            ident = CustomerIdentifier.objects.get(
                customer=customer,
                identifier_type=IdentifierType.MANYCHAT,
            )
            return int(ident.identifier_value)
        except (CustomerIdentifier.DoesNotExist, ValueError):
            return None

    @classmethod
    def _lookup_by_whatsapp_id_custom_field_api(cls, whatsapp_id: str) -> int | None:
        """Consulta ManyChat por um campo espelho do WhatsApp ID.

        ManyChat guarda WhatsApp ID como identificador do canal, mas nem sempre
        esse valor aparece no campo sistêmico ``phone``. Para lookup confiável,
        o bot deve espelhar o WhatsApp ID em um Custom User Field e configurar
        ``MANYCHAT_WHATSAPP_ID_FIELD_ID`` com o ID desse campo.
        """
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        mc_config = getattr(settings, "SHOPMAN_MANYCHAT", {}) or {}
        field_id = str(
            getattr(settings, "MANYCHAT_WHATSAPP_ID_FIELD_ID", "")
            or mc_config.get("whatsapp_id_field_id")
            or ""
        ).strip()
        if not api_token or not field_id:
            return None

        for lookup_value in _lookup_phone_values(whatsapp_id):
            url = (
                f"{_API_BASE}/subscriber/findByCustomField"
                f"?{urlencode({'field_id': field_id, 'field_value': lookup_value})}"
            )
            request = Request(url, headers={
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/json",
            })

            try:
                with urlopen(request, timeout=_API_TIMEOUT) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    if data.get("status") == "success":
                        subscriber_id = _subscriber_id(data)
                        if subscriber_id:
                            logger.info(
                                "Manychat resolver: found subscriber %s for WhatsApp ID %s "
                                "via custom field",
                                subscriber_id, whatsapp_id[:8],
                            )
                            return subscriber_id
                        logger.info(
                            "Manychat resolver: no subscriber found for WhatsApp ID %s via custom field",
                            whatsapp_id[:8],
                        )
                    else:
                        logger.warning(
                            "Manychat resolver: WhatsApp ID lookup failed for %s: %s",
                            whatsapp_id[:8],
                            _manychat_failure_message(data),
                        )
            except HTTPError as e:
                error_body = _read_http_error_body(e)
                if e.code == 404:
                    logger.debug(
                        "Manychat resolver: subscriber not found for WhatsApp ID %s",
                        whatsapp_id[:8],
                    )
                else:
                    logger.warning(
                        "Manychat resolver: API error %d for WhatsApp ID %s: %s",
                        e.code,
                        whatsapp_id[:8],
                        error_body,
                    )
            except (URLError, ValueError, Exception):
                logger.warning("Manychat resolver: WhatsApp ID API call failed")

        return None

    @classmethod
    def _lookup_by_phone_api(cls, phone: str) -> int | None:
        """Consulta ManyChat API para encontrar subscriber por telefone.

        GET /fb/subscriber/findBySystemField?phone=<E.164>
        """
        return cls._lookup_by_phone_api_outcome(phone).subscriber_id

    @classmethod
    def _lookup_by_phone_api_outcome(cls, phone: str) -> _ProviderLookupOutcome:
        """Lookup with enough outcome detail for privacy reconciliation."""
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        if not api_token:
            return _ProviderLookupOutcome()

        every_variant_conclusive = True

        for lookup_phone in _lookup_phone_values(phone):
            url = (
                f"{_API_BASE}/subscriber/findBySystemField"
                f"?{urlencode({'phone': lookup_phone})}"
            )
            request = Request(url, headers={
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/json",
            })

            try:
                with urlopen(request, timeout=_API_TIMEOUT) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    if data.get("status") == "success":
                        subscriber_id = _subscriber_id(data)
                        if subscriber_id:
                            logger.info(
                                "Manychat resolver: found subscriber %s for phone %s via API",
                                subscriber_id, phone[:8],
                            )
                            return _ProviderLookupOutcome(subscriber_id=subscriber_id)
                        logger.info(
                            "Manychat resolver: no subscriber found for phone %s via system field",
                            phone[:8],
                        )
                    else:
                        every_variant_conclusive = False
                        logger.warning(
                            "Manychat resolver: lookup failed for phone %s: %s",
                            phone[:8],
                            _manychat_failure_message(data),
                        )
            except HTTPError as e:
                every_variant_conclusive = False
                error_body = _read_http_error_body(e)
                if e.code == 404:
                    logger.debug("Manychat resolver: subscriber not found for phone %s", phone[:8])
                else:
                    logger.warning(
                        "Manychat resolver: API error %d for phone %s: %s",
                        e.code,
                        phone[:8],
                        error_body,
                    )
            except (URLError, ValueError, Exception):
                every_variant_conclusive = False
                logger.debug(
                    "Manychat resolver: API call failed for phone %s",
                    phone[:8],
                    exc_info=True,
                )

        return _ProviderLookupOutcome(conclusive_absence=every_variant_conclusive)

    @classmethod
    def _create_whatsapp_subscriber_api(cls, phone: str) -> int | None:
        """Cria contato WhatsApp no ManyChat e retorna subscriber_id.

        POST /fb/subscriber/createSubscriber
        """
        return cls._create_whatsapp_subscriber_outcome(phone).subscriber_id

    @classmethod
    def _create_whatsapp_subscriber_outcome(cls, phone: str) -> _ProviderCreateOutcome:
        """Create with a conservative distinction between rejection and doubt."""
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        if not api_token:
            return _ProviderCreateOutcome()

        payload = {"whatsapp_phone": phone}
        request = Request(
            f"{_API_BASE}/subscriber/createSubscriber",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=_API_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("status") == "success":
                    subscriber_id = _subscriber_id(data)
                    if subscriber_id:
                        logger.info(
                            "Manychat resolver: created WhatsApp subscriber %s for phone %s",
                            subscriber_id,
                            phone[:8],
                        )
                        cls._mirror_whatsapp_id_custom_field_api(subscriber_id, phone)
                        return _ProviderCreateOutcome(subscriber_id=subscriber_id)
                    logger.warning(
                        "Manychat resolver: createSubscriber returned no id for phone %s",
                        phone[:8],
                    )
                else:
                    logger.warning(
                        "Manychat resolver: createSubscriber failed for phone %s: %s",
                        phone[:8],
                        _manychat_failure_message(data),
                    )
                    # Some provider errors mean the contact already exists.  A
                    # response without its id is therefore not proof of absence;
                    # keep the reconciliation fence until a read lookup decides.
                    return _ProviderCreateOutcome()
        except HTTPError as e:
            logger.warning(
                "Manychat resolver: createSubscriber HTTP error %d for phone %s: %s",
                e.code,
                phone[:8],
                _read_http_error_body(e),
            )
        except (URLError, ValueError, Exception):
            logger.warning("Manychat resolver: createSubscriber call failed")

        return _ProviderCreateOutcome()

    @classmethod
    def _mirror_whatsapp_id_custom_field_api(cls, subscriber_id: int, phone: str) -> bool:
        """Persist WhatsApp ID into the configured custom field for future lookup."""
        from django.conf import settings

        api_token = getattr(settings, "MANYCHAT_API_TOKEN", "")
        mc_config = getattr(settings, "SHOPMAN_MANYCHAT", {}) or {}
        field_name = str(
            getattr(settings, "MANYCHAT_WHATSAPP_ID_FIELD_NAME", "")
            or mc_config.get("whatsapp_id_field_name")
            or ""
        ).strip()
        field_id = str(
            getattr(settings, "MANYCHAT_WHATSAPP_ID_FIELD_ID", "")
            or mc_config.get("whatsapp_id_field_id")
            or ""
        ).strip()
        if not field_name and field_id:
            field_name = _custom_field_name_by_id(api_token, field_id)
        if not api_token or not field_name:
            return False

        payload = {
            "subscriber_id": str(subscriber_id),
            "field_name": field_name,
            "field_value": _canonical_phone(phone).lstrip("+"),
        }
        request = Request(
            f"{_API_BASE}/subscriber/setCustomFieldByName",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=_API_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("status") == "success":
                    logger.info(
                        "Manychat resolver: mirrored WhatsApp ID for subscriber %s",
                        subscriber_id,
                    )
                    return True
                logger.warning(
                    "Manychat resolver: WhatsApp ID mirror failed for subscriber %s: %s",
                    subscriber_id,
                    _manychat_failure_message(data),
                )
        except HTTPError as e:
            logger.warning(
                "Manychat resolver: WhatsApp ID mirror HTTP error %d for subscriber %s: %s",
                e.code,
                subscriber_id,
                _read_http_error_body(e),
            )
        except (URLError, ValueError, Exception):
            logger.warning("Manychat resolver: WhatsApp ID mirror call failed")
        return False

    @classmethod
    def _persist_manychat_id(cls, customer: Customer, subscriber_id: int) -> None:
        """Persiste o subscriber_id como CustomerIdentifier para evitar future API calls."""
        from shopman.guestman.contrib.identifiers.models import (
            CustomerIdentifier,
            IdentifierType,
        )

        CustomerIdentifier.objects.get_or_create(
            customer=customer,
            identifier_type=IdentifierType.MANYCHAT,
            defaults={
                "identifier_value": str(subscriber_id),
                "is_primary": True,
                "source_system": "manychat_api_lookup",
            },
        )
