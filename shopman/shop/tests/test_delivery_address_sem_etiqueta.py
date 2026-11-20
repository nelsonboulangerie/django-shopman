"""O endereço que um pedido de entrega grava no cadastro nasce SEM etiqueta (#2775).

Gravava "Entrega" em todo endereço, e o cliente do iFood ficava com três endereços
chamados "Entrega": a etiqueta repetia o canal e não distinguia um do outro. Sem
etiqueta, quem fala nas telas é o próprio endereço.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps
from shopman.guestman.models import Customer, CustomerAddress, PriceTier

from shopman.shop.services.customer import _save_delivery_address

pytestmark = pytest.mark.django_db

migration = importlib.import_module("shopman.shop.migrations.0123_endereco_de_entrega_sem_etiqueta")

ADDRESS = "Rua das Flores, 123, Centro, Londrina - PR, 86020-000"


def _customer() -> Customer:
    tier, _ = PriceTier.objects.get_or_create(
        ref="regular", defaults={"name": "Regular", "is_default": True, "priority": 0}
    )
    return Customer.objects.create(ref="CUST-2775", first_name="Ana", phone="+5543999992775", price_tiers=tier)


def _order(address: str = ADDRESS) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "delivery_address": address,
            "delivery_address_structured": {
                "route": "Rua das Flores", "street_number": "123", "neighborhood": "Centro",
                "city": "Londrina", "state_code": "PR", "postal_code": "86020-000",
                "latitude": -23.31, "longitude": -51.16,
            },
        },
        snapshot={},
    )


def test_pedido_de_entrega_grava_o_endereco_sem_etiqueta():
    customer = _customer()

    _save_delivery_address({"ref": customer.ref}, _order())

    saved = CustomerAddress.objects.get(customer=customer)
    assert saved.formatted_address == ADDRESS
    assert (saved.label, saved.label_custom) == ("other", "")
    assert saved.is_default is True


def test_o_endereco_que_ja_existe_nao_ganha_etiqueta_nova():
    customer = _customer()
    CustomerAddress.objects.create(
        customer=customer, label="home", formatted_address=ADDRESS, is_default=True,
    )

    _save_delivery_address({"ref": customer.ref}, _order())

    saved = CustomerAddress.objects.get(customer=customer)
    assert (saved.label, saved.label_custom) == ("home", "")


def test_dois_pedidos_em_enderecos_diferentes_nao_repetem_etiqueta():
    customer = _customer()

    _save_delivery_address({"ref": customer.ref}, _order())
    _save_delivery_address({"ref": customer.ref}, _order("Av. Higienópolis, 50, Centro, Londrina - PR"))

    labels = list(CustomerAddress.objects.filter(customer=customer).values_list("label_custom", flat=True))
    assert labels == ["", ""]


# ── A migração que limpa o que já foi gravado (shop.0123) ─────────────


def _address(customer, label, label_custom="", formatted="Rua A, 1", **extra):
    return CustomerAddress.objects.create(
        customer=customer, label=label, label_custom=label_custom, formatted_address=formatted, **extra,
    )


def test_migracao_tira_so_a_etiqueta_exata_que_o_sistema_gravava(capsys):
    customer = _customer()
    gravados = [
        _address(customer, "other", "Entrega", f"Rua do iFood, {n}", is_default=(n == 1),
                 latitude="-23.3100000", longitude="-51.1600000", place_id=f"place-{n}")
        for n in (1, 2, 3)
    ]
    casa = _address(customer, "home", formatted="Rua da Casa, 10")
    trabalho = _address(customer, "work", formatted="Rua do Trabalho, 20")
    mae = _address(customer, "other", "Casa da mãe", "Rua da Mãe, 30")
    # Variações só saem da mão de alguém: nenhum escritor do sistema as grava.
    a_mao = [
        _address(customer, "other", label, f"Rua Escrita, {n}")
        for n, label in enumerate(("entrega", "Entrega ", "ENTREGA", "Entrega da tarde"))
    ]
    revisions = {row.pk: row.updated_at for row in CustomerAddress.objects.all()}

    touched = migration.drop_system_delivery_label(apps, None)

    # O log do deploy diz quantos endereços perderam a etiqueta.
    assert touched == 3
    assert '3 endereços perderam a etiqueta "Entrega"' in capsys.readouterr().out
    for row in gravados:
        row.refresh_from_db()
        assert (row.label, row.label_custom) == ("other", "")
    # Nada além da etiqueta muda: o endereço, o lugar e o padrão ficam.
    assert [row.formatted_address for row in gravados] == ["Rua do iFood, 1", "Rua do iFood, 2", "Rua do iFood, 3"]
    assert [row.place_id for row in gravados] == ["place-1", "place-2", "place-3"]
    assert [row.is_default for row in gravados] == [True, False, False]
    assert all(row.latitude is not None for row in gravados)
    # Nem a revisão que o Gestor confere ao editar.
    assert {row.pk: row.updated_at for row in CustomerAddress.objects.all()} == revisions
    for row, expected in ((casa, ("home", "")), (trabalho, ("work", "")), (mae, ("other", "Casa da mãe"))):
        row.refresh_from_db()
        assert (row.label, row.label_custom) == expected
    assert sorted(CustomerAddress.objects.filter(pk__in=[r.pk for r in a_mao]).values_list("label_custom", flat=True)) == [
        "ENTREGA", "Entrega ", "Entrega da tarde", "entrega",
    ]
    # Não apaga nem junta: os dez endereços continuam lá.
    assert CustomerAddress.objects.filter(customer=customer).count() == 10


def test_migracao_rodada_duas_vezes_nao_muda_nada(capsys):
    customer = _customer()
    _address(customer, "other", "Entrega", "Rua do iFood, 1")
    _address(customer, "home", formatted="Rua da Casa, 10")

    assert migration.drop_system_delivery_label(apps, None) == 1
    first = list(CustomerAddress.objects.order_by("pk").values_list("label", "label_custom", "updated_at"))
    assert migration.drop_system_delivery_label(apps, None) == 0
    assert "0 endereços perderam" in capsys.readouterr().out
    second = list(CustomerAddress.objects.order_by("pk").values_list("label", "label_custom", "updated_at"))

    assert first == second
    assert [row[:2] for row in first] == [("other", ""), ("home", "")]
