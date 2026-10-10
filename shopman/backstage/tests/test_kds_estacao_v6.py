"""A estação da Cozinha conforme a v4 (frente V6-KDS-HUB).

- D02: o card não mostra canal, telefone nem cliente; só a encomenda leva o nome.
- D03: "iniciado por Rafael às 21:56 · retira às 22:30" no card (nome de chamada, não o login).
- D12: o "Visto" fica no servidor, por estação: as duas telas da estação param juntas.
- D13: o pedido novo chega ao bolso de quem segue a estação; o atraso, à gerente.
- D14: densidade e som saem da estação provisionada (o cadastro), não do toque.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board, build_kds_index
from shopman.shop.directives import KDS_TICKET_LATE
from shopman.shop.handlers.kds_alerts import KDSTicketLateHandler
from shopman.shop.models import NotificationLifecycle, Shop, UserNotification
from shopman.shop.services import kds as kds_core
from shopman.shop.services import kds_alerts

pytestmark = pytest.mark.django_db


def _perm(model, codename: str) -> Permission:
    return Permission.objects.get(content_type=ContentType.objects.get_for_model(model), codename=codename)


@pytest.fixture
def forno(db):
    Shop.objects.get_or_create(name="Nelson Boulangerie")
    return KDSInstance.objects.create(ref="forno", name="Forno", type="prep", target_time_minutes=10)


@pytest.fixture
def cozinheiro(db):
    user = User.objects.create_user("rafael.s", password="pw", first_name="Rafael Souza", is_staff=True)
    user.user_permissions.add(_perm(KDSTicket, "operate_kds"))
    return user


def _order(ref: str, *, data: dict | None = None, created_days_ago: int = 0) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=Order.Status.PREPARING,
        total_q=1500,
        data={"customer": {"name": "+5543993333333"}, "fulfillment_type": "pickup", **(data or {})},
    )
    if created_days_ago:
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=created_days_ago))
        order.refresh_from_db()
    return order


def _ticket(order: Order, station: KDSInstance, **fields) -> KDSTicket:
    return KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        items=[{"sku": "PAO", "name": "Pão de Hambúrguer", "qty": 3, "line_id": "L1"}],
        **fields,
    )


# ── D02 · D03 ─────────────────────────────────────────────────────────────


def test_venda_do_dia_nao_e_encomenda_e_a_encomenda_diz_a_hora(forno):
    hoje = _order("WEB-1-S84")
    _ticket(hoje, forno)
    encomenda = _order(
        "POS-1-B52",
        data={
            "customer": {"name": "Café Parisiense"},
            "delivery_date": timezone.localdate().isoformat(),
            "delivery_time": "22:30",
        },
        created_days_ago=2,
    )
    _ticket(encomenda, forno)

    cards = {card.order_ref: card for card in build_kds_board(forno.ref).tickets}

    assert cards["WEB-1-S84"].is_preorder is False
    assert cards["WEB-1-S84"].due_time_display == ""
    assert cards["POS-1-B52"].is_preorder is True
    assert cards["POS-1-B52"].customer_name == "Café Parisiense"
    assert cards["POS-1-B52"].due_time_display == "retira às 22:30"


def test_iniciado_por_diz_o_nome_de_chamada_e_a_hora(forno, cozinheiro):
    order = _order("WEB-1-B53")
    ticket = _ticket(order, forno)
    kds_core.start_ticket(ticket, actor=cozinheiro.username)

    card = build_kds_board(forno.ref).tickets[0]

    assert card.started_by == "Rafael"
    assert card.started_at_display


# ── D12 · Visto da estação ──────────────────────────────────────────────


def test_visto_fica_no_servidor_e_vale_para_a_estacao_inteira(client, forno, cozinheiro):
    order = _order("WEB-1-U13")
    novo = _ticket(order, forno)
    outra = KDSInstance.objects.create(ref="cafe", name="Café", type="prep")
    alheio = _ticket(_order("WEB-1-K21"), outra)
    assert build_kds_board(forno.ref).tickets[0].seen is False

    client.force_login(cozinheiro)
    response = client.post(
        reverse("api-backstage-kds-station-seen", args=[forno.ref]),
        {"ticket_pks": [novo.pk, alheio.pk]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["seen"] == 1  # só o ticket desta estação
    novo.refresh_from_db()
    alheio.refresh_from_db()
    assert (novo.seen_by, alheio.seen_at) == (cozinheiro.username, None)
    # Outra tela da mesma estação lê o mesmo quadro: o aviso parou nela também.
    assert build_kds_board(forno.ref).tickets[0].seen is True


def test_cancelamento_depois_do_visto_volta_a_pedir_atencao(client, forno, cozinheiro):
    order = _order("WEB-1-F22")
    ticket = _ticket(order, forno, seen_at=timezone.now() - timedelta(minutes=2))
    ticket.status = "cancelled"
    ticket.cancelled_at = timezone.now()
    ticket.save(update_fields=["status", "cancelled_at"])

    assert build_kds_board(forno.ref).cancelled_tickets[0].seen is False

    client.force_login(cozinheiro)
    client.post(
        reverse("api-backstage-kds-station-seen", args=[forno.ref]),
        {"ticket_pks": [ticket.pk]},
        content_type="application/json",
    )
    assert build_kds_board(forno.ref).cancelled_tickets[0].seen is True


def test_iniciar_tambem_e_ver(forno, cozinheiro):
    ticket = _ticket(_order("WEB-1-X36"), forno)
    kds_core.start_ticket(ticket, actor=cozinheiro.username)

    assert build_kds_board(forno.ref).tickets[0].seen is True


def test_visto_exige_a_lista_e_a_permissao(client, forno, cozinheiro):
    url = reverse("api-backstage-kds-station-seen", args=[forno.ref])
    bare = User.objects.create_user("sem-kds", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.post(url, {"ticket_pks": []}, content_type="application/json").status_code == 403
    client.force_login(cozinheiro)
    response = client.post(url, {"ticket_pks": "1"}, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["field"] == "ticket_pks"


# ── D14 · Densidade e som da estação ────────────────────────────────────


def test_densidade_e_som_saem_do_cadastro_da_estacao(client, forno, cozinheiro):
    board = build_kds_board(forno.ref)
    assert (board.density, board.sound_enabled) == ("cozy", True)

    client.force_login(cozinheiro)
    response = client.patch(
        reverse("api-backstage-kds-station-settings", args=[forno.ref]),
        {"density": "roomy", "sound_enabled": False},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"density": "roomy", "sound_enabled": False}
    forno.refresh_from_db()
    assert forno.config["density"] == "roomy"
    board = build_kds_board(forno.ref)
    assert (board.density, board.sound_enabled) == ("roomy", False)


def test_densidade_estranha_e_recusada(client, forno, cozinheiro):
    client.force_login(cozinheiro)
    response = client.patch(
        reverse("api-backstage-kds-station-settings", args=[forno.ref]),
        {"density": "gigante"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["field"] == "density"


# ── D13 · Avisos no bolso ───────────────────────────────────────────────


def test_quem_segue_a_estacao_recebe_o_pedido_novo_e_o_aviso_some_ao_iniciar(
    client, forno, cozinheiro, django_capture_on_commit_callbacks
):
    client.force_login(cozinheiro)
    assert client.post(reverse("api-backstage-kds-station-follow", args=[forno.ref])).status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        ticket = _ticket(_order("WEB-1-W07"), forno)

    aviso = UserNotification.objects.get(user=cozinheiro, source_condition=kds_alerts.KDS_TICKET_NEW)
    assert aviso.title == "Pedido novo W07"
    assert aviso.category == "kitchen"
    assert aviso.action_url == f"/{forno.ref}"
    # O despertador do atraso fica armado na meta da estação.
    late = Directive.objects.get(topic=KDS_TICKET_LATE, payload__ticket_pk=ticket.pk)
    assert late.available_at == ticket.created_at + timedelta(minutes=10)

    with django_capture_on_commit_callbacks(execute=True):
        kds_core.start_ticket(ticket, actor=cozinheiro.username)

    aviso.refresh_from_db()
    assert aviso.lifecycle == NotificationLifecycle.RESOLVED


def test_seguir_outra_estacao_deixa_a_anterior(client, forno, cozinheiro):
    cafe = KDSInstance.objects.create(ref="cafe", name="Café", type="prep")
    client.force_login(cozinheiro)
    client.post(reverse("api-backstage-kds-station-follow", args=[forno.ref]))
    client.post(reverse("api-backstage-kds-station-follow", args=[cafe.ref]))

    forno.refresh_from_db()
    cafe.refresh_from_db()
    assert kds_alerts.followers(forno) == []
    assert kds_alerts.followers(cafe) == [cozinheiro.pk]


def test_atraso_vai_a_gerente_e_some_quando_o_ticket_sai(forno, django_capture_on_commit_callbacks):
    gerente = User.objects.create_user("gerente", password="pw", first_name="Joana", is_staff=True)
    gerente.user_permissions.add(_perm(KDSInstance, "change_kdsinstance"))
    with django_capture_on_commit_callbacks(execute=True):
        ticket = _ticket(_order("WEB-1-S85"), forno)
    KDSTicket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(minutes=12))
    message = Directive.objects.get(topic=KDS_TICKET_LATE, payload__ticket_pk=ticket.pk)

    KDSTicketLateHandler().handle(message=message, ctx={})

    aviso = UserNotification.objects.get(user=gerente, source_condition=kds_alerts.KDS_TICKET_LATE)
    assert aviso.title == "Atrasado: S85 passou de 10 min"
    assert "Estação Forno, 12 min (meta 10)" in aviso.message

    ticket.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        kds_core.complete_ticket(ticket, actor="rafael.s")
    aviso.refresh_from_db()
    assert aviso.lifecycle == NotificationLifecycle.RESOLVED


def test_despertador_de_ticket_que_ja_saiu_nao_avisa_ninguem(forno, django_capture_on_commit_callbacks):
    gerente = User.objects.create_user("gerente2", password="pw", is_staff=True)
    gerente.user_permissions.add(_perm(KDSInstance, "change_kdsinstance"))
    with django_capture_on_commit_callbacks(execute=True):
        ticket = _ticket(_order("WEB-1-S86"), forno, status="done")
    message = Directive.objects.get(topic=KDS_TICKET_LATE, payload__ticket_pk=ticket.pk)

    KDSTicketLateHandler().handle(message=message, ctx={})

    assert not UserNotification.objects.filter(source_condition=kds_alerts.KDS_TICKET_LATE).exists()


def test_o_push_da_cozinha_vibra(forno):
    from shopman.shop.handlers.notification_push import _push_payload
    from shopman.shop.models import NotificationCategory, NotificationSeverity

    user = User.objects.create_user("vibra", password="pw")
    late = UserNotification.objects.create(
        user=user, category=NotificationCategory.KITCHEN, severity=NotificationSeverity.WARNING,
        title="Atrasado: S84 passou de 10 min", message="Estação Forno",
    )
    other = UserNotification.objects.create(user=user, category=NotificationCategory.ORDER, title="Pedido")

    assert _push_payload(late)["vibrate"] == [120, 90, 120, 90, 120]
    assert "vibrate" not in _push_payload(other)


# ── A Saída no índice ───────────────────────────────────────────────────


def test_o_indice_conta_os_prontos_para_sair_da_saida_sem_quadro(forno):
    saida = KDSInstance.objects.create(ref="saida", name="Saída", type="expedition")
    Order.objects.create(ref="WEB-1-R1", channel_ref="web", status=Order.Status.READY, total_q=100, data={})
    amanha = (timezone.localdate() + timedelta(days=1)).isoformat()
    Order.objects.create(
        ref="WEB-1-R2", channel_ref="web", status=Order.Status.READY, total_q=100, data={"delivery_date": amanha}
    )

    index = {item.ref: item for item in build_kds_index()}

    assert index[saida.ref].active_count == 1
