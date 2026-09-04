"""O registro lê e escreve exatamente o que o rótulo já lia. Nada mudou de lugar.

É o gate de aceite da F1 ("PDP, rótulo, catálogo e ficha nutricional idênticos
antes e depois"), na forma que a decisão do dono deixou: como nenhum dado se
moveu, a pergunta não é "o valor sobreviveu à migração?" e sim **"as duas
leituras concordam?"**.

E isso é um guarda de verdade, não uma formalidade. Se alguém trocar o
``storage`` de ``alergenos`` para ``attributes`` sem fazer o
[WP de rename](../../../docs/plans/WP-ATRIBUTOS-RENAME-CHAVES-LEGADAS.md) junto,
o editor de rótulo do Offerman passa a ler vazio — e é **aqui** que isso vira um
teste vermelho, em vez de um alérgeno que some da página do produto.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product

from shopman.shop.services import attributes

pytestmark = pytest.mark.django_db

#: O que o formulário de rótulo do Offerman grava hoje, tal e qual.
LABEL_METADATA = {
    "allergens": ["glúten", "leite", "ovos"],
    "dietary_info": ["vegetariano"],
    "serves": 2,
}


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    attributes.invalidate_cache()
    yield
    attributes.invalidate_cache()


@pytest.fixture
def product():
    return Product.objects.create(
        sku="CROISSANT", name="Croissant", base_price_q=1200,
        unit_weight_g=80, metadata=dict(LABEL_METADATA),
    )


def _pdp_allergen(product):
    from shopman.storefront.presentation.product_detail import _allergen

    return _allergen(product)


# --- as duas leituras concordam --------------------------------------------


def test_the_registry_reads_what_the_label_form_wrote(product):
    assert attributes.get(product, "alergenos") == ["glúten", "leite", "ovos"]
    assert attributes.get(product, "dieta") == ["vegetariano"]
    assert attributes.get(product, "porcoes") == 2
    assert attributes.get(product, "peso_unidade_g") == 80


def test_the_pdp_reads_the_same_values_as_the_registry(product):
    pdp = _pdp_allergen(product)

    assert list(pdp.allergens) == attributes.get(product, "alergenos")
    assert list(pdp.dietary_info) == attributes.get(product, "dieta")
    assert pdp.serves == str(attributes.get(product, "porcoes"))


# --- escrever pelo registro não muda o que a tela mostra --------------------


def test_writing_through_the_registry_leaves_the_label_untouched(product):
    """A prova de que nada mudou de lugar: a PDP não sabe que o registro existe."""
    before = _pdp_allergen(product)

    attributes.set(product, "alergenos", ["glúten", "leite", "ovos"], source="recipe")
    product.refresh_from_db()

    assert _pdp_allergen(product) == before


def test_provenance_does_not_leak_into_the_label(product):
    """A proveniência é registro interno: a PDP nunca a vê."""
    attributes.set(product, "sabor", "doce", source="ai")
    product.refresh_from_db()

    assert _pdp_allergen(product) == _pdp_allergen(
        Product(metadata=dict(LABEL_METADATA)),
    )
    assert "attributes" in product.metadata  # a proveniência está lá, só não vaza


def test_the_label_keys_survive_a_write_to_a_neighbouring_attribute(product):
    attributes.set(product, "natureza", "comida", source="derived")
    product.refresh_from_db()

    for key, value in LABEL_METADATA.items():
        assert product.metadata[key] == value


# --- a ficha nutricional derivada da receita -------------------------------


def test_the_recipe_sentinel_is_untouched_by_the_registry(product):
    """``dietary_auto_filled`` continua sendo a palavra final do
    ``dietary_from_recipe``: o service de atributos não o escreve, não o lê e
    não o apaga. Duas fontes para a mesma verdade é como ela diverge."""
    product.metadata["dietary_auto_filled"] = True
    product.save(update_fields=["metadata"])

    attributes.set(product, "alergenos", ["glúten"], source="recipe")
    product.refresh_from_db()

    assert product.metadata["dietary_auto_filled"] is True


# --- o guarda contra o rename acidental ------------------------------------


def test_the_legacy_attributes_still_point_at_the_legacy_keys():
    """Trocar este ``storage`` sem fazer o WP de rename quebra o editor de
    rótulo do Offerman, que é quem escreve estas chaves. Se este teste ficar
    vermelho, o WP inteiro tem de vir junto — não é uma linha de configuração."""
    assert attributes.require("alergenos").storage == "metadata:allergens"
    assert attributes.require("dieta").storage == "metadata:dietary_info"
    assert attributes.require("porcoes").storage == "metadata:serves"
    assert attributes.require("peso_unidade_g").storage == "column:unit_weight_g"
