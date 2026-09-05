"""O rótulo sobreviveu à mudança de casa — que é o gate de aceite do rename.

Os três valores saíram das chaves soltas do ``metadata`` e vieram para o
registro. A pergunta que este arquivo responde é a única que importa depois de
uma migração de dados: **a PDP mostra hoje o mesmo que mostrava ontem?**

Por isso as fixtures usam o formato REAL do catálogo, não um simplificado. O
``serves`` da casa é texto de apresentação (``"2 pessoas"``, ``"pote 170 g"``) —
e foi exatamente isso que a F1 errou ao defini-lo como número: a leitura
devolvia ``None`` para todo produto, calada, porque a fixture do teste usava um
inteiro que não existe no catálogo.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product

from shopman.shop.services import attributes

pytestmark = pytest.mark.django_db

#: O que o formulário de rótulo gravava ANTES do rename — o formato real do
#: catálogo, incluindo o ``serves`` como texto de apresentação.
LEGACY_METADATA = {
    "allergens": ["glúten", "leite", "ovos"],
    "dietary_info": ["vegetariano"],
    "serves": "2 pessoas",
}


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    attributes.invalidate_cache()
    yield
    attributes.invalidate_cache()


@pytest.fixture
def product():
    """Um produto com a rotulagem já no lugar novo, como a migração a deixa."""
    p = Product.objects.create(
        sku="CROISSANT", name="Croissant", base_price_q=1200, unit_weight_g=80,
    )
    attributes.set(p, "alergenos", ["glúten", "leite", "ovos"], source="recipe", save=False)
    attributes.set(p, "dieta", ["vegetariano"], source="recipe", save=False)
    attributes.set(p, "porcoes", "2 pessoas", save=False)
    p.save(update_fields=["metadata"])
    return p


def _pdp_allergen(product):
    from shopman.storefront.presentation.product_detail import _allergen

    return _allergen(product)


# --- as duas leituras concordam --------------------------------------------


def test_the_registry_reads_the_label(product):
    assert attributes.get(product, "alergenos") == ["glúten", "leite", "ovos"]
    assert attributes.get(product, "dieta") == ["vegetariano"]
    assert attributes.get(product, "porcoes") == "2 pessoas"
    assert attributes.get(product, "peso_unidade_g") == 80


def test_the_pdp_reads_the_same_values_as_the_registry(product):
    pdp = _pdp_allergen(product)

    assert list(pdp.allergens) == attributes.get(product, "alergenos")
    assert list(pdp.dietary_info) == attributes.get(product, "dieta")
    assert pdp.serves == attributes.get(product, "porcoes")


# --- escrever pelo registro não muda o que a tela mostra --------------------


def test_the_pdp_shows_the_same_after_the_move(product):
    """O gate do rename: a PDP mostra hoje o que mostrava com a chave solta.

    Monta o MESMO produto do jeito antigo e compara as duas projections. Se a
    migração perder um alérgeno ou trocar o texto da porção, é aqui que aparece.
    """
    antigo = Product(metadata=dict(LEGACY_METADATA))

    from shopman.storefront.presentation.product_detail import AllergenInfoProjection

    esperado = AllergenInfoProjection(
        allergens=tuple(LEGACY_METADATA["allergens"]),
        dietary_info=tuple(LEGACY_METADATA["dietary_info"]),
        serves=LEGACY_METADATA["serves"],
    )
    assert _pdp_allergen(product) == esperado
    assert antigo.metadata["serves"] == esperado.serves


def test_provenance_does_not_leak_into_the_label(product):
    """A proveniência é registro interno: a PDP nunca a vê."""
    before = _pdp_allergen(product)
    attributes.set(product, "sabor", "doce", source="ai")
    product.refresh_from_db()

    assert _pdp_allergen(product) == before
    assert "attributes" in product.metadata  # está lá, só não vaza


def test_the_label_survives_a_write_to_a_neighbouring_attribute(product):
    attributes.set(product, "natureza", "comida", source="derived")
    product.refresh_from_db()

    assert attributes.get(product, "alergenos") == ["glúten", "leite", "ovos"]
    assert attributes.get(product, "porcoes") == "2 pessoas"


# --- a ficha nutricional derivada da receita -------------------------------


def test_the_sentinel_is_gone_and_provenance_took_its_place(product):
    """``dietary_auto_filled`` morreu: quem diz "veio da ficha" é o `source`.

    Duas fontes para a mesma verdade é como ela diverge — era o motivo de a F1
    não as ter unificado, e é o que este WP finalmente resolve.
    """
    assert "dietary_auto_filled" not in product.metadata
    assert attributes.source(product, "alergenos") == "recipe"

    attributes.set(product, "alergenos", ["glúten"], source="manual")
    product.refresh_from_db()
    assert attributes.source(product, "alergenos") == "manual"


# --- o guarda contra o rename acidental ------------------------------------


def test_the_three_came_home_and_the_weight_stayed_a_column():
    assert attributes.require("alergenos").storage == "attributes"
    assert attributes.require("dieta").storage == "attributes"
    assert attributes.require("porcoes").storage == "attributes"
    # Fato físico segue coluna, com integridade no banco. Nunca foi para o JSON.
    assert attributes.require("peso_unidade_g").storage == "column:unit_weight_g"


def test_the_option_list_is_closed_now_that_the_registry_owns_the_writing(product):
    """Alérgeno digitado errado é RECUSADO — o que a F1 não podia prometer.

    Enquanto o formulário do Offerman escrevia direto no metadata, declarar
    opções fechadas seria o registro prometer uma restrição que não tinha como
    aplicar. Agora ele é quem escreve.
    """
    from shopman.shop.services.attributes import AttributeError_

    with pytest.raises(AttributeError_, match="glutén"):
        attributes.set(product, "alergenos", ["glutén"])   # acento no lugar errado

    attributes.set(product, "alergenos", ["glúten"])       # o certo passa
