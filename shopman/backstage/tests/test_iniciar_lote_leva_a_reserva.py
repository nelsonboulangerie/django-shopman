"""Iniciar o lote leva a reserva junto (#2709).

Medido em 18/11/2026, com a fiação real: a encomenda reserva no saldo
planejado; a Produção inicia o lote e a ponte do Craftsman move a QUANTIDADE
para o saldo ``batch='started'``, mas as reservas ficavam no planejado, zerado.
Ao fechar, o pão ia para a vitrine com ``held 0``: o balcão lia 10 livres com o
lote aberto, a loja vendia 8 de 10 depois de fechado, e a baixa da encomenda
falhava no banco (``stk_quant_quantity_non_negative``) com o alerta
``stock_fulfill_failed`` mandando contar uma prateleira que estava certa.

Aqui nada é montado à mão. A reserva nasce do commit de verdade (a loja pelo
``CommitService`` com o portão ``secure_stock``; a encomenda do balcão pelo
``close_sale`` do PDV), o lote é planejado pelo Craftsman e aberto, fechado e
cancelado pelos serviços da tela da Produção, e quem mexe nos saldos é a ponte
``craftsman/contrib/stockman`` pelos sinais.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.tests.commit_support import seal_for
from shopman.stockman.models import Hold, HoldStatus, Position, PositionKind, Quant

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production
from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.models import Channel, Shop
from shopman.shop.services import availability
from shopman.shop.services import stock as stock_service
from shopman.shop.tests.test_pos_scheduled_order import ABERTO_TODO_DIA, _close, _payload

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
DAY = timedelta(days=1)
ACTOR = "production:forneiro"


@pytest.fixture
def ficha(monkeypatch):
    # A conferência de insumo é outra história: aqui a ficha não tem insumo.
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    Channel.objects.create(ref="web", name="Loja online", is_active=True, config={"stock": {"safety_margin": 2}})
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False, "sells_nonconforming": True},
        },
    )
    Product.objects.create(
        sku=SKU, name="Baguete", unit="un", base_price_q=1100, availability_policy="planned_ok",
        shelf_life_days=1, is_published=True, is_sellable=True,
    )
    Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True,
    )
    Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    return Recipe.objects.create(ref="baguete", name="Baguete", output_sku=SKU, batch_size=Decimal("10"))


def _hoje():
    return timezone.localdate()


# ── A reserva, pelo caminho real ─────────────────────────────────────────────


def _pedido_da_loja(qty, *, day=None, key: str = "1") -> Order:
    """Checkout da loja: sessão, commit e o portão de estoque dentro da transação."""
    data = {"payment": {"method": "cash"}}
    if day is not None:
        data.update(delivery_date=day.isoformat(), is_preorder=True)
    session_key = f"S-WEB-{key}"
    Session.objects.create(
        session_key=session_key, channel_ref="web", state="open", rev=1, data=data,
        items=[{"line_id": "L1", "sku": SKU, "name": "Baguete", "qty": qty, "unit_price_q": 1100}],
    )
    result = CommitService.commit(
        session_key=session_key, channel_ref="web", idempotency_key=f"K-WEB-{key}",
        seal=seal_for(session_key, "web"), channel_config={},
    )
    return Order.objects.get(ref=result["order_ref"] if isinstance(result, dict) else result.order_ref)


@pytest.fixture
def balcao():
    operator = get_user_model().objects.create_user(username="marina", password="x")
    return operator, cash.open_shift(operator=operator, float_q=10000)


def _encomenda_do_pdv(balcao, qty, *, day, key: str = "1") -> Order:
    operator, shift = balcao
    result = _close(operator, _payload(
        shift, client_request_id=f"enc-{key}", delivery_date=day.isoformat(),
        items=[{"sku": SKU, "name": "Baguete", "qty": qty, "unit_price_q": 1100}],
    ))
    return Order.objects.get(ref=result.order_ref)


def _reserva(order: Order) -> Hold:
    order.refresh_from_db()
    [entry] = order.data["hold_ids"]
    return Hold.objects.select_related("quant__position").get(pk=int(entry["hold_id"].split(":")[1]))


def _onde(order: Order) -> str:
    """Onde está a reserva do pedido: ``planejado``, ``em_producao``, a posição física ou ``sem_saldo``."""
    quant = _reserva(order).quant
    if quant is None:
        return "sem_saldo"
    if quant.target_date is None:
        return quant.position.ref
    return "em_producao" if quant.batch == "started" else "planejado"


# ── A Produção, pelos serviços da tela ───────────────────────────────────────


def _planejar(ficha, qty, day):
    return craft.plan(ficha, quantity=Decimal(str(qty)), date=day, position_ref="producao")


def _iniciar(work_order, qty) -> None:
    work_order.refresh_from_db()
    production.apply_start(
        work_order_id=work_order.pk, quantity=str(qty), actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"start-{work_order.pk}",
    )


def _fechar(work_order, qty, *, sem_iniciar: bool = False) -> None:
    work_order.refresh_from_db()
    production.apply_finish(
        work_order_id=work_order.pk, quantity=str(qty), actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"finish-{work_order.pk}",
        partition=[{"quantity": str(qty), "quality_grade_ref": "standard"}],
        allow_implicit_start=sem_iniciar,
        yield_deviation_confirmed=True, yield_deviation_reason="Contagem conferida.",
    )


def _cancelar(work_order) -> None:
    work_order.refresh_from_db()
    production.apply_void(
        work_order_id=work_order.pk, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"void-{work_order.pk}",
    )


# ── Leituras ─────────────────────────────────────────────────────────────────


def _livre(channel: str, day) -> Decimal:
    [answer] = availability.decide_many([(SKU, Decimal("1"))], channel_ref=channel, target_date=day)
    return Decimal(str(answer["available_qty"]))


def _saldos() -> dict[str, tuple[Decimal, Decimal]]:
    """``{lugar: (quantidade, reservado)}``, somando os saldos de cada lugar; lugar vazio some."""
    out: dict[str, tuple[Decimal, Decimal]] = {}
    for quant in Quant.objects.filter(sku=SKU).select_related("position"):
        if quant.target_date is None:
            place = quant.position.ref
        else:
            place = "em_producao" if quant.batch == "started" else "planejado"
        qty, held = out.get(place, (Decimal("0"), Decimal("0")))
        out[place] = (qty + quant.quantity, held + quant.held)
    return {place: pair for place, pair in out.items() if any(pair)}


# ── Ponta a ponta: plano → reserva → Iniciar → Fechar ────────────────────────


@pytest.mark.parametrize(
    "canal, dias", [("web", 0), ("web", 1), ("pdv", 1)], ids=["loja-hoje", "loja-amanha", "pdv-amanha"],
)
def test_a_reserva_chega_a_vitrine_com_o_pao(ficha, balcao, django_capture_on_commit_callbacks, canal, dias):
    day = _hoje() + dias * DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        if canal == "web":
            order = _pedido_da_loja(4, day=day if dias else None)
        else:
            order = _encomenda_do_pdv(balcao, 4, day=day)
    assert _onde(order) == "planejado"
    assert _livre("pdv", day) == Decimal("6")

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote, 10)

    # Lote aberto: a reserva foi com a quantidade, e a leitura segue descontando.
    assert _onde(order) == "em_producao"
    assert _saldos() == {"em_producao": (Decimal("10"), Decimal("4"))}
    assert _livre("pdv", day) == Decimal("6")
    outro = stock_adapter.create_hold(SKU, Decimal("10"), reference="order:OUTRA", channel_ref="pdv", target_date=day)
    assert outro["success"] is False, "com o lote aberto, as 4 da encomenda não são vendidas de novo"

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 10)

    # Lote fechado: a reserva está presa ao pão que foi para a vitrine.
    assert _onde(order) == "vitrine"
    assert _reserva(order).status in (HoldStatus.PENDING, HoldStatus.CONFIRMED)
    assert _saldos() == {"vitrine": (Decimal("10"), Decimal("4"))}
    assert _livre("pdv", day) == Decimal("6")
    assert _livre("web", day) == Decimal("4"), "10 na vitrine, 4 reservadas, margem de segurança 2"
    oito = availability.reserve(SKU, Decimal("8"), session_key="S-OUTRO", channel_ref="web", target_date=day)
    assert oito["ok"] is False, "o pão da encomenda não é vendido a outro cliente"

    # A baixa da encomenda sai da vitrine, sem alerta.
    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        stock_service.fulfill(order)
    assert _reserva(order).status == HoldStatus.FULFILLED
    assert _saldos() == {"vitrine": (Decimal("6"), Decimal("0"))}
    assert not OperatorAlert.objects.filter(type="stock_fulfill_failed").exists()


def test_fechar_sem_iniciar_continua_certo(ficha, django_capture_on_commit_callbacks):
    """O caminho direto (plan → finish), que já migrava a reserva, não muda."""
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(4)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 10, sem_iniciar=True)

    assert _onde(order) == "vitrine"
    assert _saldos() == {"vitrine": (Decimal("10"), Decimal("4"))}
    order.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        stock_service.fulfill(order)
    assert _saldos() == {"vitrine": (Decimal("6"), Decimal("0"))}


# ── Início parcial e quebra, pela tela (que não deixa passar do comprometido) ─


def test_inicio_parcial_leva_as_reservas_com_o_que_entrou(ficha, django_capture_on_commit_callbacks):
    """Lote de 10, entram 6: as reservas (4 e 1) vão com as 6; o resto do plano fica livre."""
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        de_quatro = _pedido_da_loja(4, key="a")
        de_um = _pedido_da_loja(1, key="b")

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote, 6)

    assert (_onde(de_quatro), _onde(de_um)) == ("em_producao", "em_producao")
    assert _saldos() == {"em_producao": (Decimal("6"), Decimal("5")), "planejado": (Decimal("4"), Decimal("0"))}
    assert _livre("pdv", day) == Decimal("5")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 6)

    assert (_onde(de_quatro), _onde(de_um)) == ("vitrine", "vitrine")
    assert _saldos() == {"vitrine": (Decimal("6"), Decimal("5"))}, "o que não entrou em produção saiu do plano"


def test_fechar_com_quebra_leva_a_reserva_para_o_que_saiu(ficha, django_capture_on_commit_callbacks):
    """10 entram, 6 saem: a reserva de 4 vai para a vitrine e a quebra some do saldo de produção."""
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(4)
        _iniciar(lote, 10)

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, 6)

    assert _onde(order) == "vitrine"
    assert _saldos() == {"vitrine": (Decimal("6"), Decimal("4"))}
    assert _livre("pdv", day) == Decimal("2")


def test_a_tela_segue_recusando_fechar_abaixo_do_comprometido(ficha, django_capture_on_commit_callbacks):
    """A trava que já existia continua de pé com a reserva no lote aberto: 8
    reservadas, o lote não fecha com 6."""
    day = _hoje()
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(8)
        _iniciar(lote, 10)

    with pytest.raises(production.ProductionOrderShortError):
        _fechar(lote, 6)

    assert _onde(order) == "em_producao"
    assert _saldos() == {"em_producao": (Decimal("10"), Decimal("8"))}


# ── Dois lotes do mesmo produto no mesmo dia ─────────────────────────────────


def test_dois_lotes_um_aberto_e_outro_nao(ficha, django_capture_on_commit_callbacks):
    """O lote que abre serve primeiro quem chegou primeiro, reserva inteira: a de 4
    e a de 6 cabem nas 10; a de 8 espera o outro lote, no planejado."""
    day = _hoje()
    primeiro = _planejar(ficha, 10, day)
    segundo = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        de_quatro = _pedido_da_loja(4, key="a")
        de_oito = _pedido_da_loja(8, key="b")
        de_seis = _pedido_da_loja(6, key="c")

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(primeiro, 10)

    assert _saldos() == {"em_producao": (Decimal("10"), Decimal("10")), "planejado": (Decimal("10"), Decimal("8"))}
    assert (_onde(de_quatro), _onde(de_oito), _onde(de_seis)) == ("em_producao", "planejado", "em_producao")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(primeiro, 10)

    assert (_onde(de_quatro), _onde(de_oito), _onde(de_seis)) == ("vitrine", "planejado", "vitrine")
    assert _livre("pdv", day) == Decimal("2")

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(segundo, 10)
        _fechar(segundo, 10)

    assert _onde(de_oito) == "vitrine"
    assert _saldos() == {"vitrine": (Decimal("20"), Decimal("18"))}


# ── A ponte, sem as travas da tela ───────────────────────────────────────────
# O Craftsman sozinho (sweeper, integração, instalação sem o backstage) deixa
# iniciar e fechar abaixo do comprometido. A reserva que não cabe inteira fica
# sem lastro, no saldo de produção: virar fato do pedido é a #2594.


def test_inicio_parcial_que_nao_cobre_deixa_no_plano_a_reserva_que_nao_cabe(
    ficha, balcao, django_capture_on_commit_callbacks,
):
    """Lote de 10, entram 6: a de 4 e a de 1 vão com o lote; a de 3 não cabe no
    que sobrou do aberto (1) e segue no que ficou planejado (4), ainda descontada."""
    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        de_quatro = _encomenda_do_pdv(balcao, 4, day=day, key="a")
        de_tres = _encomenda_do_pdv(balcao, 3, day=day, key="b")
        de_um = _encomenda_do_pdv(balcao, 1, day=day, key="c")

    with django_capture_on_commit_callbacks(execute=True):
        craft.start(lote, quantity=Decimal("6"), expected_rev=lote.rev)

    assert (_onde(de_quatro), _onde(de_tres), _onde(de_um)) == ("em_producao", "planejado", "em_producao")
    assert _saldos() == {"em_producao": (Decimal("6"), Decimal("5")), "planejado": (Decimal("4"), Decimal("3"))}
    assert _livre("pdv", day) == Decimal("2")


def test_inicio_acima_do_plano_leva_todas(ficha, balcao, django_capture_on_commit_callbacks):
    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        a = _encomenda_do_pdv(balcao, 4, day=day, key="a")
        b = _encomenda_do_pdv(balcao, 6, day=day, key="b")

    with django_capture_on_commit_callbacks(execute=True):
        craft.start(lote, quantity=Decimal("12"), expected_rev=lote.rev)

    assert _saldos() == {"em_producao": (Decimal("12"), Decimal("10"))}
    lote.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        craft.finish(lote, finished=Decimal("12"), expected_rev=lote.rev)
    assert (_onde(a), _onde(b)) == ("vitrine", "vitrine")
    assert _saldos() == {"vitrine": (Decimal("12"), Decimal("10"))}


@pytest.mark.parametrize("com_iniciar", [True, False], ids=["com-iniciar", "sem-iniciar"])
@pytest.mark.parametrize(
    "reservas, rendeu, destino, vitrine",
    [
        # Quebra abaixo do comprometido: a primeira reserva de 4 leva; a segunda não cabe.
        ((4, 4), 6, ["vitrine", "producao"], (Decimal("6"), Decimal("4"))),
        # Reserva maior que o que o lote rende: reserva é inteira, ninguém leva.
        ((8,), 6, ["producao"], (Decimal("6"), Decimal("0"))),
        # Rendeu o planejado.
        ((4, 4), 10, ["vitrine", "vitrine"], (Decimal("10"), Decimal("8"))),
        # Rendeu mais.
        ((4, 6), 12, ["vitrine", "vitrine"], (Decimal("12"), Decimal("10"))),
    ],
    ids=["quebra", "reserva-maior-que-o-rendimento", "rendeu-o-planejado", "rendeu-mais"],
)
def test_quem_leva_no_fim_do_lote_nao_depende_de_ter_iniciado(
    ficha, balcao, django_capture_on_commit_callbacks, com_iniciar, reservas, rendeu, destino, vitrine,
):
    """Quem leva e quem fica de fora é decidido pelo ``realize``, e é o mesmo
    com o lote aberto antes ou fechado direto do plano."""
    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        pedidos = [_encomenda_do_pdv(balcao, qty, day=day, key=str(index)) for index, qty in enumerate(reservas)]

    with django_capture_on_commit_callbacks(execute=True):
        if com_iniciar:
            craft.start(lote, quantity=Decimal("10"), expected_rev=lote.rev)
            lote.refresh_from_db()
        craft.finish(lote, finished=Decimal(str(rendeu)), expected_rev=lote.rev)

    onde = ["vitrine" if _onde(order) == "vitrine" else "producao" for order in pedidos]
    assert onde == destino
    assert _saldos().get("vitrine") == vitrine


# ── Cancelar um lote com outro do mesmo produto no dia ───────────────────────


def test_cancelar_o_outro_lote_nao_solta_a_reserva_que_o_aberto_cobre(ficha, django_capture_on_commit_callbacks):
    """Medido no main em 18/11: com o lote A aberto, cancelar o B soltava a reserva
    e avisava "promessa perdida", embora as 10 do A a cobrissem."""
    day = _hoje()
    aberto = _planejar(ficha, 10, day)
    outro = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(4)
        _iniciar(aberto, 10)

    with django_capture_on_commit_callbacks(execute=True):
        _cancelar(outro)

    assert _reserva(order).status == HoldStatus.PENDING
    assert _onde(order) == "em_producao"
    assert _saldos() == {"em_producao": (Decimal("10"), Decimal("4"))}
    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_cancelar_o_lote_aberto_devolve_a_reserva_ao_que_segue_planejado(ficha, django_capture_on_commit_callbacks):
    day = _hoje()
    aberto = _planejar(ficha, 10, day)
    _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(4)
        _iniciar(aberto, 10)
    assert _onde(order) == "em_producao"

    with django_capture_on_commit_callbacks(execute=True):
        _cancelar(aberto)

    assert _reserva(order).status == HoldStatus.PENDING
    assert _onde(order) == "planejado"
    assert _saldos() == {"planejado": (Decimal("10"), Decimal("4"))}
    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_cancelar_o_unico_lote_aberto_solta_a_reserva_e_avisa_o_pedido(ficha, django_capture_on_commit_callbacks):
    """Sem outro lote na data, a reserva perdeu o lastro de verdade (#2547 segue valendo)."""
    day = _hoje() + DAY
    lote = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        order = _pedido_da_loja(4, day=day)
        _iniciar(lote, 10)

    with django_capture_on_commit_callbacks(execute=True):
        _cancelar(lote)

    assert _reserva(order).status == HoldStatus.RELEASED
    assert OperatorAlert.objects.filter(type="order_promise_lost", order_ref=order.ref).exists()


def test_cancelar_o_outro_lote_solta_so_o_que_o_aberto_nao_cobre(ficha, django_capture_on_commit_callbacks):
    """Aberto 10 (com a de 4), planejado 10 (com a de 8): cancelado o planejado, a de 8
    não cabe nas 6 livres do aberto e é a única que perde o lastro."""
    day = _hoje()
    aberto = _planejar(ficha, 10, day)
    outro = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        de_quatro = _pedido_da_loja(4, key="a")
        de_oito = _pedido_da_loja(8, key="b")
        _iniciar(aberto, 10)

    with django_capture_on_commit_callbacks(execute=True):
        _cancelar(outro)

    assert _reserva(de_quatro).status == HoldStatus.PENDING
    assert _onde(de_quatro) == "em_producao"
    assert _reserva(de_oito).status == HoldStatus.RELEASED
    assert list(OperatorAlert.objects.filter(type="order_promise_lost").values_list("order_ref", flat=True)) == [
        de_oito.ref,
    ]


# ── O plano encolhe com um lote aberto ───────────────────────────────────────


def test_plano_que_encolhe_manda_a_reserva_para_o_lote_aberto(ficha, settings, django_capture_on_commit_callbacks):
    """A de 4 foi com o lote aberto; a de 5 ficou no planejado (10). O plano do
    segundo lote cai para 2: a de 5 passa para as 6 livres do aberto em vez de
    ficar sem lastro.

    Com a leitura de demanda da casa ligada, o Craftsman recusa encolher o
    plano abaixo do comprometido (``COMMITTED_HOLDS``) e este caso nem chega à
    ponte; aqui ela está desligada, como numa instalação só com o Craftsman.
    """
    settings.CRAFTSMAN = {**settings.CRAFTSMAN, "DEMAND_BACKEND": ""}
    day = _hoje()
    aberto = _planejar(ficha, 10, day)
    outro = _planejar(ficha, 10, day)
    with django_capture_on_commit_callbacks(execute=True):
        de_quatro = _pedido_da_loja(4, key="a")
        _iniciar(aberto, 10)
        de_cinco = _pedido_da_loja(5, key="b")
    assert (_onde(de_quatro), _onde(de_cinco)) == ("em_producao", "planejado")

    with django_capture_on_commit_callbacks(execute=True):
        outro.refresh_from_db()
        craft.adjust(outro, quantity=Decimal("2"), reason="menos massa", expected_rev=outro.rev)

    assert _onde(de_cinco) == "em_producao"
    assert _saldos() == {"em_producao": (Decimal("10"), Decimal("9")), "planejado": (Decimal("2"), Decimal("0"))}
