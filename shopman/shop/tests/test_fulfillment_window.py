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

# Datas fixas, para nenhum teste depender do relógio de quem roda a suíte.
#
# ⚠️ HOJE e QUINTA não são intercambiáveis: é a DATA que escolhe a grade. HOJE
# devolve as meias horas do expediente; QUINTA (encomenda) devolve os 3 slots
# canônicos da casa. Trocar um pelo outro faz o teste medir a grade errada.
HOJE = date(2026, 9, 8)      # terça
QUINTA = date(2026, 9, 10)   # encomenda
DOMINGO = date(2026, 9, 13)  # fechado
#: Bem antes do expediente — assim a antecedência de hoje nunca entra na conta e
#: o que sobra medido é só a prontidão.
AGORA = datetime(2026, 9, 8, 6, 0, tzinfo=TZ)


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
        ctx = fulfillment_window.annotate(HOJE, [], now=AGORA)
        assert ctx["windows"]
        assert all(w["enabled"] for w in ctx["windows"])
        assert ctx["earliest_ref"] == "08:00-08:30"
        assert ctx["ready_at"] == ""

    def test_a_baguete_desabilita_a_manha(self, loja, baguete):
        ctx = fulfillment_window.annotate(HOJE, ["BF"], now=AGORA)

        por_ref = {w["ref"]: w for w in ctx["windows"]}
        assert por_ref["09:00-09:30"]["enabled"] is False
        assert por_ref["11:30-12:00"]["enabled"] is False, "a janela COMEÇA às 11:30"
        assert por_ref["12:00-12:30"]["enabled"] is True
        assert ctx["earliest_ref"] == "12:00-12:30"
        assert ctx["ready_at"] == "12:00"
        assert ctx["bottleneck_sku"] == "BF"

    def test_a_janela_impossivel_aparece_com_o_motivo(self, loja, baguete):
        """Sumir com ela deixa o operador sem resposta para "e às 9h não dá?"."""
        ctx = fulfillment_window.annotate(HOJE, ["BF"], now=AGORA)

        nove = next(w for w in ctx["windows"] if w["ref"] == "09:00-09:30")
        assert nove["reason"] == "Baguette de Tradition sai às 12:00."

    def test_o_motivo_fala_do_produto_nao_do_sku(self, loja, baguete):
        ctx = fulfillment_window.annotate(HOJE, ["BF"], now=AGORA)
        nove = next(w for w in ctx["windows"] if w["ref"] == "09:00-09:30")
        assert "BF" not in nove["reason"]

    def test_vence_o_item_mais_tardio_do_carrinho(self, loja, baguete, croissant):
        ctx = fulfillment_window.annotate(HOJE, ["CR", "BF"], now=AGORA)
        assert ctx["earliest_ref"] == "12:00-12:30"
        assert ctx["bottleneck_sku"] == "BF"

    def test_carrinho_sem_prontidao_conhecida_nao_restringe(self, loja, croissant):
        """Silêncio não vira restrição. Não há o que prometer errado sobre uma
        hora que ninguém sabe — é a declaração que tira o produto desse limbo."""
        ctx = fulfillment_window.annotate(HOJE, ["CR"], now=AGORA)
        assert all(w["enabled"] for w in ctx["windows"])

    def test_dia_fechado_nao_tem_janela(self, loja, baguete):
        """Vazio é "não há expediente" — bem diferente de "todas desabilitadas"."""
        assert fulfillment_window.annotate(DOMINGO, ["BF"], now=AGORA)["windows"] == []


class TestValidate:
    def test_aceita_a_janela_compativel(self, loja, baguete):
        assert fulfillment_window.validate(HOJE, "12:00-12:30", ["BF"], now=AGORA) is None

    def test_recusa_a_janela_antes_do_preparo(self, loja, baguete):
        erro = fulfillment_window.validate(HOJE, "09:00-09:30", ["BF"], now=AGORA)
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
        assert fulfillment_window.validate(HOJE, "23:00-23:30", [], now=AGORA) is None
        assert fulfillment_window.validate(DOMINGO, "09:00-09:30", [], now=AGORA) is None

    def test_mas_a_prontidao_fecha_ate_em_dia_fechado(self, loja, baguete):
        """O eixo que importa não depende da grade existir."""
        erro = fulfillment_window.validate(DOMINGO, "09:00-09:30", ["BF"], now=AGORA)
        assert erro is not None
        assert "Baguette de Tradition sai às 12:00." in erro
        assert "outra data" in erro, "sem grade nesse dia, a saída é trocar o dia"

    def test_horario_ILEGIVEL_e_recusado_quando_ha_prontidao(self, loja, baguete):
        """⚠️ Este teste já afirmou o contrário, e afirmava um BURACO.

        "09:00-09:30" era recusado, mas "09:00 às 09:30" — o RÓTULO que a
        própria tela mostra — passava e era gravado. A guarda era derrotável
        pela string que o sistema exibe: bastava uma fila offline, um cliente
        novo ou um copiar-colar.
        """
        # Nenhum passa. Dois caminhos de recusa, e os dois servem: o que ainda
        # se lê como hora ("09:00") cai na prontidão; o que não se lê cai no
        # "não reconhecido".
        for ilegivel in ("manhã", "09:00 às 09:30", "9"):
            erro = fulfillment_window.validate(HOJE, ilegivel, ["BF"], now=AGORA)
            assert erro is not None, f"{ilegivel!r} passou"
            assert "não reconhecido" in erro, f"{ilegivel!r}: {erro}"

        erro_hora = fulfillment_window.validate(HOJE, "09:00", ["BF"], now=AGORA)
        assert erro_hora is not None
        assert "Baguette de Tradition sai às 12:00." in erro_hora

    def test_mas_sem_prontidao_no_carrinho_o_ilegivel_passa(self, loja, croissant):
        """Sem promessa a proteger, recusar seria negar venda por nada."""
        assert fulfillment_window.validate(HOJE, "manhã", ["CR"], now=AGORA) is None

    def test_janela_de_HOJE_que_ja_passou_NAO_e_recusada(self, loja):
        """Deliberado, e a suíte do repo é que mostrou o preço da alternativa.

        Recusar aqui derrubaria a comanda aberta às 13h40 com "14:00 às 14:30" e
        fechada às 14h35 — almoço movimentado, cliente que voltou para pegar mais
        um pão. Venda recusada com o cliente na frente, e o operador sem gesto.

        A grade de hoje já não OFERECE a janela passada; isso basta. Só a
        prontidão fecha a porta.
        """
        tarde = datetime(2026, 9, 8, 17, 0, tzinfo=TZ)

        assert fulfillment_window.validate(HOJE, "08:00-08:30", [], now=tarde) is None
        # Mas a prontidão continua fechando, na mesma janela passada.
        Product.objects.create(
            sku="TARDIO", name="Pão tardio", base_price_q=100,
            metadata={"ready_from": "18:00"},
        )
        assert fulfillment_window.validate(HOJE, "08:00-08:30", ["TARDIO"], now=tarde)

    def test_janela_em_branco_passa(self, loja, baguete):
        """"A combinar" é resposta legítima do balcão; exigir hora aqui
        inventaria fricção que a casa não tem."""
        assert fulfillment_window.validate(HOJE, "", ["BF"], now=AGORA) is None

    def test_a_declaracao_sozinha_ja_fecha_a_porta(self, loja):
        """O caso que o histórico deixava passar: produto SEM fornada nenhuma.

        Antes de `ready_from` existir, este carrinho não restringia horário
        nenhum, porque a única fonte era a mediana das WorkOrders — e não havia
        WorkOrder.
        """
        Product.objects.create(
            sku="NOVO", name="Pão novo", base_price_q=100, metadata={"ready_from": "15:00"}
        )
        assert fulfillment_window.validate(HOJE, "09:00-09:30", ["NOVO"], now=AGORA)
        assert fulfillment_window.validate(HOJE, "15:00-15:30", ["NOVO"], now=AGORA) is None


class TestDuasGrades:
    """A data escolhe a grade: meia hora hoje, slot canônico na encomenda.

    Encomenda não é hora marcada, é fornada — o cliente escolhe o TURNO, e é
    assim que a loja já pergunta. Oferecer meia hora para daqui a três dias seria
    precisão que a padaria não tem, e faria loja e balcão prometerem coisas
    diferentes sobre o mesmo pedido.
    """

    def test_hoje_usa_meia_hora(self, loja):
        hoje = AGORA.date()
        refs = [w["ref"] for w in fulfillment_window.annotate(hoje, [], now=AGORA)["windows"]]

        assert "08:00-08:30" in refs
        assert fulfillment_window.annotate(hoje, [], now=AGORA)["grid"] == "half_hour"

    def test_encomenda_usa_os_tres_slots_canonicos(self, loja):
        ctx = fulfillment_window.annotate(QUINTA, [], now=AGORA)

        assert [w["ref"] for w in ctx["windows"]] == ["slot-09", "slot-12", "slot-15"]
        assert [w["label"] for w in ctx["windows"]] == [
            "A partir das 09h", "A partir das 12h", "A partir das 15h",
        ]
        assert ctx["grid"] == "canonical"
        assert ctx["is_today"] is False

    def test_a_casa_manda_nos_slots_pelo_admin(self, loja):
        """`Shop.defaults["pickup_slots"]` é a fonte, e ela é editável no Admin."""
        loja.defaults = {
            **(loja.defaults or {}),
            "pickup_slots": [
                {"ref": "manha", "label": "Manhã", "starts_at": "08:30"},
                {"ref": "tarde", "label": "Tarde", "starts_at": "16:00"},
            ],
        }
        loja.save(update_fields=["defaults"])

        ctx = fulfillment_window.annotate(QUINTA, [], now=AGORA)
        assert [w["ref"] for w in ctx["windows"]] == ["manha", "tarde"]

    def test_o_expediente_do_dia_limita_o_slot_canonico(self, loja):
        """Slot configurado fora do expediente não é oferecido.

        O canônico é config da casa e não sabe do calendário: numa loja que
        fecha às 18h, um slot das 19h seria promessa para uma padaria vazia.
        """
        loja.defaults = {
            **(loja.defaults or {}),
            "pickup_slots": [
                {"ref": "cedo", "label": "Cedo", "starts_at": "06:00"},   # antes de abrir
                {"ref": "meio", "label": "Meio", "starts_at": "12:00"},
                {"ref": "noite", "label": "Noite", "starts_at": "19:00"},  # depois de fechar
            ],
        }
        loja.save(update_fields=["defaults"])

        ctx = fulfillment_window.annotate(QUINTA, [], now=AGORA)
        assert [w["ref"] for w in ctx["windows"]] == ["meio"]

    def test_a_prontidao_corta_o_slot_canonico_tambem(self, loja, baguete):
        """O corte é o mesmo nas duas grades."""
        ctx = fulfillment_window.annotate(QUINTA, ["BF"], now=AGORA)

        por_ref = {w["ref"]: w for w in ctx["windows"]}
        assert por_ref["slot-09"]["enabled"] is False
        assert por_ref["slot-09"]["reason"] == "Baguette de Tradition sai às 12:00."
        assert por_ref["slot-12"]["enabled"] is True
        assert ctx["earliest_ref"] == "slot-12"

    def test_a_mediana_precisa_e_arredondada_PARA_CIMA_no_slot(self, loja):
        """11:37 não vira "11:37" — vira "A partir das 12h".

        A mediana é mais precisa que o slot, mas na hora da encomenda ela é
        encaixada na grade da casa: o slot que COMEÇA depois de tudo estar
        pronto. Prometer 09h para algo que sai 11:37 é quebra de contrato.
        """
        Product.objects.create(
            sku="MEIO", name="Pão do meio-dia", base_price_q=100,
            metadata={"ready_from": "11:37"},
        )
        ctx = fulfillment_window.annotate(QUINTA, ["MEIO"], now=AGORA)

        assert ctx["ready_at"] == "11:37"
        assert ctx["earliest_ref"] == "slot-12"

    def test_slot_canonico_incompativel_e_RECUSADO_no_commit(self, loja, baguete):
        """O ref canônico não carrega hora no nome — quem sabe é a configuração.

        Ler a hora do ref cru ("slot-09" partido no hífen dá "slot") faria a
        janela ficar sem início e NENHUM corte se aplicar: o horário impossível
        passaria calado justamente na grade da encomenda.
        """
        erro = fulfillment_window.validate(QUINTA, "slot-09", ["BF"], now=AGORA)

        assert erro is not None
        assert "Baguette de Tradition sai às 12:00." in erro
        assert "A partir das 12h" in erro
        assert fulfillment_window.validate(QUINTA, "slot-12", ["BF"], now=AGORA) is None

    def test_encomenda_para_dia_FECHADO_nao_tem_grade(self, loja):
        """O slot canônico é config da casa e não sabe de calendário. Sem a
        guarda, um domingo em que a loja não abre voltaria oferecendo "A partir
        das 09h" — para um dia em que não há ninguém na padaria."""
        assert fulfillment_window.annotate(DOMINGO, [], now=AGORA)["windows"] == []


class TestFalhaAoApurar:
    """"Não sei a hora deste pão" e "não consegui perguntar" são DIFERENTES.

    Os dois eram o mesmo dicionário vazio, e o segundo LIBERAVA — uma falha de
    leitura virava permissão, e a baguete das 12h saía oferecida para as 7h.
    """

    def test_annotate_apaga_TODAS_as_janelas(self, loja, baguete, monkeypatch):
        from shopman.shop.services import product_readiness

        def explode(*a, **k):
            raise product_readiness.ReadinessUnavailable("banco fora do ar")

        monkeypatch.setattr(product_readiness, "bottleneck", explode)
        ctx = fulfillment_window.annotate(QUINTA, ["BF"], now=AGORA)

        assert ctx["windows"], "a grade continua aparecendo"
        assert all(w["enabled"] is False for w in ctx["windows"])
        assert ctx["earliest_ref"] == ""
        assert ctx["readiness_unavailable"] is True

    def test_validate_RECUSA(self, loja, baguete, monkeypatch):
        from shopman.shop.services import product_readiness

        def explode(*a, **k):
            raise product_readiness.ReadinessUnavailable("banco fora do ar")

        monkeypatch.setattr(product_readiness, "bottleneck", explode)
        erro = fulfillment_window.validate(QUINTA, "slot-12", ["BF"], now=AGORA)

        assert erro == fulfillment_window.UNKNOWN_READINESS

    def test_mas_sem_horario_escolhido_a_venda_passa(self, loja, baguete, monkeypatch):
        """Falhar fechado é sobre a PROMESSA. Sem horário não há promessa, e
        travar a venda de balcão por um hiccup de banco seria o outro extremo."""
        from shopman.shop.services import product_readiness

        def explode(*a, **k):
            raise product_readiness.ReadinessUnavailable("banco fora do ar")

        monkeypatch.setattr(product_readiness, "bottleneck", explode)
        assert fulfillment_window.validate(QUINTA, "", ["BF"], now=AGORA) is None
