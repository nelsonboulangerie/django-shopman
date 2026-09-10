"""Contatos do fornecedor: quem recebe o pedido, e com que nome ele cumprimenta.

O pedido de compra saía endereçado à razão social ("Olá, INDUSTRIA E COMERCIO
DE PRODUTOS ALIMENTICIOS TAMURA LTDA.") porque era o único nome que o sistema
tinha. Estes testes prendem os três degraus da rota — pessoa, contato gravado
no metadata, central da empresa — e a regra de que a saudação pessoal só
acompanha a mensagem que foi de fato para a pessoa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.apps import apps
from shopman.buyman.models import (
    Material,
    MaterialConversion,
    Supplier,
    SupplierContact,
    SupplierMaterialCost,
)
from shopman.orderman.models import Directive
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services.purchase import (
    PurchaseError,
    _supplier_dispatch_route,
    set_purchase_request_status,
)
from shopman.shop.adapters._notification_templates import derive_context
from shopman.shop.adapters.notification_email import BODY_TEMPLATES
from shopman.shop.directives import NOTIFICATION_SEND

Role = SupplierContact.Role


def _deposito():
    """A sugestão de reposição só existe com posição padrão; o pedido depende dela."""
    return Position.objects.get_or_create(
        ref="deposito",
        defaults={"name": "Depósito", "kind": PositionKind.PHYSICAL, "is_default": True},
    )[0]


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        ref="tamura",
        name="INDUSTRIA E COMERCIO DE PRODUTOS ALIMENTICIOS TAMURA LTDA",
        trade_name="Tamura",
        document="84.290.690/0002-28",
        email="central@tamura.example",
    )


@pytest.fixture
def material(db):
    return Material.objects.create(
        sku="CAFE-GRAO",
        name="Café em grão da casa",
        unit="kg",
        metadata={"purchase": {"min_stock": "20"}},
    )


@pytest.fixture
def preferred_cost(material, supplier):
    conversion = MaterialConversion.objects.create(
        material=material,
        supplier=supplier,
        label="Pacote 500g",
        to_base_factor=Decimal("0.5"),
    )
    return SupplierMaterialCost.objects.create(
        material=material,
        supplier=supplier,
        conversion=conversion,
        cost_q=5925,
        is_preferred=True,
    )


# ── Rota ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_route_prefers_the_person_over_the_company_switchboard(supplier):
    SupplierContact.objects.create(
        supplier=supplier, name="Marcelo Tanaka", role=Role.SALES,
        email="marcelo@tamura.example",
    )

    route = _supplier_dispatch_route(supplier)

    assert route.recipient == "marcelo@tamura.example"
    assert route.contact_name == "Marcelo"


@pytest.mark.django_db
def test_route_falls_back_to_the_switchboard_without_a_greeting(supplier):
    """Sem pessoa, o pedido sai — e cumprimenta a casa, não um nome inventado."""
    route = _supplier_dispatch_route(supplier)

    assert route.recipient == "central@tamura.example"
    assert route.contact_name == ""


@pytest.mark.django_db
def test_route_never_greets_a_person_it_did_not_write_to(supplier):
    """O comercial só deixou telefone; o e-mail vai para a central, sem o nome.

    Cumprimentar "Olá, Marcelo" numa mensagem que caiu na caixa geral da
    empresa é pior do que não cumprimentar ninguém.
    """
    SupplierContact.objects.create(
        supplier=supplier, name="Marcelo Tanaka", role=Role.SALES, phone="43999998888",
    )
    supplier.metadata = {"purchase": {"order_channel": "email"}}
    supplier.save(update_fields=["metadata", "updated_at"])

    route = _supplier_dispatch_route(supplier)

    assert route.recipient == "central@tamura.example"
    assert route.contact_name == ""


@pytest.mark.django_db
def test_route_does_not_leak_into_another_role(supplier):
    """Só o financeiro cadastrado: o pedido de compra NÃO cai nele."""
    SupplierContact.objects.create(
        supplier=supplier, name="Rita", role=Role.FINANCE, email="rita@tamura.example",
    )

    route = _supplier_dispatch_route(supplier)

    assert route.recipient == "central@tamura.example"


@pytest.mark.django_db
def test_route_refuses_when_nobody_is_reachable(supplier):
    supplier.email = ""
    supplier.phone = ""
    supplier.save(update_fields=["email", "phone", "updated_at"])

    with pytest.raises(PurchaseError) as exc:
        _supplier_dispatch_route(supplier)

    assert exc.value.code == "supplier_contact_missing"


# ── O que sai na mensagem ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_purchase_request_greets_the_person_by_first_name(supplier, material, preferred_cost):
    _deposito()
    SupplierContact.objects.create(
        supplier=supplier, name="Marcelo Tanaka", role=Role.SALES,
        email="marcelo@tamura.example",
    )

    set_purchase_request_status(material.sku, "sent")

    directive = Directive.objects.get(topic=NOTIFICATION_SEND, payload__event="purchase_request")
    context = directive.payload["context"]
    assert directive.payload["recipient"] == "marcelo@tamura.example"
    assert context["contact_name"] == "Marcelo"
    # O nome fantasia é o que vai na mensagem; a razão social fica no rodapé.
    assert context["supplier_name"] == "Tamura"
    assert context["supplier_legal_name"].startswith("INDUSTRIA E COMERCIO")

    body = BODY_TEMPLATES["purchase_request"].format_map(derive_context(context))
    assert body.startswith("Olá, Marcelo!")
    assert "INDUSTRIA E COMERCIO" not in body


@pytest.mark.django_db
def test_purchase_request_greets_the_house_when_nobody_is_registered(supplier, material, preferred_cost):
    _deposito()

    set_purchase_request_status(material.sku, "sent")

    directive = Directive.objects.get(topic=NOTIFICATION_SEND, payload__event="purchase_request")
    body = BODY_TEMPLATES["purchase_request"].format_map(derive_context(directive.payload["context"]))
    assert body.startswith("Olá, Tamura!")


@pytest.mark.django_db
def test_estimated_total_carries_the_thousands_separator(supplier, material, preferred_cost):
    """``R$ 1185,00`` lê como número de sistema; ``R$ 1.185,00`` lê como preço."""
    _deposito()

    set_purchase_request_status(material.sku, "sent")

    directive = Directive.objects.get(topic=NOTIFICATION_SEND, payload__event="purchase_request")
    total = directive.payload["context"]["estimated_total"]
    assert total.startswith("R$ ")
    assert "." in total.split(",")[0]


@pytest.mark.django_db
def test_receipt_rejection_tells_the_operator_whom_to_call(supplier):
    """A devolução é aviso interno: o valor do contato é dizer quem chamar."""
    SupplierContact.objects.create(
        supplier=supplier, name="Ana Prado", role=Role.QUALITY, email="ana@tamura.example",
    )
    from shopman.backstage.services.purchase import _supplier_contact_line

    line = _supplier_contact_line(supplier)
    assert "Ana Prado" in line
    assert "Qualidade" in line

    note = derive_context({"supplier_contact": line})["supplier_contact_note"]
    assert note.startswith("\n\nFalar com: Ana Prado")


@pytest.mark.django_db
def test_receipt_rejection_says_nothing_when_nobody_is_registered(supplier):
    """Sem pessoa, a linha some — em vez de mentir uma central como se fosse gente."""
    from shopman.backstage.services.purchase import _supplier_contact_line

    assert _supplier_contact_line(supplier) == ""
    assert derive_context({"supplier_contact": ""})["supplier_contact_note"] == ""


# ── O que a tela vê ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_projection_answers_who_receives_the_order_before_it_is_sent(supplier, material, preferred_cost):
    _deposito()
    SupplierContact.objects.create(
        supplier=supplier, name="Marcelo Tanaka", role=Role.SALES,
        email="marcelo@tamura.example",
    )
    SupplierContact.objects.create(
        supplier=supplier, name="Rita", role=Role.FINANCE, email="rita@tamura.example",
    )

    projected = next(item for item in build_purchase().suppliers if item.ref == supplier.ref)

    assert projected.displayName == "Tamura"
    assert projected.tradeName == "Tamura"
    assert projected.orderContactName == "Marcelo Tanaka"
    assert {person.roleLabel for person in projected.contacts} == {"Comercial", "Financeiro"}


@pytest.mark.django_db
def test_projection_says_nobody_when_the_order_would_fall_to_the_switchboard(supplier):
    projected = next(item for item in build_purchase().suppliers if item.ref == supplier.ref)

    assert projected.orderContactName == ""
    assert projected.contacts == ()
    assert projected.contact == "central@tamura.example"


@pytest.mark.django_db
def test_projection_does_not_query_per_supplier(django_assert_max_num_queries):
    """A tela lista todos os fornecedores: contato não pode custar uma query cada."""
    for index in range(6):
        supplier = Supplier.objects.create(ref=f"forn-{index}", name=f"Fornecedor {index}")
        SupplierContact.objects.create(
            supplier=supplier, name=f"Pessoa {index}", role=Role.SALES,
            email=f"p{index}@example.com",
        )

    Model = apps.get_model("buyman", "Supplier")
    assert Model.objects.count() == 6
    with django_assert_max_num_queries(20):
        build_purchase()
