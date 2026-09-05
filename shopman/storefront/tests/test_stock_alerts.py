"""WP-3 — "Me avise quando disponível" (stock-back alerts).

Cobre: subscribe (anônimo/dedup/sem contato), notify idempotente (dispara só
quando disponível, marca uma vez, não marca em falha de envio) e o endpoint.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from shopman.offerman.models import Product

from shopman.storefront.models import StockAlertSubscription
from shopman.storefront.services import stock_alerts

pytestmark = pytest.mark.django_db

PHONE = "+5543999990001"


def _state(can_add: bool, available_qty: int | None = None):
    return MagicMock(can_add_to_cart=can_add, available_qty=available_qty)


def _publish(sku="SKU-NOTIFY", *, is_batch_produced=False):
    return Product.objects.create(
        sku=sku, name="Pão Teste", base_price_q=500,
        is_published=True, is_sellable=True, is_batch_produced=is_batch_produced,
    )


def _move(sku: str, *, kind: str = "buy"):
    """Um ``Move`` de mentira, com o ``kind`` que o receptor lê para decidir a rede."""
    fake = MagicMock(quant_id=1, kind=kind)
    fake.quant.sku = sku
    return fake


# ── subscribe ───────────────────────────────────────────────────────


def test_subscribe_anonymous_creates_pending():
    sub = stock_alerts.subscribe("SKU-1", channel_ref="web", phone=PHONE)
    assert sub is not None
    assert sub.is_pending
    assert sub.contact_phone == PHONE


def test_subscribe_dedupes_pending_for_same_contact():
    a = stock_alerts.subscribe("SKU-1", phone=PHONE)
    b = stock_alerts.subscribe("SKU-1", phone=PHONE)
    assert a.pk == b.pk
    assert StockAlertSubscription.objects.filter(sku="SKU-1").count() == 1


def test_subscribe_requires_a_contact():
    assert stock_alerts.subscribe("SKU-1") is None


# ── notify ──────────────────────────────────────────────────────────


def test_notify_sends_and_marks_when_available():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 1
    nf.assert_called_once()
    assert nf.call_args.kwargs["event"] == "stock_arrived"
    assert nf.call_args.kwargs["recipient"] == PHONE
    sub.refresh_from_db()
    assert sub.notified_at is not None


def test_notify_context_includes_truthful_availability_phrase():
    stock_alerts.subscribe("SKU-1", phone=PHONE, alert_type="production_ready")
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, available_qty=12)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_bake_ready("SKU-1")

    assert notified == 1
    assert nf.call_args.kwargs["event"] == "production_ready"
    context = nf.call_args.kwargs["context"]
    assert context["available_qty"] == "12"
    assert context["availability_phrase"] == "Neste momento ainda temos 12 unidades."


def test_notify_context_uses_neutral_phrase_when_quantity_is_unknown():
    stock_alerts.subscribe("SKU-1", phone=PHONE, alert_type="production_ready")
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_bake_ready("SKU-1")

    assert notified == 1
    context = nf.call_args.kwargs["context"]
    assert context["available_qty"] == ""
    assert context["availability_phrase"] == "Já está disponível para pedido."


def test_availability_phrase_uses_singular_for_one_unit():
    from shopman.shop.services.availability_copy import availability_phrase

    assert availability_phrase(1) == "Neste momento ainda temos 1 unidade."


def test_notify_skips_when_still_unavailable():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(False)),
        patch("shopman.shop.notifications.notify") as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 0
    nf.assert_not_called()
    sub.refresh_from_db()
    assert sub.notified_at is None


def test_notify_is_idempotent_once_notified():
    stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)),
    ):
        stock_alerts.notify_back_in_stock("SKU-1")
        again = stock_alerts.notify_back_in_stock("SKU-1")

    assert again == 0


def test_notify_does_not_mark_on_send_failure():
    sub = stock_alerts.subscribe("SKU-1", phone=PHONE)
    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=False)),
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-1")

    assert notified == 0
    sub.refresh_from_db()
    assert sub.notified_at is None  # mantém pendente p/ retry na próxima chegada


# ── endpoint ────────────────────────────────────────────────────────


def test_endpoint_anonymous_subscribes(client):
    p = _publish()
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {"phone": PHONE})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert StockAlertSubscription.objects.filter(sku=p.sku, notified_at__isnull=True).exists()


def test_endpoint_repairs_legacy_mobile_and_persists_pending_session_marker(client):
    p = _publish(sku="SKU-LEGACY-PHONE")
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {"phone": "(43) 9840-4900"})
    assert resp.status_code == 200
    sub = StockAlertSubscription.objects.get(sku=p.sku)
    assert sub.contact_phone == "+5543998404900"
    assert client.session.get("stock_alert_subscriptions") == [
        {
            "sku": p.sku,
            "alert_type": StockAlertSubscription.AlertType.STOCK_BACK,
            "contact_phone": "+5543998404900",
        }
    ]
    assert "stock_alert_skus" not in client.session


def test_endpoint_requires_phone_when_anonymous(client):
    p = _publish()
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {})
    assert resp.status_code == 400


def test_endpoint_404_for_unknown_sku(client):
    resp = client.post("/api/v1/availability/NOPE/notify/", {"phone": PHONE})
    assert resp.status_code == 404


def test_anonymous_session_marker_only_counts_while_subscription_is_pending(rf):
    from django.contrib.sessions.middleware import SessionMiddleware

    from shopman.storefront.presentation.catalog import notify_subscribed_skus

    sub = stock_alerts.subscribe("SKU-PENDING-MARK", phone=PHONE)
    request = rf.get("/")
    SessionMiddleware(lambda request: None).process_request(request)
    request.session["stock_alert_skus"] = ["SKU-LEGACY-MARK"]
    request.session["stock_alert_subscriptions"] = [
        {
            "sku": "SKU-PENDING-MARK",
            "alert_type": StockAlertSubscription.AlertType.STOCK_BACK,
            "contact_phone": PHONE,
        }
    ]

    assert notify_subscribed_skus(request) == {"SKU-PENDING-MARK"}

    sub.notified_at = timezone.now()
    sub.save(update_fields=["notified_at"])

    assert notify_subscribed_skus(request) == set()


# ── trigger (Move receiver) ─────────────────────────────────────────


def test_move_receiver_schedules_notify_for_pending_sku():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-MOVE", phone=PHONE)
    fake = _move("SKU-MOVE", kind="buy")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=fake)
    nb.assert_called_once_with("SKU-MOVE", also_bake_waiters=True)


def test_move_receiver_skips_when_no_pending_subscription():
    from shopman.storefront import handlers

    fake = _move("SKU-NO-WAITERS")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_back_in_stock") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=fake)
    nb.assert_not_called()


# ── trigger (fornada) ───────────────────────────────────────────────


def test_bake_receiver_notifies_production_ready_subscribers():
    """"Me avise quando sair do forno" dispara na fornada, não na reposição."""
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_bake_ready") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="finished", work_order=None
        )
    nb.assert_called_once_with("SKU-BAKE")


def test_bake_receiver_ignores_other_production_actions():
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE, alert_type="production_ready")
    with (
        patch("shopman.storefront.services.stock_alerts.notify_bake_ready") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="started", work_order=None
        )
    nb.assert_not_called()


def test_stock_back_subscriber_is_not_woken_by_a_bake():
    """Os dois gatilhos são independentes: quem espera reposição não recebe fornada."""
    from shopman.storefront import handlers

    stock_alerts.subscribe("SKU-BAKE", phone=PHONE)  # stock_back (default)
    with (
        patch("shopman.storefront.services.stock_alerts.notify_bake_ready") as nb,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="SKU-BAKE", date=None, action="finished", work_order=None
        )
    nb.assert_not_called()


def test_both_alert_types_coexist_for_the_same_shopper():
    back = stock_alerts.subscribe("SKU-BOTH", phone=PHONE)
    bake = stock_alerts.subscribe("SKU-BOTH", phone=PHONE, alert_type="production_ready")
    assert back.pk != bake.pk
    assert bake.alert_type == "production_ready"


def test_endpoint_accepts_the_bake_alert_type(client):
    p = _publish(sku="SKU-BAKE-API")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"phone": PHONE, "alert_type": "production_ready"},
    )
    assert resp.status_code == 200
    sub = StockAlertSubscription.objects.get(sku=p.sku)
    assert sub.alert_type == "production_ready"


def test_endpoint_rejects_an_unknown_alert_type(client):
    p = _publish(sku="SKU-BAD-TYPE")
    resp = client.post(
        f"/api/v1/availability/{p.sku}/notify/",
        {"phone": PHONE, "alert_type": "telepatia"},
    )
    assert resp.status_code == 400
    assert resp.json()["field"] == "alert_type"


# ── o eixo do aviso: quem decide é o servidor ────────────────────────


def test_bread_subscribes_to_the_oven_not_to_the_shelf():
    """O caso do Pablo: o sino de um pão entra na fila da FORNADA.

    A loja manda só o telefone. Antes, sem ``alert_type`` no corpo, todo mundo
    caía em ``stock_back`` e a fila de fornada nascia vazia para sempre.
    """
    _publish(sku="BF", is_batch_produced=True)
    sub = stock_alerts.subscribe("BF", phone=PHONE)
    assert sub.alert_type == StockAlertSubscription.AlertType.PRODUCTION_READY


def test_shelf_item_subscribes_to_the_shelf():
    _publish(sku="AG")  # água: chega por recebimento, não sai do forno
    sub = stock_alerts.subscribe("AG", phone=PHONE)
    assert sub.alert_type == StockAlertSubscription.AlertType.STOCK_BACK


def test_an_active_recipe_is_enough_to_make_it_an_oven_item():
    """A flag do gestor não é preenchida na prática; a receita ativa é a prova.

    No banco vivo do alpha (05/09/2026) todo produto tem ``is_batch_produced``
    em ``False``, pães inclusive. Derivar só pela flag entregaria uma correção
    que nunca dispara.
    """
    from decimal import Decimal

    from shopman.craftsman.models import Recipe

    _publish(sku="CI")
    Recipe.objects.create(
        ref="ciabatta", name="Ciabatta", output_sku="CI",
        batch_size=Decimal("10"), is_active=True,
    )
    assert stock_alerts.subscribe("CI", phone=PHONE).alert_type == "production_ready"


def test_unknown_sku_falls_back_to_the_shelf():
    """Na dúvida, prateleira: é o eixo com mais caminhos de chegada."""
    assert stock_alerts.subscribe("SKU-GHOST", phone=PHONE).alert_type == "stock_back"


def test_explicit_alert_type_still_wins():
    _publish(sku="BF-EXPLICIT", is_batch_produced=True)
    sub = stock_alerts.subscribe("BF-EXPLICIT", phone=PHONE, alert_type="stock_back")
    assert sub.alert_type == "stock_back"


def test_endpoint_derives_the_oven_axis_without_the_front_asking(client):
    """A tela continua dizendo só "avise-me sobre este produto"."""
    p = _publish(sku="BF-API", is_batch_produced=True)
    resp = client.post(f"/api/v1/availability/{p.sku}/notify/", {"phone": PHONE})
    assert resp.status_code == 200
    assert StockAlertSubscription.objects.get(sku=p.sku).alert_type == "production_ready"
    assert client.session["stock_alert_subscriptions"][0]["alert_type"] == "production_ready"


# ── uma fornada, UMA mensagem ────────────────────────────────────────


def test_a_bake_does_not_send_twice_to_the_same_person():
    """A fornada acorda os DOIS receptores; só um pode falar.

    O ``finish`` escreve o ledger (``kind=make``), então nasce um ``Move`` no
    mesmo instante em que ``production_changed`` dispara. Com o eixo certo, o
    receptor de estoque não acha ``stock_back`` pendente e se cala.
    """
    from shopman.storefront import handlers

    _publish(sku="BF-BAKE", is_batch_produced=True)
    stock_alerts.subscribe("BF-BAKE", phone=PHONE)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 6)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("BF-BAKE", kind="make"))
        handlers.on_production_finished_for_stock_alerts(
            sender=None, product_ref="BF-BAKE", date=None, action="finished", work_order=None,
        )

    assert nf.call_count == 1
    assert nf.call_args.kwargs["event"] == "production_ready"


def test_a_production_move_never_serves_the_oven_queue():
    """A rede de segurança fica DESLIGADA na produção.

    Ligada ali, o ``Move`` chegaria primeiro (os dois ``on_commit`` correm em
    ordem de registro) e o "saiu do forno" viraria "chegou ao estoque" — a
    mensagem certa trocada pela errada, sem ninguém perceber.
    """
    from shopman.storefront import handlers

    _publish(sku="BF-MAKE", is_batch_produced=True)
    stock_alerts.subscribe("BF-MAKE", phone=PHONE)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("BF-MAKE", kind="make"))

    nf.assert_not_called()
    assert StockAlertSubscription.objects.get(sku="BF-MAKE").is_pending


def test_one_person_two_subscriptions_gets_one_message():
    """Contato legado com os dois eixos (o que o concierge fazia) recebe UMA vez."""
    stock_alerts.subscribe("SKU-LEGACY-BOTH", phone=PHONE, alert_type="stock_back")
    stock_alerts.subscribe("SKU-LEGACY-BOTH", phone=PHONE, alert_type="production_ready")

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
    ):
        notified = stock_alerts.notify_back_in_stock("SKU-LEGACY-BOTH", also_bake_waiters=True)

    assert notified == 1
    assert nf.call_count == 1
    assert StockAlertSubscription.objects.filter(
        sku="SKU-LEGACY-BOTH", notified_at__isnull=True
    ).count() == 0


# ── rede de segurança: estoque que chega por fora da produção ────────


def test_a_non_production_arrival_serves_the_oven_queue_with_arrival_copy():
    """Pão que volta por recebimento/ajuste não pode deixar a fila muda.

    Sem isto, quem assinou ``production_ready`` ficaria calado para sempre
    quando o estoque voltasse por um caminho que não é fornada. A copy é a da
    CHEGADA: nada saiu do forno, e mentir sobre isso é pior que o silêncio.
    """
    from shopman.storefront import handlers

    _publish(sku="BF-RECEBIDO", is_batch_produced=True)
    stock_alerts.subscribe("BF-RECEBIDO", phone=PHONE)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_state(True, 3)),
        patch("shopman.shop.notifications.notify", return_value=MagicMock(success=True)) as nf,
        patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()),
    ):
        handlers.on_move_for_stock_alerts(sender=None, instance=_move("BF-RECEBIDO", kind="adjust"))

    assert nf.call_count == 1
    assert nf.call_args.kwargs["event"] == "stock_arrived"
    assert StockAlertSubscription.objects.get(sku="BF-RECEBIDO").notified_at is not None
