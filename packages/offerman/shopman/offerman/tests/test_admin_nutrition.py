"""Admin form test for Product nutrition fields."""

from __future__ import annotations

import pytest
from shopman.offerman.contrib.admin_unfold.nutrition_form import ProductAdminForm
from shopman.offerman.models import Product

pytestmark = pytest.mark.django_db


def _base_data(**overrides) -> dict:
    data = {
        "sku": "TST",
        "name": "Test",
        "unit": "un",
        "short_description": "",
        "long_description": "",
        "keywords": "",
        "base_price_q": "100",
        "availability_policy": "planned_ok",
        "ingredients_text": "",
        "is_published": "on",
        "is_sellable": "on",
        "nutrition_facts": "{}",
        "metadata": "{}",
    }
    data.update(overrides)
    return data


def test_form_renders_nutrition_fields():
    form = ProductAdminForm()
    # Virtual fields injected
    for name in (
        "serving_size_g",
        "energy_kcal",
        "carbohydrates_g",
        "sugars_g",
        "sodium_mg",
    ):
        assert name in form.fields

    for name in (
        "allergens_text",
        "dietary_info_text",
        "serves_text",
        "approx_dimensions_text",
    ):
        assert name in form.fields


@pytest.fixture
def sem_provedor(settings):
    """Força o contrato do Core: rodar SEM provedor de rotulagem.

    Sem isto o teste muda de resultado conforme o settings que o pytest escolhe
    (o do pacote não tem o `shop`; o do projeto tem), e um teste que depende de
    como foi invocado não afirma nada.
    """
    settings.OFFERMAN = {**getattr(settings, "OFFERMAN", {}), "LABEL_ATTRIBUTES_PROVIDER": None}
    return settings


def test_the_core_has_no_opinion_about_label_vocabulary(sem_provedor):
    """O Offerman roda SOZINHO, e é isso que esta suíte prova.

    Alérgeno, dieta e porção são vocabulário do TENANT: quem os define é o
    registro do orquestrador, alcançado por
    ``OFFERMAN["LABEL_ATTRIBUTES_PROVIDER"]``. Nesta suíte não há orquestrador —
    de propósito — e então não há provedor.

    O contrato do Core aqui é **não quebrar**: os campos existem no formulário,
    o save funciona, e nada de vocabulário de tenant vaza para o ``metadata``.
    O caminho COM provedor é responsabilidade de quem o configura, e tem teste
    do outro lado (``shopman/shop/tests/test_label_provider.py``).
    """
    from shopman.offerman.contrib.admin_unfold.nutrition_form import _label_attributes

    assert _label_attributes() is None


def test_form_populates_initial_from_instance(sem_provedor):
    product = Product.objects.create(
        sku="INIT",
        name="Init",
        base_price_q=100,
        nutrition_facts={
            "serving_size_g": 50,
            "energy_kcal": 180.0,
            "proteins_g": 6.0,
            "auto_filled": False,
        },
        metadata={"approx_dimensions": "aprox. 24 x 12 x 10 cm"},
    )
    form = ProductAdminForm(instance=product)
    assert form.fields["serving_size_g"].initial == 50
    assert form.fields["energy_kcal"].initial == 180.0
    assert form.fields["proteins_g"].initial == 6.0
    # Sem provedor de rotulagem, os três campos do tenant ficam em branco — e
    # `approx_dimensions`, que é do próprio catálogo, continua vindo.
    assert not form.fields["allergens_text"].initial
    assert form.fields["approx_dimensions_text"].initial == "aprox. 24 x 12 x 10 cm"


def test_form_serializes_to_json_on_save():
    product = Product.objects.create(
        sku="SAVE",
        name="Save",
        base_price_q=100,
    )
    data = _base_data(
        sku="SAVE",
        name="Save",
        serving_size_g="50",
        energy_kcal="180",
        proteins_g="6",
    )
    form = ProductAdminForm(data=data, instance=product)
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.nutrition_facts["serving_size_g"] == 50
    assert saved.nutrition_facts["energy_kcal"] == 180.0
    assert saved.nutrition_facts["auto_filled"] is False


def test_form_serializes_remote_purchase_metadata_on_save(sem_provedor):
    product = Product.objects.create(
        sku="META",
        name="Meta",
        base_price_q=100,
        metadata={"external_id": "keep"},
    )
    data = _base_data(
        sku="META",
        name="Meta",
        metadata='{"external_id": "keep"}',
        allergens_text="glúten, gergelim",
        dietary_info_text="100% vegetal, sem lactose",
        serves_text="2 a 4 pessoas",
        approx_dimensions_text="aprox. 24 x 12 x 10 cm",
    )
    form = ProductAdminForm(data=data, instance=product)
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    # Sem provedor, nada de vocabulário de tenant entra no metadata — nem as
    # chaves antigas, que morreram, nem o registro, que é do orquestrador.
    for morta in ("allergens", "dietary_info", "serves", "dietary_auto_filled", "attributes"):
        assert morta not in saved.metadata
    assert saved.metadata == {
        "external_id": "keep",
        "approx_dimensions": "aprox. 24 x 12 x 10 cm",
        "allows_next_day_sale": False,
        # Promessa da casa ("Preparado na hora"): switch próprio, gravado sempre
        # — inclusive como False. O selo da sacola lê SÓ este campo; deduzi-lo de
        # `availability_policy` acoplava promessa a política de estoque.
        "made_to_order": False,
    }


def test_form_rejects_invalid_invariant():
    """trans > total must be blocked by Product.clean() via form.full_clean()."""
    product = Product.objects.create(
        sku="BAD",
        name="Bad",
        base_price_q=100,
    )
    data = _base_data(
        sku="BAD",
        name="Bad",
        serving_size_g="50",
        total_fat_g="2",
        trans_fat_g="3",
    )
    form = ProductAdminForm(data=data, instance=product)
    assert not form.is_valid()


def test_form_declares_the_ready_time():
    """"Pronto a partir de" chega normalizado ao metadata."""
    product = Product.objects.create(sku="BF", name="Baguette", base_price_q=1600)
    form = ProductAdminForm(
        data=_base_data(sku="BF", name="Baguette", ready_from="9:5"), instance=product
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.metadata["ready_from"] == "09:05"


def test_form_refuses_an_unreadable_ready_time():
    """Hora ilegível DÓI na porta.

    Guardá-la seria pior: o cadastro diria que a casa respondeu, e o resto do
    sistema agiria como se ninguém tivesse respondido — que é justamente o estado
    que libera qualquer horário ao cliente.
    """
    product = Product.objects.create(sku="BF2", name="Baguette", base_price_q=1600)
    form = ProductAdminForm(
        data=_base_data(sku="BF2", name="Baguette", ready_from="12h"), instance=product
    )
    assert not form.is_valid()
    assert "ready_from" in form.errors


def test_form_clears_the_ready_time_when_emptied():
    """Em branco APAGA — a casa pode devolver a palavra ao histórico."""
    product = Product.objects.create(
        sku="BF3", name="Baguette", base_price_q=1600, metadata={"ready_from": "12:00"}
    )
    form = ProductAdminForm(
        data=_base_data(sku="BF3", name="Baguette", ready_from=""), instance=product
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert "ready_from" not in saved.metadata
