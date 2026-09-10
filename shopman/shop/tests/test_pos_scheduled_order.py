"""O pedido agendado do balcão — retirada inclusive, e sem horário impossível.

Duas coisas se provam aqui, e as duas nasceram do mesmo mal-entendido: *quando* o
pedido acontece era tratado como fato da ENTREGA.

1. **A retirada agendada chega ao pedido.** O commit descartava `delivery_date` e
   `delivery_time_slot` sempre que o recebimento não fosse entrega. O operador
   combinava quinta às 10h com o cliente no telefone e o pedido nascia para hoje,
   em silêncio.
2. **A janela impossível é RECUSADA no commit.** A review anota o que não cabe,
   mas review é tela — e payload não passa por tela. Fila offline reenviando
   rascunho de ontem, item trocado depois do horário escolhido, relógio de tablet
   fora de hora: nos três a promessa entrava calada.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service

pytestmark = pytest.mark.django_db

ABERTO_TODO_DIA = {
    day: {"open": "08:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


@pytest.fixture
def balcao():
    from shopman.offerman.models import Product

    Shop.objects.create(name="Nelson", brand_name="Nelson", opening_hours=ABERTO_TODO_DIA)
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )
    Product.objects.create(
        sku="CR", name="Croissant", base_price_q=900, is_published=True, is_sellable=True
    )
    Product.objects.create(
        sku="BF",
        name="Baguette de Tradition",
        base_price_q=1600,
        is_published=True,
        is_sellable=True,
        metadata={"ready_from": "12:00"},
    )
    operator = get_user_model().objects.create_user(username="marina", password="x")
    return operator, cash.open_shift(operator=operator, float_q=10000)


def _amanha():
    return (timezone.localdate() + timezone.timedelta(days=1)).isoformat()


def _payload(shift, *, client_request_id: str, sku: str = "CR", **overrides) -> dict:
    payload = {
        "items": [{"sku": sku, "name": sku, "qty": 1, "unit_price_q": 900}],
        "customer_name": "Cliente",
        "fulfillment_type": "pickup",
        "payment_method": "cash",
        "client_request_id": client_request_id,
        "cash_shift_id": shift.pk,
    }
    payload.update(overrides)
    return payload


def _close(operator, payload):
    return pos_service.close_sale(
        channel_ref="pdv",
        payload=payload,
        actor=f"pos:{operator.username}",
        operator_username=operator.username,
    )


# ── A retirada agendada sobrevive ao commit ──────────────────────────────────


def test_retirada_agendada_chega_ao_pedido(balcao):
    """O caso do telefone: "pode separar dois croissants para quinta às 10h?".

    Antes, as duas chaves eram descartadas no commit porque a retirada não é
    entrega — e o pedido nascia para hoje.
    """
    operator, shift = balcao
    amanha = _amanha()

    result = _close(
        operator,
        _payload(
            shift,
            client_request_id="ag-1",
            delivery_date=amanha,
            delivery_time_slot="10:00-10:30",
        ),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["delivery_date"] == amanha
    assert order.data["delivery_time_slot"] == "10:00-10:30"


def test_retirada_nao_ganha_endereco_nem_taxa(balcao):
    """*Onde* e *quanto* continuam sendo fatos da entrega, e continuam saindo."""
    operator, shift = balcao

    result = _close(
        operator,
        _payload(
            shift,
            client_request_id="ag-2",
            delivery_date=_amanha(),
            delivery_address="Rua Pará, 86",
            delivery_fee_override_q=500,
        ),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert "delivery_address" not in order.data
    assert "delivery_fee_q" not in order.data
    assert order.data["delivery_date"] == _amanha()


def test_entrega_agendada_continua_carregando_tudo(balcao):
    operator, shift = balcao
    amanha = _amanha()

    result = _close(
        operator,
        _payload(
            shift,
            client_request_id="ag-3",
            fulfillment_type="delivery",
            delivery_address="Rua Pará, 86",
            delivery_date=amanha,
            delivery_time_slot="14:00-14:30",
        ),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["delivery_date"] == amanha
    assert order.data["delivery_time_slot"] == "14:00-14:30"
    assert order.data["delivery_address"] == "Rua Pará, 86"


# ── A janela impossível é recusada, não anotada ──────────────────────────────


def test_commit_recusa_janela_antes_do_preparo(balcao):
    """A baguete sai às 12:00; as 09:00 não podem ser prometidas.

    Esta é a falha que o Pablo chamou de gravíssima: quebra de contrato com o
    cliente que aparece às 9h e não tem o pão dele.
    """
    operator, shift = balcao

    with pytest.raises(ValueError) as erro:
        _close(
            operator,
            _payload(
                shift,
                client_request_id="ag-4",
                sku="BF",
                delivery_date=_amanha(),
                delivery_time_slot="09:00-09:30",
            ),
        )

    assert "Baguette de Tradition sai às 12:00." in str(erro.value)
    assert Order.objects.count() == 0


def test_commit_recusa_a_janela_na_ENTREGA_tambem(balcao):
    """A entrega passava ao largo de qualquer prontidão, nas duas superfícies."""
    operator, shift = balcao

    with pytest.raises(ValueError):
        _close(
            operator,
            _payload(
                shift,
                client_request_id="ag-5",
                sku="BF",
                fulfillment_type="delivery",
                delivery_address="Rua Pará, 86",
                delivery_date=_amanha(),
                delivery_time_slot="09:00-09:30",
            ),
        )

    assert Order.objects.count() == 0


def test_commit_aceita_a_janela_compativel(balcao):
    operator, shift = balcao

    result = _close(
        operator,
        _payload(
            shift,
            client_request_id="ag-6",
            sku="BF",
            delivery_date=_amanha(),
            delivery_time_slot="12:00-12:30",
        ),
    )

    assert Order.objects.get(ref=result.order_ref).data["delivery_time_slot"] == "12:00-12:30"


def test_janela_fora_da_grade_do_dia_NAO_e_recusada(balcao):
    """23:00 num dia que fecha às 18h passa — e isso é deliberado.

    A grade do expediente diz o que a casa OFERECE, não o que ela aceita.
    Recusar aqui faria a dona, no balcão às 18h05, não conseguir agendar a
    retirada de amanhã — e faria uma loja com `opening_hours` em branco recusar
    TODA venda com horário. Só a prontidão fecha a porta, porque só ela é
    promessa que a casa não pode cumprir.
    """
    operator, shift = balcao

    result = _close(
        operator,
        _payload(
            shift,
            client_request_id="ag-7",
            delivery_date=_amanha(),
            delivery_time_slot="23:00-23:30",
        ),
    )

    assert Order.objects.get(ref=result.order_ref).data["delivery_time_slot"] == "23:00-23:30"


def test_sem_horario_combinado_a_venda_passa(balcao):
    """"A combinar" é resposta legítima do balcão. A venda rápida do dia a dia
    não pode ganhar uma pergunta obrigatória que a casa nunca fez."""
    operator, shift = balcao

    result = _close(operator, _payload(shift, client_request_id="ag-8", sku="BF"))

    assert Order.objects.get(ref=result.order_ref)


def test_review_desabilita_a_manha_e_aponta_a_primeira_possivel(balcao):
    """A janela impossível APARECE, com o motivo — sumir com ela deixaria o
    operador sem resposta para "e às 9h não dá?"."""
    review = pos_service.review_sale(
        channel_ref="pdv",
        payload={
            "items": [{"sku": "BF", "name": "Baguette", "qty": 1, "unit_price_q": 1600}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "delivery_date": _amanha(),
        },
        operator_username="marina",
    )

    # Encomenda → slots canônicos da casa (a grade de meia hora é só de HOJE).
    por_ref = {s["ref"]: s for s in review.delivery_slots}
    assert por_ref["slot-09"]["enabled"] is False
    assert por_ref["slot-09"]["reason"] == "Baguette de Tradition sai às 12:00."
    assert por_ref["slot-12"]["enabled"] is True
    assert review.delivery_earliest_slot == "slot-12"


# ── A venda de hoje NÃO vira encomenda ───────────────────────────────────────


def test_data_de_HOJE_nao_adia_a_venda_de_balcao(balcao):
    """O caso em que errar quebraria o balcão inteiro.

    Agora que a retirada grava `delivery_date`, uma venda comum poderia passar a
    escrever a data de HOJE — e se o lifecycle tratasse isso como encomenda, TODA
    venda de balcão pararia de disparar KDS e baixa de estoque na hora, esperando
    um despertador para a madrugada seguinte.

    Não acontece porque a condição é `target > localdate()` (estritamente
    futura). Este teste existe para que ela continue estritamente futura.
    """
    from shopman.orderman.models import Directive

    operator, shift = balcao
    hoje = timezone.localdate().isoformat()

    result = _close(
        operator,
        _payload(shift, client_request_id="hoje-1", delivery_date=hoje),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["delivery_date"] == hoje
    assert not Directive.objects.filter(
        topic="preorder.activate", payload__order_ref=order.ref
    ).exists()


def test_a_fronteira_da_encomenda_e_ESTRITAMENTE_futura(balcao):
    """O contraponto, na fronteira exata: hoje não adia, amanhã adia.

    Testado no predicado (`_physical_work_deferred`) e não pelo pedido inteiro
    de propósito: o agendamento só acontece depois que o pedido é ACEITO, e o
    canal mínimo desta fixture deixa o pedido em `new`. O que precisa ficar
    guardado aqui é a COMPARAÇÃO — `>` e não `>=` —, e ela não depende de
    confirmação nenhuma. O fio inteiro (aceite → directive na madrugada da data)
    já é coberto pelas suítes de lifecycle, e foi conferido no PDV real.
    """
    from shopman.shop.lifecycle import _physical_work_deferred

    hoje = timezone.localdate()

    class _Pedido:
        def __init__(self, dia):
            self.data = {"delivery_date": dia.isoformat()} if dia else {}

    assert _physical_work_deferred(_Pedido(hoje)) is False
    assert _physical_work_deferred(_Pedido(hoje + timezone.timedelta(days=1))) is True
    assert _physical_work_deferred(_Pedido(hoje - timezone.timedelta(days=1))) is False
    assert _physical_work_deferred(_Pedido(None)) is False


# ── A data também é conferida, e sem ela um pedido pago some ─────────────────


def test_data_ABSURDA_e_recusada(balcao):
    """O achado mais caro da auditoria adversarial, e o mais barato de causar.

    Um dígito errado em "Outra data" — 2027 no lugar de 2026 — e o pedido nascia
    `accepted` para daqui a um ano: sem ticket de cozinha, sem baixa de estoque,
    sem fidelidade, sem notificação, e sem NADA que alertasse ninguém. O cliente
    tinha pago em dinheiro e ido embora com o comprovante na mão.

    A loja sempre guardou contra isso; o balcão era estritamente mais fraco.
    """
    operator, shift = balcao

    with pytest.raises(ValueError) as erro:
        _close(operator, _payload(shift, client_request_id="abs-1", delivery_date="3000-01-01"))

    assert "encomenda até" in str(erro.value)
    assert Order.objects.count() == 0


def test_data_no_PASSADO_e_recusada(balcao):
    operator, shift = balcao
    ontem = (timezone.localdate() - timezone.timedelta(days=1)).isoformat()

    with pytest.raises(ValueError) as erro:
        _close(operator, _payload(shift, client_request_id="abs-2", delivery_date=ontem))

    assert "já passou" in str(erro.value)
    assert Order.objects.count() == 0


def test_data_ilegivel_e_recusada_MESMO_SEM_horario(balcao):
    """Antes, data podre sem horário passava e era gravada crua no pedido.

    A conferência era feita só quando havia janela escolhida — o caminho mais
    comum (data sem hora) era justamente o desprotegido.
    """
    operator, shift = balcao

    with pytest.raises(ValueError) as erro:
        _close(
            operator,
            _payload(shift, client_request_id="abs-3", delivery_date="amanha de manha"),
        )

    assert "inválida" in str(erro.value)
    assert Order.objects.count() == 0


# ── Encomenda anônima é recusada: promessa precisa de destinatário ──────────


def test_agendado_sem_NENHUM_identificador_e_recusado(balcao):
    """Pedido para outro dia sem nome, telefone nem cadastro não nasce.

    Se a fornada atrasar ou o item acabar, alguém precisa avisar alguém — e um
    agendado 100% anônimo não tem quem avisar. O erro é tipado no molde do
    `house_account_not_eligible`: a UI lê code/field/recovery e abre o Cliente.
    """
    from shopman.shop.services.pos_intent import PosIntentError

    operator, shift = balcao

    with pytest.raises(PosIntentError) as erro:
        _close(
            operator,
            _payload(
                shift,
                client_request_id="anon-1",
                customer_name="",
                delivery_date=_amanha(),
            ),
        )

    assert erro.value.code == "customer_required_for_scheduled"
    assert erro.value.field == "customer_phone"
    assert erro.value.focus == "customer"
    assert erro.value.recovery
    assert Order.objects.count() == 0


def test_agendado_com_so_o_telefone_passa(balcao):
    """UM identificador basta — o balcão não vira formulário."""
    operator, shift = balcao
    amanha = _amanha()

    result = _close(
        operator,
        _payload(
            shift,
            client_request_id="anon-2",
            customer_name="",
            customer_phone="43999990000",
            delivery_date=amanha,
        ),
    )

    order = Order.objects.get(ref=result.order_ref)
    assert order.data["delivery_date"] == amanha


def test_data_de_HOJE_sem_cliente_passa(balcao):
    """A venda de agora segue anônima: data de hoje não é agendamento."""
    operator, shift = balcao
    hoje = timezone.localdate().isoformat()

    result = _close(
        operator,
        _payload(shift, client_request_id="anon-3", customer_name="", delivery_date=hoje),
    )

    assert Order.objects.get(ref=result.order_ref)


def test_review_avisa_o_agendado_sem_cliente(balcao):
    """A review anota ANTES do commit — mesmo code/field da recusa, para a UI
    apontar o mesmo lugar."""
    review = pos_service.review_sale(
        channel_ref="pdv",
        payload={
            "items": [{"sku": "CR", "name": "Croissant", "qty": 1, "unit_price_q": 900}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "delivery_date": _amanha(),
        },
        operator_username="marina",
    )

    aviso = next(
        (w for w in review.warnings if w["code"] == "customer_required_for_scheduled"), None
    )
    assert aviso is not None
    assert aviso["field"] == "customer_phone"


def test_o_teto_sai_da_configuracao_da_casa(balcao):
    """`max_preorder_days` viajava na projection e ninguém aplicava."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    shop.defaults = {**(shop.defaults or {}), "max_preorder_days": 3}
    shop.save(update_fields=["defaults"])
    operator, shift = balcao

    dentro = (timezone.localdate() + timezone.timedelta(days=3)).isoformat()
    fora = (timezone.localdate() + timezone.timedelta(days=4)).isoformat()

    assert _close(operator, _payload(shift, client_request_id="teto-ok", delivery_date=dentro))
    with pytest.raises(ValueError):
        _close(operator, _payload(shift, client_request_id="teto-no", delivery_date=fora))


def test_a_data_limite_EXATA_ainda_passa(balcao):
    """Fronteira: o dia do teto é aceito, o seguinte não (testado acima)."""
    operator, shift = balcao
    limite = (timezone.localdate() + timezone.timedelta(days=30)).isoformat()

    result = _close(operator, _payload(shift, client_request_id="lim-1", delivery_date=limite))

    assert Order.objects.get(ref=result.order_ref).data["delivery_date"] == limite
