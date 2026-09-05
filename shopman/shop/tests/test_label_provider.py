"""O seam entre o formulário de rótulo do Core e o registro do tenant.

O `ProductAdminForm` vive no Offerman, que é **Core e não importa o
orquestrador** — mas alérgeno, dieta e porção são vocabulário que a Nelson
cadastrou, e isso mora aqui. A ponte é
``OFFERMAN["LABEL_ATTRIBUTES_PROVIDER"]``, o mesmo padrão que o Craftsman usa
para as variantes de lifecycle: o pacote renderiza o campo e pergunta ao
provedor como ler e gravar.

O lado de lá — "sem provedor, sem campo, e o Core segue de pé" — tem teste na
suíte do Offerman, que roda sem o `shop` instalado. Este arquivo prova o lado
de cá: com provedor, o formulário escreve no registro e a validação morde.
"""

from __future__ import annotations

import pytest
from shopman.offerman.contrib.admin_unfold.nutrition_form import (
    ProductAdminForm,
    _label_attributes,
)
from shopman.offerman.models import Product

from shopman.shop.services import attributes

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    attributes.invalidate_cache()
    yield
    attributes.invalidate_cache()


def _form_data(**overrides):
    data = {
        "sku": "PAO", "name": "Pão", "unit": "un", "base_price_q": "100",
        "availability_policy": "planned_ok", "metadata": "{}",
        "nutrition_facts": "{}", "is_published": "on", "is_sellable": "on",
        "allergens_text": "", "dietary_info_text": "",
        "serves_text": "", "approx_dimensions_text": "",
        "ready_from": "",
    }
    data.update({k: str(v) for k, v in overrides.items()})
    return data


def _product(sku="PAO"):
    return Product.objects.create(sku=sku, name="Pão", base_price_q=100)


# --- o provedor existe deste lado ------------------------------------------


def test_the_provider_is_configured_for_the_deployment():
    provider = _label_attributes()
    assert provider is not None, (
        "OFFERMAN['LABEL_ATTRIBUTES_PROVIDER'] não está apontando para o registro"
    )


def test_the_provider_reads_and_writes_the_registry():
    product = _product()
    provider = _label_attributes()

    provider.set(product, "alergenos", ["glúten", "leite"])
    product.save(update_fields=["metadata"])

    assert provider.get(product, "alergenos") == ["glúten", "leite"]
    assert attributes.get(product, "alergenos") == ["glúten", "leite"]
    # E o valor NÃO volta para a chave solta que este WP aposentou.
    assert "allergens" not in product.metadata


def test_a_ref_that_left_the_registry_reads_empty_instead_of_breaking():
    """Atributo desativado não pode derrubar a tela de produto inteira."""
    from shopman.shop.models import AttributeDefinition

    AttributeDefinition.objects.filter(ref="alergenos").update(is_active=False)
    attributes.invalidate_cache()

    assert _label_attributes().get(_product(), "alergenos") is None


# --- o formulário, ponta a ponta -------------------------------------------


def test_the_form_writes_the_label_into_the_registry():
    product = _product()
    form = ProductAdminForm(
        data=_form_data(
            allergens_text="glúten, gergelim",
            dietary_info_text="100% vegetal, sem lactose",
            serves_text="2 a 4 pessoas",
        ),
        instance=product,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert attributes.get(saved, "alergenos") == ["glúten", "gergelim"]
    assert attributes.get(saved, "dieta") == ["100% vegetal", "sem lactose"]
    assert attributes.get(saved, "porcoes") == "2 a 4 pessoas"
    for morta in ("allergens", "dietary_info", "serves", "dietary_auto_filled"):
        assert morta not in saved.metadata


def test_a_misspelt_allergen_is_refused_at_the_door():
    """O gate do WP: alérgeno fora da lista é RECUSADO, com mensagem.

    Enquanto o formulário escrevia direto no metadata, declarar opções fechadas
    seria o registro prometer o que não tinha como cumprir. Agora ele é quem
    escreve — e um "glutén" com o acento no lugar errado não vira um alérgeno
    novo em silêncio, que é o pior que um rótulo pode fazer.
    """
    form = ProductAdminForm(
        data=_form_data(allergens_text="glutén"), instance=_product(),
    )

    assert not form.is_valid()
    assert "allergens_text" in form.errors


def test_the_form_marks_the_label_as_the_gestor_word_only_when_it_changes():
    """Re-salvar um produto derivado da ficha NÃO congela a derivação."""
    product = _product()
    attributes.set(product, "alergenos", ["glúten"], source="recipe", save=False)
    attributes.set(product, "dieta", ["100% vegetal"], source="recipe")

    form = ProductAdminForm(
        data=_form_data(allergens_text="glúten", dietary_info_text="100% vegetal"),
        instance=product,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert attributes.source(saved, "alergenos") == "recipe"


def test_editing_the_label_makes_it_the_gestor_word():
    product = _product()
    attributes.set(product, "alergenos", ["glúten"], source="recipe")

    form = ProductAdminForm(
        data=_form_data(allergens_text="glúten, leite"), instance=product,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()

    assert attributes.get(saved, "alergenos") == ["glúten", "leite"]
    assert attributes.source(saved, "alergenos") == "manual"
