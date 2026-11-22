"""B.I. de Vendas: o não retirado do período (#2698, sobra do WP-G11).

O pedido de retirada que ficou pronto e o cliente não buscou termina cancelado:
conta em "Cancelados", fora do faturamento. O B.I. diz, por período, quantos
foram, quanto voltou ao cliente, quanto ficou com a loja e o valor de venda do
que virou perda, lendo o bloco ``Order.data["no_show"]`` que o gesto grava.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.bi_sales import BISalesNoShow, build_bi_sales

pytestmark = pytest.mark.django_db


def _at(days_ago: int):
    local = timezone.localtime(timezone.now()).replace(hour=10, minute=0, second=0, microsecond=0)
    return local - timedelta(days=days_ago)


def _order(ref: str, days_ago: int, *, status=Order.Status.COMPLETED, channel_ref="web", no_show=None, total_q=3000):
    data = {"payment": {"method": "pix"}}
    if no_show is not None:
        data["no_show"] = no_show
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=total_q, data=data)
    Order.objects.filter(pk=order.pk).update(created_at=_at(days_ago))
    return order


def _block(*, paid_q, refund_q, retained_q, lines):
    return {
        "at": _at(0).isoformat(), "actor": "joyce", "approved_by": "joyce",
        "paid_q": paid_q, "refund_q": refund_q, "retained_q": retained_q, "on_account": False,
        "lines": [
            {"line_id": f"L{i}", "qty": "1", "destiny": destiny, "value_q": value_q}
            for i, (destiny, value_q) in enumerate(lines)
        ],
    }


def test_o_nao_retirado_do_periodo_soma_o_dinheiro_e_a_perda():
    _order("NS-1", 1, status=Order.Status.CANCELLED, no_show=_block(
        paid_q=3000, refund_q=1800, retained_q=1200, lines=[("restock", 1800), ("loss", 1200)],
    ))
    _order("NS-2", 2, status=Order.Status.CANCELLED, channel_ref="whatsapp", no_show=_block(
        paid_q=0, refund_q=0, retained_q=0, lines=[("loss", 900)],
    ))
    _order("CANCELADO-COMUM", 1, status=Order.Status.CANCELLED)
    _order("VENDA", 1)

    report = build_bi_sales(date_from=_at(3).date(), date_to=_at(0).date())

    assert report.no_show == BISalesNoShow(orders=2, paid_q=3000, refund_q=1800, retained_q=1200, loss_q=2100)
    # Continua contado entre os cancelados, fora do faturamento.
    assert report.cancelled_total == 3
    assert report.revenue_total_q == 3000


def test_o_recorte_de_canal_e_de_periodo_vale_para_o_nao_retirado():
    _order("NS-WEB", 1, status=Order.Status.CANCELLED, no_show=_block(
        paid_q=1000, refund_q=0, retained_q=1000, lines=[("loss", 1000)],
    ))
    _order("NS-ZAP", 1, status=Order.Status.CANCELLED, channel_ref="whatsapp", no_show=_block(
        paid_q=500, refund_q=500, retained_q=0, lines=[("restock", 500)],
    ))
    _order("NS-ANTIGO", 20, status=Order.Status.CANCELLED, no_show=_block(
        paid_q=800, refund_q=0, retained_q=800, lines=[("loss", 800)],
    ))
    # O chip de canal só oferece canal que vendeu no período.
    _order("VENDA-WEB", 1)

    web = build_bi_sales(date_from=_at(3).date(), date_to=_at(0).date(), channel="web")
    assert web.no_show == BISalesNoShow(orders=1, paid_q=1000, refund_q=0, retained_q=1000, loss_q=1000)


def test_sem_nao_retirado_o_bloco_vem_zerado():
    _order("VENDA-SO", 1)
    report = build_bi_sales(date_from=_at(3).date(), date_to=_at(0).date())
    assert report.no_show == BISalesNoShow(orders=0, paid_q=0, refund_q=0, retained_q=0, loss_q=0)
