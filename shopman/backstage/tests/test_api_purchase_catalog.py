"""Cadastro da Base do Compras (api/v1/backstage/purchase/*): insumo, fornecedor,
contato e conversão.

A API de operação já existia; o que se prova aqui é a escrita que faltava:
criar, editar e duplicar sem passar pelo Admin, com o Core intacto.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierContact

from shopman.backstage.models import DayClosing


def _operate_purchase_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="operate_purchase",
    )


@pytest.fixture
def purchase_operator(db):
    user = User.objects.create_user("purchase-catalog", password="pw", is_staff=True)
    user.user_permissions.add(_operate_purchase_perm())
    return user


@pytest.fixture
def material(db):
    return Material.objects.create(
        sku="FARINHA-NOVARA-T55",
        name="Farinha T65",
        unit="kg",
        shelf_life_days=180,
        metadata={
            "purchase": {
                "category": "Farinhas",
                "min_stock": "30",
                "eans": ["7891000053508"],
                "request_status": "sent",
            }
        },
    )


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        ref="moinho-sp",
        name="Moinho São Paulo",
        document="12.345.678/0001-90",
        metadata={
            "purchase": {
                "lead_time_days": 2,
                "payment_term": "14 dias",
                "invoice_product_map": {"FAR-25": "FARINHA-NOVARA-T55"},
                "receipt_volume_counts": {"4126": 3},
            }
        },
    )


def _post(client, name, data=None, args=None, *, key=None):
    return client.post(
        reverse(name, args=args or []),
        data=json.dumps(data or {}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


# ── Permissão ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_catalog_writes_require_operate_purchase(client):
    bare = User.objects.create_user("bare-catalog", password="pw", is_staff=True)
    client.force_login(bare)

    assert _post(client, "api-backstage-purchase-materials", {"sku": "X", "name": "X", "unit": "kg"}).status_code == 403
    assert _post(client, "api-backstage-purchase-suppliers", {"name": "X"}).status_code == 403
    assert Material.objects.count() == 0
    assert Supplier.objects.count() == 0


# ── Insumo ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_material_persists_and_returns_projection(client, purchase_operator):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-materials",
        {
            "sku": "MANTEIGA-PRESIDENT",
            "name": "Manteiga francesa",
            "unit": "kg",
            "shelfLifeDays": 90,
            "isActive": True,
            "category": "Laticínios",
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["ok"] is True
    assert body["message"] == "Insumo Manteiga francesa criado."
    assert body["resource"] == {"kind": "material", "ref": "MANTEIGA-PRESIDENT"}
    created = Material.objects.get(sku="MANTEIGA-PRESIDENT")
    assert created.unit == "kg"
    assert created.shelf_life_days == 90
    assert created.metadata["purchase"]["category"] == "Laticínios"
    rows = {row["sku"]: row for row in body["purchase"]["materials"]}
    assert rows["MANTEIGA-PRESIDENT"]["category"] == "Laticínios"


@pytest.mark.django_db
def test_create_material_refuses_duplicate_sku_ignoring_case(client, purchase_operator, material):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-materials",
        {"sku": "farinha-novara-t55", "name": "Outra", "unit": "kg"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "material_sku_exists"
    assert response.json()["field"] == "sku"
    assert Material.objects.count() == 1


@pytest.mark.django_db
def test_create_material_requires_sku_and_name(client, purchase_operator):
    client.force_login(purchase_operator)

    missing_sku = _post(client, "api-backstage-purchase-materials", {"name": "Sem SKU", "unit": "kg"})
    assert missing_sku.status_code == 400
    assert missing_sku.json()["field"] == "sku"

    missing_name = _post(client, "api-backstage-purchase-materials", {"sku": "SEM-NOME", "unit": "kg"})
    assert missing_name.status_code == 400
    assert missing_name.json()["field"] == "name"


@pytest.mark.django_db
def test_create_material_refuses_bad_unit_and_negative_shelf_life(client, purchase_operator):
    client.force_login(purchase_operator)

    bad_unit = _post(client, "api-backstage-purchase-materials", {"sku": "A", "name": "A", "unit": "cx"})
    assert bad_unit.status_code == 400
    assert bad_unit.json()["field"] == "unit"

    bad_shelf = _post(
        client, "api-backstage-purchase-materials",
        {"sku": "B", "name": "B", "unit": "kg", "shelfLifeDays": -1},
    )
    assert bad_shelf.status_code == 400
    assert bad_shelf.json()["field"] == "shelfLifeDays"

    fractional = _post(
        client, "api-backstage-purchase-materials",
        {"sku": "C", "name": "C", "unit": "kg", "shelfLifeDays": "1,5"},
    )
    assert fractional.status_code == 400
    assert fractional.json()["error"]["code"] == "shelf_life_invalid"


@pytest.mark.django_db
def test_create_material_refuses_a_flag_that_is_not_yes_or_no(client, purchase_operator):
    """O parser do service é estrito: "talvez" é recusa com campo, nunca False calado."""
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-materials",
        {"sku": "FLAG-INVALIDA", "name": "Flag", "unit": "kg", "isActive": "talvez"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "isActive_invalid"
    assert response.json()["field"] == "isActive"
    assert Material.objects.count() == 0


@pytest.mark.django_db
def test_update_material_keeps_untouched_metadata(client, purchase_operator, material):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-material",
        {"name": "Farinha T80", "unit": "kg", "shelfLifeDays": None, "category": "Farinhas especiais"},
        args=[material.sku],
    )

    assert response.status_code == 200, response.json()
    material.refresh_from_db()
    assert material.name == "Farinha T80"
    assert material.shelf_life_days is None
    assert material.metadata["purchase"]["category"] == "Farinhas especiais"
    # O resto do metadata do insumo continua onde estava.
    assert material.metadata["purchase"]["min_stock"] == "30"
    assert material.metadata["purchase"]["eans"] == ["7891000053508"]


@pytest.mark.django_db
def test_update_material_unknown_sku_is_404(client, purchase_operator):
    client.force_login(purchase_operator)
    response = _post(client, "api-backstage-purchase-material", {"name": "X"}, args=["NAO-EXISTE"])
    assert response.status_code == 404


@pytest.mark.django_db
def test_update_material_refuses_a_stale_form(client, purchase_operator, material):
    stale_revision = material.updated_at.isoformat()
    material.name = "Alterado em outra tela"
    material.save()
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-material",
        {"name": "Meu rascunho", "expectedRevision": stale_revision},
        args=[material.sku],
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "catalog_changed"
    material.refresh_from_db()
    assert material.name == "Alterado em outra tela"


@pytest.mark.django_db
def test_duplicate_material_copies_content_but_not_identity(client, purchase_operator, material):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-material-duplicate",
        {"sku": "FARINHA-NOVARA-T80", "name": "Farinha T80"},
        args=[material.sku],
    )

    assert response.status_code == 200, response.json()
    assert response.json()["resource"] == {"kind": "material", "ref": "FARINHA-NOVARA-T80"}
    copy = Material.objects.get(sku="FARINHA-NOVARA-T80")
    assert copy.name == "Farinha T80"
    assert copy.unit == "kg"
    assert copy.shelf_life_days == 180
    assert copy.metadata["purchase"]["category"] == "Farinhas"
    # Identidade e decisão operacional do original não atravessam a cópia.
    assert "eans" not in copy.metadata["purchase"]
    assert "min_stock" not in copy.metadata["purchase"]
    assert "request_status" not in copy.metadata["purchase"]


@pytest.mark.django_db
def test_duplicate_material_refuses_the_same_sku(client, purchase_operator, material):
    client.force_login(purchase_operator)
    response = _post(
        client,
        "api-backstage-purchase-material-duplicate",
        {"sku": material.sku, "name": "Cópia"},
        args=[material.sku],
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "material_sku_same"
    assert Material.objects.count() == 1


# ── Fornecedor ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_supplier_derives_ref_from_the_name(client, purchase_operator):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-suppliers",
        {
            "name": "Indústria e Comércio de Produtos Alimentícios Tamura Ltda.",
            "tradeName": "Tamura",
            "document": "84.290.690/0002-28",
            "email": "pedidos@tamura.example",
            "phone": "43 3322-1100",
            "leadTimeDays": 3,
            "paymentTerm": "21 dias",
        },
    )

    assert response.status_code == 200, response.json()
    supplier = Supplier.objects.get()
    assert supplier.ref == "tamura"
    assert supplier.trade_name == "Tamura"
    assert supplier.metadata["purchase"]["lead_time_days"] == 3
    assert supplier.metadata["purchase"]["payment_term"] == "21 dias"
    assert response.json()["message"] == "Fornecedor cadastrado."
    assert response.json()["resource"] == {"kind": "supplier", "ref": "tamura"}


@pytest.mark.django_db
def test_create_supplier_returns_the_exact_generated_ref_with_homonyms(client, purchase_operator):
    Supplier.objects.create(ref="tamura", name="Tamura")
    client.force_login(purchase_operator)

    response = _post(client, "api-backstage-purchase-suppliers", {"name": "Tamura"})

    assert response.status_code == 200, response.json()
    assert response.json()["resource"] == {"kind": "supplier", "ref": "tamura-2"}
    assert Supplier.objects.filter(ref="tamura-2").exists()


@pytest.mark.django_db
def test_create_supplier_retry_returns_the_same_record(client, purchase_operator):
    """Resposta perdida não pode transformar o reenvio em outro fornecedor."""
    client.force_login(purchase_operator)
    key = str(uuid4())
    payload = {"name": "Tamura"}

    first = _post(client, "api-backstage-purchase-suppliers", payload, key=key)
    retried = _post(client, "api-backstage-purchase-suppliers", payload, key=key)

    assert first.status_code == retried.status_code == 200
    assert first.json()["resource"] == retried.json()["resource"]
    assert Supplier.objects.count() == 1


@pytest.mark.django_db
def test_create_supplier_refuses_reusing_intention_for_other_payload(client, purchase_operator):
    client.force_login(purchase_operator)
    key = str(uuid4())

    assert _post(client, "api-backstage-purchase-suppliers", {"name": "Tamura"}, key=key).status_code == 200
    conflict = _post(client, "api-backstage-purchase-suppliers", {"name": "Outro"}, key=key)

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "intention_conflict"
    assert Supplier.objects.count() == 1


@pytest.mark.django_db
def test_supplier_refuses_fractional_or_negative_delivery_days(client, purchase_operator):
    client.force_login(purchase_operator)

    for value in ("1,5", -1):
        response = _post(
            client,
            "api-backstage-purchase-suppliers",
            {"name": "Prazo inválido", "leadTimeDays": value},
        )
        assert response.status_code == 400
        assert response.json()["field"] == "leadTimeDays"


@pytest.mark.django_db
def test_create_supplier_refuses_duplicate_ref(client, purchase_operator, supplier):
    client.force_login(purchase_operator)
    response = _post(
        client,
        "api-backstage-purchase-suppliers",
        {"ref": supplier.ref, "name": "Outro Moinho"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "supplier_ref_exists"
    assert response.json()["field"] == "ref"


@pytest.mark.django_db
def test_update_supplier_changes_commercial_terms(client, purchase_operator, supplier):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-supplier",
        {"tradeName": "Moinho SP", "leadTimeDays": 5, "paymentTerm": "28 dias"},
        args=[supplier.ref],
    )

    assert response.status_code == 200, response.json()
    supplier.refresh_from_db()
    assert supplier.trade_name == "Moinho SP"
    assert supplier.metadata["purchase"]["lead_time_days"] == 5
    assert supplier.metadata["purchase"]["payment_term"] == "28 dias"
    # O de-para de nota continua sendo história daquele fornecedor.
    assert supplier.metadata["purchase"]["invoice_product_map"] == {"FAR-25": "FARINHA-NOVARA-T55"}


@pytest.mark.django_db
def test_update_supplier_refuses_a_stale_form(client, purchase_operator, supplier):
    stale_revision = supplier.updated_at.isoformat()
    supplier.trade_name = "Alterado em outra tela"
    supplier.save()
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-supplier",
        {"tradeName": "Meu rascunho", "expectedRevision": stale_revision},
        args=[supplier.ref],
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "catalog_changed"
    supplier.refresh_from_db()
    assert supplier.trade_name == "Alterado em outra tela"


@pytest.mark.django_db
def test_duplicate_supplier_copies_contacts_and_terms_but_not_document(client, purchase_operator, supplier):
    SupplierContact.objects.create(
        supplier=supplier, name="Cláudia Ramos", role="sales",
        email="claudia@moinho.example", is_primary=True,
    )
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-supplier-duplicate",
        {"ref": "moinho-sp-2", "name": "Moinho São Paulo Filial"},
        args=[supplier.ref],
    )

    assert response.status_code == 200, response.json()
    assert response.json()["resource"] == {"kind": "supplier", "ref": "moinho-sp-2"}
    copy = Supplier.objects.get(ref="moinho-sp-2")
    assert copy.name == "Moinho São Paulo Filial"
    assert copy.document == ""
    assert copy.metadata["purchase"]["lead_time_days"] == 2
    assert "invoice_product_map" not in copy.metadata["purchase"]
    contacts = list(copy.contacts.all())
    assert len(contacts) == 1
    assert contacts[0].name == "Cláudia Ramos"
    # O primeiro contato do papel vira principal sozinho, também na cópia.
    assert contacts[0].is_primary is True


# ── Contato ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_contact_needs_a_way_to_reach(client, purchase_operator, supplier):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-supplier-contacts",
        {"name": "Sem meio", "role": "sales"},
        args=[supplier.ref],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "contact_reach_required"
    assert SupplierContact.objects.count() == 0


@pytest.mark.django_db
def test_create_contact_normalizes_phone_and_promotes_the_first(client, purchase_operator, supplier):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-supplier-contacts",
        {"name": "Cláudia Ramos", "role": "sales", "phone": "43 99999-0000"},
        args=[supplier.ref],
    )

    assert response.status_code == 200, response.json()
    contact = SupplierContact.objects.get(supplier=supplier)
    assert contact.is_primary is True
    assert contact.phone != ""
    body = response.json()
    people = body["purchase"]["suppliers"][0]["contacts"]
    assert people[0]["name"] == "Cláudia Ramos"
    assert people[0]["phone"] == contact.phone


@pytest.mark.django_db
def test_create_contact_retry_does_not_duplicate_the_person(client, purchase_operator, supplier):
    client.force_login(purchase_operator)
    key = str(uuid4())
    payload = {"name": "Cláudia Ramos", "role": "sales", "phone": "43 99999-0000"}

    first = _post(
        client, "api-backstage-purchase-supplier-contacts", payload,
        args=[supplier.ref], key=key,
    )
    retried = _post(
        client, "api-backstage-purchase-supplier-contacts", payload,
        args=[supplier.ref], key=key,
    )

    assert first.status_code == retried.status_code == 200
    assert SupplierContact.objects.filter(supplier=supplier).count() == 1


@pytest.mark.django_db
def test_create_contact_refuses_an_invalid_email(client, purchase_operator, supplier):
    client.force_login(purchase_operator)

    response = _post(
        client,
        "api-backstage-purchase-supplier-contacts",
        {"name": "Cláudia", "role": "sales", "email": "email-inválido"},
        args=[supplier.ref],
    )

    assert response.status_code == 400
    assert response.json()["field"] == "email"
    assert SupplierContact.objects.count() == 0


@pytest.mark.django_db
def test_update_contact_saves_and_refuses_retiring_the_primary(client, purchase_operator, supplier):
    contact = SupplierContact.objects.create(
        supplier=supplier, name="Cláudia Ramos", role="sales",
        email="claudia@moinho.example", is_primary=True,
    )
    client.force_login(purchase_operator)

    saved = _post(
        client, "api-backstage-purchase-contact",
        {"name": "Cláudia Ramos Silva", "notes": "Atende das 8h às 17h."},
        args=[contact.pk],
    )
    assert saved.status_code == 200, saved.json()
    contact.refresh_from_db()
    assert contact.name == "Cláudia Ramos Silva"
    assert contact.notes == "Atende das 8h às 17h."

    refused = _post(
        client, "api-backstage-purchase-contact", {"isActive": False}, args=[contact.pk],
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "contact_refused"
    contact.refresh_from_db()
    assert contact.is_active is True


# ── Conversão ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_update_conversion_fixes_the_factor(client, purchase_operator, material):
    conversion = MaterialConversion.objects.create(
        material=material, label="saco 25 kg", to_base_factor=Decimal("25"),
    )
    client.force_login(purchase_operator)

    response = _post(
        client, "api-backstage-purchase-conversion",
        {"label": "saco 20 kg", "factor": "20"},
        args=[conversion.pk],
    )

    assert response.status_code == 200, response.json()
    conversion.refresh_from_db()
    assert conversion.label == "saco 20 kg"
    assert conversion.to_base_factor == Decimal("20.000000")
    assert response.json()["message"] == "Conversão salva: 1 saco 20 kg = 20 kg."


@pytest.mark.django_db
def test_update_conversion_refuses_a_factor_that_is_not_positive(client, purchase_operator, material):
    conversion = MaterialConversion.objects.create(
        material=material, label="saco 25 kg", to_base_factor=Decimal("25"),
    )
    client.force_login(purchase_operator)

    response = _post(
        client, "api-backstage-purchase-conversion", {"factor": "0"}, args=[conversion.pk],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "conversion_factor_invalid"
    conversion.refresh_from_db()
    assert conversion.to_base_factor == Decimal("25.000000")


# ── Leitura: o cadastro não piorou a projeção ───────────────────────────────


@pytest.mark.django_db
def test_purchase_board_query_budget_is_unchanged(client, purchase_operator, material, supplier):
    """A projeção do Compras vista pela API. O cadastro não encosta na leitura.

    O número é o teto MEDIDO antes desta frente (o mesmo do origin/main, porque
    esta frente não toca `projections/purchase.py`): se a criação/edição tivesse
    trazido consulta para o GET, este teste pegaria.
    """
    client.force_login(purchase_operator)
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("api-backstage-purchase"))

    assert response.status_code == 200
    # 31 no dataset deste teste (medido em 31/10 no worktree); o teto guarda folga
    # sem deixar passar um N+1 que dobre a contagem.
    assert len(captured) <= 40, f"O board passou do teto: {len(captured)} consultas."


@pytest.mark.django_db
def test_create_material_costs_a_bounded_number_of_queries(client, purchase_operator):
    """Criar e devolver a projeção é um gesto só; sem laço de escrita por linha."""
    client.force_login(purchase_operator)
    with CaptureQueriesContext(connection) as captured:
        response = _post(
            client, "api-backstage-purchase-materials",
            {"sku": "NOVO-INSUMO", "name": "Novo insumo", "unit": "kg"},
        )
    assert response.status_code == 200, response.json()
    # 45 neste dataset: escrita + projeção inteira + recibo idempotente local.
    # O teto mantém folga curta sem esconder N+1; o custo não cresce com a Base.
    assert len(captured) <= 48, f"Criar insumo custou {len(captured)} consultas."
