"""`qa_scenarios` — arma os estados da vitrine num banco JÁ semeado.

O perfil `qa` do seed cobre os mesmos estados, mas custa `seed --flush`. Este
comando existe para o QA manual do alpha (perfil demo, tudo com estoque), e o
que ele arma tem de ser o que o cliente vê — por isso cada asserção aqui passa
pela projeção do cardápio, não pelo estoque cru.
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import CommandError, call_command
from shopman.offerman.models import ListingItem, Product

from config.management.commands.qa_scenarios import DEFAULT_SKUS
from shopman.shop.projections.types import Availability
from shopman.storefront.presentation.catalog import build_catalog_items_for_skus
from shopman.storefront.services import stock_alerts

pytestmark = pytest.mark.django_db

PHONE = "+5543999990001"
#: Um SKU que NÃO é alvo padrão de nenhum cenário — o caso do `--arm estado=SKU`.
FORA_DA_LISTA = "BF"


@pytest.fixture
def vitrine(db):
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return position


@pytest.fixture
def cenario(db, listing, vitrine):
    """Os SKUs dos cenários, publicados na vitrine web e com estoque cheio."""
    from shopman.stockman import stock

    produtos = {}
    for sku in sorted(set(DEFAULT_SKUS.values()) | {FORA_DA_LISTA}):
        produto = Product.objects.create(
            sku=sku, name=f"Produto {sku}", base_price_q=1000,
            is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(
            listing=listing, product=produto, price_q=1000,
            is_published=True, is_sellable=True,
        )
        stock.receive(quantity=20, sku=sku, position=vitrine, reason="baseline do teste")
        produtos[sku] = produto
    return produtos


def _items():
    return {
        item.sku: item
        for item in build_catalog_items_for_skus(
            sorted(set(DEFAULT_SKUS.values()) | {FORA_DA_LISTA}), channel_ref="web"
        )
    }


# ── armar ────────────────────────────────────────────────────────────


def test_arm_puts_each_sku_in_its_storefront_state(cenario):
    call_command("qa_scenarios", arm=[])
    items = _items()

    esgotado = items[DEFAULT_SKUS["sold_out"]]
    assert esgotado.availability == Availability.UNAVAILABLE
    assert esgotado.is_notifiable is True  # é ele que faz o sino aparecer
    assert esgotado.is_paused is False

    ultimas = items[DEFAULT_SKUS["low_stock"]]
    assert ultimas.availability == Availability.LOW_STOCK
    assert ultimas.can_add_to_cart is True

    previsto = items[DEFAULT_SKUS["planned"]]
    assert previsto.availability == Availability.UNAVAILABLE

    pausado = items[DEFAULT_SKUS["paused"]]
    assert pausado.is_paused is True
    assert pausado.is_notifiable is False  # pausa é decisão, não falta

    pausado_canal = items[DEFAULT_SKUS["paused_channel"]]
    assert pausado_canal.is_paused is True
    # A pausa é da SUPERFÍCIE: o produto continua vendável para o balcão.
    assert Product.objects.get(sku=DEFAULT_SKUS["paused_channel"]).is_sellable is True


def test_arm_accepts_one_state_on_a_chosen_sku(cenario):
    alvo = DEFAULT_SKUS["low_stock"]
    call_command("qa_scenarios", arm=[f"sold_out={alvo}"])

    items = _items()
    assert items[alvo].is_notifiable is True
    # Sem o estado na linha de comando, nada mais é tocado.
    assert items[DEFAULT_SKUS["paused"]].is_paused is False


def test_arm_refuses_an_unknown_state(cenario):
    with pytest.raises(CommandError, match="Estado desconhecido"):
        call_command("qa_scenarios", arm=["fora_do_ar"])


def test_arm_refuses_a_sku_outside_the_catalog(cenario):
    with pytest.raises(CommandError, match="não existe no catálogo"):
        call_command("qa_scenarios", arm=["sold_out=NAO-EXISTE"])


# ── repor: o gatilho do "Avise-me" ───────────────────────────────────


def test_restock_fires_the_pending_alert(cenario, django_capture_on_commit_callbacks):
    sku = DEFAULT_SKUS["sold_out"]
    call_command("qa_scenarios", arm=[f"sold_out={sku}"])
    sub = stock_alerts.subscribe(sku, channel_ref="web", phone=PHONE)

    # O envio é agendado em `transaction.on_commit`: fora do runner isso roda
    # sozinho (autocommit), aqui o commit nunca chega e precisa ser capturado.
    with patch(
        "shopman.shop.notifications.notify", return_value=MagicMock(success=True)
    ) as notify:
        with django_capture_on_commit_callbacks(execute=True):
            call_command("qa_scenarios", restock=sku)

    notify.assert_called_once()
    assert notify.call_args.kwargs["event"] == "stock_arrived"
    sub.refresh_from_db()
    assert sub.notified_at is not None
    assert _items()[sku].can_add_to_cart is True


def test_restock_refuses_a_sku_outside_the_catalog(cenario):
    with pytest.raises(CommandError, match="não existe no catálogo"):
        call_command("qa_scenarios", restock="NAO-EXISTE")


def test_restock_refuses_a_non_positive_quantity(cenario):
    with pytest.raises(CommandError, match="maior que zero"):
        call_command("qa_scenarios", restock=f"{DEFAULT_SKUS['sold_out']}:0")


# ── desarmar ─────────────────────────────────────────────────────────


def test_reset_puts_every_sku_back_on_sale(cenario):
    call_command("qa_scenarios", arm=[])
    call_command("qa_scenarios", reset=[])

    items = _items()
    assert items[DEFAULT_SKUS["paused"]].is_paused is False
    assert items[DEFAULT_SKUS["paused_channel"]].is_paused is False
    assert items[DEFAULT_SKUS["sold_out"]].can_add_to_cart is True
    assert items[DEFAULT_SKUS["low_stock"]].availability == Availability.AVAILABLE


# ── trava ────────────────────────────────────────────────────────────


def test_refuses_to_run_in_production(cenario, settings):
    settings.SHOPMAN_ENVIRONMENT = "production"
    with pytest.raises(CommandError, match="Recusando qa_scenarios em produção"):
        call_command("qa_scenarios", arm=[])


# ── o relatório fecha sobre o que ESTA execução mirou ────────────────


def test_report_covers_the_sku_you_armed(cenario):
    out = StringIO()
    call_command("qa_scenarios", arm=[f"sold_out={FORA_DA_LISTA}"], stdout=out)

    linhas = out.getvalue().splitlines()
    alvo = [ln for ln in linhas if ln.strip().startswith(FORA_DA_LISTA)]
    # Armar num SKU escolhido e receber um relatório que não o menciona é pior
    # que não relatar nada.
    assert alvo, out.getvalue()
    assert "sold_out" in alvo[-1]
    # O SKU padrão que perdeu o posto continua na lista, sem rótulo de cenário.
    padrao = [ln for ln in linhas if ln.strip().startswith(DEFAULT_SKUS["sold_out"])]
    assert padrao and "sold_out" not in padrao[-1]


def test_reset_finds_a_sku_armed_in_an_earlier_run(cenario):
    call_command("qa_scenarios", arm=[f"sold_out={FORA_DA_LISTA}"])
    assert _items()[FORA_DA_LISTA].is_notifiable is True

    # `--reset` sem argumento: o SKU vem do rastro que o comando deixou no
    # ledger, não da memória desta sessão.
    call_command("qa_scenarios", reset=[])
    assert _items()[FORA_DA_LISTA].can_add_to_cart is True


def test_reset_accepts_a_named_sku_for_a_pause(cenario):
    # Pausa não gera movimento de estoque, então o ledger não a reencontra:
    # é o caso em que o SKU precisa ser nomeado no reset.
    call_command("qa_scenarios", arm=[f"paused={FORA_DA_LISTA}"])
    call_command("qa_scenarios", reset=[FORA_DA_LISTA])
    assert Product.objects.get(sku=FORA_DA_LISTA).is_sellable is True
