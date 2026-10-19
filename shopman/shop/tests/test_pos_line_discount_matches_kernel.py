"""A review mede o desconto de LINHA como o kernel mede, porque quem mede é o kernel.

Regressão de dinheiro provada numa venda real (PDV-260826-V03): o checkout exibiu
total R$ 44,78 e TROCO R$ 25,22; o pedido selou R$ 45,80 e registrou troco
R$ 24,20. A diferença de R$ 1,02 era uma cortesia de 10% numa linha que já levava
"Semana do Pão −15%" — o kernel descarta ("maior desconto ganha, um por item") e
a review somava assim mesmo.

O primeiro conserto foi uma conta do PDV que imitava o kernel, e ela divergiu de
novo no arredondamento (A3-1, laudo CORE-SOVEREIGNTY de 18/10/2026). Agora a
review pergunta ao motor (``_stamp_engine_manual_discounts``), e estes testes
passam pela review de verdade, com uma promoção de verdade no ar: o que eles
travam é a política, não uma segunda implementação dela.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def semana_do_pao():
    """Tabatière de R$ 6,00 com "Semana do Pão −15%" no ar (automático de R$ 0,90)."""
    from shopman.offerman.models import Listing, ListingItem, Product

    from shopman.shop.models import Channel, Promotion

    Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
    get_user_model().objects.create_user(username="alice", password="x")
    listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
    for sku, price_q in (("TAB", 600), ("PAO", 500)):
        product = Product.objects.create(
            sku=sku, name=sku, base_price_q=price_q, is_published=True, is_sellable=True,
        )
        ListingItem.objects.create(listing=listing, product=product, price_q=price_q)
    now = timezone.now()
    Promotion.objects.create(
        ref="semana-do-pao", name="Semana do Pão", type=Promotion.PERCENT, value=15, is_active=True,
        skus=["TAB"], valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1),
    )
    cache.clear()


def _review(sku: str, discount: dict | None, *, qty: int = 2):
    item = {"line_id": "L1", "sku": sku, "name": sku, "qty": qty, "unit_price_q": 0}
    if discount:
        item["discount"] = {"reason": "cortesia", **discount}
    return pos_service.review_sale(
        channel_ref="pdv",
        payload={"items": [item], "fulfillment_type": "pickup", "payment_method": "cash"},
        operator_username="alice",
    )


def test_desconto_de_linha_que_PERDE_do_automatico_nao_entra_na_conta(semana_do_pao):
    # Manual de 10% sobre a etiqueta = 0,60 < 0,90 → o kernel descarta.
    review = _review("TAB", {"type": "percent", "value": 10})
    assert review.subtotal_q == 510 * 2
    assert review.line_discount_q == 0
    assert review.total_q == 510 * 2


def test_desconto_de_linha_que_GANHA_entra_pela_DIFERENCA(semana_do_pao):
    # Manual de 30% = 1,80 > 0,90 → substitui. Sai a diferença: 0,90 por unidade.
    review = _review("TAB", {"type": "percent", "value": 30})
    assert review.line_discount_q == 90 * 2
    assert review.total_q == 420 * 2


def test_linha_sem_desconto_automatico_desconta_o_percentual_inteiro(semana_do_pao):
    review = _review("PAO", {"type": "percent", "value": 10}, qty=1)
    assert review.line_discount_q == 50
    assert review.total_q == 450


def test_linha_sem_desconto_nao_soma_nada(semana_do_pao):
    review = _review("TAB", None)
    assert review.line_discount_q == 0
    assert review.total_q == 510 * 2


def test_desconto_nunca_passa_do_preco_da_linha(semana_do_pao):
    # 100% da etiqueta = 6,00; menos o automático de 0,90 = 5,10, que é
    # exatamente o preço cobrado — nunca mais que isso.
    review = _review("TAB", {"type": "percent", "value": 100})
    assert review.line_discount_q == 510 * 2
    assert review.total_q == 0


# ── O MESMO, em REAIS ────────────────────────────────────────────────────────
#
# O valor é POR UNIDADE, de propósito: é assim que ele compete com o automático
# no "maior desconto ganha", que mede tudo por unidade contra a etiqueta.


def test_reais_que_PERDE_do_automatico_nao_entra_na_conta(semana_do_pao):
    review = _review("TAB", {"type": "fixed", "value": 0.60})
    assert review.line_discount_q == 0
    assert review.total_q == 510 * 2


def test_reais_que_GANHA_entra_pela_DIFERENCA(semana_do_pao):
    review = _review("TAB", {"type": "fixed", "value": 1.80})
    assert review.line_discount_q == 90 * 2
    assert review.total_q == 420 * 2


def test_reais_sem_automatico_sai_inteiro_por_unidade(semana_do_pao):
    review = _review("PAO", {"type": "fixed", "value": 1.00})
    assert review.line_discount_q == 200
    assert review.total_q == 800


def test_reais_acima_da_etiqueta_nao_passa_do_preco(semana_do_pao):
    review = _review("PAO", {"type": "fixed", "value": 50.0})
    assert review.line_discount_q == 500 * 2
    assert review.total_q == 0


class TestOGateMedeOMesmoDinheiroQueAReview:
    """O desconto do motor tem de valer nas DUAS portas.

    No ``close_sale`` o ``validate_manager_approval`` roda antes de a sessão ser
    regravada. Se o gate medisse por conta própria, a review prometeria um número
    e o gate mediria outro, podendo exigir gerente logo depois de uma review que
    dissera que não precisava; e, num controle ANTI-FRAUDE, quem decidiria o
    limiar seria a etiqueta declarada pelo navegador.
    """

    def test_o_gate_recebe_o_desconto_do_motor(self, semana_do_pao, monkeypatch) -> None:
        session_key = pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="1007", actor="pos:alice", operator_username="alice",
        ).session_key
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={"tab_session_key": session_key, "items": [
                {"line_id": "L1", "sku": "TAB", "name": "TAB", "qty": 1, "unit_price_q": 510},
            ]},
            actor="pos:alice", operator_username="alice",
        )
        visto: dict = {}
        payload = {
            "tab_session_key": session_key,
            # O navegador NÃO mandou a etiqueta (ou mandaria a errada).
            "items": [{
                "line_id": "L1", "sku": "TAB", "name": "TAB", "qty": 1, "unit_price_q": 510,
                "discount": {"type": "percent", "value": 10, "reason": "cortesia"},
            }],
            "payment_method": "cash",
        }
        review = pos_service.review_sale(channel_ref="pdv", payload=payload, operator_username="alice")
        payload["expected_total_q"] = review.total_q

        class _Parou(Exception):
            """Interrompe o close logo depois do gate: aqui só o gate importa."""

        def _espiao(payload, *, operator_username=""):
            visto["list_price_q"] = payload["items"][0].get("list_price_q")
            visto["discount_q"] = pos_service._payload_discount_q(payload)
            raise _Parou

        monkeypatch.setattr(pos_service, "validate_manager_approval", _espiao)

        with pytest.raises(_Parou):
            pos_service.close_sale(channel_ref="pdv", payload=payload, actor="pos:alice", operator_username="alice")

        # A etiqueta chegou da SESSÃO, não do navegador.
        assert visto["list_price_q"] == 600
        # A cortesia de 10% (0,60) perde da Semana do Pão (0,90): desconto nenhum,
        # na review e no gate.
        assert review.discount_q == 0
        assert visto["discount_q"] == 0


def test_somar_desconto_manual_sem_o_motor_falha_gritando():
    """Sem o carimbo do motor não há conta: devolver zero cobraria a mais calado."""
    payload = {"items": [{"sku": "TAB", "qty": 1, "unit_price_q": 600, "discount": {"value": 10}}]}
    with pytest.raises(RuntimeError, match="motor"):
        pos_service._payload_line_discounts_q(payload)


def test_o_teto_de_100_nao_estraga_o_valor_em_reais():
    # `pos_intent._line_discount` clampava em 100 sem olhar o tipo: R$ 150,00
    # virava R$ 100,00 em silêncio. O clamp é do percentual.
    from shopman.shop.services.pos_intent import _line_discount

    assert _line_discount({"type": "fixed", "value": 150.0, "reason": "cortesia"}) == {
        "type": "fixed",
        "value": 150.0,
        "reason": "cortesia",
    }
    assert _line_discount({"type": "percent", "value": 150.0, "reason": "cortesia"})["value"] == 100.0


def test_formato_desconhecido_cai_em_percentual():
    from shopman.shop.services.pos_intent import _line_discount

    assert _line_discount({"type": "esquisito", "value": 10, "reason": "x"})["type"] == "percent"
    assert pos_service._normalize_line_discount({"type": "esquisito", "value": 10})["type"] == "percent"
