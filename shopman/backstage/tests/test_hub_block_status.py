"""A linha de estado dos blocos da Central (V4-HUB2, prévia v4 `hub.jpg`).

O que se trava aqui:

- cada bloco diz o estado do app com a MESMA leitura que o app faz, e fonte que não
  existe não vira número (linha vazia);
- o estado bom e sabido ("Caixa aberto", "Aberta") vai em ``status_positive``, que o
  bloco pinta com o ponto verde quando nada pede alguém;
- nenhum valor de caixa (o fechamento é às cegas): o PDV diz só se a gaveta está aberta;
- o bloco só existe, e só diz o estado, para quem pode abrir o app;
- a coluna do app na fila usa o nome curto da identidade ("Gestor").
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.buyman.models import Material
from shopman.cashman.models import Shift, Terminal
from shopman.orderman.models import Order

from shopman.backstage.projections import hub_queue
from shopman.backstage.projections.sales_series import DailySales
from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate, Campaign

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


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _operator(username: str, *perms: tuple[str, str]) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for app_label, codename in perms:
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    return User.objects.get(pk=user.pk)


def _tiles(client, user) -> dict[str, dict]:
    client.force_login(user)
    response = client.get(reverse("api-backstage-hub"))
    assert response.status_code == 200
    return {tile["ref"]: tile for tile in response.json()["hub"]["tiles"]}


def _admin(name: str) -> User:
    return User.objects.create_superuser(name, f"{name}@example.test", "pw")


# ── PDV: a gaveta, nunca o valor ──────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_pdv_com_gaveta_aberta_diz_caixa_aberto_em_verde(client):
    admin = _admin("hub-b-caixa")
    Shift.objects.create(terminal=Terminal.objects.create(ref="balcao", label="Balcão"), opened_by=admin)

    pos = _tiles(client, admin)["pos"]

    assert pos["status_positive"] == "Caixa aberto"
    assert pos["status_attention"] == ""
    assert "R$" not in pos["status_summary"]


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_pdv_sem_gaveta_aberta_diz_caixa_fechado_sem_verde(client):
    pos = _tiles(client, _admin("hub-b-sem-caixa"))["pos"]

    assert pos["status_positive"] == ""
    assert pos["status_summary"].startswith("Caixa fechado")


# ── Compras ───────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_compras_conta_pedido_para_enviar_e_pedido_a_caminho(client):
    Material.objects.create(sku="FAR", name="Farinha", unit="g", metadata={"purchase": {"request_status": "approved"}})
    # Dois insumos no MESMO pedido enviado contam como um pedido a caminho.
    for sku in ("MAN", "LEI"):
        Material.objects.create(
            sku=sku, name=sku, unit="g", metadata={"purchase": {"request_status": "sent", "request_ref": "PC-7"}}
        )
    Material.objects.create(sku="OVO", name="Ovos", unit="g", metadata={"purchase": {"request_status": "sent"}})
    Material.objects.create(sku="SAL", name="Sal", unit="g")

    purchase = _tiles(client, _admin("hub-b-compras"))["purchase"]

    assert purchase["status_attention"] == "1 pedido para enviar"
    assert purchase["status_summary"] == "2 pedidos a caminho"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_compras_sem_pedido_diz_o_estado_calmo(client):
    """Todo bloco tem estado (prévia v4, auditoria H05): sem pedido também é um fato."""
    Material.objects.create(sku="SAL", name="Sal", unit="g")

    purchase = _tiles(client, _admin("hub-b-compras-vazio"))["purchase"]

    assert purchase["status_attention"] == purchase["status_positive"] == ""
    assert purchase["status_summary"] == "Nenhum pedido em andamento"


# ── Marketing ─────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_marketing_diz_as_decisoes_da_fila_e_as_campanhas_ligadas(client):
    template = AnnouncementTemplate.objects.create(name="Fornada", body="{{product_name}} saiu do forno!")
    Campaign.objects.create(name="Fornada", trigger="production_finished", template=template, platforms=["instagram"])
    Announcement.objects.create(
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": "Croissant saiu do forno"},
        platforms=["instagram"],
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    # Quem só vê o Marketing (sem aprovar) também lê o estado do bloco: ele abre o app.
    leitor = _operator("hub-b-mkt", ("shop", "view_marketing"))

    marketing = _tiles(client, leitor)["marketing"]

    assert marketing["status_attention"] == "1 decisão"
    assert marketing["status_summary"] == "1 campanha ligada"


# ── B.I. ──────────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_bi_diz_as_vendas_da_janela_padrao_e_a_variacao(client, monkeypatch):
    def fake_daily_sales(since: date, until: date) -> dict[date, DailySales]:
        current = until >= timezone.localdate()
        revenue = 20_860_000 if current else 23_440_000
        return {until: DailySales(revenue_q=revenue, orders=10, source="shopman", cash_orders=0, payments_known=0)}

    monkeypatch.setattr("shopman.backstage.projections.sales_series.daily_sales", fake_daily_sales)

    bi = _tiles(client, _admin("hub-b-bi"))["bi"]

    assert bi["status_summary"] == "28D: R$ 208,6 mil (−11%)"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_bi_sem_venda_diz_o_estado_calmo(client):
    bi = _tiles(client, _admin("hub-b-bi-vazio"))["bi"]

    assert bi["status_summary"] == "Sem vendas nos últimos 28 dias"


def test_dinheiro_compacto_e_variacao_com_sinal():
    assert hub_queue._compact_money(20_860_000) == "R$ 208,6 mil"
    assert hub_queue._compact_money(100_000_000) == "R$ 1 mi"
    assert hub_queue._compact_money(95_000) == "R$ 950"
    assert hub_queue._signed_percent(12) == "+12%"
    assert hub_queue._signed_percent(-11) == "−11%"
    assert hub_queue._signed_percent(0) == "0%"


# ── Loja ──────────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_loja_aberta_com_pedidos_de_hoje(client, monkeypatch):
    from shopman.shop.services.business_calendar import BusinessCalendarState

    monkeypatch.setattr(
        "shopman.shop.services.business_calendar.current_business_state",
        lambda **_: BusinessCalendarState(is_open=True, opens_at="07:00", closes_at="20:00", message=""),
    )
    monkeypatch.setattr("shopman.shop.projections.channel_state.accepting_orders", lambda ref: True)
    for index in range(2):
        Order.objects.create(ref=f"WEB-HOJE-{index}", channel_ref="web", status="accepted", total_q=1000)
    Order.objects.create(ref="WEB-HOJE-X", channel_ref="web", status="cancelled", total_q=1000)
    Order.objects.create(ref="PDV-HOJE-1", channel_ref="pdv", status="completed", total_q=1000)

    loja = _tiles(client, _admin("hub-b-loja"))["loja"]

    assert loja["status_positive"] == "Aberta"
    assert loja["status_summary"] == "2 pedidos hoje"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_loja_fechada_diz_quando_abre_sem_verde(client, monkeypatch):
    from shopman.shop.services.business_calendar import BusinessCalendarState

    reopens = timezone.now() + timedelta(days=1)
    monkeypatch.setattr(
        "shopman.shop.services.business_calendar.current_business_state",
        lambda **_: BusinessCalendarState(is_open=False, opens_at=None, closes_at=None, message="", next_open_at=reopens),
    )

    loja = _tiles(client, _admin("hub-b-loja-fechada"))["loja"]

    assert loja["status_positive"] == ""
    assert loja["status_summary"].startswith("Fechada · abre amanhã às")
    assert loja["status_summary"].endswith("0 pedidos hoje")


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_loja_no_horario_com_o_canal_desligado_nao_fica_verde(client, monkeypatch):
    from shopman.shop.services.business_calendar import BusinessCalendarState

    monkeypatch.setattr(
        "shopman.shop.services.business_calendar.current_business_state",
        lambda **_: BusinessCalendarState(is_open=True, opens_at="07:00", closes_at="20:00", message=""),
    )
    monkeypatch.setattr("shopman.shop.projections.channel_state.accepting_orders", lambda ref: False)

    loja = _tiles(client, _admin("hub-b-loja-off"))["loja"]

    assert loja["status_positive"] == ""
    assert loja["status_summary"] == "Aberta, pedidos online desligados · 0 pedidos hoje"


# ── Permissão e nome curto ────────────────────────────────────────────────────


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_cada_bloco_so_aparece_com_estado_para_quem_abre_o_app(client):
    Material.objects.create(sku="FAR", name="Farinha", unit="g", metadata={"purchase": {"request_status": "approved"}})
    comprador = _operator("hub-b-comprador", ("backstage", "operate_purchase"))

    tiles = _tiles(client, comprador)

    assert list(tiles) == ["purchase"]
    assert tiles["purchase"]["status_attention"] == "1 pedido para enviar"


@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_a_fila_usa_o_nome_curto_do_app(client):
    order = Order.objects.create(ref="WEB-CURTO-1", channel_ref="web", status="new", total_q=1000, data={})
    admin = _admin("hub-b-curto")
    client.force_login(admin)

    hub = client.get(reverse("api-backstage-hub")).json()["hub"]

    item = next(item for item in hub["queue"]["items"] if item["key"] == f"gestor:order:{order.ref}")
    assert item["app_label"] == "Gestor"
    # O bloco continua com o nome inteiro.
    assert next(tile for tile in hub["tiles"] if tile["ref"] == "gestor")["label"] == "Gestor de pedidos"
