"""O 0800 do iFood não é o telefone do cliente — e não é WhatsApp.

Medido em 21/09/2026: o detalhe do pedido oferecia "WhatsApp" para o 0800 da
central do iFood e "Ligar" para ele SEM o localizador — a ligação caía na
central, não na pessoa. O #901 já tinha ensinado as notificações a reconhecer o
relé; a tela de detalhe montava os botões do telefone cru.
"""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from shopman.backstage.projections.order_queue import _customer_contact


def _ifood(localizer="89338721", expires=None):
    customer = {"name": "Cliente", "phone": "0800 705 3040", "phone_localizer": localizer}
    if expires is not None:
        customer["phone_localizer_expiration"] = expires.isoformat()
    return SimpleNamespace(channel_ref="ifood", data={"customer": customer}), customer


@pytest.mark.django_db
def test_rele_nao_vira_whatsapp_nem_se_passa_por_telefone_do_cliente():
    order, customer = _ifood(expires=timezone.now() + timedelta(hours=2))
    contact = _customer_contact(order, customer)
    assert contact["customer_whatsapp_url"] == ""
    assert contact["customer_phone"] == ""
    assert contact["customer_relay_phone"] == "0800 705 3040"


@pytest.mark.django_db
def test_ligar_pela_central_disca_o_0800_e_o_codigo():
    order, customer = _ifood(expires=timezone.now() + timedelta(hours=2))
    contact = _customer_contact(order, customer)
    assert contact["customer_phone_uri"] == "tel:08007053040,89338721"
    assert contact["customer_relay_code"] == "89338721"


@pytest.mark.django_db
def test_codigo_vencido_nao_oferece_ligacao_para_o_nada():
    order, customer = _ifood(expires=timezone.now() - timedelta(minutes=1))
    contact = _customer_contact(order, customer)
    assert contact["customer_phone_uri"] == ""
    assert contact["customer_relay_code"] == ""
    assert contact["customer_relay_phone"] == "0800 705 3040"  # a central continua dita


@pytest.mark.django_db
def test_telefone_de_verdade_continua_com_whatsapp_e_ligar():
    customer = {"name": "Ana", "phone": "+5543999990000"}
    order = SimpleNamespace(channel_ref="web", data={"customer": customer})
    contact = _customer_contact(order, customer)
    assert contact["customer_whatsapp_url"] == "https://wa.me/5543999990000"
    assert contact["customer_phone_uri"] == "tel:+5543999990000"
    assert contact["customer_relay_phone"] == ""
