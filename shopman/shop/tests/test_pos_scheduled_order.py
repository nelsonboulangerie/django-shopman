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

    por_ref = {s["ref"]: s for s in review.delivery_slots}
    assert por_ref["09:00-09:30"]["enabled"] is False
    assert por_ref["09:00-09:30"]["reason"] == "Baguette de Tradition sai às 12:00."
    assert por_ref["12:00-12:30"]["enabled"] is True
    assert review.delivery_earliest_slot == "12:00-12:30"
