"""O aviso de confirmado diz a data da encomenda (WP-DATA-E-PROMESSA, L9).

"Seu pedido A47 está confirmado" sem dia nenhum deixava o cliente da encomenda
sem a promessa escrita. Na encomenda, o texto diz para quando e como recebe; no
pedido de hoje, nada muda.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from shopman.shop import notification_copy
from shopman.shop.adapters._notification_templates import render_template
from shopman.shop.services.notification import _commitment_suffix


def _order(**data):
    return SimpleNamespace(ref="WEB-260101-A47", data=data)


def _body(order) -> str:
    return render_template(
        notification_copy.CUSTOMER_COPY["order_accepted"]["body"],
        {
            "order_ref_short": "A47",
            "order_total_display": "R$ 38,00",
            "tracking_url": "https://loja/pedido/A47",
            "commitment_suffix": _commitment_suffix(order),
        },
    )


def _amanha():
    return timezone.localdate() + timedelta(days=1)


def test_encomenda_de_amanha_diz_o_dia_e_a_retirada():
    order = _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="pickup")

    body = _body(order)

    assert body.startswith("Seu pedido *A47* está confirmado para retirada amanhã. O total é *R$ 38,00*.")


def test_encomenda_de_entrega_diz_entrega():
    order = _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="delivery")

    assert _commitment_suffix(order) == " para entrega amanhã"


@pytest.mark.django_db
def test_dia_da_semana_leva_artigo_e_data():
    hoje = timezone.localdate()
    dia = hoje + timedelta(days=(5 - hoje.weekday()) % 7 or 7)  # o próximo sábado
    if dia == hoje + timedelta(days=1):
        dia += timedelta(days=7)
    order = _order(delivery_date=dia.isoformat(), is_preorder=True, fulfillment_type="pickup")

    suffix = _commitment_suffix(order)

    assert suffix == f" para retirada no sábado, {dia:%d/%m}", suffix


def test_pedido_de_hoje_fica_como_era():
    order = _order(delivery_date=timezone.localdate().isoformat(), fulfillment_type="pickup")

    assert _commitment_suffix(order) == ""
    assert _body(order).startswith("Seu pedido *A47* está confirmado. O total é *R$ 38,00*.")


def test_pedido_sem_data_fica_como_era():
    assert _commitment_suffix(_order()) == ""


def test_texto_sem_travessao():
    order = _order(delivery_date=_amanha().isoformat(), is_preorder=True, fulfillment_type="pickup")

    assert "—" not in _body(order)
    assert "–" not in _body(order)
