"""Headless operator orders API contract (api/v1/backstage/orders/*).

Mirrors the Admin order console actions on the REST surface that the dedicated
Gestor de Pedidos (orders-nuxt) consumes. The gate is the existing
``shop.manage_orders`` permission (granted to the Caixa/Gerente groups), so a
non-superuser staff operator with that permission can drive the queue; staff
without it — and non-staff — are blocked.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.tests._order_intent import advance_payload, context_payload
from shopman.shop.models import Shop
from shopman.shop.services.operator_orders import cash_settlement_revision, operational_revision


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    """Floor operator: staff + manage_orders, NOT superuser."""
    user = User.objects.create_user("orders-api", password="pw", is_staff=True)
    user.user_permissions.add(_manage_orders_perm())
    return user


@pytest.fixture
def plain_staff(db, shop):
    """Staff user WITHOUT manage_orders — must be blocked."""
    return User.objects.create_user("plain-staff", password="pw", is_staff=True)


def _order(ref: str, status: str = "accepted", **data_extra) -> Order:
    data = {"customer": {"name": "Ana"}, "payment": {"method": "cash"}}
    data.update(data_extra)
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=1500,
        data=data,
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500
    )
    return order


@pytest.fixture
def order(db):
    return _order("ORD-API-1")


# ── Permission gate (the WP-G1 fix: was dangling, superuser-only) ──────────


@pytest.mark.django_db
def test_queue_requires_manage_orders(client, operator, plain_staff, order):
    client.force_login(plain_staff)
    assert client.get(reverse("api-backstage-orders")).status_code == 403

    client.force_login(operator)
    response = client.get(reverse("api-backstage-orders"))
    assert response.status_code == 200
    assert "queue" in response.json()


@pytest.mark.django_db
def test_queue_blocks_non_staff(client, db, shop, order):
    customer = User.objects.create_user("customer", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-orders")).status_code == 403


@pytest.mark.django_db
def test_all_action_endpoints_require_permission(client, plain_staff, order):
    client.force_login(plain_staff)
    ref = order.ref
    action_urls = [
        reverse("api-backstage-order-advance", args=[ref]),
        reverse("api-backstage-order-confirm", args=[ref]),
        reverse("api-backstage-order-reject", args=[ref]),
        reverse("api-backstage-order-cancel", args=[ref]),
        reverse("api-backstage-order-settle-delivery-cash", args=[ref]),
        reverse("api-backstage-order-requeue-fiscal", args=[ref]),
        reverse("api-backstage-order-notes", args=[ref]),
        reverse("api-backstage-order-assign", args=[ref]),
        reverse("api-backstage-order-unassign", args=[ref]),
        reverse("api-backstage-order-comment", args=[ref]),
    ]
    for url in action_urls:
        assert client.post(url).status_code == 403, url


@pytest.mark.django_db
def test_comment_appears_in_timeline(client, operator, order):
    client.force_login(operator)
    ref = order.ref

    blank = client.post(reverse("api-backstage-order-comment", args=[ref]), data={"note": "  "})
    assert blank.status_code == 400  # empty comment rejected

    ok = client.post(
        reverse("api-backstage-order-comment", args=[ref]),
        data={"note": "Cliente vai retirar às 18h", "expected_actor_id": operator.pk, "base_revision": operational_revision(order, field="comment"), "idempotency_key": "comment-18h"},
        content_type="application/json",
    )
    assert ok.status_code == 200

    detail = client.get(reverse("api-backstage-order-detail", args=[ref])).json()["order"]
    comments = [e for e in detail["timeline"] if e["event_type"] == "operator_comment"]
    assert len(comments) == 1
    assert comments[0]["label"] == "Comentário"
    assert "18h" in comments[0]["detail"]


@pytest.mark.django_db
def test_assign_then_unassign_roundtrip(client, operator, order):
    client.force_login(operator)
    ref = order.ref

    assign = client.post(reverse("api-backstage-order-assign", args=[ref]), context_payload(client, ref, "assign"), content_type="application/json")
    assert assign.status_code == 200
    order.refresh_from_db()
    assert order.data["assignment"]["operator_id"] == operator.pk

    # the card projection surfaces the holder's name
    queue = client.get(reverse("api-backstage-orders")).json()["queue"]
    cards = [c for zone in queue.values() if isinstance(zone, list) for c in zone]
    assigned = next(c for c in cards if c["ref"] == ref)
    assert assigned["assigned_operator"] == (operator.get_full_name().strip() or operator.get_username())

    unassign = client.post(reverse("api-backstage-order-unassign", args=[ref]), context_payload(client, ref, "unassign"), content_type="application/json")
    assert unassign.status_code == 200
    order.refresh_from_db()
    assert "assignment" not in order.data


# ── Read surface ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_order_detail_returns_projection(client, operator, order):
    client.force_login(operator)
    response = client.get(reverse("api-backstage-order-detail", args=[order.ref]))
    assert response.status_code == 200
    payload = response.json()["order"]
    assert payload["ref"] == order.ref
    assert any(item["sku"] == "SKU" for item in payload["items"])


@pytest.mark.django_db
def test_order_detail_unknown_ref_is_404(client, operator):
    client.force_login(operator)
    assert client.get(reverse("api-backstage-order-detail", args=["NOPE"])).status_code == 404


# ── Write actions ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_advance_confirmed_order(client, operator, order):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-advance", args=[order.ref]), advance_payload(client, order.ref), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["ref"] == order.ref
    assert response.json()["outcome"] == "applied"
    order.refresh_from_db()
    assert order.status == "preparing"


@pytest.mark.django_db
def test_reject_requires_reason(client, operator, order):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-reject", args=[order.ref]))
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_confirm_conflicts_when_order_already_left_new(client, operator, order):
    # `order` já está CONFIRMED (a auto-confirmação venceu a corrida):
    # conflito de estado responde 409, não 400.
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-confirm", args=[order.ref]), data={"expected_actor_id": operator.pk, "base_revision": operational_revision(order), "idempotency_key": "already-confirmed"}, content_type="application/json")
    assert response.status_code == 409
    assert "não está mais aguardando confirmação" in response.json()["detail"]


@pytest.mark.django_db
def test_reject_conflicts_when_order_was_auto_confirmed(client, operator, order):
    """Corrida Recusar × auto-confirmação otimista: o guard reavalia o status na
    linha travada e responde 409 — nunca aplica CONFIRMED→CANCELLED decidindo
    sobre estado velho."""
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-order-reject", args=[order.ref]),
        data={"reason": "Sem estoque", "expected_actor_id": operator.pk, "base_revision": operational_revision(order), "idempotency_key": "reject-auto-confirmed"},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert "não está mais aguardando confirmação" in response.json()["detail"]
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED  # pedido segue intacto


@pytest.mark.django_db
def test_save_notes_persists(client, operator, order):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-order-notes", args=[order.ref]), context_payload(client, order.ref, "notes", notes="Separar"), content_type="application/json")
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Separar"


@pytest.mark.django_db
def test_requeue_fiscal_requeues_failed_directive(client, operator):
    order = _order("ORD-API-FISCAL", fiscal={"issue_document": True})
    directive = Directive.objects.create(
        topic="fiscal.emit_nfce",
        status="failed",
        payload={"order_ref": order.ref},
        last_error="Rejeição",
        error_code="terminal",
    )
    client.force_login(operator)
    from shopman.backstage.services.orders import fiscal_revision

    response = client.post(reverse("api-backstage-order-requeue-fiscal", args=[order.ref]), {"base_revision": fiscal_revision(order), "expected_actor_id": operator.pk, "idempotency_key": "fiscal-requeue"}, content_type="application/json")
    assert response.status_code == 200
    directive.refresh_from_db()
    assert directive.status == "queued"
    assert directive.last_error == ""


@pytest.mark.django_db
def test_settle_delivery_cash_rejects_without_open_shift(client, operator):
    """Endpoint is wired and maps the service guard to a 400 (not a 500)."""
    order = _order(
        "ORD-API-COD",
        status="dispatched",
        fulfillment_type="delivery",
        payment={"method": "cash", "collection": "on_delivery"},
    )
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-order-settle-delivery-cash", args=[order.ref]),
        {"amount": "15,00", "base_revision": cash_settlement_revision(order, None), "expected_actor_id": operator.pk, "idempotency_key": "no-open-shift"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_cancel_endpoint_delivers_operator_reason_to_customer(
    client, operator, django_capture_on_commit_callbacks
):
    """G2: the operator's justification reaches the customer, not a generic notice."""
    order = _order("ORD-API-CANCEL", status="preparing")
    client.force_login(operator)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("api-backstage-order-cancel", args=[order.ref]),
            data={"reason": "Item indisponível no momento", "expected_actor_id": operator.pk, "base_revision": operational_revision(order), "idempotency_key": "cancel-note"},
            content_type="application/json",
        )
    assert response.status_code == 200

    order.refresh_from_db()
    assert order.status == "cancelled"
    assert order.data["cancellation_note"] == "Item indisponível no momento"

    notice = Directive.objects.get(
        topic="notification.send",
        payload__order_ref=order.ref,
        payload__template="order_cancelled",
    )
    assert notice.payload["reason"] == "Item indisponível no momento"


@pytest.mark.django_db
def test_cancel_endpoint_without_reason_stays_generic(
    client, operator, django_capture_on_commit_callbacks
):
    order = _order("ORD-API-CANCEL-GEN", status="preparing")
    client.force_login(operator)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("api-backstage-order-cancel", args=[order.ref]), data={"expected_actor_id": operator.pk, "base_revision": operational_revision(order), "idempotency_key": "cancel-generic"}, content_type="application/json")
    assert response.status_code == 200

    order.refresh_from_db()
    assert "cancellation_note" not in order.data
    notice = Directive.objects.get(
        topic="notification.send",
        payload__order_ref=order.ref,
        payload__template="order_cancelled",
    )
    assert notice.payload.get("reason") is None


@pytest.mark.django_db
def test_advance_requires_intention_and_replays_exact_target(client, operator, order):
    from shopman.backstage.tests._order_intent import advance_payload

    client.force_login(operator)
    url = reverse("api-backstage-order-advance", args=[order.ref])
    assert client.post(url, {}, content_type="application/json").status_code == 400
    body = advance_payload(client, order.ref)
    first = client.post(url, body, content_type="application/json")
    assert first.status_code == 200
    replay = client.post(url, body, content_type="application/json")
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    order.refresh_from_db()
    assert order.status == "preparing"
    assert client.get(url, {"idempotency_key": body["idempotency_key"]}).json()["outcome"] == "applied"
    changed = client.post(url, {**body, "target_status": "ready"}, content_type="application/json")
    assert changed.status_code == 409
    order.refresh_from_db()
    assert order.status == "preparing"


@pytest.mark.django_db
def test_advance_receipt_is_private_and_lookup_does_not_create_it(client, operator, plain_staff, order):
    from shopman.orderman.models import IdempotencyKey

    client.force_login(operator)
    url = reverse("api-backstage-order-advance", args=[order.ref])
    before = IdempotencyKey.objects.count()
    assert client.get(url, {"idempotency_key": "missing"}).status_code == 202
    assert IdempotencyKey.objects.count() == before
    client.force_login(plain_staff)
    assert client.get(url, {"idempotency_key": "missing"}).status_code == 403


@pytest.mark.django_db
def test_context_mutations_merge_independent_fields_and_refuse_stale_note(client, operator, order):
    client.force_login(operator)
    note = context_payload(client, order.ref, "notes", notes="Sem cebola")
    claim = context_payload(client, order.ref, "assign")
    note_url = reverse("api-backstage-order-notes", args=[order.ref])
    assert client.post(note_url, note, content_type="application/json").status_code == 200
    assert client.post(reverse("api-backstage-order-assign", args=[order.ref]), claim, content_type="application/json").status_code == 200
    response = client.post(note_url, {**note, "idempotency_key": "other-intention", "notes": "Sem alho"}, content_type="application/json")
    assert response.status_code == 409
    assert response.json()["order"]["kitchen_note"] == "Sem cebola"
    order.refresh_from_db()
    assert order.data["assignment"]["operator_id"] == operator.pk
    assert order.data["kitchen_note"] == "Sem cebola"
    assert client.post(note_url, note, content_type="application/json").json()["replayed"] is True


@pytest.mark.django_db
def test_advance_receipt_survives_projection_outage(client, operator, order, monkeypatch):
    client.force_login(operator)
    url = reverse("api-backstage-order-advance", args=[order.ref])
    body = advance_payload(client, order.ref)
    assert client.post(url, body, content_type="application/json").status_code == 200

    def unavailable(*args, **kwargs):
        raise RuntimeError("projection unavailable")

    monkeypatch.setattr("shopman.backstage.api.operations.build_operator_order", unavailable)
    receipt = client.get(url, {"idempotency_key": body["idempotency_key"]})
    assert receipt.status_code == 200
    assert receipt.json()["outcome"] == "applied"
    assert receipt.json()["applied"]["status"] == "preparing"
    order.refresh_from_db()
    assert order.status == "preparing"
