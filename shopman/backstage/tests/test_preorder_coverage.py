"""Agenda com cobertura (WP-G10, salto S3 do EXCELENCIA-GESTOR).

A lista de Encomendas dizia cada pedido e ninguém somava o dia: o furo só
aparecia no próprio dia, pedido a pedido. A leitura
``projections/preorder_coverage`` soma, por dia e por produto, o prometido ao
lado do que a Produção planejou para aquela data. Esta suíte prende:

- o dia que cobre, o dia que falta e o dia sem lote, com a frase do cabeçalho;
- lote cancelado não conta; o em andamento conta inteiro, o pronto pelo que rendeu;
- dois produtos no mesmo dia, cada um com a conta dele;
- o feito na hora e o que a casa não produz ficam fora da conta de lote;
- só o pedido aceito e aberto é promessa (novo, cancelado e encerrado não);
- de hoje, só a encomenda (o pedido comum do dia não é agenda);
- a quantidade que vale é a do pedido depois do ajuste, e o combo abre nos componentes;
- a rota: quem lê, a forma e o atalho para a Produção naquele dia;
- o número de consultas não cresce com o número de pedidos, e nada grava.

Os lotes são planejados, abertos, fechados e cancelados pelo Craftsman de verdade.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Terminal
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product, ProductComponent
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Position, PositionKind

from shopman.backstage.projections.order_attention import commitment_day_label
from shopman.backstage.projections.preorder_coverage import build_preorder_coverage
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Channel, Shop

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

URL = "api-backstage-order-preorder-coverage"

BAGUETE = "BAGUETE"
CIABATTA = "CIABATTA"


@pytest.fixture(autouse=True)
def casa(db):
    # A ponte do Craftsman com o estoque: planejar um lote mexe nos saldos de produção.
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401, I001
    from django.core.cache import cache

    cache.clear()
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "config": {}})
    Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    Product.objects.create(sku="FARINHA", name="Farinha", unit="kg", base_price_q=500, is_sellable=False)
    yield
    cache.clear()


def _product(sku: str, name: str, *, policy: str = "planned_ok", unit: str = "un") -> Product:
    return Product.objects.create(
        sku=sku, name=name, unit=unit, base_price_q=1100, availability_policy=policy, is_sellable=True,
    )


def _recipe(sku: str) -> Recipe:
    recipe = Recipe.objects.create(ref=sku.lower(), name=sku.title(), output_sku=sku, batch_size=Decimal("10"))
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA", quantity=Decimal("0.5"), unit="kg")
    return recipe


@pytest.fixture
def baguete(db) -> Recipe:
    _product(BAGUETE, "Baguete de tradição")
    return _recipe(BAGUETE)


@pytest.fixture
def ciabatta(db) -> Recipe:
    _product(CIABATTA, "Ciabatta")
    return _recipe(CIABATTA)


def _user(django_user_model, username: str, *perms: str):
    user = django_user_model.objects.create_user(username=username, is_staff=True)
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(Permission.objects.get(codename=codename, content_type__app_label=app_label))
    return user


@pytest.fixture
def gerente(django_user_model):
    return _user(django_user_model, "gerente-g10", "shop.manage_orders", "backstage.operate_production")


def _day(days: int = 0):
    return timezone.localdate() + timedelta(days=days)


def _order(ref: str, items: dict[str, str], *, days: int = 1, status: str = "accepted", **data) -> Order:
    """Uma encomenda aceita para daqui a ``days`` dias, com ``{sku: quantidade}``."""
    body = {
        "customer": {"name": f"Cliente {ref}", "phone": "+5543999990000"},
        "fulfillment_type": "pickup",
        "payment": {"method": "cash"},
        "delivery_date": _day(days).isoformat(),
        "is_preorder": True,
        **data,
    }
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=4400, data=body,
    )
    for index, (sku, qty) in enumerate(items.items(), start=1):
        OrderItem.objects.create(
            order=order, line_id=f"{ref}-{index}", sku=sku, name=sku.title(), qty=Decimal(qty),
            unit_price_q=1100, line_total_q=1100,
        )
    return order


def _lot(recipe: Recipe, qty: str, *, days: int = 1):
    return craft.plan(recipe, quantity=Decimal(qty), date=_day(days))


def _days():
    return build_preorder_coverage().days


def _only_day():
    days = _days()
    assert len(days) == 1
    return days[0]


def _row(day, sku: str):
    return next(row for row in day.products if row.sku == sku)


# ── O dia que cobre, o que falta e o sem lote ────────────────────────────────


def test_dia_que_cobre(baguete):
    _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "4"})
    _order("ENC-2", {BAGUETE: "4"})

    day = _only_day()

    assert (day.date, day.day_label, day.days_ahead) == (_day(1).isoformat(), "amanhã", 1)
    assert (day.state, day.state_label) == ("covered", "Produção cobre")
    assert day.headline == "A produção cobre as encomendas."
    assert day.orders_count == 2
    row = _row(day, BAGUETE)
    assert (row.name, row.unit) == ("Baguete de tradição", "un")
    assert (row.state, row.state_label) == ("covered", "Lote cobre")
    assert (row.promised_qty, row.promised_display) == ("8", "8x")
    assert (row.planned_qty, row.planned_display) == ("10", "10x")
    assert (row.missing_qty, row.surplus_qty) == ("0", "2")
    assert row.label == ""
    assert row.detail == "As encomendas somam 8x e os lotes, 10x."
    assert (row.orders_count, row.batch_count) == (2, 1)


def test_dia_que_falta_as_encomendas_somam_mais_que_o_lote(baguete):
    _lot(baguete, "10")
    for index in range(4):
        _order(f"ENC-{index}", {BAGUETE: "4"})

    day = _only_day()

    assert (day.state, day.state_label) == ("short", "Produção não cobre")
    assert day.headline == "Faltam 6 Baguete de tradição."
    row = _row(day, BAGUETE)
    assert (row.state, row.state_label) == ("short", "Lote não cobre")
    assert (row.promised_qty, row.planned_qty, row.missing_qty, row.surplus_qty) == ("16", "10", "6", "0")
    assert row.label == "Faltam 6 Baguete de tradição"
    assert row.detail == "As encomendas somam 16x e os lotes, 10x."
    assert row.orders_count == 4


def test_falta_uma_unidade_no_singular(baguete):
    _lot(baguete, "3")
    _order("ENC-1", {BAGUETE: "4"})

    assert _only_day().headline == "Falta 1 Baguete de tradição."


def test_dia_sem_lote(baguete):
    _order("ENC-1", {BAGUETE: "4"}, days=3)

    day = _only_day()

    assert day.day_label == commitment_day_label(_day(3))
    assert day.days_ahead == 3
    assert (day.state, day.state_label) == ("no_batch", "Sem lote")
    assert day.headline == "Sem lote para Baguete de tradição."
    row = _row(day, BAGUETE)
    assert (row.state, row.state_label) == ("no_batch", "Sem lote")
    assert (row.promised_qty, row.planned_qty, row.missing_qty) == ("4", "0", "4")
    assert row.label == "Sem lote para Baguete de tradição"
    assert row.detail == "Nenhum lote planejado para o dia."
    assert row.batch_count == 0


def test_o_lote_de_outro_dia_nao_cobre(baguete):
    """A encomenda de uma data só é coberta pelo lote daquela data (dono, 18/11/2026)."""
    _lot(baguete, "50", days=1)
    _order("ENC-1", {BAGUETE: "4"}, days=2)

    day = _only_day()

    assert day.date == _day(2).isoformat()
    assert day.state == "no_batch"


def test_cada_dia_tem_a_conta_dele_em_ordem(baguete):
    _lot(baguete, "10", days=1)
    _lot(baguete, "2", days=2)
    _order("ENC-A", {BAGUETE: "4"}, days=2)
    _order("ENC-B", {BAGUETE: "4"}, days=1)

    days = _days()

    assert [day.date for day in days] == [_day(1).isoformat(), _day(2).isoformat()]
    assert [day.state for day in days] == ["covered", "short"]
    assert days[1].headline == "Faltam 2 Baguete de tradição."


# ── O lote: cancelado, em andamento, pronto ──────────────────────────────────


def test_lote_cancelado_nao_conta(baguete):
    work_order = _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "4"})
    work_order.refresh_from_db()
    craft.void(work_order, reason="Forno parou")

    day = _only_day()

    assert day.state == "no_batch"
    assert day.headline == "Sem lote para Baguete de tradição."
    row = _row(day, BAGUETE)
    assert (row.planned_qty, row.missing_qty, row.batch_count) == ("0", "4", 0)
    assert row.detail == "O lote do dia foi cancelado."


def test_um_de_dois_lotes_cancelado_conta_so_o_que_ficou(baguete):
    _lot(baguete, "6")
    cancelado = _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "8"})
    cancelado.refresh_from_db()
    craft.void(cancelado, reason="Massa passou do ponto")

    row = _row(_only_day(), BAGUETE)

    assert (row.state, row.planned_qty, row.missing_qty, row.batch_count) == ("short", "6", "2", 1)


def test_lote_em_andamento_conta_inteiro_e_o_pronto_pelo_que_rendeu(baguete):
    aberto = _lot(baguete, "10", days=0)
    fechado = _lot(baguete, "10", days=0)
    _order("ENC-HOJE", {BAGUETE: "17"}, days=0)
    aberto.refresh_from_db()
    craft.start(aberto, quantity=Decimal("10"), expected_rev=aberto.rev)
    fechado.refresh_from_db()
    craft.finish(fechado, finished=Decimal("6"), expected_rev=fechado.rev)

    day = _only_day()

    assert (day.day_label, day.days_ahead) == ("hoje", 0)
    row = _row(day, BAGUETE)
    assert (row.state, row.planned_qty, row.missing_qty, row.batch_count) == ("short", "16", "1", 2)
    assert day.headline == "Falta 1 Baguete de tradição."


# ── Dois produtos no mesmo dia ───────────────────────────────────────────────


def test_dois_produtos_no_mesmo_dia_um_falta_e_o_outro_nao_tem_lote(baguete, ciabatta):
    _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "8", CIABATTA: "2"})
    _order("ENC-2", {BAGUETE: "8"})

    day = _only_day()

    assert day.state == "short"
    assert day.headline == "Faltam 6 Baguete de tradição. Sem lote para Ciabatta."
    assert [(row.sku, row.state) for row in day.products] == [(BAGUETE, "short"), (CIABATTA, "no_batch")]
    assert _row(day, CIABATTA).orders_count == 1
    assert day.orders_count == 2


def test_dois_produtos_faltando_cabem_numa_frase_so(baguete, ciabatta):
    _lot(baguete, "10")
    _lot(ciabatta, "5")
    _order("ENC-1", {BAGUETE: "12", CIABATTA: "6"})

    assert _only_day().headline == "Faltam 2 Baguete de tradição e 1 Ciabatta."


def test_um_produto_coberto_e_outro_sem_lote_o_dia_e_sem_lote(baguete, ciabatta):
    _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "4", CIABATTA: "2"})

    day = _only_day()

    assert (day.state, day.headline) == ("no_batch", "Sem lote para Ciabatta.")
    assert [(row.sku, row.state) for row in day.products] == [(CIABATTA, "no_batch"), (BAGUETE, "covered")]


# ── Quem não entra na conta de lote ──────────────────────────────────────────


def test_produto_feito_na_hora_nao_entra_na_conta_de_lote(baguete):
    _product("CROQUE", "Croque monsieur", policy="demand_ok")
    _recipe("CROQUE")
    _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "4", "CROQUE": "3"})

    day = _only_day()

    assert (day.state, day.headline) == ("covered", "A produção cobre as encomendas.")
    row = _row(day, "CROQUE")
    assert (row.state, row.state_label) == ("made_to_order", "Feito na hora")
    assert (row.promised_qty, row.promised_display) == ("3", "3x")
    assert (row.planned_qty, row.planned_display, row.missing_qty, row.surplus_qty) == ("", "", "", "")
    assert row.label == ""
    assert row.detail == "Feito na hora: não depende de lote."


def test_dia_so_com_feito_na_hora_nao_depende_de_lote():
    _product("CROQUE", "Croque monsieur", policy="demand_ok")
    _order("ENC-1", {"CROQUE": "3"})

    day = _only_day()

    assert (day.state, day.state_label) == ("not_batch_based", "Não depende de lote")
    assert day.headline == "Nenhum item depende de lote."


def test_o_que_a_casa_nao_produz_sai_do_estoque_e_nao_pede_lote(baguete):
    """A geleia de revenda não tem ficha: "Sem lote para Geleia" seria pedir um lote que ninguém faz."""
    _product("GELEIA", "Geleia de morango")
    _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "4", "GELEIA": "2"})

    day = _only_day()

    assert day.state == "covered"
    row = _row(day, "GELEIA")
    assert (row.state, row.state_label) == ("from_stock", "Do estoque")
    assert (row.promised_qty, row.planned_qty, row.missing_qty) == ("2", "", "")
    assert row.detail == "Sai do estoque: a casa não produz este item."


def test_produto_por_peso_diz_a_unidade():
    _product("BRIOCHE-KG", "Brioche a granel", unit="kg")
    recipe = _recipe("BRIOCHE-KG")
    _lot(recipe, "1")
    _order("ENC-1", {"BRIOCHE-KG": "1.35"})

    day = _only_day()

    row = _row(day, "BRIOCHE-KG")
    assert (row.promised_display, row.planned_display, row.missing_qty) == ("1,35 kg", "1 kg", "0,35")
    assert day.headline == "Falta 0,35 kg de Brioche a granel."


# ── Quais pedidos são promessa ───────────────────────────────────────────────


@pytest.mark.parametrize("status", ["new", "cancelled", "completed", "dispatched", "delivered", "returned"])
def test_pedido_novo_cancelado_ou_encerrado_fica_fora_da_conta(baguete, status):
    _lot(baguete, "10")
    _order("ENC-FORA", {BAGUETE: "9"}, status=status)
    _order("ENC-DENTRO", {BAGUETE: "4"})

    row = _row(_only_day(), BAGUETE)

    assert (row.promised_qty, row.orders_count) == ("4", 1)


@pytest.mark.parametrize("status", ["accepted", "preparing", "ready"])
def test_pedido_aceito_e_aberto_e_promessa(baguete, status):
    _order("ENC-1", {BAGUETE: "4"}, status=status)

    assert _row(_only_day(), BAGUETE).promised_qty == "4"


def test_sem_encomenda_a_agenda_vem_vazia_com_uma_consulta(baguete):
    _lot(baguete, "10")
    _order("ENC-CANCELADA", {BAGUETE: "4"}, status="cancelled")

    with CaptureQueriesContext(connection) as queries:
        assert build_preorder_coverage().days == ()
    assert len(queries) == 1


def test_de_hoje_so_a_encomenda_entra(baguete):
    """O pedido comum do dia também tem data, e não é promessa de agenda."""
    _lot(baguete, "10", days=0)
    _order("HOJE-COMUM", {BAGUETE: "9"}, days=0, is_preorder=False)
    _order("HOJE-ENCOMENDA", {BAGUETE: "4"}, days=0)
    _order(
        "HOJE-NA-COZINHA", {BAGUETE: "2"}, days=0, status="preparing", is_preorder=False,
        kitchen_released_at=timezone.now().isoformat(),
    )

    day = _only_day()

    assert day.day_label == "hoje"
    row = _row(day, BAGUETE)
    assert (row.promised_qty, row.orders_count) == ("6", 2)


def test_encomenda_de_ontem_ainda_aberta_nao_e_agenda(baguete):
    _order("ONTEM", {BAGUETE: "4"}, days=-1)

    assert _days() == ()


def test_balcao_e_pedido_de_teste_ficam_de_fora(baguete):
    _order("BALCAO", {BAGUETE: "4"}, origin_channel="pos", pos={"sales_mode": "counter"})
    _order("TESTE", {BAGUETE: "4"}, ifood={"is_test": True})

    assert _days() == ()


def test_vale_a_quantidade_do_pedido_depois_do_ajuste(baguete, ciabatta):
    """O pedido alterado tem a lista dele lida do ajuste, não das linhas seladas."""
    _lot(baguete, "10")
    _order("ENC-AJUSTADA", {BAGUETE: "4"}, adjustment={
        "source": "pos:edit", "revision": 1, "total_q": 9900,
        "items": [
            {"line_id": "ENC-AJUSTADA-1", "sku": BAGUETE, "name": "Baguete", "qty": "6"},
            {"line_id": "E1-1", "sku": CIABATTA, "name": "Ciabatta", "qty": "3"},
            {"line_id": "E1-FEE", "sku": "__DELIVERY_FEE__", "name": "Entrega", "qty": "1", "meta": {"type": "delivery_fee"}},
        ],
    })

    day = _only_day()

    assert {row.sku: row.promised_qty for row in day.products} == {BAGUETE: "6", CIABATTA: "3"}


def test_o_combo_abre_nos_componentes(baguete, ciabatta):
    """A cesta promete os pães dela: a conta é por produto que a Produção faz."""
    cesta = _product("CESTA", "Cesta de café da manhã")
    ProductComponent.objects.create(parent=cesta, component=Product.objects.get(sku=BAGUETE), qty=Decimal("2"))
    ProductComponent.objects.create(parent=cesta, component=Product.objects.get(sku=CIABATTA), qty=Decimal("1"))
    _lot(baguete, "10")
    _lot(ciabatta, "2")
    _order("ENC-CESTA", {"CESTA": "3", BAGUETE: "1"})

    day = _only_day()

    assert {row.sku: (row.promised_qty, row.state) for row in day.products} == {
        BAGUETE: ("7", "covered"),
        CIABATTA: ("3", "short"),
    }
    assert day.headline == "Falta 1 Ciabatta."


# ── O atalho para a Produção ─────────────────────────────────────────────────


def test_o_atalho_abre_o_plano_da_producao_naquele_dia(baguete, gerente, settings):
    settings.SHOPMAN_SURFACE_URLS = {"production": "https://producao.example.test/"}
    _order("ENC-1", {BAGUETE: "4"}, days=2)

    day = build_preorder_coverage(user=gerente).days[0]

    assert day.production_url == f"https://producao.example.test/plan?date={_day(2).isoformat()}"
    assert day.production_label == "Abrir a Produção"


def test_sem_endereco_da_producao_o_atalho_vem_vazio(baguete, gerente, settings):
    settings.DEBUG = False
    settings.SHOPMAN_SURFACE_URLS = {"pos": "https://pdv.example.test/"}
    _order("ENC-1", {BAGUETE: "4"})

    day = build_preorder_coverage(user=gerente).days[0]

    assert (day.production_url, day.production_label) == ("", "")
    assert day.headline == "Sem lote para Baguete de tradição."


def test_quem_nao_opera_a_producao_le_a_conta_e_nao_recebe_o_atalho(baguete, django_user_model, settings):
    settings.SHOPMAN_SURFACE_URLS = {"production": "https://producao.example.test/"}
    caixa = _user(django_user_model, "caixa-g10", "shop.manage_orders")
    _order("ENC-1", {BAGUETE: "4"})

    day = build_preorder_coverage(user=caixa).days[0]

    assert (day.production_url, day.production_label) == ("", "")
    assert day.state == "no_batch"
    assert build_preorder_coverage().days[0].production_url == ""


# ── A rota ───────────────────────────────────────────────────────────────────


@pytest.fixture
def posto(client):
    Terminal.objects.create(ref="passe", label="Passe", metadata={"station": {"mode": "attended"}})
    trust_station(client, "passe")
    return client


def test_a_rota_devolve_a_agenda_a_quem_le_o_quadro(posto, baguete, gerente, settings):
    settings.SHOPMAN_SURFACE_URLS = {"production": "https://producao.example.test/"}
    _lot(baguete, "10")
    _order("ENC-1", {BAGUETE: "8"})
    _order("ENC-2", {BAGUETE: "8"})
    posto.force_login(gerente)

    response = posto.get(reverse(URL))

    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"coverage", "generated_at", "contract_version"}
    assert list(body["coverage"]) == ["days"]
    (day,) = body["coverage"]["days"]
    assert day == {
        "date": _day(1).isoformat(),
        "day_label": "amanhã",
        "days_ahead": 1,
        "state": "short",
        "state_label": "Produção não cobre",
        "headline": "Faltam 6 Baguete de tradição.",
        "orders_count": 2,
        "products": [{
            "sku": BAGUETE,
            "name": "Baguete de tradição",
            "unit": "un",
            "state": "short",
            "state_label": "Lote não cobre",
            "promised_qty": "16",
            "promised_display": "16x",
            "planned_qty": "10",
            "planned_display": "10x",
            "missing_qty": "6",
            "surplus_qty": "0",
            "label": "Faltam 6 Baguete de tradição",
            "detail": "As encomendas somam 16x e os lotes, 10x.",
            "orders_count": 2,
            "batch_count": 1,
        }],
        "production_url": f"https://producao.example.test/plan?date={_day(1).isoformat()}",
        "production_label": "Abrir a Produção",
    }


def test_a_rota_fica_antes_da_rota_do_pedido():
    from django.urls import resolve

    assert resolve(reverse(URL)).url_name == URL


def test_quem_so_expede_le_a_agenda(posto, baguete, django_user_model):
    """A mesma porta do quadro: quem opera a Saída lê, como lê a lista de Encomendas."""
    _order("ENC-1", {BAGUETE: "4"})
    posto.force_login(_user(django_user_model, "saida-g10", "backstage.operate_kds"))

    response = posto.get(reverse(URL))

    assert response.status_code == 200, response.content
    assert response.json()["coverage"]["days"][0]["production_url"] == ""


def test_sem_permissao_do_quadro_a_rota_recusa(posto, baguete, django_user_model):
    _order("ENC-1", {BAGUETE: "4"})
    posto.force_login(_user(django_user_model, "padeiro-g10", "backstage.operate_production"))

    assert posto.get(reverse(URL)).status_code == 403


def test_sem_ninguem_identificado_a_rota_recusa(client, baguete):
    _order("ENC-1", {BAGUETE: "4"})

    assert client.get(reverse(URL)).status_code in (401, 403)


def test_a_rota_so_le(posto, gerente):
    posto.force_login(gerente)

    assert posto.post(reverse(URL), {}, content_type="application/json").status_code == 405


# ── Custo ────────────────────────────────────────────────────────────────────


def test_o_numero_de_consultas_nao_cresce_com_o_numero_de_pedidos_e_nada_grava(baguete, ciabatta, gerente):
    """Uma agenda com 4 encomendas e uma com 24 custam as mesmas consultas."""
    _product("CROQUE", "Croque monsieur", policy="demand_ok")
    cesta = _product("CESTA", "Cesta de café da manhã")
    ProductComponent.objects.create(parent=cesta, component=Product.objects.get(sku=BAGUETE), qty=Decimal("2"))
    _lot(baguete, "10", days=0)
    _lot(baguete, "10", days=1)
    _lot(ciabatta, "10", days=1)

    def agenda(prefix: str, groups: int) -> None:
        for index in range(groups):
            _order(f"{prefix}-HOJE-{index}", {BAGUETE: "4"}, days=0)
            _order(f"{prefix}-AMANHA-{index}", {BAGUETE: "4", CIABATTA: "2", "CROQUE": "1"}, days=1)
            _order(f"{prefix}-CESTA-{index}", {"CESTA": "1"}, days=2)
            _order(f"{prefix}-AJUSTE-{index}", {BAGUETE: "1"}, days=3, adjustment={
                "source": "pos:edit", "revision": 1, "items": [{"line_id": "1", "sku": CIABATTA, "qty": "2"}],
            })

    gerente.has_perm("backstage.operate_production")  # as permissões de quem lê ficam fora da conta
    agenda("P", 1)
    with CaptureQueriesContext(connection) as few:
        small = build_preorder_coverage(user=gerente)
    agenda("G", 5)
    with CaptureQueriesContext(connection) as many:
        large = build_preorder_coverage(user=gerente)

    assert [day.days_ahead for day in small.days] == [0, 1, 2, 3]
    assert [day.orders_count for day in large.days] == [6, 6, 6, 6]
    assert len(many) == len(few)
    # Pedidos, ajustes, itens, combos, produtos, lotes e fichas.
    assert len(few) == 7
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in (*few, *many))
