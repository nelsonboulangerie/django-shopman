"""O preço da comanda é o do servidor: o ``unit_price_q`` do corpo não mede desconto.

Auditoria de 03/11/2026. O portão do gerente mede o desconto de linha como
``subtotal - o que o motor cobra``, e o subtotal sai do ``unit_price_q`` das
linhas. Sem comanda, o motor reprecifica (``_stamp_engine_prices``); com comanda,
o preço declarado pelo navegador era mantido. Um corpo com R$ 4,00 num pão de
R$ 12,00 em cortesia de 100% media R$ 4,00 de desconto, abaixo do limite de
R$ 5,00, e a venda saía de graça sem gerente: o total do motor (zero) batia com
o selo do fechamento.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError, pos_session_revision
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db

COURTESY = {"type": "percent", "value": 100, "reason": "cortesia"}


@pytest.fixture
def counter(settings):
    settings.SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q = 500
    return _Counter()


def _line(**overrides):
    line = {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200, "line_id": "L-pao00001"}
    line.update(overrides)
    return line


def _tab_with(items):
    tab = pos_service.open_pos_tab(channel_ref="pdv", tab_ref="31", actor="pos:marina", operator_username="marina")
    pos_service.save_pos_tab(
        channel_ref="pdv",
        payload={"tab_session_key": tab.session_key, "items": items},
        actor="pos:marina",
        operator_username="marina",
    )
    tab.refresh_from_db()
    return tab, pos_session_revision(tab)


def _review(counter, tab, items):
    return pos_service.review_sale(
        channel_ref="pdv",
        payload={
            "items": items,
            "tab_session_key": tab.session_key,
            "customer_name": "Cliente",
            "payment_method": "cash",
            "cash_shift_id": counter.shift.pk,
        },
        operator_username="marina",
    )


def test_cortesia_inteira_na_comanda_pede_gerente(counter):
    line = _line(discount=COURTESY)
    tab, rev = _tab_with([line])
    with pytest.raises(PosIntentError) as refused:
        counter.close(client_request_id="comanda-ctrl", items=[line], tab_session_key=tab.session_key,
                      expected_revision=rev, expected_total_q=0)
    assert refused.value.code == "manager_approval_required"


def test_preco_declarado_na_comanda_nao_esconde_o_desconto_do_gerente(counter):
    line = _line(discount=COURTESY)
    tab, rev = _tab_with([line])
    forged = {**line, "unit_price_q": 400}
    with pytest.raises(PosIntentError) as refused:
        counter.close(client_request_id="comanda-forjada", items=[forged], tab_session_key=tab.session_key,
                      expected_revision=rev, expected_total_q=0)
    assert refused.value.code == "manager_approval_required"
    assert not Order.objects.exists()


def test_revisao_da_comanda_mede_o_desconto_pelo_preco_do_servidor(counter):
    line = _line(discount=COURTESY)
    tab, _ = _tab_with([line])
    review = _review(counter, tab, [{**line, "unit_price_q": 400}])
    assert review.subtotal_q == 1200
    assert review.discount_q == 1200
    assert review.total_q == 0
    assert review.requires_manager_approval is True


def test_linha_nova_na_comanda_leva_a_etiqueta_do_motor(counter):
    """A linha que a comanda ainda não gravou também não traz preço do navegador."""
    Product.objects.create(sku="BRIOCHE", name="Brioche", base_price_q=1500, is_published=True, is_sellable=True)
    tab, rev = _tab_with([_line()])
    new_line = {"sku": "BRIOCHE", "name": "Brioche", "qty": 1, "unit_price_q": 300,
                "line_id": "L-bri00001", "discount": COURTESY}
    review = _review(counter, tab, [_line(), new_line])
    assert review.subtotal_q == 2700
    assert review.requires_manager_approval is True
    with pytest.raises(PosIntentError) as refused:
        counter.close(client_request_id="comanda-linha-nova", items=[_line(), new_line],
                      tab_session_key=tab.session_key, expected_revision=rev, expected_total_q=1200)
    assert refused.value.code == "manager_approval_required"


def test_desconto_abaixo_do_limite_na_comanda_fecha_sem_gerente(counter):
    """Controle: o caminho honesto continua igual (R$ 12,00 com 25%: R$ 3,00 de desconto)."""
    line = _line(discount={"type": "percent", "value": 25, "reason": "cortesia"})
    tab, rev = _tab_with([line])
    result = counter.close(client_request_id="comanda-honesta", items=[line], tab_session_key=tab.session_key,
                           expected_revision=rev, expected_total_q=900)
    assert Order.objects.get(ref=result.order_ref).total_q == 900


def test_venda_sem_comanda_com_preco_forjado_e_reprecificada(counter):
    """Controle: sem comanda e sem 'offline', o preço do navegador não vale."""
    with pytest.raises(PosIntentError):
        counter.close(
            client_request_id="direta-forjada",
            items=[{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1}],
            expected_total_q=1,
        )


# ── Promoção automática na comanda (beta test de 05/11/2026, P0) ─────────────
#
# O PDV manda a etiqueta em ``unit_price_q``. Sem desconto manual, a revisão
# somava a etiqueta (R$ 12,00), o selo do fechamento conferia contra o motor
# (R$ 10,20, com a Semana do Pão) e recusava com "O total mudou" em toda
# tentativa: a comanda com item em promoção não fechava nunca.


@pytest.fixture
def semana_do_pao(counter):
    from datetime import timedelta

    from django.core.cache import cache
    from django.utils import timezone

    from shopman.shop.models import Promotion

    now = timezone.now()
    Promotion.objects.create(
        ref="semana-do-pao", name="Semana do Pão", type=Promotion.PERCENT, value=15, is_active=True,
        skus=["PAO"], valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    cache.clear()
    return counter


def test_comanda_com_promocao_automatica_revisa_o_preco_do_motor(semana_do_pao):
    tab, _ = _tab_with([_line()])
    review = _review(semana_do_pao, tab, [_line()])
    assert review.total_q == 1020


def test_comanda_com_promocao_automatica_fecha_pelo_total_da_revisao(semana_do_pao):
    line = _line(qty=5)
    tab, rev = _tab_with([line])
    review = _review(semana_do_pao, tab, [line])
    assert review.total_q == 1020 * 5
    result = semana_do_pao.close(
        client_request_id="comanda-promo", items=[line], tab_session_key=tab.session_key,
        expected_revision=rev, expected_total_q=review.total_q,
    )
    assert Order.objects.get(ref=result.order_ref).total_q == 1020 * 5


def test_linha_nova_na_comanda_com_promocao_revisa_pelo_motor(semana_do_pao):
    """O carrinho que a comanda ainda não gravou passa pela sonda, com a mesma promoção."""
    tab, _ = _tab_with([_line()])
    review = _review(semana_do_pao, tab, [_line(qty=2)])
    assert review.total_q == 1020 * 2
