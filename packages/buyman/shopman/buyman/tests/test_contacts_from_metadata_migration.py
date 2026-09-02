"""A conversão do escape hatch do metadata em ``SupplierContact`` (migração 0009).

O caso real que a motivou: o fornecedor `tamura`, criado por leitura de NF-e,
com ``order_contact``/``order_phone`` gravados à mão para o pedido chegar ao
Michael. Sem a conversão, a rota nova (que prefere a pessoa) passaria a ignorar
aquilo, e o dado ficaria em dois lugares envelhecendo em silêncio.
"""

from importlib import import_module

import pytest
from shopman.buyman.models import Supplier, SupplierContact

# O módulo começa com dígito: só dá para alcançá-lo por import dinâmico.
_0009 = import_module("shopman.buyman.migrations.0009_contacts_from_supplier_metadata")

pytestmark = pytest.mark.django_db


class _Apps:
    """O ``apps`` da migração, servido pelos modelos reais.

    A migração não usa nada que os históricos não tenham (sem métodos próprios,
    sem propriedades), então rodá-la contra os modelos vivos mede a lógica sem
    montar um migrator inteiro.
    """

    @staticmethod
    def get_model(app_label, model_name):
        return {"Supplier": Supplier, "SupplierContact": SupplierContact}[model_name]


def _run():
    _0009.contacts_from_metadata(_Apps, None)


def test_converts_the_hand_written_contact_into_a_person():
    supplier = Supplier.objects.create(
        ref="tamura",
        name="INDUSTRIA E COMERCIO DE PRODUTOS ALIMENTICIOS TAMURA LTDA",
        phone="4430265168",
        metadata={
            "purchase": {
                "created_from": "nfe_scan",
                "order_contact": "Michael Tamura",
                "order_phone": "+5544991131020",
            }
        },
    )

    _run()

    contact = SupplierContact.objects.get(supplier=supplier)
    assert contact.name == "Michael Tamura"
    assert contact.role == SupplierContact.Role.SALES
    assert contact.phone == "+5544991131020"
    assert contact.is_primary is True

    supplier.refresh_from_db()
    purchase = supplier.metadata["purchase"]
    # As chaves consumidas somem; o que não é pessoa fica.
    assert "order_contact" not in purchase
    assert "order_phone" not in purchase
    assert purchase["created_from"] == "nfe_scan"


def test_keeps_the_routing_preference_in_place():
    """Canal preferido é preferência de rota, não pessoa: não é consumido."""
    supplier = Supplier.objects.create(
        ref="moinho",
        name="Moinho",
        metadata={"purchase": {"order_channel": "email", "order_contact": "Ana", "order_email": "ana@moinho.example"}},
    )

    _run()

    supplier.refresh_from_db()
    assert supplier.metadata["purchase"]["order_channel"] == "email"
    assert SupplierContact.objects.get(supplier=supplier).email == "ana@moinho.example"


def test_a_bare_email_is_not_turned_into_a_nameless_person():
    supplier = Supplier.objects.create(
        ref="coop",
        name="Cooperativa",
        metadata={"purchase": {"order_contact": "pedidos@coop.example"}},
    )

    _run()

    assert not SupplierContact.objects.filter(supplier=supplier).exists()
    supplier.refresh_from_db()
    assert supplier.metadata["purchase"]["order_contact"] == "pedidos@coop.example"


def test_a_name_with_no_way_to_reach_is_left_alone():
    """A CheckConstraint recusaria — e recusar aqui seria quebrar o deploy."""
    supplier = Supplier.objects.create(
        ref="sem-meio", name="Sem meio", metadata={"purchase": {"order_contact": "Fulano"}},
    )

    _run()

    assert not SupplierContact.objects.filter(supplier=supplier).exists()


def test_does_not_overwrite_a_contact_already_registered():
    supplier = Supplier.objects.create(
        ref="tamura", name="Tamura",
        metadata={"purchase": {"order_contact": "Michael Tamura", "order_phone": "+5544991131020"}},
    )
    SupplierContact.objects.create(
        supplier=supplier, name="Quem já estava", role=SupplierContact.Role.SALES,
        email="ja@tamura.example",
    )

    _run()

    assert SupplierContact.objects.get(supplier=supplier).name == "Quem já estava"


def test_supplier_without_purchase_metadata_is_untouched():
    supplier = Supplier.objects.create(ref="anaconda", name="Anaconda", metadata={})

    _run()

    assert not SupplierContact.objects.filter(supplier=supplier).exists()
