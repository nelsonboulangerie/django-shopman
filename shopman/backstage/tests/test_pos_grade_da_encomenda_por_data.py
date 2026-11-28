"""A grade da encomenda para outro dia lê o saldo DAQUELE dia.

Beta test de 05/11/2026 (PDV2-04). A grade só sabia o esgotado de hoje: na
encomenda para amanhã, o Bichon que acabou hoje não entrava; e o Brioche que a
grade deixava entrar o salvamento recusava ("não tem saldo para 07/11"). O
agendamento (``pos/schedule/``) passa a dizer, para a data escolhida, o que não
tem saldo, pela mesma régua por data da reserva.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.backstage.projections.pos import build_pos_schedule
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

ABERTO_TODO_DIA = {
    day: {"open": "08:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


@pytest.fixture(autouse=True)
def grade():
    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    for sku in ("BICHON", "BRIOCHE"):
        product = Product.objects.create(sku=sku, name=sku, base_price_q=900, is_published=True, is_sellable=True)
        ListingItem.objects.create(listing=listing, product=product, price_q=900)


def _saldo(por_data: dict):
    """Stock por data: o Bichon acabou hoje e tem fornada amanhã; o Brioche, o contrário."""

    def availability(skus, *, channel_ref, target_date=None):
        sem = {"is_tracked": True, "total_promisable": Decimal("0"), "availability_policy": "planned_ok"}
        com = {"is_tracked": True, "total_promisable": Decimal("10"), "available": Decimal("10")}
        sold = por_data.get(target_date, set())
        return {sku: (sem if sku in sold else com) for sku in skus}

    return mock.patch("shopman.shop.projections.catalog_context.availability_for_skus", side_effect=availability)


def test_encomenda_para_amanha_diz_o_que_nao_tem_saldo_amanha():
    amanha = timezone.localdate() + timedelta(days=1)
    with _saldo({None: {"BICHON"}, amanha: {"BRIOCHE"}}) as availability:
        schedule = build_pos_schedule(delivery_date=amanha.isoformat())
    assert schedule["sold_out_skus"] == ["BRIOCHE"]
    assert any(call.kwargs.get("target_date") == amanha for call in availability.call_args_list)


def test_hoje_a_grade_ja_sabe_e_nao_paga_a_pergunta():
    with _saldo({None: {"BICHON"}}) as availability:
        schedule = build_pos_schedule()
    assert schedule["sold_out_skus"] == []
    assert not any(call.kwargs.get("target_date") for call in availability.call_args_list)
