"""Precisa de você: a fila das filas da Central (UX-H1, SUITE-UX §4.1 e §6).

O que se trava aqui:

- cada fonte vira o ITEM EXATO, com o gesto que abre o lugar exato no app certo;
- a ordem é por urgência ENTRE apps (o que estourou a meta vem primeiro);
- permissão é por item: quem não pode agir no app não vê o item dele, nem o anúncio quem
  só vê o Marketing sem poder aprovar;
- app sem URL configurada não gera item (nunca gesto para link morto);
- o excedente vira número ("+N"), nunca paginação;
- uma fonte que quebra não derruba a Central;
- a linha de estado de cada bloco concorda com a fila.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket, OperatorAlert
from shopman.backstage.projections import hub_queue
from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate

pytestmark = pytest.mark.django_db

SURFACE_URLS = {
    "pos": "https://pdv.example.test/",
    "kds": "https://kds.example.test/",
    "gestor": "https://gestor.example.test/",
    "production": "https://prod.example.test/",
    "purchase": "https://compras.example.test/",
    "marketing": "https://mkt.example.test/",
    "bi": "https://bi.example.test/",
    "loja": "https://loja.example.test/",
}


def _perm(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _operator(username: str, *perms: tuple[str, str]) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for app_label, codename in perms:
        user.user_permissions.add(_perm(app_label, codename))
    return User.objects.get(pk=user.pk)


def _hub(client, user) -> dict:
    client.force_login(user)
    response = client.get(reverse("api-backstage-hub"))
    assert response.status_code == 200
    return response.json()["hub"]


def _order_to_accept(ref: str = "WEB-20261003-K7Q2", *, minutes_ago: int = 1) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status="new",
        total_q=5840,
        data={"customer": {"name": "Ana Ferreira"}, "fulfillment_type": "pickup"},
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
    return order


def _late_ticket(*, minutes_ago: int = 25) -> KDSTicket:
    station = KDSInstance.objects.create(ref="forno", name="Forno", type="prep", target_time_minutes=10)
    order = Order.objects.create(
        ref="WEB-20261003-F15",
        channel_ref="web",
        session_key="sk-hub-f15",
        status=Order.Status.ACCEPTED,
        total_q=1500,
        data={"customer": {"name": "Bia"}},
    )
    ticket = KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        items=[{"sku": "CRO", "name": "Croissant", "qty": 2, "notes": ""}],
    )
    KDSTicket.objects.filter(pk=ticket.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago))
    return ticket


def _late_work_order() -> WorkOrder:
    recipe = Recipe.objects.create(
        ref="croissant",
        name="Croissant",
        output_sku="CRO",
        batch_size=Decimal("10"),
        is_active=True,
        meta={"max_started_minutes": 30},
    )
    return WorkOrder.objects.create(
        recipe=recipe,
        output_sku="CRO",
        quantity=Decimal("10"),
        status=WorkOrder.Status.STARTED,
        target_date=timezone.localdate(),
        started_at=timezone.now() - timedelta(minutes=50),
    )


def _pending_announcement(*, expires_in: int = 10) -> Announcement:
    template = AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu do forno!")
    return Announcement.objects.create(
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Croissant saiu do forno"},
        platforms=["instagram"],
        audience={"total": 86},
        expires_at=timezone.now() + timedelta(minutes=expires_in),
    )


def _preorder_due_now() -> Order:
    """Encomenda de retirada para hoje com a janela começando há 10 minutos."""
    local_now = timezone.localtime()
    start = local_now - timedelta(minutes=10)
    if start.date() != local_now.date():
        pytest.skip("perto da meia-noite a janela de hoje cairia em ontem")
    end = start + timedelta(minutes=30)
    slot = f"{start.strftime('%H:%M')}-{min(end, datetime.combine(local_now.date(), time(23, 59), tzinfo=local_now.tzinfo)).strftime('%H:%M')}"
    return Order.objects.create(
        ref="WEB-20261003-ENC1",
        channel_ref="web",
        status="accepted",
        total_q=3600,
        data={
            "customer": {"name": "Café Parisiense"},
            "fulfillment_type": "pickup",
            "delivery_date": local_now.date().isoformat(),
            "delivery_time_slot": slot,
        },
    )


# ── Item exato, gesto exato ───────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_superuser_ve_o_item_exato_de_cada_fila_com_o_gesto_do_lugar_certo(client):
    _order_to_accept()
    _late_ticket()
    wo = _late_work_order()
    announcement = _pending_announcement()
    _preorder_due_now()
    admin = User.objects.create_superuser("hub-q-admin", "a@b.c", "pw")

    queue = _hub(client, admin)["queue"]
    by_kind = {item["kind"]: item for item in queue["items"]}

    order = by_kind["order_to_accept"]
    assert order["title"] == "Pedido K7Q2 para aceitar"
    assert "Ana Ferreira" in order["detail"] and "R$ 58,40" in order["detail"]
    assert order["url"] == "https://gestor.example.test/WEB-20261003-K7Q2"
    assert order["action_label"] == "Abrir pedido"
    assert order["app"] == "gestor" and order["app_label"] == "Gestor de pedidos"

    ticket = by_kind["ticket_late"]
    assert ticket["title"] == "Pedido F15 atrasado: 2x Croissant"
    assert ticket["detail"] == "Estação Forno · meta 10 min"
    assert ticket["url"] == "https://kds.example.test/forno"
    assert ticket["attention"] is True

    lot = by_kind["work_order_late"]
    assert lot["title"] == "Lote de Croissant passou do tempo"
    assert lot["url"] == (
        f"https://prod.example.test/close?q={wo.ref}&date={timezone.localdate().isoformat()}"
    )

    review = by_kind["announcement_review"]
    assert review["title"] == "Anúncio para decidir: Fornada"
    assert review["detail"] == "Instagram · 86 pessoas"
    assert review["due_label"] == "decide até" and review["due_style"] == "clock"
    assert review["url"] == f"https://mkt.example.test/announcements/{announcement.pk}"
    assert review["attention"] is True  # faltam menos de 15 minutos

    preorder = by_kind["preorder_pickup"]
    assert preorder["title"] == "Encomenda de Café Parisiense para retirar"
    assert preorder["url"] == "https://pdv.example.test/preorders/WEB-20261003-ENC1"
    assert preorder["due_label"] == "retira às"

    assert queue["total_count"] == 5
    assert queue["more_count"] == 0
    assert queue["server_now"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_a_ordem_e_por_urgencia_entre_apps(client):
    """O pedido 15 minutos além da meta da estação vem antes do pedido novo de 1 minuto."""
    _order_to_accept(minutes_ago=1)
    _late_ticket(minutes_ago=25)
    admin = User.objects.create_superuser("hub-q-ordem", "a@b.c", "pw")

    kinds = [item["kind"] for item in _hub(client, admin)["queue"]["items"]]

    assert kinds.index("ticket_late") < kinds.index("order_to_accept")


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_pedido_com_prazo_de_confirmacao_mostra_quando_aceita_sozinho(client):
    from shopman.orderman.models import Directive

    order = _order_to_accept()
    expires = timezone.now() + timedelta(minutes=3)
    Directive.objects.create(
        topic="confirmation.timeout",
        status="queued",
        payload={"order_ref": order.ref, "expires_at": expires.isoformat(), "action": "confirm"},
    )
    admin = User.objects.create_superuser("hub-q-prazo", "a@b.c", "pw")

    item = _hub(client, admin)["queue"]["items"][0]

    assert item["due_label"] == "aceita sozinho em"
    assert item["due_style"] == "countdown"
    assert item["due_at"]


# ── Permissão é por item ──────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_operador_sem_acesso_ao_app_nao_ve_o_item_dele(client):
    _order_to_accept()
    _late_ticket()
    _late_work_order()
    _pending_announcement()
    gestor = _operator("hub-q-gestor", ("shop", "manage_orders"))

    hub = _hub(client, gestor)
    apps = {item["app"] for item in hub["queue"]["items"]}

    assert apps == {"gestor"}
    assert [tile["ref"] for tile in hub["tiles"]] == ["gestor"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_cozinheiro_ve_so_o_pedido_atrasado_da_cozinha(client):
    _order_to_accept()
    _late_ticket()
    cozinheiro = _operator("hub-q-cozinha", ("backstage", "operate_kds"))

    items = _hub(client, cozinheiro)["queue"]["items"]

    assert [item["kind"] for item in items] == ["ticket_late"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_quem_so_ve_o_marketing_nao_recebe_anuncio_para_decidir(client):
    """Ver o Marketing abre o app; decidir anúncio exige a permissão de aprovar."""
    _pending_announcement()
    leitor = _operator("hub-q-mkt-leitor", ("shop", "view_marketing"))
    decisor = _operator(
        "hub-q-mkt-decisor",
        ("shop", "view_marketing"),
        ("shop", "approve_marketing_announcements"),
    )

    leitor_hub = _hub(client, leitor)
    assert [tile["ref"] for tile in leitor_hub["tiles"]] == ["marketing"]
    assert leitor_hub["queue"]["items"] == []

    assert [item["kind"] for item in _hub(client, decisor)["queue"]["items"]] == ["announcement_review"]


@override_settings(SHOPMAN_SURFACE_URLS={k: v for k, v in SURFACE_URLS.items() if k != "kds"})
def test_app_sem_url_nao_gera_item(client):
    _late_ticket()
    admin = User.objects.create_superuser("hub-q-sem-url", "a@b.c", "pw")

    kinds = {item["kind"] for item in _hub(client, admin)["queue"]["items"]}

    assert "ticket_late" not in kinds


# ── Avisos ────────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_aviso_nao_visto_de_pedido_leva_ao_pedido_no_gestor(client):
    alert = OperatorAlert.objects.create(
        type="customer_cancellation_requested",
        severity="error",
        message="Cliente pediu para cancelar o pedido WEB-1.",
        order_ref="WEB-1",
    )
    OperatorAlert.objects.create(
        type="customer_cancellation_requested",
        severity="error",
        message="Já visto.",
        order_ref="WEB-2",
        acknowledged=True,
    )
    gestor = _operator("hub-q-aviso", ("shop", "manage_orders"))

    hub = _hub(client, gestor)
    alerts = [item for item in hub["queue"]["items"] if item["kind"] == "alert"]

    assert len(alerts) == 1
    assert alerts[0]["key"] == f"gestor:alert:{alert.pk}"
    assert alerts[0]["url"] == "https://gestor.example.test/WEB-1"
    assert alerts[0]["title"] == "Cliente solicitou cancelamento"
    gestor_tile = next(tile for tile in hub["tiles"] if tile["ref"] == "gestor")
    assert "1 aviso" in gestor_tile["status_attention"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_aviso_de_pedido_nao_chega_a_quem_so_opera_a_producao(client):
    OperatorAlert.objects.create(
        type="customer_cancellation_requested",
        severity="error",
        message="Cliente pediu para cancelar.",
        order_ref="WEB-1",
    )
    padeiro = _operator("hub-q-padeiro", ("backstage", "operate_production"))

    assert _hub(client, padeiro)["queue"]["items"] == []


# ── Excedente, falha isolada, linha de estado ─────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_excedente_vira_numero_nunca_pagina(client):
    for index in range(hub_queue.FOCUS_LIMIT + 2):
        _order_to_accept(f"WEB-20261003-P{index:02d}")
    admin = User.objects.create_superuser("hub-q-mais", "a@b.c", "pw")

    queue = _hub(client, admin)["queue"]

    assert len(queue["items"]) == hub_queue.FOCUS_LIMIT
    assert queue["total_count"] == hub_queue.FOCUS_LIMIT + 2
    assert queue["more_count"] == 2


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_uma_fonte_que_quebra_nao_derruba_a_central(client, monkeypatch, caplog):
    _order_to_accept()
    _late_ticket()  # sem a falha, a Cozinha também teria item

    def explode(*args, **kwargs):
        raise RuntimeError("fonte fora do ar")

    monkeypatch.setattr(
        hub_queue,
        "_SOURCES",
        tuple((app, can, explode if app == "kds" else source) for app, can, source in hub_queue._SOURCES),
    )
    admin = User.objects.create_superuser("hub-q-falha", "a@b.c", "pw")

    queue = _hub(client, admin)["queue"]

    assert [item["kind"] for item in queue["items"]] == ["order_to_accept"]
    assert "hub_queue.source_failed app=kds" in caplog.text


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_a_linha_de_estado_do_bloco_concorda_com_a_fila(client):
    _order_to_accept()
    _late_ticket()
    _late_work_order()
    admin = User.objects.create_superuser("hub-q-estado", "a@b.c", "pw")

    tiles = {tile["ref"]: tile for tile in _hub(client, admin)["tiles"]}

    assert tiles["gestor"]["status_attention"] == "1 para aceitar"
    # O pedido novo e o pedido da estação (aceito) são os dois ativos do dia.
    assert tiles["gestor"]["status_summary"] == "2 ativos"
    assert tiles["kds"]["status_attention"] == "1 pedido atrasado"
    assert tiles["kds"]["status_summary"] == "1 pedido nas estações"
    assert tiles["production"]["status_attention"] == "1 lote passou do tempo"
    assert tiles["production"]["status_summary"] == "0 de 1 lote finalizado hoje"
    # Sem fonte de estado: linha vazia, nunca um número inventado.
    assert tiles["purchase"]["status_attention"] == "" and tiles["purchase"]["status_summary"] == ""


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_staff_sem_app_recebe_fila_vazia(client):
    _order_to_accept()
    plain = _operator("hub-q-plain")

    queue = _hub(client, plain)["queue"]

    assert queue["items"] == [] and queue["total_count"] == 0


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_aviso_de_lote_nunca_vira_abrir_o_pedido_no_gestor(client):
    """O alerta de produção guarda o ref do LOTE em ``order_ref``. Quem lê o público de
    produção mas não opera o app da Produção não recebe o item, nem como pedido no Gestor."""
    OperatorAlert.objects.create(
        type="production_forgotten",
        severity="error",
        message="Lote WO-001 planejado nunca iniciado.",
        order_ref="WO-001",
    )
    gerente = _operator("hub-q-gerente", ("shop", "manage_orders"), ("shop", "manage_production"))
    padeiro = _operator("hub-q-padeiro-2", ("backstage", "operate_production"), ("shop", "manage_production"))

    assert _hub(client, gerente)["queue"]["items"] == []
    items = _hub(client, padeiro)["queue"]["items"]
    assert [item["app"] for item in items] == ["production"]
    assert items[0]["url"].startswith("https://prod.example.test/plan?q=WO-001")
