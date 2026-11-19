"""O lote aberto conta para a loja como conta para o balcão (#2715).

Medido em 18/11/2026, com a fiação real da Produção: lote de 10 baguetes para
hoje. A loja online lia 8 com o lote planejado, **0 com o lote aberto** e 8
depois de fechado; o balcão lia 10 nos três momentos. A loja prometia o pão
planejado e deixava de prometê-lo justamente quando ele entrava no forno.

A causa: o saldo em produção mora num quant com ``batch="started"``, que é um
marcador de etapa e não um lote. O canal remoto lê com lista de graus
permitidos, e o portão de qualidade do Stockman (deliberadamente fechado para
lote nomeado sem ``Batch``) tratava o marcador como lote não classificado.

Decisão da coordenação (19/11/2026, pelo princípio do dono "disponibilidade é
questão de QUANDO"): o que está em produção conta para a loja como conta para o
balcão.

Aqui a Produção é a da tela (``apply_start``/``apply_finish``), os saldos são
mexidos pela ponte do Craftsman, e a configuração de estoque de cada canal é a
da casa (``config/instances/nelson.json``).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import CraftService as craft
from shopman.offerman.models import Product
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.tests.commit_support import seal_for
from shopman.stockman.models import Batch, Hold, HoldStatus, Position, PositionKind, Quant

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production
from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.models import Channel, QualityDefect, Shop
from shopman.shop.services import availability, waitlist
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

SKU = "BAGUETE"
ACTOR = "production:forneiro"
NELSON_DESCRIPTOR = Path(__file__).resolve().parents[3] / "config" / "instances" / "nelson.json"
CHANNELS = ("pdv", "web", "whatsapp", "ifood")
REMOTE = ("web", "whatsapp", "ifood")


def _descriptor_overrides(ref: str) -> dict:
    """A configuração do canal como a casa a declara, só os aspectos que a reserva lê."""
    descriptor = json.loads(NELSON_DESCRIPTOR.read_text())
    [entry] = [c for c in descriptor["bootstrap"]["channels"] if c["ref"] == ref]
    overrides = entry["config"]["overrides"]
    return {key: overrides[key] for key in ("confirmation", "payment", "stock", "waitlist") if key in overrides}


@pytest.fixture
def lote(monkeypatch):
    """Um lote de 10 baguetes planejado para hoje, com os quatro canais da casa."""
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
    ficha = Recipe.objects.create(ref="baguete", name="Baguete", output_sku=SKU, batch_size=Decimal("10"))
    return craft.plan(ficha, quantity=Decimal("10"), date=timezone.localdate(), position_ref="producao")


def _iniciar(work_order, qty="10") -> None:
    work_order.refresh_from_db()
    production.apply_start(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"start-{work_order.pk}",
    )


def _fechar(work_order, qty="10", *, grade: str = "standard") -> None:
    work_order.refresh_from_db()
    group = {"quantity": qty, "quality_grade_ref": grade}
    if grade not in ("excellent", "standard"):
        group["quality_defect_ref"] = (
            QualityDefect.objects.filter(is_active=True, forces_discard=False).values_list("ref", flat=True).first()
        )
    production.apply_finish(
        work_order_id=work_order.pk, quantity=qty, actor=ACTOR, expected_rev=work_order.rev,
        idempotency_key=f"finish-{work_order.pk}", partition=[group],
    )


def _livre(channel: str) -> Decimal:
    [answer] = availability.decide_many([(SKU, Decimal("1"))], channel_ref=channel, target_date=timezone.localdate())
    return Decimal(str(answer["available_qty"]))


def _margem(channel: str) -> Decimal:
    return Decimal(stock_adapter.get_channel_scope(channel)["safety_margin"])


def _hold(hold_id: str) -> Hold:
    return Hold.objects.select_related("quant__position").get(pk=int(hold_id.split(":")[1]))


def _onde(hold_id: str) -> str:
    """Onde está a reserva: ``planejado``, ``em_producao`` ou a posição física."""
    quant = _hold(hold_id).quant
    if quant.target_date is None:
        return quant.position.ref
    return "em_producao" if quant.batch == "started" else "planejado"


def _reservar(channel: str, qty: str, *, key: str = "1") -> str:
    """A reserva da sacola pelo canal, como a loja a faz."""
    result = availability.reserve(SKU, Decimal(qty), session_key=f"S-{channel}-{key}", channel_ref=channel)
    assert result["ok"], result
    [hold_id] = result["hold_ids"]
    return hold_id


# ── A leitura não cai a zero no meio ─────────────────────────────────────────


@pytest.mark.parametrize("channel", CHANNELS)
def test_a_leitura_e_a_mesma_planejado_aberto_e_fechado(lote, channel, django_capture_on_commit_callbacks):
    """10 de hoje, menos a margem de segurança do canal, nos três momentos.

    Antes, os canais remotos liam 8, 0 e 8. O balcão já lia 10, 10 e 10.
    """
    esperado = Decimal("10") - _margem(channel)
    assert esperado == (Decimal("10") if channel == "pdv" else Decimal("8"))

    planejado = _livre(channel)
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    aberto = _livre(channel)
    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)
    fechado = _livre(channel)

    assert (planejado, aberto, fechado) == (esperado, esperado, esperado)


@pytest.mark.parametrize("channel", CHANNELS)
def test_todo_caminho_de_leitura_ve_o_lote_aberto(lote, channel, django_capture_on_commit_callbacks):
    from shopman.shop.projections import catalog_context

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    hoje = timezone.localdate()
    esperado = Decimal("10") - _margem(channel)

    one = availability.decide(SKU, Decimal("1"), channel_ref=channel, target_date=hoje)
    check = availability.check(SKU, esperado, channel_ref=channel, target_date=hoje)
    acima = availability.check(SKU, esperado + 1, channel_ref=channel, target_date=hoje)
    catalogo = catalog_context.availability_for_sku(SKU, channel_ref=channel, target_date=hoje)
    em_lote = availability.stock_on_dates([SKU], [hoje], **waitlist.scope_kwargs(channel))[hoje][SKU]

    assert one["available_qty"] == esperado
    assert check["ok"] is True
    assert acima["ok"] is False
    assert catalogo["total_promisable"] == esperado
    assert em_lote["total_promisable"] == esperado
    assert em_lote["breakdown"]["in_production"] == Decimal("10")
    assert em_lote["available"] == Decimal("0"), "em produção não é pronto: nada na vitrine ainda"


# ── A reserva feita com o lote aberto ancora e chega à vitrine ───────────────


@pytest.mark.parametrize("channel", CHANNELS)
def test_reserva_no_lote_aberto_chega_a_vitrine_com_grau_integral(lote, channel, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)

    hold_id = _reservar(channel, "4")

    assert _onde(hold_id) == "em_producao"
    assert _livre(channel) == Decimal("6") - _margem(channel)
    # A reserva acha exatamente o que a leitura contou: o resto cabe, uma a mais não.
    resto = Decimal("6") - _margem(channel)
    demais = availability.reserve(SKU, resto + 1, session_key=f"S-{channel}-demais", channel_ref=channel)
    assert demais["ok"] is False
    assert availability.reserve(SKU, resto, session_key=f"S-{channel}-resto", channel_ref=channel)["ok"] is True

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)

    assert _onde(hold_id) == "vitrine"
    vitrine = Quant.objects.get(sku=SKU, target_date__isnull=True)
    assert Batch.objects.get(ref=vitrine.batch).quality_grade_ref == "standard"
    assert (vitrine.quantity, vitrine.held) == (Decimal("10"), Decimal("4") + resto)


@pytest.mark.parametrize("channel", ["web", "whatsapp"])
def test_no_canal_com_fila_a_reserva_no_lote_aberto_continua_sendo_fila(lote, channel, django_capture_on_commit_callbacks):
    """Lote planejado ou aberto, a loja oferece a mesma coisa: a vaga na fornada, sem prazo."""
    antes = _hold(_reservar(channel, "2", key="antes"))
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    depois = _hold(_reservar(channel, "2", key="depois"))

    for hold in (antes, depois):
        assert hold.expires_at is None
        assert (hold.metadata or {}).get("planned") is True
        assert waitlist.is_waitlist_hold(hold)
    assert depois.quant.batch == "started"


@pytest.mark.parametrize("channel", ["web", "whatsapp"])
def test_pedido_da_loja_feito_com_o_lote_aberto(lote, channel, django_capture_on_commit_callbacks):
    """O commit de verdade: o portão de estoque do checkout aceita o pão que está no forno."""
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    session_key = f"S-COMMIT-{channel}"
    Session.objects.create(
        session_key=session_key, channel_ref=channel, state="open", rev=1, data={"payment": {"method": "pix"}},
        items=[{"line_id": "L1", "sku": SKU, "name": "Baguete", "qty": 4, "unit_price_q": 1100}],
    )

    result = CommitService.commit(
        session_key=session_key, channel_ref=channel, idempotency_key=f"K-{channel}",
        seal=seal_for(session_key, channel), channel_config={},
    )

    order = Order.objects.get(ref=result["order_ref"] if isinstance(result, dict) else result.order_ref)
    [entry] = order.data["hold_ids"]
    assert _onde(entry["hold_id"]) == "em_producao"

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote)
    assert _onde(entry["hold_id"]) == "vitrine"

    order.refresh_from_db()
    stock_service.fulfill(order)
    assert _hold(entry["hold_id"]).status == HoldStatus.FULFILLED
    assert Quant.objects.get(sku=SKU, target_date__isnull=True).quantity == Decimal("6")
    assert not OperatorAlert.objects.filter(type="stock_fulfill_failed").exists()


def test_o_pedido_da_loja_acima_do_lote_aberto_e_recusado(lote, django_capture_on_commit_callbacks):
    """10 no forno: onze não cabem, e o commit não cria pedido (o portão do
    commit não aplica a margem de vitrine, que é da sacola)."""
    from shopman.orderman.exceptions import ValidationError

    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    Session.objects.create(
        session_key="S-ONZE", channel_ref="web", state="open", rev=1, data={"payment": {"method": "pix"}},
        items=[{"line_id": "L1", "sku": SKU, "name": "Baguete", "qty": 11, "unit_price_q": 1100}],
    )

    with pytest.raises(ValidationError) as error:
        CommitService.commit(
            session_key="S-ONZE", channel_ref="web", idempotency_key="K-ONZE",
            seal=seal_for("S-ONZE", "web"), channel_config={},
        )

    assert error.value.code == "insufficient_supply"
    assert not Order.objects.filter(channel_ref="web").exists()


# ── No fechamento, quem decide é a inspeção ──────────────────────────────────


@pytest.mark.parametrize("channel", REMOTE)
def test_lote_que_sai_com_desconto_nao_leva_a_reserva_do_canal_remoto(lote, channel, django_capture_on_commit_callbacks):
    """A reserva remota feita no lote aberto não vai para pão que saiu com grau de desconto.

    Ela continua ativa, presa ao saldo de produção já zerado: sem lastro e sem
    aviso ao pedido. Esse desfecho já existia para a reserva feita no lote
    planejado; virar fato do pedido é a issue citada no PR.
    """
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    hold_id = _reservar(channel, "4")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, grade="fair")

    vitrine = Quant.objects.get(sku=SKU, target_date__isnull=True)
    assert Batch.objects.get(ref=vitrine.batch).quality_grade_ref == "fair"
    assert (vitrine.quantity, vitrine.held) == (Decimal("10"), Decimal("0")), "ninguém do canal remoto levou"
    hold = _hold(hold_id)
    assert _onde(hold_id) == "em_producao"
    assert hold.status == HoldStatus.PENDING
    assert hold.quant.quantity == Decimal("0")
    assert _livre(channel) == Decimal("0"), "o canal remoto não vende o lote com desconto"
    assert _livre("pdv") == Decimal("10"), "o balcão vende, com a etiqueta"


def test_no_balcao_a_reserva_acompanha_tambem_o_lote_com_desconto(lote, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    hold_id = _reservar("pdv", "4")

    with django_capture_on_commit_callbacks(execute=True):
        _fechar(lote, grade="fair")

    assert _onde(hold_id) == "vitrine"
    assert _livre("pdv") == Decimal("6")


# ── A porta continua fechada para lote nomeado sem Batch ─────────────────────


@pytest.mark.parametrize("channel", CHANNELS)
def test_lote_nomeado_sem_batch_continua_fora_do_canal_remoto(lote, channel, django_capture_on_commit_callbacks):
    """O marcador de produção passa; lote nomeado sem ``Batch`` de verdade, não.

    Cinco unidades na vitrine e três num saldo planejado, as duas com um ref de
    lote que não existe: o canal remoto não as lê nem reserva; o balcão segue
    lendo tudo, como antes.
    """
    with django_capture_on_commit_callbacks(execute=True):
        _iniciar(lote)
    hoje = timezone.localdate()
    Quant.objects.create(
        sku=SKU, position=Position.objects.get(ref="vitrine"), batch="LOTE-SEM-CADASTRO", _quantity=Decimal("5"),
    )
    Quant.objects.create(
        sku=SKU, position=Position.objects.get(ref="producao"), target_date=hoje, batch="PLANO-SEM-CADASTRO",
        _quantity=Decimal("3"),
    )

    if channel == "pdv":
        assert _livre(channel) == Decimal("18")
        return
    assert _livre(channel) == Decimal("8"), "só as 10 do lote aberto, menos a margem"
    # Reservando tudo o que o canal alcança (como o commit do pedido, sem a
    # margem da sacola): só o lote aberto, nunca os dois saldos sem cadastro.
    tudo = stock_adapter.create_holds_up_to(
        SKU, Decimal("50"), reference="order:TUDO", channel_ref=channel, apply_safety_margin=False,
    )
    assert {_hold(hold_id).quant.batch for hold_id, _qty in tudo} == {"started"}
    assert sum((qty for _hold_id, qty in tudo), Decimal("0")) == Decimal("10")
