"""A janela combinada tem que caber no expediente E no preparo.

O caso que dá nome a tudo: *"Se tem baguete de tradição no pedido, mas ela só sai
depois do meio-dia, não tem como poder escolher os slots das 9h."* Prometer 09:00
para um pão que sai às 12:00 é quebra de contrato na porta, e o cliente que
aparece às 9h tem razão.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from shopman.offerman.models import Product

from shopman.shop.models import Shop
from shopman.shop.services import fulfillment_window

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("America/Sao_Paulo")

ABERTO_SEG_A_SAB = {
    "monday": {"open": "08:00", "close": "18:00"},
    "tuesday": {"open": "08:00", "close": "18:00"},
    "wednesday": {"open": "08:00", "close": "18:00"},
    "thursday": {"open": "08:00", "close": "18:00"},
    "friday": {"open": "08:00", "close": "18:00"},
    "saturday": {"open": "08:00", "close": "18:00"},
}

# Uma quinta-feira futura, para nenhum teste depender do relógio de hoje.
QUINTA = date(2026, 9, 10)
DOMINGO = date(2026, 9, 13)
#: Bem antes do expediente do dia — assim a antecedência de hoje nunca entra na
#: conta e o que sobra medido é só a prontidão.
AGORA = datetime(2026, 9, 10, 6, 0, tzinfo=TZ)


@pytest.fixture
def loja():
    return Shop.objects.create(
        name="Nelson", timezone="America/Sao_Paulo", opening_hours=ABERTO_SEG_A_SAB
    )


@pytest.fixture
def baguete():
    return Product.objects.create(
        sku="BF",
        name="Baguette de Tradition",
        base_price_q=1600,
        metadata={"ready_from": "12:00"},
    )


@pytest.fixture
def croissant():
    return Product.objects.create(sku="CR", name="Croissant", base_price_q=900, metadata={})


class TestAnnotate:
    def test_sem_carrinho_todas_as_janelas_valem(self, loja):
        ctx = fulfillment_window.annotate(QUINTA, [], now=AGORA)
        assert ctx["windows"]
        assert all(w["enabled"] for w in ctx["windows"])
        assert ctx["earliest_ref"] == "08:00-08:30"
        assert ctx["ready_at"] == ""

    def test_a_baguete_desabilita_a_manha(self, loja, baguete):
        ctx = fulfillment_window.annotate(QUINTA, ["BF"], now=AGORA)

        por_ref = {w["ref"]: w for w in ctx["windows"]}
        assert por_ref["09:00-09:30"]["enabled"] is False
        assert por_ref["11:30-12:00"]["enabled"] is False, "a janela COMEÇA às 11:30"
        assert por_ref["12:00-12:30"]["enabled"] is True
        assert ctx["earliest_ref"] == "12:00-12:30"
        assert ctx["ready_at"] == "12:00"
        assert ctx["bottleneck_sku"] == "BF"

    def test_a_janela_impossivel_aparece_com_o_motivo(self, loja, baguete):
        """Sumir com ela deixa o operador sem resposta para "e às 9h não dá?"."""
        ctx = fulfillment_window.annotate(QUINTA, ["BF"], now=AGORA)

        nove = next(w for w in ctx["windows"] if w["ref"] == "09:00-09:30")
        assert nove["reason"] == "Baguette de Tradition sai às 12:00."

    def test_o_motivo_fala_do_produto_nao_do_sku(self, loja, baguete):
        ctx = fulfillment_window.annotate(QUINTA, ["BF"], now=AGORA)
        nove = next(w for w in ctx["windows"] if w["ref"] == "09:00-09:30")
        assert "BF" not in nove["reason"]

    def test_vence_o_item_mais_tardio_do_carrinho(self, loja, baguete, croissant):
        ctx = fulfillment_window.annotate(QUINTA, ["CR", "BF"], now=AGORA)
        assert ctx["earliest_ref"] == "12:00-12:30"
        assert ctx["bottleneck_sku"] == "BF"

    def test_carrinho_sem_prontidao_conhecida_nao_restringe(self, loja, croissant):
        """Silêncio não vira restrição. Não há o que prometer errado sobre uma
        hora que ninguém sabe — é a declaração que tira o produto desse limbo."""
        ctx = fulfillment_window.annotate(QUINTA, ["CR"], now=AGORA)
        assert all(w["enabled"] for w in ctx["windows"])

    def test_dia_fechado_nao_tem_janela(self, loja, baguete):
        """Vazio é "não há expediente" — bem diferente de "todas desabilitadas"."""
        assert fulfillment_window.annotate(DOMINGO, ["BF"], now=AGORA)["windows"] == []


class TestValidate:
    def test_aceita_a_janela_compativel(self, loja, baguete):
        assert fulfillment_window.validate(QUINTA, "12:00-12:30", ["BF"], now=AGORA) is None

    def test_recusa_a_janela_antes_do_preparo(self, loja, baguete):
        erro = fulfillment_window.validate(QUINTA, "09:00-09:30", ["BF"], now=AGORA)
        assert erro is not None
        assert "Baguette de Tradition sai às 12:00." in erro
        assert "12:00 às 12:30" in erro, "o erro diz o que fazer, não só o que deu errado"

    def test_o_expediente_nao_fecha_a_porta(self, loja):
        """23:00 num dia que fecha às 18h passa — e isso é deliberado.

        A grade diz o que a casa OFERECE. Recusar aqui faria a dona, no balcão
        às 18h05, não conseguir agendar a retirada de amanhã; e faria uma loja com
        `opening_hours` em branco (grade vazia) recusar TODA venda com horário.
        Nada disso é promessa quebrada — é a casa mandando na própria agenda.
        """
        assert fulfillment_window.validate(QUINTA, "23:00-23:30", [], now=AGORA) is None
        assert fulfillment_window.validate(DOMINGO, "09:00-09:30", [], now=AGORA) is None

    def test_mas_a_prontidao_fecha_ate_em_dia_fechado(self, loja, baguete):
        """O eixo que importa não depende da grade existir."""
        erro = fulfillment_window.validate(DOMINGO, "09:00-09:30", ["BF"], now=AGORA)
        assert erro is not None
        assert "Baguette de Tradition sai às 12:00." in erro
        assert "outra data" in erro, "sem grade nesse dia, a saída é trocar o dia"

    def test_horario_em_formato_livre_passa(self, loja, baguete):
        """"manhã" não tem eixo de hora — não há o que conferir."""
        assert fulfillment_window.validate(QUINTA, "manhã", ["BF"], now=AGORA) is None

    def test_janela_em_branco_passa(self, loja, baguete):
        """"A combinar" é resposta legítima do balcão; exigir hora aqui
        inventaria fricção que a casa não tem."""
        assert fulfillment_window.validate(QUINTA, "", ["BF"], now=AGORA) is None

    def test_a_declaracao_sozinha_ja_fecha_a_porta(self, loja):
        """O caso que o histórico deixava passar: produto SEM fornada nenhuma.

        Antes de `ready_from` existir, este carrinho não restringia horário
        nenhum, porque a única fonte era a mediana das WorkOrders — e não havia
        WorkOrder.
        """
        Product.objects.create(
            sku="NOVO", name="Pão novo", base_price_q=100, metadata={"ready_from": "15:00"}
        )
        assert fulfillment_window.validate(QUINTA, "09:00-09:30", ["NOVO"], now=AGORA)
        assert fulfillment_window.validate(QUINTA, "15:00-15:30", ["NOVO"], now=AGORA) is None
