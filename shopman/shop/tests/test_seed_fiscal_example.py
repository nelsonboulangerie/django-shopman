"""O exemplo fiscal do seed não fabrica consulta de uma nota na SEFAZ."""
from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from config.management.commands.seed import Command
from shopman.backstage.projections.order_queue import _fiscal_status


@pytest.mark.django_db
def test_illustrative_fiscal_example_does_not_offer_a_fabricated_sefaz_qr():
    order = Order.objects.create(ref="FISCAL-EXAMPLE", status="completed", channel_ref="web", total_q=800)
    OrderItem.objects.create(
        order=order, line_id="1", sku="ESP", name="Espresso", qty=1,
        unit_price_q=800, line_total_q=800,
    )
    Command()._seed_fiscal_example()
    order.refresh_from_db()
    assert not order.data.get("nfce_qrcode_url")
    assert order.data["nfce_danfe_url"].startswith("https://homologacao.focusnfe.com.br/")
    _status, _label, _state, links = _fiscal_status(order)
    assert [link["label"] for link in links] == ["DANFE"]


def _completed_order(ref: str) -> Order:
    order = Order.objects.create(ref=ref, status="completed", channel_ref="web", total_q=800)
    OrderItem.objects.create(
        order=order, line_id="1", sku="ESP", name="Espresso", qty=1,
        unit_price_q=800, line_total_q=800,
    )
    return order


@pytest.mark.django_db
def test_segunda_passada_do_seed_nao_repete_a_nota_da_primeira():
    """``seed --flush`` de novo no mesmo banco (o passo re-entrante do Omotenashi Gate).

    A primeira passada grava a nota de exemplo num pedido. O flush apaga os pedidos
    e precisa levar a nota junto; a segunda passada escolhe outro pedido, e a chave
    dele não pode colidir com a do anterior (a chave é única no FiscalDocument).
    """
    from shopman.fiscalman.models import FiscalDocument

    first = _completed_order("FISCAL-EXAMPLE-1")
    Command()._seed_fiscal_example()
    first_key = FiscalDocument.objects.get(reference=first.ref).access_key

    Command()._flush()
    assert not FiscalDocument.objects.exists()

    second = _completed_order("FISCAL-EXAMPLE-2")
    Command()._seed_fiscal_example()

    document = FiscalDocument.objects.get()
    assert document.reference == second.ref
    assert len(document.access_key) == 44 and document.access_key.isdigit()
    assert document.access_key != first_key
    second.refresh_from_db()
    assert second.data["nfce_access_key"] == document.access_key


@pytest.mark.django_db
def test_seed_sem_flush_sobre_outro_pedido_nao_colide_a_chave():
    """Sem flush, o seed rodado de novo pode escolher outro pedido concluído."""
    from shopman.fiscalman.models import FiscalDocument

    _completed_order("FISCAL-EXAMPLE-A")
    Command()._seed_fiscal_example()
    _completed_order("FISCAL-EXAMPLE-B")
    Command()._seed_fiscal_example()
    Command()._seed_fiscal_example()

    keys = list(FiscalDocument.objects.values_list("access_key", flat=True))
    assert len(keys) == 2 and len(set(keys)) == 2
