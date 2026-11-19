"""O checkout diz do dinheiro e usa o relógio da loja (WP-L05 do plano EXCELENCIA-STOREFRONT).

P1-06: antes de "Enviar pedido" a cliente não lia que paga agora, que a loja confere
em seguida, nem que o valor volta se a loja não confirmar. A frase sai do servidor,
com o prazo de aceite do canal (5 min no dia, 60 na encomenda e com a casa fechada;
dono, 09/11/2026), contado em tempo de loja aberta.

P2-08: "hoje" e os limites do calendário vinham do relógio do aparelho; a projeção
passa a publicar o "hoje" da loja.

P1-11: a recusa de estoque no envio chegava à tela sem o item e mandando "ajustar o
carrinho"; agora leva o código e o item.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from shopman.orderman.exceptions import ValidationError as OrderingValidationError
from shopman.orderman.models import Order

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop
from shopman.shop.projections import checkout as checkout_projection
from shopman.storefront.api.views import _stock_refusal_payload
from shopman.storefront.presentation.checkout import _money_notices

pytestmark = pytest.mark.django_db

SP = ZoneInfo("America/Sao_Paulo")
WEB = {
    "confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "preorder_timeout_minutes": 60},
    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
}
OPEN_9_TO_18 = {
    day: {"open": "09:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
}
# Quarta-feira, 18/11/2026.
WEDNESDAY = datetime(2026, 11, 18, tzinfo=SP).date()
THURSDAY = WEDNESDAY + timedelta(days=1)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 18, hour, minute, tzinfo=SP)


@pytest.fixture
def web_shop():
    Shop.objects.create(name="Casa de teste", opening_hours=OPEN_9_TO_18)
    Channel.objects.update_or_create(
        ref="web", defaults={"name": "Loja online", "is_active": True, "config": WEB},
    )


def _methods(*refs):
    return tuple(SimpleNamespace(ref=ref) for ref in refs)


def _notices(*, order_date, now):
    found = _money_notices("web", _methods("pix", "card"), order_date.isoformat() if order_date else "", now=now)
    return {notice.method: notice.text for notice in found}


# ── o prazo de aceite ──────────────────────────────────────────────────


class TestAcceptanceWindow:
    def test_pedido_do_dia_com_a_casa_aberta_tem_o_prazo_curto_e_cabe_no_expediente(self, web_shop):
        window = checkout_projection.acceptance_window("web", order_date=WEDNESDAY, now=_at(10))

        assert window.minutes == 5
        assert window.runs_now is True
        assert window.deadline == _at(10, 5)

    def test_encomenda_tem_o_prazo_longo(self, web_shop):
        window = checkout_projection.acceptance_window("web", order_date=THURSDAY, now=_at(10))

        assert window.minutes == 60
        assert window.runs_now is True
        assert window.deadline == _at(11)

    def test_prazo_que_nao_cabe_ate_o_fechamento_continua_na_abertura_seguinte(self, web_shop):
        # 17h30, a casa fecha às 18h: 30 min hoje e 30 min depois de abrir amanhã.
        window = checkout_projection.acceptance_window("web", order_date=THURSDAY, now=_at(17, 30))

        assert window.minutes == 60
        assert window.runs_now is False
        assert window.deadline == datetime(2026, 11, 19, 9, 30, tzinfo=SP)

    def test_casa_fechada_vale_o_prazo_longo_mesmo_para_hoje(self, web_shop):
        window = checkout_projection.acceptance_window("web", order_date=None, now=_at(20))

        assert window.minutes == 60
        assert window.runs_now is False
        assert window.deadline == datetime(2026, 11, 19, 10, 0, tzinfo=SP)

    @pytest.mark.parametrize(
        ("order_date", "hour"),
        [(WEDNESDAY, 10), (THURSDAY, 10), (WEDNESDAY, 20), (THURSDAY, 20), (None, 10), (None, 20)],
    )
    def test_a_regua_e_a_mesma_de_quem_agenda_o_cancelamento(self, web_shop, order_date, hour):
        """Uma régua só: o que a tela promete é o que o lifecycle agenda."""
        from shopman.shop.lifecycle import acceptance_timeout_minutes

        data = {"payment": {"method": "pix"}}
        if order_date is not None:
            data["delivery_date"] = order_date.isoformat()
        order = Order.objects.create(ref=f"WEB-{hour}-{order_date}", channel_ref="web", status=Order.Status.NEW, total_q=1500, data=data)
        moment = _at(hour)

        window = checkout_projection.acceptance_window("web", order_date=order_date, now=moment)

        assert window.minutes == acceptance_timeout_minutes(order, ChannelConfig.for_channel("web"), now=moment)

    def test_outro_modo_de_confirmacao_nao_tem_prazo_a_prometer(self, web_shop):
        Channel.objects.filter(ref="web").update(
            config={**WEB, "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5}},
        )

        assert checkout_projection.acceptance_window("web", order_date=WEDNESDAY, now=_at(10)) is None


# ── a frase do dinheiro ────────────────────────────────────────────────


class TestMoneyNotices:
    def test_pix_no_dia_paga_agora_e_volta_inteiro(self, web_shop):
        assert _notices(order_date=WEDNESDAY, now=_at(10))["pix"] == (
            "Você paga agora, pelo Pix. A loja confirma o pedido em até 5 minutos; "
            "se não confirmar, o valor volta inteiro para a mesma conta."
        )

    def test_cartao_fica_reservado_e_so_e_cobrado_no_aceite(self, web_shop):
        assert _notices(order_date=WEDNESDAY, now=_at(10))["card"] == (
            "O valor fica reservado no cartão agora e só é cobrado quando a loja confirmar "
            "o pedido, em até 5 minutos. Se não confirmar, a reserva é desfeita e nada é cobrado."
        )

    def test_encomenda_com_a_casa_aberta_diz_60_minutos(self, web_shop):
        assert "em até 60 minutos" in _notices(order_date=THURSDAY, now=_at(10))["pix"]

    def test_com_a_casa_fechada_diz_a_hora_em_que_o_prazo_vence_e_nao_minutos(self, web_shop):
        text = _notices(order_date=THURSDAY, now=_at(20))["pix"]

        assert "A loja confirma o pedido até amanhã, quinta, às 10h;" in text
        assert "minutos" not in text

    def test_prazo_que_atravessa_o_fechamento_diz_a_hora_de_amanha(self, web_shop):
        assert "até amanhã, quinta, às 9h30" in _notices(order_date=THURSDAY, now=_at(17, 30))["card"]

    def test_antes_de_abrir_o_prazo_vence_hoje(self, web_shop):
        assert "até hoje, às 10h" in _notices(order_date=WEDNESDAY, now=_at(7))["pix"]

    def test_so_as_formas_do_canal_ganham_frase(self, web_shop):
        found = _money_notices("web", _methods("pix", "cash"), WEDNESDAY.isoformat(), now=_at(10))

        assert [notice.method for notice in found] == ["pix"]

    def test_loja_que_nao_cobra_ao_pedir_nao_tem_frase(self, web_shop):
        Channel.objects.filter(ref="web").update(
            config={**WEB, "payment": {"method": ["pix"], "timing": "post_commit"}},
        )

        assert _notices(order_date=WEDNESDAY, now=_at(10)) == {}

    def test_a_frase_nao_usa_travessao_nem_carrinho(self, web_shop):
        for text in _notices(order_date=THURSDAY, now=_at(20)).values():
            assert "—" not in text and "–" not in text
            assert "carrinho" not in text


# ── o relógio da loja ──────────────────────────────────────────────────


def test_o_hoje_da_loja_e_o_do_fuso_dela(web_shop):
    # 23h30 de quarta em São Paulo já é quinta em UTC: o "hoje" da loja é quarta.
    assert checkout_projection.shop_today(now=_at(23, 30)) == WEDNESDAY


# ── a recusa de estoque no envio ───────────────────────────────────────


class TestStockRefusal:
    def test_leva_o_codigo_e_o_item_e_fala_a_voz_da_loja(self, web_shop):
        from shopman.offerman.models import Product

        Product.objects.create(sku="TABAT", name="Tabatière", base_price_q=600, is_published=True, is_sellable=True)
        exc = OrderingValidationError(
            code="insufficient_supply",
            message="Tabatière ficou indisponível antes de concluirmos a sua reserva. Ajuste o carrinho e tente novamente, por favor.",
            context={"sku": "TABAT", "component_sku": "TABAT", "requested_qty": "2", "error_code": "INSUFFICIENT_AVAILABLE"},
        )

        payload = _stock_refusal_payload(exc)

        assert payload["error_code"] == "insufficient_supply"
        assert payload["detail"] == "Tabatière ficou indisponível antes de concluirmos o seu pedido."
        assert payload["field"] == "checkout"
        assert payload["errors"] == {"checkout": payload["detail"]}
        assert payload["context"] == {"sku": "TABAT", "name": "Tabatière", "requested_qty": "2", "is_paused": False}
        assert "carrinho" not in payload["detail"]

    def test_item_pausado_e_marcado(self, web_shop):
        exc = OrderingValidationError(
            code="insufficient_supply", message="x", context={"sku": "MDLN", "error_code": "SKU_PAUSED"},
        )

        assert _stock_refusal_payload(exc)["context"]["is_paused"] is True

    def test_outras_recusas_seguem_o_caminho_de_antes(self, web_shop):
        exc = OrderingValidationError(code="lead_time", message="x", context={"sku": "TABAT"})

        assert _stock_refusal_payload(exc) is None
        assert _stock_refusal_payload(ValueError("x")) is None
