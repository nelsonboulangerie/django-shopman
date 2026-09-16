"""Bounded-memory, complete customer account export.

The export is deliberately built here instead of in the HTTP view.  That keeps
the privacy boundary testable and makes it impossible for a response to start
before every database read and JSON encoding step has succeeded.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterable, Mapping
from typing import Any, BinaryIO

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

SCHEMA_VERSION = "account_export.v1"
DEFAULT_SPOOL_MAX_SIZE = 2 * 1024 * 1024
DEFAULT_ITERATOR_CHUNK_SIZE = 500

# JSON fields can contain integration payloads.  Their outer model field may be
# allowlisted while an embedded credential is not, so apply the same explicit
# deny boundary recursively before encoding any value.
FORBIDDEN_EMBEDDED_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "badge_hash",
        "client_secret",
        "code_hash",
        "connection_key",
        "credential_id",
        "idempotency_key",
        "password",
        "password_hash",
        "pin_hash",
        "private_key",
        "public_key",
        "refresh_token",
        "secret",
        "secret_key",
        "session_key",
        "target_key",
        "token",
        "token_hash",
    }
)

# These tuples are the export contract.  Using ``values(*allowlist)`` ensures a
# newly added model field cannot silently become downloadable.
CUSTOMER_FIELDS = (
    "ref",
    "uuid",
    "first_name",
    "last_name",
    "customer_type",
    "document",
    "birthday",
    "email",
    "phone",
    "is_active",
    "metadata",
    "price_tier__ref",
    "price_tier__name",
    "price_tier__listing_ref",
    "created_at",
    "updated_at",
)
ADDRESS_FIELDS = (
    "label",
    "label_custom",
    "place_id",
    "formatted_address",
    "street_number",
    "route",
    "neighborhood",
    "city",
    "state",
    "state_code",
    "postal_code",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "complement",
    "delivery_instructions",
    "is_default",
    "is_verified",
    "created_at",
    "updated_at",
)
CONTACT_POINT_FIELDS = (
    "id",
    "type",
    "value_normalized",
    "value_display",
    "is_primary",
    "is_verified",
    "verification_method",
    "verified_at",
    "created_at",
    "updated_at",
)
PREFERENCE_FIELDS = (
    "preference_type",
    "category",
    "key",
    "value",
    "confidence",
    "source",
    "created_at",
    "updated_at",
)
CONSENT_FIELDS = (
    "channel",
    "purpose",
    "status",
    "legal_basis",
    "source",
    "policy_version",
    "disclosure_hash",
    "evidence_hash",
    "locale",
    "proof_status",
    "ip_address",
    "consented_at",
    "revoked_at",
    "created_at",
    "updated_at",
)
ORDER_FIELDS = (
    "ref",
    "channel_ref",
    "external_ref",
    "status",
    "currency",
    "total_q",
    "created_at",
    "updated_at",
    "accepted_at",
    "preparing_at",
    "ready_at",
    "dispatched_at",
    "delivered_at",
    "completed_at",
    "cancelled_at",
    "returned_at",
)
ORDER_ITEM_FIELDS = (
    "order__ref",
    "line_id",
    "sku",
    "name",
    "qty",
    "unit_price_q",
    "line_total_q",
    "meta",
)
LOYALTY_FIELDS = (
    "points_balance",
    "lifetime_points",
    "stamps_current",
    "stamps_target",
    "stamps_completed",
    "tier",
    "is_active",
    "enrolled_at",
    "updated_at",
)
LOYALTY_TRANSACTION_FIELDS = (
    "transaction_type",
    "points",
    "balance_after",
    "description",
    "reference",
    "created_at",
)
ORDER_DATA_KEYS = (
    "customer",
    "customer_ref",
    "fulfillment_type",
    "delivery_address",
    "delivery_address_structured",
    "delivery_date",
    "delivery_time_slot",
    "order_notes",
    "origin_channel",
    "receipt",
    "fiscal",
    "is_gift",
    "recipient",
    "gift_message",
    "gift_hide_values",
)
PRICING_KEYS = (
    "subtotal_q",
    "items_total_q",
    "discount_q",
    "delivery_fee_q",
    "service_fee_q",
    "total_q",
    "currency",
)


def _clean_embedded(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _clean_embedded(item)
            for key, item in value.items()
            if str(key).lower() not in FORBIDDEN_EMBEDDED_KEYS
        }
    if isinstance(value, list):
        return [_clean_embedded(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clean_embedded(item) for item in value)
    return value


def _closed_mapping(value: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {field: _clean_embedded(value[field]) for field in fields if field in value}


def _project_customer_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    projected: dict[str, Any] = {}
    if "house_account" in value:
        projected["house_account"] = bool(value["house_account"])
    if "preferences" in value:
        projected["preferences"] = str(value["preferences"] or "")
    fiscal = _closed_mapping(value.get("fiscal_prefs"), ("cpf_na_nota", "email_receipt"))
    if fiscal:
        projected["fiscal_prefs"] = {key: bool(item) for key, item in fiscal.items()}
    return projected


def _project_pricing(value: Any) -> dict[str, Any]:
    return _closed_mapping(value, PRICING_KEYS)


def _project_order_data(value: Any) -> dict[str, Any]:
    return _closed_mapping(value, ORDER_DATA_KEYS)


def _project_item_meta(value: Any) -> dict[str, Any]:
    return _closed_mapping(
        value,
        (
            "customer_note",
            "customization",
            "gift_wrap",
            "options",
            "modifiers",
        ),
    )


def _project_message_content(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projected = []
    for block in value:
        if not isinstance(block, Mapping):
            continue
        kind = str(block.get("type") or "")
        if kind not in {"text", "input_text", "output_text"}:
            continue
        safe = _closed_mapping(block, ("type", "text"))
        if safe:
            projected.append(safe)
    return projected


def _owned_footprint_query(customer_ref: str, phone: str) -> Q:
    # Exportar e excluir são as duas faces do mesmo direito; compartilhar a
    # consulta impede que uma delas volte a atravessar o dono canônico.
    from shopman.shop.services.account import customer_footprint_query

    return customer_footprint_query(customer_ref, phone)


def _pack_json_paths(
    row: dict[str, Any],
    *,
    prefix: str,
    target: str,
    projector: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    source = {}
    for key in tuple(row):
        if key.startswith(prefix):
            source[key.removeprefix(prefix)] = row.pop(key)
    projected = projector(source)
    if projected:
        row[target] = projected
    return row


def _project_session_row(row: dict[str, Any]) -> Mapping[str, Any]:
    _pack_json_paths(row, prefix="data__", target="data", projector=_project_order_data)
    return _pack_json_paths(row, prefix="pricing__", target="pricing", projector=_project_pricing)


def _project_order_row(row: dict[str, Any]) -> Mapping[str, Any]:
    return _pack_json_paths(row, prefix="data__", target="data", projector=_project_order_data)


def _project_order_item_row(row: dict[str, Any]) -> Mapping[str, Any]:
    row["order_ref"] = row.pop("order__ref")
    row["meta"] = _project_item_meta(row.get("meta"))
    return row


def _project_session_item_row(row: dict[str, Any]) -> Mapping[str, Any]:
    row["meta"] = _project_item_meta(row.get("meta"))
    return row


def _project_conversation_message(row: dict[str, Any]) -> Mapping[str, Any]:
    row["content"] = _project_message_content(row.get("content"))
    return row


def _write_json(output: BinaryIO, value: Any) -> None:
    # DjangoJSONEncoder is intentional: dates, datetimes, Decimal and UUID are
    # supported, while unknown objects raise instead of being hidden by str().
    encoder = DjangoJSONEncoder(
        ensure_ascii=False,
        separators=(",", ":"),
    )
    for chunk in encoder.iterencode(_clean_embedded(value)):
        output.write(chunk.encode())


class _ObjectWriter:
    def __init__(self, output: BinaryIO, *, chunk_size: int):
        self.output = output
        self.chunk_size = chunk_size
        self.first_property = True
        self.counts: dict[str, int] = {}
        self.output.write(b"{")

    def _property(self, name: str) -> None:
        if not self.first_property:
            self.output.write(b",")
        self.first_property = False
        _write_json(self.output, name)
        self.output.write(b":")

    def value(self, name: str, value: Any, *, count: bool = False) -> None:
        self._property(name)
        _write_json(self.output, value)
        if count:
            self.counts[name] = int(value is not None)

    def array(
        self,
        name: str,
        rows: QuerySet | Iterable[Mapping[str, Any]],
        *,
        transform: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self._property(name)
        self.output.write(b"[")
        first = True
        count = 0
        iterator = rows.iterator(chunk_size=self.chunk_size) if isinstance(rows, QuerySet) else iter(rows)
        for source in iterator:
            row = dict(source)
            if transform is not None:
                row = dict(transform(row))
            if not first:
                self.output.write(b",")
            first = False
            _write_json(self.output, row)
            count += 1
        self.output.write(b"]")
        self.counts[name] = count

    def finish(self) -> None:
        self.value("section_counts", self.counts)
        self.output.write(b"}")


def _values(
    label: str,
    *,
    fields: tuple[str, ...],
    order_by: tuple[str, ...],
    filters: Mapping[str, Any] | None = None,
    query: Q | None = None,
) -> QuerySet:
    queryset = apps.get_model(label).objects.all()
    if filters:
        queryset = queryset.filter(**filters)
    if query is not None:
        queryset = queryset.filter(query)
    return queryset.order_by(*order_by).values(*fields)


def _rename(source: str, target: str) -> Callable[[dict[str, Any]], Mapping[str, Any]]:
    def transform(row: dict[str, Any]) -> Mapping[str, Any]:
        row[target] = row.pop(source)
        return row

    return transform


def _postgres_repeatable_read_if_safe(*, outermost: bool) -> None:
    if connection.vendor != "postgresql" or not outermost:
        return
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")


def _write_export(writer: _ObjectWriter, customer: Any) -> None:
    customer_model = apps.get_model("guestman.Customer")
    customer_row = customer_model.objects.filter(pk=customer.pk).values(*CUSTOMER_FIELDS).get()
    customer_ref = customer_row["ref"]
    customer_uuid = customer_row["uuid"]
    phone = customer_row["phone"] or ""
    email = customer_row["email"] or ""
    customer_row["metadata"] = _project_customer_metadata(customer_row.get("metadata"))

    writer.value("schema_version", SCHEMA_VERSION)
    writer.value("generated_at", timezone.now())
    writer.value("customer", customer_row, count=True)

    writer.array(
        "addresses",
        _values(
            "guestman.CustomerAddress",
            fields=ADDRESS_FIELDS,
            order_by=("-is_default", "label", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "contact_points",
        _values(
            "guestman.ContactPoint",
            fields=CONTACT_POINT_FIELDS,
            order_by=("type", "-is_primary", "created_at", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "customer_tags",
        customer_model.objects.filter(pk=customer.pk)
        .order_by("tags__name", "tags__pk")
        .values("tags__name")
        .exclude(tags__isnull=True),
        transform=_rename("tags__name", "name"),
    )
    writer.array(
        "customer_identifiers",
        _values(
            "customer_identifiers.CustomerIdentifier",
            fields=(
                "identifier_type",
                "identifier_value",
                "is_primary",
                "verified_at",
                "created_at",
                "source_system",
            ),
            order_by=("identifier_type", "identifier_value", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "external_identities",
        _values(
            "guestman.ExternalIdentity",
            fields=(
                "provider",
                "provider_uid",
                "is_active",
                "created_at",
                "updated_at",
            ),
            order_by=("provider", "provider_uid", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "preferences",
        _values(
            "customer_preferences.CustomerPreference",
            fields=PREFERENCE_FIELDS,
            order_by=("category", "key", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "customer_insights",
        _values(
            "customer_insights.CustomerInsight",
            fields=(
                "total_orders",
                "total_spent_q",
                "average_ticket_q",
                "first_order_at",
                "last_order_at",
                "days_since_last_order",
                "average_days_between_orders",
                "preferred_weekday",
                "preferred_hour",
                "favorite_products",
                "preferred_channel",
                "channels_used",
                "rfm_recency",
                "rfm_frequency",
                "rfm_monetary",
                "rfm_segment",
                "churn_risk",
                "predicted_ltv_q",
                "calculated_at",
                "calculation_version",
            ),
            order_by=("calculated_at", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "timeline_events",
        _values(
            "customer_timeline.TimelineEvent",
            fields=(
                "event_type",
                "title",
                "description",
                "channel",
                "reference",
                "created_at",
            ),
            order_by=("created_at", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "consents",
        _values(
            "customer_consent.CommunicationConsent",
            fields=CONSENT_FIELDS,
            order_by=("channel", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )
    writer.array(
        "consent_events",
        _values(
            "customer_consent.CommunicationConsentEvent",
            fields=(
                "ref",
                "channel",
                "purpose",
                "event_type",
                "resulting_status",
                "legal_basis",
                "source",
                "disclosure_text",
                "disclosure_version",
                "disclosure_hash",
                "evidence_hash",
                "proof_status",
                "locale",
                "ip_address",
                "occurred_at",
                "created_at",
            ),
            order_by=("occurred_at", "pk"),
            filters={"customer_id": customer.pk},
        ),
    )

    customer_users = apps.get_model("doorman.CustomerUser").objects.filter(customer_id=customer_uuid)
    writer.array(
        "auth_accounts",
        customer_users.order_by("created_at", "pk").values(
            "user__username",
            "user__first_name",
            "user__last_name",
            "user__email",
            "user__is_active",
            "user__date_joined",
            "user__last_login",
            "created_at",
        ),
    )
    writer.array(
        "auth_access_links",
        _values(
            "doorman.AccessLink",
            fields=("audience", "created_at", "expires_at", "used_at", "source"),
            order_by=("created_at", "pk"),
            filters={"customer_id": customer_uuid},
        ),
    )
    writer.array(
        "auth_trusted_devices",
        _values(
            "doorman.TrustedDevice",
            fields=(
                "id",
                "user_agent",
                "ip_address",
                "label",
                "created_at",
                "expires_at",
                "last_used_at",
                "is_active",
            ),
            order_by=("created_at", "pk"),
            filters={"subject_type": "customer", "subject_id": str(customer_uuid)},
        ),
    )
    writer.array(
        "auth_passkeys",
        _values(
            "doorman.Passkey",
            fields=("transports", "label", "created_at", "last_used_at"),
            order_by=("created_at", "pk"),
            filters={"customer_id": customer_uuid},
        ),
    )
    verification_query = Q(customer_id=customer_uuid)
    if phone:
        verification_query |= Q(customer_id__isnull=True, target_value=phone)
    if email:
        verification_query |= Q(customer_id__isnull=True, target_value=email)
    writer.array(
        "auth_verification_codes",
        _values(
            "doorman.VerificationCode",
            fields=(
                "target_value",
                "purpose",
                "status",
                "created_at",
                "expires_at",
                "sent_at",
                "verified_at",
                "delivery_method",
                "ip_address",
            ),
            order_by=("created_at", "pk"),
            query=verification_query,
        ),
    )
    writer.array(
        "auth_pin_credentials",
        apps.get_model("doorman.PinCredential")
        .objects.filter(user_id__in=customer_users.values("user_id"))
        .order_by("created_at", "pk")
        .values("locked_until", "must_change", "created_at", "updated_at", "last_verified_at"),
    )

    footprint = _owned_footprint_query(customer_ref, phone)
    sessions = apps.get_model("orderman.Session").objects.filter(footprint)
    writer.array(
        "order_sessions",
        sessions.order_by("opened_at", "pk").values(
            "id",
            "channel_ref",
            "handle_type",
            "handle_ref",
            "state",
            *(f"data__{key}" for key in ORDER_DATA_KEYS),
            *(f"pricing__{key}" for key in PRICING_KEYS),
            "opened_at",
            "committed_at",
            "updated_at",
        ),
        transform=_project_session_row,
    )
    writer.array(
        "order_session_items",
        apps.get_model("orderman.SessionItem")
        .objects.filter(session_id__in=sessions.values("pk"))
        .order_by("session_id", "created_at", "pk")
        .values(
            "session_id",
            "line_id",
            "sku",
            "name",
            "qty",
            "unit_price_q",
            "line_total_q",
            "meta",
            "created_at",
            "updated_at",
        ),
        transform=_project_session_item_row,
    )
    writer.array(
        "order_session_events",
        apps.get_model("orderman.SessionEvent")
        .objects.filter(session_key__in=sessions.values("session_key"))
        .order_by("created_at", "pk")
        .values("seq", "type", "created_at"),
    )
    order_model = apps.get_model("orderman.Order")
    orders = order_model.objects.filter(footprint)
    writer.array(
        "orders",
        orders.order_by("created_at", "pk").values(
            *ORDER_FIELDS,
            *(f"data__{key}" for key in ORDER_DATA_KEYS),
        ),
        transform=_project_order_row,
    )
    writer.array(
        "order_items",
        apps.get_model("orderman.OrderItem")
        .objects.filter(order_id__in=orders.values("pk"))
        .order_by("order__created_at", "order__pk", "line_id", "pk")
        .values(*ORDER_ITEM_FIELDS),
        transform=_project_order_item_row,
    )
    writer.array(
        "order_events",
        apps.get_model("orderman.OrderEvent")
        .objects.filter(order_id__in=orders.values("pk"))
        .order_by("order__created_at", "order__pk", "seq", "pk")
        .values("order__ref", "seq", "type", "created_at"),
        transform=_rename("order__ref", "order_ref"),
    )
    fulfillments = apps.get_model("orderman.Fulfillment").objects.filter(order_id__in=orders.values("pk"))
    writer.array(
        "order_fulfillments",
        fulfillments.order_by("created_at", "pk").values(
            "id",
            "order__ref",
            "status",
            "tracking_code",
            "tracking_url",
            "carrier",
            "created_at",
            "updated_at",
            "dispatched_at",
            "delivered_at",
        ),
        transform=_rename("order__ref", "order_ref"),
    )
    writer.array(
        "order_fulfillment_items",
        apps.get_model("orderman.FulfillmentItem")
        .objects.filter(fulfillment_id__in=fulfillments.values("pk"))
        .order_by("fulfillment_id", "order_item__line_id", "pk")
        .values(
            "fulfillment_id",
            "order_item__line_id",
            "order_item__sku",
            "order_item__name",
            "qty",
        ),
    )
    payment_intents = apps.get_model("payman.PaymentIntent").objects.filter(order_ref__in=orders.values("ref"))
    writer.array(
        "payment_intents",
        payment_intents.order_by("created_at", "pk").values(
            "ref",
            "order_ref",
            "method",
            "status",
            "amount_q",
            "currency",
            "gateway",
            "created_at",
            "authorized_at",
            "captured_at",
            "cancelled_at",
            "expires_at",
            "cancel_reason",
        ),
    )
    writer.array(
        "payment_transactions",
        apps.get_model("payman.PaymentTransaction")
        .objects.filter(intent_id__in=payment_intents.values("pk"))
        .order_by("created_at", "pk")
        .values("intent__ref", "type", "amount_q", "reason", "created_at"),
        transform=_rename("intent__ref", "intent_ref"),
    )

    loyalty_model = apps.get_model("customer_loyalty.LoyaltyAccount")
    loyalty = loyalty_model.objects.filter(customer_id=customer.pk).values(*LOYALTY_FIELDS).first()
    writer.value("loyalty", loyalty, count=True)
    writer.array(
        "loyalty_transactions",
        _values(
            "customer_loyalty.LoyaltyTransaction",
            fields=LOYALTY_TRANSACTION_FIELDS,
            order_by=("created_at", "pk"),
            filters={"account__customer_id": customer.pk},
        ),
    )

    conversation_query = Q(customer_ref=customer_ref)
    if phone:
        conversation_query |= Q(customer_ref="", phone=phone)
    conversation_model = apps.get_model("shop.Conversation")
    conversations = conversation_model.objects.filter(conversation_query)
    writer.array(
        "conversations",
        conversations.order_by("created_at", "pk").values(
            "id",
            "phone",
            "customer_ref",
            "customer_name",
            "channel_ref",
            "state",
            "handoff_reason",
            "handoff_at",
            "last_order_ref",
            "last_inbound_at",
            "last_outbound_at",
            "created_at",
            "updated_at",
        ),
    )
    writer.array(
        "conversation_bindings",
        apps.get_model("shop.ConversationBinding")
        .objects.filter(conversation_id__in=conversations.values("pk"))
        .order_by("conversation_id", "created_at", "pk")
        .values(
            "conversation_id",
            "provider",
            "account",
            "transport_channel",
            "subject",
            "status",
            "identity_assurance",
            "last_inbound_at",
            "last_outbound_at",
            "activated_at",
            "deactivated_at",
            "created_at",
            "updated_at",
        ),
    )
    writer.array(
        "conversation_messages",
        apps.get_model("shop.ConversationMessage")
        .objects.filter(
            conversation_id__in=conversations.values("pk"),
            kind__in=("inbound", "reply"),
        )
        .order_by("conversation_id", "created_at", "pk")
        .values("conversation_id", "role", "kind", "text", "content", "created_at"),
        transform=_project_conversation_message,
    )
    conversation_messages = apps.get_model("shop.ConversationMessage").objects.filter(
        conversation_id__in=conversations.values("pk")
    )
    writer.array(
        "conversation_delivery_attempts",
        apps.get_model("shop.OutboundAttempt")
        .objects.filter(message_id__in=conversation_messages.values("pk"))
        .order_by("message_id", "attempt_no", "pk")
        .values(
            "message_id",
            "attempt_no",
            "state",
            "code",
            "started_at",
            "completed_at",
        ),
    )

    writer.array(
        "favorites",
        _values(
            "storefront.CustomerFavorite",
            fields=("sku", "created_at"),
            order_by=("created_at", "pk"),
            filters={"customer_ref": customer_ref},
        ),
    )
    stock_query = Q(customer_ref=customer_ref)
    if phone:
        stock_query |= Q(customer_ref="", contact_phone=phone)
    subscriptions = apps.get_model("storefront.StockAlertSubscription").objects.filter(stock_query)
    writer.array(
        "stock_alert_subscriptions",
        subscriptions.order_by("subscribed_at", "pk").values(
            "ref",
            "sku",
            "alert_type",
            "channel_ref",
            "delivery_channel",
            "purpose",
            "customer_ref",
            "contact_phone",
            "disclosure_text",
            "disclosure_version",
            "disclosure_hash",
            "evidence_hash",
            "proof_status",
            "adult_declared",
            "subscribed_at",
            "notified_at",
            "expires_at",
            "revoked_at",
            "revoke_reason",
            "revocation_evidence_hash",
            "paused_at",
            "pause_reason",
        ),
    )
    writer.array(
        "stock_alert_deliveries",
        apps.get_model("storefront.StockAlertDelivery")
        .objects.filter(subscription_id__in=subscriptions.values("pk"))
        .order_by("created_at", "pk")
        .values(
            "ref",
            "subscription__ref",
            "occurrence__ref",
            "occurrence__sku",
            "occurrence__event_type",
            "purpose",
            "delivery_channel",
            "status",
            "claimed_at",
            "accepted_at",
            "created_at",
            "updated_at",
        ),
    )

    audience_members = apps.get_model("shop.AudienceSnapshotMember").objects.filter(
        Q(customer_id=customer.pk) | Q(subscription_ref__in=subscriptions.values("ref"))
    )
    writer.array(
        "marketing_audience_members",
        audience_members.order_by("created_at", "pk").values(
            "snapshot__ref",
            "snapshot__announcement_id",
            "subscription_ref",
            "reasons",
            "is_vip",
            "preferred_hour",
            "created_at",
        ),
    )
    delivery_targets = apps.get_model("shop.DeliveryTarget").objects.filter(member_id__in=audience_members.values("pk"))
    writer.array(
        "marketing_delivery_targets",
        delivery_targets.order_by("created_at", "pk").values(
            "ref",
            "announcement_id",
            "snapshot__ref",
            "platform",
            "delivery_kind",
            "format",
            "wave_key",
            "state",
            "attempt_count",
            "last_attempt_at",
            "settled_at",
            "created_at",
            "updated_at",
        ),
    )
    delivery_attempts = apps.get_model("shop.DeliveryAttempt").objects.filter(
        target_id__in=delivery_targets.values("pk")
    )
    writer.array(
        "marketing_delivery_attempts",
        delivery_attempts.order_by("created_at", "pk").values(
            "ref",
            "target__ref",
            "ordinal",
            "state",
            "outcome_kind",
            "error_code",
            "retry_after_seconds",
            "http_status",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ),
    )
    writer.array(
        "marketing_delivery_reconciliations",
        apps.get_model("shop.DeliveryReconciliation")
        .objects.filter(target_id__in=delivery_targets.values("pk"))
        .order_by("created_at", "pk")
        .values(
            "ref",
            "target__ref",
            "attempt__ref",
            "state",
            "outcome_kind",
            "last_error_code",
            "available_at",
            "completed_at",
            "created_at",
            "updated_at",
        ),
    )

    notifications = apps.get_model("shop.UserNotification").objects.filter(user_id__in=customer_users.values("user_id"))
    writer.array(
        "notifications",
        notifications.order_by("created_at", "pk").values(
            "id",
            "category",
            "title",
            "message",
            "is_actionable",
            "is_read",
            "read_at",
            "lifecycle",
            "severity",
            "expires_at",
            "acknowledged_at",
            "resolved_at",
            "created_at",
        ),
    )
    writer.array(
        "notification_events",
        apps.get_model("shop.UserNotificationEvent")
        .objects.filter(notification_id__in=notifications.values("pk"))
        .order_by("occurred_at", "pk")
        .values(
            "notification_id",
            "event_type",
            "from_state",
            "to_state",
            "action_code",
            "outcome_code",
            "occurred_at",
        ),
    )
    writer.finish()


def build_account_export(
    customer: Any,
    *,
    spool_max_size: int = DEFAULT_SPOOL_MAX_SIZE,
    chunk_size: int = DEFAULT_ITERATOR_CHUNK_SIZE,
) -> BinaryIO:
    """Build a complete JSON artifact and return it positioned at byte zero.

    The returned ``SpooledTemporaryFile`` has ``byte_count`` and
    ``section_counts`` attributes for receipt/audit evidence.  The caller owns
    the successful file and must close it.  On every failure this function
    closes the partial artifact before re-raising.
    """

    if spool_max_size < 1:
        raise ValueError("spool_max_size must be positive")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    artifact = tempfile.SpooledTemporaryFile(max_size=spool_max_size, mode="w+b")
    try:
        writer = _ObjectWriter(artifact, chunk_size=chunk_size)
        outermost = not connection.in_atomic_block
        with transaction.atomic():
            _postgres_repeatable_read_if_safe(outermost=outermost)
            _write_export(writer, customer)
        byte_count = artifact.tell()
        artifact.byte_count = byte_count
        artifact.section_counts = dict(writer.counts)
        artifact.schema_version = SCHEMA_VERSION
        artifact.seek(0)
        return artifact
    except BaseException:
        artifact.close()
        raise


__all__ = [
    "DEFAULT_ITERATOR_CHUNK_SIZE",
    "DEFAULT_SPOOL_MAX_SIZE",
    "FORBIDDEN_EMBEDDED_KEYS",
    "SCHEMA_VERSION",
    "build_account_export",
]
