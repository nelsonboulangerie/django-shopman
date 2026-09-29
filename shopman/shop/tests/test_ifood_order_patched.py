"""ORDER_PATCHED: o cliente alterou o pedido depois de confirmado.

O defeito medido em 19/09/2026: o evento caía no ramo "código que não cria
pedido é reconhecido e ignorado" de ``ifood_events.process_events``. Virava
``ignored``, entrava no lote de acknowledge e sumia — dizíamos ao iFood que
tratamos. O ``Order`` local ficava com os itens originais, divergindo o que a
cozinha prepara, o estoque que sai, a cobrança e a nota.

Fundamento (referência oficial de eventos do módulo Order, lida em 19/09/2026
em https://developer.ifood.com.br/pt-BR/docs/food/guides/modules/order/events):

    ORDER_PATCHED — "Cliente adicionou, removeu ou modificou itens após
    confirmação." Três ``changeType`` documentados, um exemplo cada:
    ``DELETE_ITEMS``, ``ADD_ITEMS`` e ``UPDATE_ITEMS``. O ``metadata`` traz
    ``items`` (SÓ os afetados), ``oldTotal`` e ``newTotal`` — é DELTA, nunca o
    estado final do pedido.

Este arquivo cobre o que a Etapa 1 (#897) trouxe e o que **continua valendo
depois da Etapa 2**: o registro do fato e o aviso ao operador quando a loja NÃO
pode acompanhar a alteração. A reconciliação em si — releitura do pedido, ajuste
em ``order.data`` e a leitura composta que cozinha, Gestor, vias, fechamento,
nota e B.I. usam — está em ``test_ifood_order_patched_reconciliation.py``.

Para isolar esta metade, ``_process`` faz a **releitura do pedido falhar de
propósito**. É o ramo ``blocked:fetch_failed``: sem o estado final vindo do
iFood não há o que reconciliar, e a resposta certa volta a ser exatamente a da
Etapa 1 — gravar, avisar alto e parar. Sem esse recorte estes testes passariam
por acidente (num ambiente de teste sem credencial o ``GET`` falha sozinho), e
teste que passa por acidente não prova nada.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import ifood_events, ifood_orders


def _patch_event(*, change_type="DELETE_ITEMS", items=None, old_total=25.5, new_total=20.5,
                 event_id="evt-patch-1", order_id="ifood-order"):
    metadata = {"id": order_id, "changeType": change_type}
    if items is not None:
        metadata["items"] = items
    if old_total is not None:
        metadata["oldTotal"] = old_total
    if new_total is not None:
        metadata["newTotal"] = new_total
    return {
        "id": event_id, "code": "ORDER_PATCHED", "fullCode": "ORDER_PATCHED",
        "orderId": order_id, "metadata": metadata,
    }


def _order(**kwargs):
    defaults = {
        "ref": "IFD-PATCH", "channel_ref": "ifood", "external_ref": "ifood-order",
        "status": "preparing", "total_q": 2550,
        "data": {"fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"}},
    }
    defaults.update(kwargs)
    return Order.objects.create(**defaults)


def _process(events):
    """Roda o lote com a releitura do pedido FALHANDO (ver o docstring do módulo)."""
    with (
        patch.object(ifood_events, "acknowledge", return_value=True) as ack,
        patch.object(
            ifood_orders, "fetch_order", side_effect=ifood_orders.IFoodOrderFetchError("403")
        ),
    ):
        summary = ifood_events.process_events(events)
    return summary, ack


# ── O evento deixa de ser engolido ─────────────────────────────────────────────


@pytest.mark.django_db
def test_order_patched_is_handled_not_ignored():
    """A prova do defeito: antes disto o evento saía como `ignored`."""
    order = _order()
    summary, _ack = _process([_patch_event()])

    assert summary["ignored"] == 0
    assert summary["ingested"] == 1
    assert summary["failed"] == 0
    order.refresh_from_db()
    assert len(order.data["ifood"]["patches"]) == 1


@pytest.mark.django_db
def test_the_change_is_recorded_with_the_facts_the_operator_needs():
    order = _order()
    _process([_patch_event(items=[{"id": "item_789", "name": "Bebida", "quantity": 1, "price": 5.0}])])

    order.refresh_from_db()
    record = order.data["ifood"]["patches"][0]
    assert record["event_id"] == "evt-patch-1"
    assert record["change_type"] == "DELETE_ITEMS"
    assert record["items"][0]["name"] == "Bebida"
    # Reais do iFood viram centavos, na convenção `_q` da casa.
    assert record["old_total_q"] == 2550
    assert record["new_total_q"] == 2050
    assert record["local_total_q"] == 2550
    assert record["order_status"] == "preparing"
    # A chave que impede um registro sem reconciliação de se passar por uma.
    assert record["reconciled"] is False


@pytest.mark.django_db
def test_a_change_that_could_not_be_applied_never_pretends_it_was():
    """Sem reconciliar, o pedido local segue o original — e o registro admite isso."""
    order = _order()
    _process([_patch_event(new_total=20.5)])

    order.refresh_from_db()
    assert order.total_q == 2550  # o total local segue o original, explicitamente
    record = order.data["ifood"]["patches"][0]
    assert record["reconciled"] is False
    assert record["reconciliation"] == "blocked:fetch_failed"
    assert "adjustment" not in order.data


@pytest.mark.django_db
def test_the_operator_is_told_loudly():
    order = _order()
    _process([_patch_event(items=[{"id": "item_789", "name": "Bebida", "quantity": 1}])])

    alert = OperatorAlert.objects.get(type="ifood_order_patched")
    assert alert.severity == "error"
    assert alert.order_ref == order.ref
    # A copy tem de ser inequívoca: o que mudou, quanto era, quanto é, e que a
    # loja NÃO acompanhou a mudança.
    assert "Bebida" in alert.message
    assert "R$ 25,50" in alert.message
    assert "R$ 20,50" in alert.message
    assert "itens originais" in alert.message


@pytest.mark.django_db
@pytest.mark.parametrize(("change_type", "expected"), [
    ("DELETE_ITEMS", "itens removidos"),
    ("ADD_ITEMS", "itens adicionados"),
    ("UPDATE_ITEMS", "quantidade de itens alterada"),
])
def test_every_documented_change_type_reads_in_plain_portuguese(change_type, expected):
    _order()
    _process([_patch_event(change_type=change_type, items=[{"id": "i", "name": "Sobremesa", "quantity": 1}])])

    assert expected in OperatorAlert.objects.get(type="ifood_order_patched").message


@pytest.mark.django_db
def test_quantity_change_says_from_what_to_what():
    """`UPDATE_ITEMS` traz oldQuantity/newQuantity — o aviso não pode omitir."""
    _order()
    _process([_patch_event(
        change_type="UPDATE_ITEMS",
        items=[{"id": "item_789", "name": "Pão", "oldQuantity": 1, "newQuantity": 2}],
        old_total=25.5, new_total=51.0,
    )])

    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "de 1 para 2" in message


@pytest.mark.django_db
def test_an_undocumented_change_type_is_reported_raw_not_swallowed():
    """Classificar mal é pior que não classificar: o changeType cru vai junto."""
    _order()
    _process([_patch_event(change_type="SWAP_ITEMS", items=[{"id": "i", "name": "Café", "quantity": 1}])])

    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "SWAP_ITEMS" in message
    assert "Café" in message


@pytest.mark.django_db
def test_a_missing_total_is_not_shown_as_zero():
    """Ausente não é R$ 0,00 — zero como código secreto é defeito de copy."""
    _order()
    _process([_patch_event(old_total=None, new_total=None)])

    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "R$ 0,00" not in message
    assert "(não informado)" in message


# ── O ACK é honesto: sai quando tratamos, não sai quando não dá ────────────────


@pytest.mark.django_db
def test_the_event_is_acknowledged_once_it_is_recorded():
    _order()
    _, ack = _process([_patch_event()])
    assert ack.call_args[0][0] == ["evt-patch-1"]


@pytest.mark.django_db
def test_a_patch_before_the_order_exists_is_not_acknowledged():
    """Pode chegar antes do PLACED, inclusive no mesmo lote: sem ACK, reentrega."""
    summary, ack = _process([_patch_event()])

    assert summary["failed"] == 1
    assert summary["ingested"] == 0
    ack.assert_not_called()
    assert not OperatorAlert.objects.filter(type="ifood_order_patched").exists()


@pytest.mark.django_db
def test_redelivery_does_not_record_the_same_change_twice():
    order = _order()
    _process([_patch_event()])
    summary, _ack = _process([_patch_event()])

    assert summary["deduped"] == 1
    order.refresh_from_db()
    assert len(order.data["ifood"]["patches"]) == 1


@pytest.mark.django_db
def test_two_different_changes_both_survive():
    """Alteração é acumulável: a segunda não pode apagar a primeira."""
    order = _order()
    _process([_patch_event(event_id="evt-1", change_type="DELETE_ITEMS")])
    _process([_patch_event(event_id="evt-2", change_type="ADD_ITEMS")])

    order.refresh_from_db()
    assert [p["change_type"] for p in order.data["ifood"]["patches"]] == ["DELETE_ITEMS", "ADD_ITEMS"]


@pytest.mark.django_db
def test_an_event_from_another_merchant_is_never_consumed():
    _order()
    from django.test import override_settings

    event = _patch_event()
    event["merchantId"] = "outra-loja"
    with override_settings(SHOPMAN_IFOOD={"merchant_id": "nossa-loja"}):
        summary, ack = _process([event])

    assert summary["failed"] == 1
    ack.assert_not_called()


# ── O que o pedido já viveu muda o TAMANHO do problema, não o registro ─────────


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["accepted", "preparing", "ready", "dispatched", "completed"])
def test_a_patch_is_recorded_whatever_the_order_already_lived(status):
    """A documentação não promete que ORDER_PATCHED pare no despacho.

    Chegando depois de o pedido ter saído ou concluído, o registro e o aviso
    continuam valendo — é justamente aí que a divergência custa dinheiro. Nada
    aqui reabre o pedido: só grava o fato e chama alguém.
    """
    order = _order(status=status)
    summary, _ack = _process([_patch_event()])

    assert summary["ingested"] == 1
    order.refresh_from_db()
    assert order.status == status  # nenhum status foi mexido
    assert order.data["ifood"]["patches"][0]["order_status"] == status


@pytest.mark.django_db
def test_an_authorized_nfce_turns_the_warning_into_a_fiscal_one():
    """Nota autorizada e mercadoria já entregue: o caminho é devolução, não cancelamento.

    ``completed`` é saída da mercadoria, e o art. 35 do Subanexo I do Anexo III
    do RICMS/PR exige as DUAS condições — dentro de 30 minutos **e** sem saída.
    Mesmo com a nota recém-autorizada, cancelar aqui já não é caminho.
    """
    order = _order(status="completed", data={
        "fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"},
        "nfce_access_key": "3526...chave",
        "nfce_authorized_at": timezone.now().isoformat(),
    })
    _process([_patch_event()])

    order.refresh_from_db()
    assert order.data["ifood"]["patches"][0]["fiscal_authorized"] is True
    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "NFC-e" in message
    # A porta que fechou é a SAÍDA, não o relógio: a nota tem segundos de vida.
    assert "A MERCADORIA JÁ SAIU" in message
    assert "PRAZO DE CANCELAMENTO JÁ PASSOU" not in message
    assert "DEVOLUÇÃO" in message


@pytest.mark.django_db
def test_an_authorized_nfce_inside_the_window_says_there_is_still_time_to_cancel():
    """Dentro dos 30 minutos e com a mercadoria na casa: cancelar e reemitir.

    O operador do iFood tem minutos, não um telefonema: a frase precisa dizer
    QUAL dos dois caminhos vale, não que existem dois.
    """
    _order(status="preparing", data={
        "fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"},
        "nfce_access_key": "3526...chave",
        "nfce_authorized_at": (timezone.now() - timedelta(minutes=5)).isoformat(),
    })
    _process([_patch_event()])

    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "AINDA DÁ TEMPO DE CANCELAR" in message
    # 30 − 5 = 25 minutos de sobra, arredondados para baixo.
    assert "restam cerca de 25" in message
    assert "devolução" not in message


@pytest.mark.django_db
def test_an_authorized_nfce_past_the_window_sends_the_operator_to_the_return_note():
    """Passados os 30 minutos, o PR não tem cancelamento extemporâneo: é estorno."""
    _order(status="preparing", data={
        "fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"},
        "nfce_access_key": "3526...chave",
        "nfce_authorized_at": (timezone.now() - timedelta(minutes=31)).isoformat(),
    })
    _process([_patch_event()])

    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "PRAZO DE CANCELAMENTO JÁ PASSOU" in message
    assert "DEVOLUÇÃO" in message
    assert "AINDA DÁ TEMPO" not in message


@pytest.mark.django_db
def test_an_authorized_nfce_without_an_authorization_time_refuses_to_guess():
    """Sem a hora da autorização o prazo não se mede — e não se chuta.

    Errar para o lado do "provavelmente dá tempo" é mandar cancelar fora do
    prazo, levar a recusa do autorizador e ficar sem documento nenhum.
    """
    _order(status="preparing", data={
        "fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"},
        "nfce_access_key": "3526...chave",
    })
    _process([_patch_event()])

    message = OperatorAlert.objects.get(type="ifood_order_patched").message
    assert "não pôde ser medido" in message
    assert "AINDA DÁ TEMPO" not in message
    assert "JÁ PASSOU" not in message


@pytest.mark.django_db
def test_a_cancelled_nfce_is_not_treated_as_authorized():
    order = _order(data={
        "fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"},
        "nfce_access_key": "3526...chave", "nfce_cancelled": True,
    })
    _process([_patch_event()])

    order.refresh_from_db()
    assert order.data["ifood"]["patches"][0]["fiscal_authorized"] is False


# ── Pedido de teste: registra e loga, mas não põe a padaria para trabalhar ─────


@pytest.mark.django_db
def test_a_test_order_records_the_change_without_alarming_the_shop():
    """A supressão da #887 é sobre a padaria; o registro e o log continuam."""
    order = _order(data={
        "fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT", "is_test": True},
    })
    summary, _ack = _process([_patch_event()])

    assert summary["ingested"] == 1
    order.refresh_from_db()
    assert len(order.data["ifood"]["patches"]) == 1
    assert not OperatorAlert.objects.filter(type="ifood_order_patched").exists()


# ── O ramo que engolia tudo agora tem três destinos ───────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("code", sorted(ifood_events._INERT_CODES))
def test_codes_with_a_written_decision_stay_quiet(code):
    summary, ack = _process([{"id": f"evt-{code}", "code": code, "orderId": "ifood-order"}])

    assert summary["ignored"] == 1
    assert ack.call_args[0][0] == [f"evt-{code}"]
    assert not OperatorAlert.objects.filter(type="ifood_event_unhandled").exists()


@pytest.mark.django_db
def test_an_unknown_code_is_acknowledged_but_never_silent():
    """ACK para não reentregar em laço; alerta para não sumir."""
    summary, ack = _process([{"id": "evt-x", "code": "SOME_NEW_IFOOD_CODE", "orderId": "ifood-order"}])

    assert summary["ignored"] == 1
    assert ack.call_args[0][0] == ["evt-x"]
    alert = OperatorAlert.objects.get(type="ifood_event_unhandled")
    assert "SOME_NEW_IFOOD_CODE" in alert.message


@pytest.mark.django_db
@pytest.mark.parametrize("code", [
    "DELIVERY_ADDRESS_CHANGE",
    "DELIVERY_PHONE_CHANGE",
    "DELIVERY_RETURNED_TO_ORIGIN",
    "CANCELLATION_REQUEST_FAILED",
])
def test_documented_codes_we_do_not_handle_yet_are_visible(code):
    """Estes têm ação oficial e NÃO têm tratamento aqui: têm de aparecer.

    Eles não entram em `_INERT_CODES` de propósito. Enquanto não houver
    processador, o operador é quem faz — e para fazer precisa saber.
    """
    _process([{"id": f"evt-{code}", "code": code, "orderId": "ifood-order"}])

    assert OperatorAlert.objects.filter(type="ifood_event_unhandled").exists()


@pytest.mark.django_db
def test_patch_codes_carry_no_invented_short_code():
    """`PTC` não existe na documentação — adivinhar sigla é como se erra aqui.

    Na referência oficial, ORDER_PATCHED é um dos códigos cujo `code` e
    `fullCode` são a mesma string. Se uma sigla aparecer no vivo, ela cai no
    ramo não tratado e grita, que é o comportamento seguro.
    """
    assert ifood_events._PATCH_CODES == {"ORDER_PATCHED"}
    assert "PTC" not in ifood_events._INERT_CODES
