"""O lote de amanhã fechado hoje é pão de amanhã (#2693, conserto da fila do #2703).

A regra do dono (18/11/2026): a sobra de hoje não lastreia encomenda. Para
cumpri-la, a leitura de data futura passou a exigir que o saldo ainda valha um
dia depois da data (``promise_expiry_margin``). A primeira forma da regra
julgava o saldo físico pelo ``created_at``, o dia em que ele entrou no estoque.
O lote planejado PARA amanhã e fechado hoje à noite entrou hoje: era tratado
como pão de hoje e sumia da encomenda de amanhã, justamente a que ele existe
para atender. Medido na fila de merge: 10 na vitrine, 4 reservadas, livre 0.

O dia de produção de um saldo físico é o do lote dele (``Batch.production_date``,
que o fechamento grava com a data do lote). O pão de hoje continua fora da
encomenda de amanhã; o lote de amanhã conta para amanhã.

Aqui a Produção é a da tela (``apply_start``/``apply_finish``), o estoque é
mexido pela ponte do Craftsman, e a configuração de estoque de cada canal é a
da casa (``config/instances/nelson.json``).
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product
from shopman.stockman.models import Batch, Hold, Position, PositionKind, Quant

from shopman.backstage.services import production
from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.models import Channel, Shop
from shopman.shop.services import availability, waitlist

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
ACTOR = "production:forneiro"
DAY = timedelta(days=1)
NELSON_DESCRIPTOR = Path(__file__).resolve().parents[3] / "config" / "instances" / "nelson.json"
CHANNELS = ("pdv", "web", "whatsapp", "ifood")


def _descriptor_overrides(ref: str) -> dict:
    """A configuração do canal como a casa a declara, só os aspectos que a reserva lê."""
    descriptor = json.loads(NELSON_DESCRIPTOR.read_text())
    [entry] = [c for c in descriptor["bootstrap"]["channels"] if c["ref"] == ref]
    overrides = entry["config"]["overrides"]
    return {key: overrides[key] for key in ("confirmation", "payment", "stock", "waitlist") if key in overrides}


@pytest.fixture(params=[False, True], ids=["ficha-sem-validade", "ficha-com-validade"])
def ficha(request, monkeypatch):
    """A ficha da baguete de um dia, com os quatro canais da casa.

    Com e sem ``shelf_life_days`` na ficha: é ele que decide se o lote fechado
    pela tela nasce com validade ou só com a data de produção. A regra tem de
    valer nos dois casos.
    """
    # A conferência de insumo é outra história: aqui a ficha não tem insumo.
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    for ref in CHANNELS:
        Channel.objects.create(ref=ref, name=ref, is_active=True, config=_descriptor_overrides(ref))
    Product.objects.create(
        sku=SKU, name="Baguete", unit="un", base_price_q=1100, availability_policy="planned_ok",
        shelf_life_days=1, is_published=True, is_sellable=True,
    )
    Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True,
    )
    Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    return Recipe.objects.create(
        ref="baguete", name="Baguete", output_sku=SKU, batch_size=Decimal("10"),
        meta={"shelf_life_days": 1} if request.param else {},
    )


def _hoje():
    return timezone.localdate()


def _planejar(ficha, day, qty="10"):
    return craft.plan(ficha, quantity=Decimal(qty), date=day, position_ref="producao")


def _iniciar(work_order, qty="10") -> None:
    work_order.refresh_from_db()
    production.apply_start(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"start-{work_order.pk}",
    )


def _fechar(work_order, qty="10") -> None:
    work_order.refresh_from_db()
    production.apply_finish(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"finish-{work_order.pk}", partition=[{"quantity": qty, "quality_grade_ref": "standard"}],
    )


def _produzir(ficha, day, callbacks) -> Quant:
    """Planeja para ``day``, inicia e fecha HOJE; devolve o saldo que foi para a vitrine."""
    antes = set(Quant.objects.filter(sku=SKU, target_date__isnull=True).values_list("pk", flat=True))
    lote = _planejar(ficha, day)
    with callbacks(execute=True):
        _iniciar(lote)
    with callbacks(execute=True):
        _fechar(lote)
    [novo] = Quant.objects.filter(sku=SKU, target_date__isnull=True).exclude(pk__in=antes)
    return novo


def _livre(channel: str, day) -> Decimal:
    [answer] = availability.decide_many([(SKU, Decimal("1"))], channel_ref=channel, target_date=day)
    return Decimal(str(answer["available_qty"]))


def _margem(channel: str) -> Decimal:
    return Decimal(stock_adapter.get_channel_scope(channel)["safety_margin"])


# ── O lote de amanhã, fechado hoje, conta para amanhã ────────────────────────


@pytest.mark.parametrize("channel", CHANNELS)
def test_lote_de_amanha_fechado_hoje_conta_para_amanha(ficha, channel, django_capture_on_commit_callbacks):
    amanha = _hoje() + DAY

    vitrine = _produzir(ficha, amanha, django_capture_on_commit_callbacks)

    lote = Batch.objects.get(ref=vitrine.batch)
    assert lote.production_date == amanha, "o fechamento grava o lote com a data dele"
    # A validade do lote vem da ficha; sem ela o lote só declara a produção.
    assert lote.expiry_date == (amanha + DAY if ficha.meta.get("shelf_life_days") else None)
    assert timezone.localdate(vitrine.created_at) == _hoje(), "e o saldo entrou no estoque hoje"
    assert _livre(channel, amanha) == Decimal("10") - _margem(channel)


@pytest.mark.parametrize("channel", CHANNELS)
def test_todo_caminho_de_leitura_ve_o_lote_de_amanha(ficha, channel, django_capture_on_commit_callbacks):
    """A decisão, o portão, a leitura de várias datas e a reserva dão o mesmo número."""
    amanha = _hoje() + DAY
    _produzir(ficha, amanha, django_capture_on_commit_callbacks)
    esperado = Decimal("10") - _margem(channel)

    one = availability.decide(SKU, Decimal("1"), channel_ref=channel, target_date=amanha)
    cabe = availability.check(SKU, esperado, channel_ref=channel, target_date=amanha)
    acima = availability.check(SKU, esperado + 1, channel_ref=channel, target_date=amanha)
    por_datas = availability.stock_on_dates([SKU], [amanha], **waitlist.scope_kwargs(channel))[amanha][SKU]

    assert one["available_qty"] == esperado
    assert cabe["ok"] is True
    assert acima["ok"] is False
    assert por_datas["total_promisable"] == esperado
    # A reserva acha o que a leitura contou.
    hold = stock_adapter.create_hold(
        SKU, Decimal("4"), reference="order:AMANHA", channel_ref=channel, target_date=amanha,
    )
    assert hold["success"] is True, hold
    assert _livre(channel, amanha) == esperado - Decimal("4")


# ── O pão de hoje segue fora da encomenda de amanhã ──────────────────────────


@pytest.mark.parametrize("channel", CHANNELS)
def test_pao_de_hoje_segue_fora_da_encomenda_de_amanha(ficha, channel, django_capture_on_commit_callbacks):
    hoje = _hoje()

    vitrine = _produzir(ficha, hoje, django_capture_on_commit_callbacks)

    assert Batch.objects.get(ref=vitrine.batch).production_date == hoje
    assert _livre(channel, hoje) == Decimal("10") - _margem(channel), "hoje ele é pão do dia"
    assert _livre(channel, hoje + DAY) == Decimal("0")
    hold = stock_adapter.create_hold(
        SKU, Decimal("1"), reference="order:AMANHA", channel_ref=channel, target_date=hoje + DAY,
    )
    assert hold["success"] is False, "a reserva recusa o que a leitura recusa"


@pytest.mark.parametrize("channel", CHANNELS)
def test_o_lote_de_hoje_e_o_de_amanha_lado_a_lado(ficha, channel, django_capture_on_commit_callbacks):
    """Os dois na vitrine hoje à noite: amanhã só conta o lote de amanhã, e é nele que a reserva prende."""
    hoje = _hoje()
    de_hoje = _produzir(ficha, hoje, django_capture_on_commit_callbacks)
    de_amanha = _produzir(ficha, hoje + DAY, django_capture_on_commit_callbacks)
    assert de_hoje.pk != de_amanha.pk

    assert _livre(channel, hoje + DAY) == Decimal("10") - _margem(channel)

    hold = stock_adapter.create_hold(
        SKU, Decimal("3"), reference="order:AMANHA", channel_ref=channel, target_date=hoje + DAY,
    )
    assert hold["success"] is True, hold
    reserva = Hold.objects.get(pk=int(hold["hold_id"].split(":")[1]))
    assert reserva.quant_id == de_amanha.pk


# ── A fornada planejada da véspera segue fora ────────────────────────────────


@pytest.mark.parametrize("channel", CHANNELS)
def test_fornada_de_hoje_planejada_ou_no_forno_nao_conta_para_amanha(
    ficha, channel, django_capture_on_commit_callbacks,
):
    hoje = _hoje()
    lote = _planejar(ficha, hoje)
    assert _livre(channel, hoje) == Decimal("10") - _margem(channel)
    assert _livre(channel, hoje + DAY) == Decimal("0"), "planejada para hoje"

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)

    assert _livre(channel, hoje) == Decimal("10") - _margem(channel)
    assert _livre(channel, hoje + DAY) == Decimal("0"), "no forno, de hoje"


# ── Lote que não declara nada não ganha passe ────────────────────────────────


def test_lote_nomeado_sem_cadastro_nao_ganha_passe(ficha, django_capture_on_commit_callbacks):
    """Saldo na vitrine com ref de lote que não existe: o balcão o lê hoje, como sempre,
    e ele não conta para amanhã (o canal remoto nem o lê, pelo portão de qualidade)."""
    hoje = _hoje()
    Quant.objects.create(
        sku=SKU, position=Position.objects.get(ref="vitrine"), batch="LOTE-SEM-CADASTRO", _quantity=Decimal("5"),
    )

    assert _livre("pdv", hoje) == Decimal("5")
    assert _livre("pdv", hoje + DAY) == Decimal("0")
    for channel in ("web", "whatsapp", "ifood"):
        assert _livre(channel, hoje + DAY) == Decimal("0")
