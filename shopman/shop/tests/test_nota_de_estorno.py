"""P1-12: NFC-e que não pode mais ser cancelada vira a pendência "nota de estorno".

No Paraná a NFC-e só se cancela em 30 minutos da Autorização de Uso **e** com a
mercadoria na casa (RICMS/PR, Anexo III, Subanexo I, art. 35). Fora disso o
sistema tentava cancelar mesmo assim, colhia a recusa e só então avisava. Agora
ele não tenta: abre a pendência no Gestor com o que o contador precisa para a
nota de estorno, que o sistema ainda não emite. Dentro da janela, nada muda.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.fiscalman.contracts import FiscalCancellationResult
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.models import OperatorAlert
from shopman.shop.handlers.fiscal import NFCeCancelHandler
from shopman.shop.models import Channel
from shopman.shop.services import fiscal

pytestmark = pytest.mark.django_db

ACCESS_KEY = "4126" + "1" * 40


class FakeBackend:
    def __init__(self, *, cancel_result=None):
        self.cancel_result = cancel_result or FiscalCancellationResult(success=True, protocol_number="P1")
        self.cancel_calls = 0

    def cancel(self, *, reference, reason):
        self.cancel_calls += 1
        return self.cancel_result


@pytest.fixture
def fiscal_backend_configured(settings):
    from shopman.shop.fiscal import fiscal_pool

    settings.SHOPMAN_FISCAL_ADAPTER = "shopman.shop.tests.test_nota_de_estorno.FakeBackend"
    settings.SHOPMAN_NFCE_CANCELLATION_WINDOW_MINUTES = 30
    fiscal_pool.reset()
    yield
    fiscal_pool.reset()


def _order(*, ref="EST-1", status="cancelled", minutes_ago: int | None = 5, data=None):
    Channel.objects.get_or_create(ref="pdv", defaults={"name": "PDV"})
    payload = {"nfce_access_key": ACCESS_KEY, **(data or {})}
    if minutes_ago is not None:
        payload["nfce_authorized_at"] = (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()
    order = Order.objects.create(ref=ref, channel_ref="pdv", status="new", total_q=2700, data=payload)
    OrderItem.objects.create(
        order=order, line_id="L1", sku="CROISSANT", name="Croissant",
        qty=Decimal("2"), unit_price_q=900, line_total_q=1800,
    )
    OrderItem.objects.create(
        order=order, line_id="L2", sku="BAGUETE", name="Baguete",
        qty=Decimal("1"), unit_price_q=900, line_total_q=900,
    )
    Order.objects.filter(pk=order.pk).update(status=status)
    order.refresh_from_db()
    return order


def _cancel_directives(order):
    return Directive.objects.filter(topic="fiscal.cancel_nfce", payload__order_ref=order.ref)


def _return_note_alerts(order):
    return OperatorAlert.objects.filter(type=fiscal.RETURN_NOTE_ALERT_TYPE, order_ref=order.ref)


# ── dentro da janela: cancelamento como sempre ───────────────────────────────


def test_cancelled_inside_the_window_still_cancels(fiscal_backend_configured):
    order = _order(minutes_ago=5)

    fiscal.cancel(order)

    assert _cancel_directives(order).count() == 1
    assert not _return_note_alerts(order).exists()
    order.refresh_from_db()
    assert fiscal.RETURN_NOTES_KEY not in order.data


def test_counter_undo_inside_the_window_still_cancels(fiscal_backend_configured):
    """O desfazer do balcão (``completed`` → ``cancelled``) devolve o pão ao saldo:
    o cancelamento não é saída, e quem decide é o relógio."""
    order = _order(status="cancelled", minutes_ago=2)

    assert fiscal.goods_left_the_house(order) is False
    fiscal.cancel(order)

    assert _cancel_directives(order).count() == 1


def test_without_the_authorization_time_a_cancelled_sale_still_tries(fiscal_backend_configured):
    """Sem a hora não se chuta: segue a tentativa, e a recusa, se vier, avisa."""
    order = _order(minutes_ago=None)

    fiscal.cancel(order)

    assert _cancel_directives(order).count() == 1
    assert not _return_note_alerts(order).exists()


# ── fora da janela: pendência, nunca a tentativa ─────────────────────────────


def test_cancelled_past_the_window_opens_the_return_note_instead_of_cancelling(fiscal_backend_configured):
    order = _order(minutes_ago=31, data={"cancellation_reason_key": "customer_request"})

    fiscal.cancel(order)

    assert not _cancel_directives(order).exists()
    alert = _return_note_alerts(order).get()
    assert alert.severity == "warning"
    assert alert.audience == "orders"
    from shopman.backstage.projections.alerts import readable_message

    lines = readable_message(alert.message).split("\n")
    month = fiscal._MONTH_NAMES[timezone.localtime(order.created_at).month - 1]
    # Primeiro o fato e o gesto, numa frase; depois os dados, um por linha.
    assert lines == [
        f"Passou o prazo de cancelar a NFC-e. Envie ao contador até o fim de {month}:",
        "Chave:",
        ACCESS_KEY,
        "Devolvido: 2 × Croissant, R$ 18,00 · 1 × Baguete, R$ 9,00",
        "Total: R$ 27,00",
        "Motivo: O cliente pediu",
    ]
    # O pedido está no rodapé do aviso; o corpo não o repete. Sem travessão.
    assert order.ref not in readable_message(alert.message)
    assert "—" not in alert.message
    order.refresh_from_db()
    [note] = order.data[fiscal.RETURN_NOTES_KEY]
    assert note["source"] == "order"
    assert note["reason"] == "window_closed"
    assert note["opened_at"]


def test_returned_after_the_goods_left_never_tries_to_cancel(fiscal_backend_configured):
    """Devolução é saída: mesmo com a nota de dois minutos, cancelar não é caminho."""
    order = _order(
        status="returned", minutes_ago=2,
        data={"returns": [{"type": "total", "reason": "Cliente recusou na porta", "items": []}]},
    )

    fiscal.cancel(order)

    assert not _cancel_directives(order).exists()
    message = _return_note_alerts(order).get().message
    assert message.startswith("A mercadoria já saiu, e a NFC-e não pode mais ser cancelada.")
    assert "prazo" not in message
    assert "Motivo: Cliente recusou na porta" in message
    order.refresh_from_db()
    assert order.data[fiscal.RETURN_NOTES_KEY][0]["reason"] == "goods_dispatched"


def test_returned_without_the_authorization_time_still_opens_the_return_note(fiscal_backend_configured):
    """A saída fecha a porta sozinha: não precisa do relógio para saber."""
    order = _order(status="returned", minutes_ago=None)

    fiscal.cancel(order)

    assert not _cancel_directives(order).exists()
    assert _return_note_alerts(order).count() == 1


def test_the_return_note_opens_once(fiscal_backend_configured):
    order = _order(minutes_ago=45)

    fiscal.cancel(order)
    fiscal.cancel(order)
    # Depois da janela de debounce do aviso, a marca no pedido ainda segura.
    OperatorAlert.objects.filter(order_ref=order.ref).update(created_at=timezone.now() - timedelta(hours=2))
    fiscal.cancel(order)

    assert _return_note_alerts(order).count() == 1
    order.refresh_from_db()
    assert len(order.data[fiscal.RETURN_NOTES_KEY]) == 1


def test_a_cancelled_note_opens_no_return_note(fiscal_backend_configured):
    order = _order(minutes_ago=45, data={"nfce_cancelled": True})

    assert fiscal.open_return_note(order) is False
    assert not _return_note_alerts(order).exists()


def test_a_sale_from_a_closed_month_asks_for_now(fiscal_backend_configured):
    """O mês da venda já fechou: "até o fim de setembro" seria um prazo vencido."""
    order = _order(minutes_ago=45)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=62))
    order.refresh_from_db()

    fiscal.cancel(order)

    first_line = _return_note_alerts(order).get().message.split("\n")[0]
    assert "Envie ao contador agora (a venda é de " in first_line
    assert "até o fim" not in first_line


# ── a fila que segurou o cancelamento além da janela ─────────────────────────


def test_cancel_directive_run_after_the_window_opens_the_return_note(fiscal_backend_configured):
    """Enfileirado a tempo, executado tarde (worker parado): não tenta, abre a pendência."""
    order = _order(minutes_ago=40)
    directive = Directive.objects.create(
        topic="fiscal.cancel_nfce", payload={"order_ref": order.ref, "reason": "cancelled"},
    )
    backend = FakeBackend()

    NFCeCancelHandler(backend).handle(message=directive, ctx={})

    assert backend.cancel_calls == 0
    assert _return_note_alerts(order).count() == 1
    assert not OperatorAlert.objects.filter(type="fiscal_cancel_failed").exists()


def test_cancel_directive_inside_the_window_cancels(fiscal_backend_configured):
    order = _order(minutes_ago=5)
    directive = Directive.objects.create(
        topic="fiscal.cancel_nfce", payload={"order_ref": order.ref, "reason": "cancelled"},
    )
    backend = FakeBackend()

    NFCeCancelHandler(backend).handle(message=directive, ctx={})

    assert backend.cancel_calls == 1
    order.refresh_from_db()
    assert order.data["nfce_cancelled"] is True
    assert not _return_note_alerts(order).exists()


# ── devolução parcial: a parte devolvida, nunca a nota inteira ───────────────


def test_partial_return_opens_the_return_note_for_the_returned_part(fiscal_backend_configured):
    from shopman.shop.handlers.returns import ReturnHandler

    order = _order(status="completed", minutes_ago=5)
    order.data["returns"] = [{
        "type": "partial", "reason": "Croissant queimado",
        "items": [{"line_id": "L1", "sku": "CROISSANT", "qty": "1", "refund_q": 900}],
        "refund_total_q": 900,
    }]
    order.save(update_fields=["data"])

    ReturnHandler._open_partial_return_note(order, order.data["returns"], 0)

    assert not _cancel_directives(order).exists()
    message = _return_note_alerts(order).get().message
    assert message.startswith("Devolução de parte da venda: a NFC-e não pode ser cancelada.")
    assert "Devolvido: 1 × Croissant, R$ 9,00\n" in message
    assert "Baguete" not in message
    assert "Total: R$ 9,00" in message
    assert "Motivo: Croissant queimado" in message
    order.refresh_from_db()
    assert order.data[fiscal.RETURN_NOTES_KEY][0]["source"] == "return:0"


# ── no Gestor: acionável e dispensável ───────────────────────────────────────


def test_the_return_note_reaches_the_order_manager_with_open_and_seen(fiscal_backend_configured):
    from shopman.backstage.projections.alerts import build_operator_alerts_projection
    from shopman.backstage.services import alerts as alert_service

    order = _order(minutes_ago=45)
    fiscal.cancel(order)

    rows = alert_service.list_active_alerts(scope="orders")
    projection = build_operator_alerts_projection(
        alerts=rows, counts=alert_service.active_counts(scope="orders"),
    )
    [row] = [a for a in projection.alerts if a.type == fiscal.RETURN_NOTE_ALERT_TYPE]
    assert row.subject == "Nota de estorno para o contador"
    kinds = {action.kind: action for action in row.actions}
    assert kinds["open_alert_context"].href == f"/{order.ref}"
    assert kinds["open_alert_context"].label == "Abrir o pedido"
    assert kinds["acknowledge_alert"].label == "Visto"
