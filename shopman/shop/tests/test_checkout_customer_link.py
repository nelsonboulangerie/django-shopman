"""O vínculo do pedido com o cadastro não some calado.

``ensure_customer`` tinha um ``except IntegrityError: pass``. O pedido fechava,
o cadastro não nascia, e ninguém ficava sabendo: o cliente perdia histórico,
fidelidade e rastreio, e a padaria não tinha como perceber. Agora a colisão ou
VINCULA ao dono existente (é o mesmo telefone, que nesta loja é a identidade do
cliente) ou vira alerta de operador.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.guestman.models import ContactPoint, Customer

from shopman.shop.services import checkout

pytestmark = pytest.mark.django_db


class _Intent:
    def __init__(self, phone: str, name: str = "Ana"):
        self.customer_phone = phone
        self.customer_name = name


def test_colisao_com_cadastro_ativo_vincula_em_vez_de_descartar():
    """Corrida entre dois checkouts do mesmo número: o dono é o cadastro certo."""
    dono = Customer.objects.create(ref="CUS-LINK-01", first_name="", phone="+5543988883333")

    # A busca inicial não vê o dono (é o que a corrida produz); a criação bate no
    # UNIQUE global do ContactPoint.
    with patch.object(checkout, "logger"):
        with patch(
            "shopman.guestman.services.customer.get_by_phone", return_value=None
        ):
            checkout.ensure_customer(_Intent("+5543988883333"), order_ref="ORD-LINK-1")

    dono.refresh_from_db()
    # Vinculado ao dono: o nome do checkout preencheu a lacuna do cadastro.
    assert dono.first_name == "Ana"
    assert Customer.objects.filter(phone="+5543988883333").count() == 1


def test_telefone_preso_em_cadastro_desativado_vira_alerta():
    """Sem dono utilizável, o pedido fica sem cadastro — e isso GRITA."""
    desativado = Customer.objects.create(
        ref="CUS-LINK-02", first_name="Antigo", phone="+5543988884444"
    )
    desativado.is_active = False
    desativado.save(update_fields=["is_active"])

    with patch.object(checkout, "logger"), patch(
        "shopman.shop.services.observability.create_operator_alert"
    ) as alerta:
        checkout.ensure_customer(_Intent("+5543988884444"), order_ref="ORD-LINK-2")

    alerta.assert_called_once()
    kwargs = alerta.call_args.kwargs
    assert kwargs["type"] == "checkout_customer_unlinked"
    assert kwargs["order_ref"] == "ORD-LINK-2"
    assert "desativado" in kwargs["message"]

    # E o cadastro desativado NÃO foi ressuscitado nem escrito.
    desativado.refresh_from_db()
    assert desativado.first_name == "Antigo"
    assert desativado.is_active is False
    # Nem sobrou cadastro meia-boca: `customer_service.create` é atômico.
    assert not Customer.objects.filter(ref__startswith="WEB-").exists()


def test_telefone_novo_cria_o_cadastro_normalmente():
    checkout.ensure_customer(_Intent("+5543988885555", name="Bia"), order_ref="ORD-LINK-3")

    criado = Customer.objects.get(phone="+5543988885555")
    assert criado.first_name == "Bia"
    assert criado.ref.startswith("WEB-")
    assert ContactPoint.objects.filter(
        customer=criado, type=ContactPoint.Type.PHONE
    ).exists()
