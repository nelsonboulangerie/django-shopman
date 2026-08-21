"""SSE channel permission tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from shopman.doorman.models import CustomerUser
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.eventstream import ShopmanChannelManager

pytestmark = pytest.mark.django_db


def test_stock_channels_remain_public():
    manager = ShopmanChannelManager()

    assert manager.can_read_channel(None, "stock-web") is True


def test_stock_channels_are_ephemeral_invalidations():
    manager = ShopmanChannelManager()

    assert manager.is_channel_reliable("stock-web") is False
    assert manager.is_channel_reliable("order-ORD-1") is True
    assert manager.is_channel_reliable("backstage-orders-main") is True


# ── Canais de operador: a permissão da TELA, não só o crachá de staff ──────
#
# ⚠️ O teste antigo afirmava "staff lê / anônimo não lê" — verdade, e insuficiente:
# ele nunca perguntou se um staff SEM a permissão da tela também lia. Lia. Era o
# gate mais frouxo do sistema (prefixo + ``is_staff``), enquanto o endpoint
# equivalente exigia permissão nominal. Os testes abaixo perguntam a pergunta que
# faltava, canal por canal.


def _grant(user, app_label: str, model: str, codename: str) -> User:
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    ct, _ = ContentType.objects.get_or_create(app_label=app_label, model=model)
    perm, _ = Permission.objects.get_or_create(content_type=ct, codename=codename)
    user.user_permissions.add(perm)
    # `has_perm` memoiza no objeto; recarregar é o que faz o grant valer aqui.
    return User.objects.get(pk=user.pk)


def test_backstage_channels_reject_anonymous_and_non_staff():
    manager = ShopmanChannelManager()
    customer_user = User.objects.create_user(username="customer")

    assert manager.can_read_channel(None, "backstage-orders-main") is False
    assert manager.can_read_channel(customer_user, "backstage-orders-main") is False


def test_staff_without_the_screen_permission_cannot_read_the_channel():
    """Crachá de staff não abre canal: cada um exige a permissão da sua tela."""
    manager = ShopmanChannelManager()
    staff = User.objects.create_user(username="staff-sem-nada", is_staff=True)

    assert manager.can_read_channel(staff, "backstage-orders-main") is False
    assert manager.can_read_channel(staff, "backstage-kds-main") is False
    assert manager.can_read_channel(staff, "backstage-production-main") is False
    assert manager.can_read_channel(staff, "backstage-alerts-main") is False


def test_kitchen_operator_reads_kds_and_production_but_not_the_cash_alerts():
    """O vazamento que existia: ``diofer`` da cozinha assinando ``alerts``.

    O canal ``alerts`` carrega o pedido de troco do balcão com ``amount_q``,
    ``denominations``, terminal e quem pediu. A cozinha (Grupo "Cozinha":
    ``operate_kds`` + ``operate_production``) não opera caixa, e não vê mais.
    """
    manager = ShopmanChannelManager()
    cozinha = User.objects.create_user(username="diofer", is_staff=True)
    cozinha = _grant(cozinha, "backstage", "kdsticket", "operate_kds")
    cozinha = _grant(cozinha, "backstage", "dayclosing", "operate_production")

    assert manager.can_read_channel(cozinha, "backstage-kds-main") is True
    assert manager.can_read_channel(cozinha, "backstage-kds-bancada") is True
    assert manager.can_read_channel(cozinha, "backstage-production-main") is True
    # O painel de retirada do KDS consome o mesmo /sse/orders — ref + status.
    assert manager.can_read_channel(cozinha, "backstage-orders-main") is True
    # Dinheiro, não.
    assert manager.can_read_channel(cozinha, "backstage-alerts-main") is False


def test_counter_operator_reads_cash_alerts_and_orders_but_not_the_kitchen():
    """Grupo "Caixa": ``operate_pos`` + ``manage_orders``, e nada de cozinha."""
    manager = ShopmanChannelManager()
    caixa = User.objects.create_user(username="marina", is_staff=True)
    caixa = _grant(caixa, "cashman", "shift", "operate_pos")
    caixa = _grant(caixa, "shop", "shop", "manage_orders")

    assert manager.can_read_channel(caixa, "backstage-alerts-main") is True
    assert manager.can_read_channel(caixa, "backstage-orders-main") is True
    assert manager.can_read_channel(caixa, "backstage-kds-main") is False
    assert manager.can_read_channel(caixa, "backstage-production-main") is False


def test_superuser_reads_every_mapped_channel():
    manager = ShopmanChannelManager()
    dono = User.objects.create_superuser(username="dono", email="dono@example.invalid", password="x")

    for kind in ("orders", "kds", "production", "alerts"):
        assert manager.can_read_channel(dono, f"backstage-{kind}-main") is True, kind


def test_unknown_backstage_kind_is_denied_even_for_the_superuser():
    """A regra que impede o PRÓXIMO canal de nascer aberto.

    Enquanto o gate era prefixo + staff, qualquer ``backstage-<coisa-nova>-*``
    nascia legível para todo staff sem ninguém decidir nada. Agora um ``kind``
    fora do mapa é negado — inclusive para o dono, para que a falta de decisão
    apareça como canal mudo em vez de virar vazamento silencioso.
    """
    manager = ShopmanChannelManager()
    dono = User.objects.create_superuser(username="dona", email="dona@example.invalid", password="x")
    staff = User.objects.create_user(username="staff-tudo", is_staff=True)
    staff = _grant(staff, "cashman", "shift", "operate_pos")

    assert manager.can_read_channel(dono, "backstage-cash-main") is False
    assert manager.can_read_channel(dono, "backstage-bi-main") is False
    assert manager.can_read_channel(staff, "backstage-cash-main") is False


def test_order_channels_require_matching_customer_or_staff():
    manager = ShopmanChannelManager()
    customer = Customer.objects.create(
        ref="CUST-SSE-001",
        first_name="Ana",
        phone="5543999990001",
    )
    matching_user = User.objects.create_user(username="ana")
    other_user = User.objects.create_user(username="other")
    staff = User.objects.create_user(username="ops", is_staff=True)
    CustomerUser.objects.create(user=matching_user, customer_id=customer.uuid)
    order = Order.objects.create(
        ref="ORD-SSE-001",
        channel_ref="web",
        status="new",
        total_q=1000,
        handle_type="phone",
        handle_ref=customer.phone,
        data={"customer_ref": customer.ref},
    )

    assert manager.can_read_channel(None, f"order-{order.ref}") is False
    assert manager.can_read_channel(other_user, f"order-{order.ref}") is False
    assert manager.can_read_channel(matching_user, f"order-{order.ref}") is True
    assert manager.can_read_channel(staff, f"order-{order.ref}") is True


def test_order_channels_accept_session_scoped_event_user():
    manager = ShopmanChannelManager()
    order = Order.objects.create(
        ref="ORD-SSE-SESSION-001",
        channel_ref="web",
        status="new",
        total_q=1000,
        handle_type="phone",
        handle_ref="5543999990001",
    )
    event_user = SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        is_superuser=False,
        pk="order-session:test",
        _shopman_order_sse_refs=frozenset({order.ref}),
    )
    other_event_user = SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        is_superuser=False,
        pk="order-session:other",
        _shopman_order_sse_refs=frozenset({"OTHER-ORDER"}),
    )

    assert manager.can_read_channel(event_user, f"order-{order.ref}") is True
    assert manager.can_read_channel(other_event_user, f"order-{order.ref}") is False


def test_the_gate_under_test_is_the_gate_django_eventstream_uses():
    """Sem esta costura, todo o resto acima poderia estar testando um objeto
    que ninguém instancia em produção: as regras só valem porque o
    ``EVENTSTREAM_CHANNELMANAGER_CLASS`` aponta para esta classe."""
    from django_eventstream.utils import get_channelmanager

    assert isinstance(get_channelmanager(), ShopmanChannelManager)


def test_channel_permissions_mirror_the_views_that_serve_the_same_data():
    """O canal não pode virar uma segunda régua, mais frouxa que a da tela.

    Foi essa divergência que abriu o vazamento: a view exigia permissão nominal,
    o canal exigia só ``is_staff``. Aqui as duas são comparadas peça a peça —
    se alguém trocar o ``required_permission`` de uma tela e esquecer o canal,
    isto reprova.
    """
    from shopman.backstage.api.kds import KDSBoardView
    from shopman.backstage.api.operations import (
        OrderQueueView,
        POSView,
        ProductionBoardView,
    )
    from shopman.shop.eventstream import _BACKSTAGE_CHANNEL_RULES as rules

    assert OrderQueueView.required_permission in rules["orders"]
    assert KDSBoardView.required_permission in rules["kds"]
    assert ProductionBoardView.required_permission in rules["production"]
    # `alerts` é o caso deliberadamente MAIS restrito que o endpoint homônimo:
    # o canal carrega o pedido de troco (valor + cédulas), então vale a régua do
    # caixa, a mesma do PDV. Ver o comentário do mapa em eventstream.py.
    assert POSView.required_permission in rules["alerts"]
