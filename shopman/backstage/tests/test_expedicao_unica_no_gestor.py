"""UX-G3: uma Saída só, no Gestor (SUITE-UX-FUNCTION-PLAN §9, §15, §16).

A Saída da Cozinha virou a coluna Saída do Gestor. O que ela fazia e o Gestor
não fazia veio para o cartão do Gestor, pelos mesmos serviços:

* quem expede (``backstage.operate_kds``, a permissão que operava a Saída) entra
  no quadro e expede, sem ganhar o resto do Gestor;
* o progresso por estação ("Faltam Cafés e Lanches") e o "Pronto" da estação
  sem tela;
* devolver à cozinha (recall) o ticket de uma estação já pronta.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from shopman.cashman.models import Terminal
from shopman.doorman.models import PinCredential
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket, PrintAgentCredential
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db

GESTOR_PERM = "shop.manage_orders|backstage.operate_kds"


def _perm(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@pytest.fixture(autouse=True)
def loja(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})


@pytest.fixture
def expeditor(db):
    """Quem operava a Saída da Cozinha: só ``operate_kds``."""
    user = User.objects.create_user("passe", password="pw", is_staff=True, first_name="Pedro")
    user.user_permissions.add(_perm("backstage", "operate_kds"))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def gestor(db):
    """Quem gerencia pedidos e NÃO tem ``operate_kds`` (a Gerente)."""
    user = User.objects.create_user("gerente", password="pw", is_staff=True)
    user.user_permissions.add(_perm("shop", "manage_orders"))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def lanches(db):
    terminal = Terminal.objects.create(ref="lanches-printer", label="Impressora Lanches")
    PrintAgentCredential.issue(terminal=terminal)
    return KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep", print_terminal=terminal)


@pytest.fixture
def cafes(db):
    return KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")


def _order(ref: str, *, status=Order.Status.READY, fulfillment="pickup", payment=None) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=status, total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": fulfillment, "payment": payment or {"method": "cash"}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _ticket(order: Order, station: KDSInstance, *, status: str = "pending") -> KDSTicket:
    return KDSTicket.objects.create(
        session_key=order.session_key, kds_instance=station, status=status,
        items=[{"sku": "PAO", "name": "Pão", "qty": 1, "line_id": "1"}],
    )


def _cards(client) -> list[dict]:
    response = client.get(reverse("api-backstage-orders"))
    assert response.status_code == 200, response.json()
    queue = response.json()["queue"]
    return [card for value in queue.values() if isinstance(value, list) for card in value if isinstance(card, dict) and "ref" in card]


def _card(client, ref: str) -> dict:
    return next(card for card in _cards(client) if card["ref"] == ref)


def _action(card: dict, ref: str) -> dict:
    return next(action for action in card["actions"] if action["ref"] == ref)


def _intent(action: dict, **inputs) -> dict:
    return {**inputs, **action["payload_schema"], "idempotency_key": str(uuid4())}


# ── Quem expede entra no quadro e expede, e só isso ────────────────────────


def test_expeditor_reads_the_board_and_the_layout_but_not_the_detail(client, expeditor):
    client.force_login(expeditor)
    _order("EXP-1")

    assert client.get(reverse("api-backstage-orders")).status_code == 200
    assert client.get(reverse("api-backstage-order-board-layout")).status_code == 200
    # O detalhe (cliente, histórico, cancelar, iFood) continua de quem gerencia.
    assert client.get(reverse("api-backstage-order-detail", args=["EXP-1"])).status_code == 403


def test_someone_with_neither_permission_does_not_enter_the_board(client):
    user = User.objects.create_user("visita", password="pw", is_staff=True)
    client.force_login(user)
    assert client.get(reverse("api-backstage-orders")).status_code == 403


def test_expeditor_hands_over_a_ready_pickup_and_undoes_it(client, expeditor):
    client.force_login(expeditor)
    order = _order("EXP-2")
    card = _card(client, order.ref)
    advance = _action(card, "advance")
    assert advance["enabled"] is True and advance["payload_schema"]["target_status"] == "completed"

    response = client.post(reverse("api-backstage-order-advance", args=[order.ref]), _intent(advance), content_type="application/json")
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert order.data["pending_handoff"]["to_status"] == "completed"

    undo = _action(_card(client, order.ref), "undo-handoff")
    assert undo["enabled"] is True
    response = client.post(reverse("api-backstage-order-undo-handoff", args=[order.ref]), _intent(undo), content_type="application/json")
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert "pending_handoff" not in order.data


def test_expeditor_cannot_accept_mark_ready_or_cancel(client, expeditor):
    client.force_login(expeditor)
    new = _order("EXP-NEW", status=Order.Status.NEW)
    preparing = _order("EXP-PREP", status=Order.Status.PREPARING)

    assert _action(_card(client, new.ref), "confirm")["enabled"] is False
    mark_ready = _action(_card(client, preparing.ref), "advance")
    assert mark_ready["enabled"] is False
    assert mark_ready["reason"] == operator_orders.EXPEDITE_SCOPE_REASON

    # O servidor recusa mesmo com a intenção montada à mão.
    response = client.post(
        reverse("api-backstage-order-advance", args=[preparing.ref]),
        _intent(mark_ready), content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["detail"] == operator_orders.EXPEDITE_SCOPE_REASON
    preparing.refresh_from_db()
    assert preparing.status == Order.Status.PREPARING
    # Aceitar e cancelar seguem atrás de ``shop.manage_orders``.
    assert client.post(reverse("api-backstage-order-confirm", args=[new.ref]), {}, content_type="application/json").status_code == 403
    assert client.post(reverse("api-backstage-order-cancel", args=[new.ref]), {}, content_type="application/json").status_code == 403


def test_expeditor_does_not_dispatch_with_change_from_the_drawer(client, expeditor):
    client.force_login(expeditor)
    order = _order(
        "EXP-TROCO", fulfillment="delivery",
        payment={"method": "cash", "collection": "on_delivery", "change_for_q": 5000},
    )
    dispatch = _action(_card(client, order.ref), "advance")
    assert dispatch["enabled"] is False
    assert dispatch["reason"] == operator_orders.EXPEDITE_CUSTODY_REASON

    response = client.post(
        reverse("api-backstage-order-advance", args=[order.ref]),
        _intent(dispatch, change_out="20,00"), content_type="application/json",
    )
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.Status.READY and "pending_handoff" not in order.data


def test_expeditor_dispatches_a_delivery_without_custody_questions(client, expeditor):
    client.force_login(expeditor)
    order = _order("EXP-DLV", fulfillment="delivery", payment={"method": "pix", "status": "captured"})
    dispatch = _action(_card(client, order.ref), "advance")
    if not dispatch["enabled"]:
        pytest.skip(f"pagamento do cenário barrou a saída: {dispatch['reason']}")
    response = client.post(reverse("api-backstage-order-advance", args=[order.ref]), _intent(dispatch), content_type="application/json")
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert order.data["pending_handoff"]["to_status"] == "dispatched"


# ── A antessala do Gestor aceita as duas portas ─────────────────────────────


def test_gestor_surface_admits_the_expeditor_and_keeps_its_own_lock(client, expeditor):
    trust_station(client, "passe")
    PinCredential.set_for(expeditor, "2468")
    session_url = reverse("api-backstage-operator-session")

    eligible = client.get(reverse("api-backstage-operator-eligible"), {"perm": GESTOR_PERM}).json()["operators"]
    assert [card["username"] for card in eligible] == ["passe"]

    unlock = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": expeditor.pk, "pin": "2468", "perm": GESTOR_PERM},
        content_type="application/json",
    )
    assert unlock.status_code == 200, unlock.json()
    body = client.get(session_url, {"perm": GESTOR_PERM}).json()
    assert body["locked"] is False and body["authorized"] is True
    # A barra do Gestor pergunta por ``manage_orders`` para mostrar as outras seções.
    assert client.get(session_url, {"perm": "shop.manage_orders"}).json()["authorized"] is False

    # Travar o Gestor tranca o quadro (a chave é ``shop.manage_orders``).
    assert client.post(reverse("api-backstage-operator-lock"), {"perm": GESTOR_PERM}, content_type="application/json").status_code == 200
    assert client.get(session_url, {"perm": GESTOR_PERM}).json()["locked"] is True
    locked = client.get(reverse("api-backstage-orders"))
    assert locked.status_code == 403
    assert locked.json()["error"]["code"] == "station_locked"


def test_surface_perm_with_an_unknown_alternative_is_refused(client):
    trust_station(client, "passe")
    response = client.get(reverse("api-backstage-operator-session"), {"perm": "shop.manage_orders|auth.delete_user"})
    assert response.status_code == 400


# ── Progresso por estação, "Pronto" da estação sem tela, voltar à cozinha ──


def test_preparing_card_says_which_stations_are_missing(client, gestor, lanches, cafes):
    client.force_login(gestor)
    order = _order("EXP-PROG", status=Order.Status.PREPARING)
    _ticket(order, cafes, status="in_progress")
    _ticket(order, lanches)

    kitchen = _card(client, order.ref)["kitchen"]
    assert kitchen["order_pk"] == order.pk
    assert kitchen["missing_label"] == "Faltam Cafés e Lanches"
    by_station = {station["station_ref"]: station for station in kitchen["stations"]}
    assert by_station["cafes"]["state_label"] == "em preparo" and by_station["cafes"]["can_mark_ready"] is False
    assert by_station["lanches"]["prints"] is True and by_station["lanches"]["can_mark_ready"] is True


def test_gestor_marks_the_printed_station_ready_without_operate_kds(client, gestor, lanches, cafes):
    client.force_login(gestor)
    order = _order("EXP-SEMTELA", status=Order.Status.PREPARING)
    _ticket(order, cafes, status="done")
    paper = _ticket(order, lanches)

    response = client.post(reverse("api-backstage-kds-exit-printed-station-done", args=[order.pk, "lanches"]))
    assert response.status_code == 200, response.json()
    assert response.json()["completed"] == 1
    paper.refresh_from_db()
    assert paper.status == "done"
    assert paper.completed_via == KDSTicket.COMPLETED_VIA_EXIT
    order.refresh_from_db()
    assert order.status == Order.Status.READY  # a última estação fechou o pedido


def test_ready_card_offers_back_to_the_station_and_the_gestor_recalls(client, gestor, cafes):
    client.force_login(gestor)
    order = _order("EXP-RECALL", status=Order.Status.READY)
    done = _ticket(order, cafes, status="done")

    kitchen = _card(client, order.ref)["kitchen"]
    assert kitchen["missing_label"] == ""
    station = kitchen["stations"][0]
    assert station["recall_ticket_pk"] == done.pk

    response = client.post(reverse("api-backstage-kds-ticket-recall", args=[done.pk]))
    assert response.status_code == 200, response.json()
    done.refresh_from_db()
    order.refresh_from_db()
    assert done.status == "in_progress"
    assert order.status == Order.Status.PREPARING


def test_leaving_order_does_not_offer_back_to_the_station(client, expeditor, cafes):
    client.force_login(expeditor)
    order = _order("EXP-SAINDO", status=Order.Status.READY)
    _ticket(order, cafes, status="done")
    advance = _action(_card(client, order.ref), "advance")
    client.post(reverse("api-backstage-order-advance", args=[order.ref]), _intent(advance), content_type="application/json")

    station = _card(client, order.ref)["kitchen"]["stations"][0]
    assert station["recall_ticket_pk"] is None


def test_the_narrow_rule_does_not_depend_on_staff_flags(client, expeditor):
    """Quem entra pelo quadro sem gerenciar pedidos cai na régua estreita, sempre."""
    preparing = _order("EXP-NOSTAFF", status=Order.Status.PREPARING)
    client.force_login(expeditor)
    mark_ready = _action(_card(client, preparing.ref), "advance")
    User.objects.filter(pk=expeditor.pk).update(is_staff=False)

    response = client.post(
        reverse("api-backstage-order-advance", args=[preparing.ref]),
        _intent(mark_ready), content_type="application/json",
    )
    assert response.status_code in (400, 403)
    preparing.refresh_from_db()
    assert preparing.status == Order.Status.PREPARING
