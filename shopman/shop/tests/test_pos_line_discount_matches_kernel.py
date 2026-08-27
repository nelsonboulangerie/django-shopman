"""A review mede o desconto de LINHA como o kernel mede.

Regressão de dinheiro provada numa venda real (PDV-260826-V03): o checkout exibiu
total R$ 44,78 e TROCO R$ 25,22; o pedido selou R$ 45,80 e registrou troco
R$ 24,20. A diferença de R$ 1,02 era uma cortesia de 10% numa linha que já levava
"Semana do Pão −15%" — o kernel descarta ("maior desconto ganha, um por item") e
a review somava assim mesmo. O operador devolveria R$ 1,02 a mais do que a gaveta
contava, em TODA venda com desconto de linha perdedor.
"""

import pytest

from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos import _payload_line_discounts_q


def _payload(**item):
    base = {"sku": "TAB", "qty": 2, "unit_price_q": 510}
    base.update(item)
    return {"items": [base]}


def test_desconto_de_linha_que_PERDE_do_automatico_nao_entra_na_conta():
    # Etiqueta 6,00; automático já tirou 0,90 (unit 5,10). Manual de 10% sobre a
    # etiqueta = 0,60 < 0,90 → o kernel descarta, e a review não pode prometer.
    payload = _payload(
        list_price_q=600,
        discount={"type": "percent", "value": 10, "reason": "cortesia"},
    )
    assert _payload_line_discounts_q(payload) == 0


def test_desconto_de_linha_que_GANHA_entra_pela_DIFERENCA():
    # Etiqueta 6,00; automático 0,90. Manual de 30% = 1,80 > 0,90 → substitui.
    # O subtotal da review já é pós-automático (5,10), então o que ainda sai é a
    # diferença: 1,80 − 0,90 = 0,90 por unidade.
    payload = _payload(
        list_price_q=600,
        discount={"type": "percent", "value": 30, "reason": "cortesia"},
    )
    assert _payload_line_discounts_q(payload) == 90 * 2


def test_linha_sem_desconto_automatico_desconta_o_percentual_inteiro():
    payload = {
        "items": [{
            "sku": "PAO", "qty": 1, "unit_price_q": 500, "list_price_q": 500,
            "discount": {"type": "percent", "value": 10, "reason": "cortesia"},
        }],
    }
    assert _payload_line_discounts_q(payload) == 50


def test_sem_etiqueta_declarada_a_linha_se_comporta_como_sem_automatico():
    # Venda sem comanda (o servidor não tem `_list_q` para carimbar): etiqueta e
    # preço cobrado são o mesmo número, e o manual vale inteiro.
    payload = _payload(discount={"type": "percent", "value": 10, "reason": "cortesia"})
    assert _payload_line_discounts_q(payload) == 51 * 2


def test_linha_sem_desconto_nao_soma_nada():
    assert _payload_line_discounts_q(_payload(list_price_q=600)) == 0


def test_desconto_nunca_passa_do_preco_cobrado_da_linha():
    payload = _payload(
        list_price_q=600,
        discount={"type": "percent", "value": 100, "reason": "cortesia"},
    )
    # 100% da etiqueta = 6,00; menos o automático de 0,90 = 5,10, que é
    # exatamente o preço cobrado — nunca mais que isso.
    assert _payload_line_discounts_q(payload) == 510 * 2


@pytest.mark.django_db
class TestOGateMedeOMesmoDinheiroQueAReview:
    """O carimbo da etiqueta tem de valer nas DUAS portas.

    O conserto acima vivia só no ``review_sale``. No ``close_sale`` o
    ``validate_manager_approval`` roda antes de a sessão ser resolvida, então o
    gate media o desconto num payload sem carimbo e caía no fallback
    ``list_price_q = unit_price_q`` — a conta velha. Duas consequências: a review
    prometia um número e o gate media outro (inflado), podendo exigir gerente logo
    depois de uma review que dissera que não precisava; e, num controle
    ANTI-FRAUDE, quem decidia o limiar passava a ser a etiqueta declarada pelo
    navegador, que é exatamente o que o carimbo existe para impedir.
    """

    def _tab_com_etiqueta(self) -> str:
        """Abre comanda com a linha do Batard: etiqueta 13,00, lote tirou 1,95."""
        from shopman.offerman.models import Product
        from shopman.orderman.models import Session

        from shopman.shop.models import Channel

        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        Product.objects.create(
            sku="BATARD", name="Batard", base_price_q=1300,
            is_published=True, is_sellable=True,
        )
        session_key = pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="1007",
            actor="pos:alice", operator_username="alice",
        ).session_key
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "tab_session_key": session_key,
                "items": [{"sku": "BATARD", "name": "Batard", "qty": 1, "unit_price_q": 1105}],
            },
            actor="pos:alice", operator_username="alice",
        )
        session = Session.objects.get(session_key=session_key)
        items = session.items
        items[0]["meta"] = {**(items[0].get("meta") or {}), "_list_q": 1300}
        items[0]["unit_price_q"] = 1105
        session.update_items(items)
        return session_key

    def test_o_gate_recebe_o_payload_ja_carimbado(self, monkeypatch) -> None:
        session_key = self._tab_com_etiqueta()
        visto: dict = {}

        class _Parou(Exception):
            """Interrompe o close logo depois do gate: aqui só o gate importa."""

        def _espiao(payload, *, operator_username=""):
            visto["list_price_q"] = payload["items"][0].get("list_price_q")
            visto["discount_q"] = pos_service._payload_discount_q(payload)
            raise _Parou

        monkeypatch.setattr(pos_service, "validate_manager_approval", _espiao)

        with pytest.raises(_Parou):
            pos_service.close_sale(
                channel_ref="pdv",
                payload={
                    "tab_session_key": session_key,
                    # O navegador NÃO mandou a etiqueta (ou mandaria a errada):
                    # quem manda é a sessão.
                    "items": [{
                        "sku": "BATARD", "name": "Batard", "qty": 1, "unit_price_q": 1105,
                        "discount": {"type": "percent", "value": 10, "reason": "cortesia"},
                    }],
                    "payment_method": "cash",
                },
                actor="pos:alice", operator_username="alice",
            )

        # A etiqueta chegou da SESSÃO, não do navegador.
        assert visto["list_price_q"] == 1300
        # E com ela o gate mede o que o kernel vai cobrar: a cortesia de 10%
        # (1,30) perde do lote já aplicado (1,95), então não há desconto nenhum.
        # Sem o carimbo o gate veria 1,10 e poderia exigir gerente por um desconto
        # que a venda nunca daria.
        assert visto["discount_q"] == 0
