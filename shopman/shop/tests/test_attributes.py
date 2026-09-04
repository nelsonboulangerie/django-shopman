"""O registro de atributos: definição, validação, os três storages e proveniência."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.shop.models import AttributeDefinition
from shopman.shop.services import attributes
from shopman.shop.services.attributes import AttributeError_

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    attributes.invalidate_cache()
    yield
    attributes.invalidate_cache()


def _product(sku="PAO", **kwargs):
    return Product.objects.create(sku=sku, name=kwargs.pop("name", "Pão"), **kwargs)


# --- as definições que a migração cria -------------------------------------


def test_migration_seeds_the_seven_definitions():
    refs = set(AttributeDefinition.objects.values_list("ref", flat=True))
    assert refs == {
        "alergenos", "dieta", "porcoes", "peso_unidade_g",
        "natureza", "sabor", "temperatura",
    }


def test_legacy_attributes_point_at_the_keys_that_already_exist():
    # É a decisão da F1: o registro nasce completo sem mover dado nenhum.
    assert attributes.require("alergenos").metadata_key == "allergens"
    assert attributes.require("dieta").metadata_key == "dietary_info"
    assert attributes.require("porcoes").metadata_key == "serves"
    assert attributes.require("peso_unidade_g").column_field == "unit_weight_g"
    assert attributes.require("sabor").metadata_key is None
    assert attributes.require("sabor").column_field is None


# --- validação da definição ------------------------------------------------


def test_choice_definition_requires_options():
    with pytest.raises(ValidationError) as exc:
        AttributeDefinition(ref="cor", label="Cor", type="choice", options=[]).full_clean()
    assert "options" in exc.value.message_dict


def test_number_definition_refuses_options():
    with pytest.raises(ValidationError) as exc:
        AttributeDefinition(
            ref="tamanho", label="Tamanho", type="number",
            options=[{"value": "g", "label": "G"}],
        ).full_clean()
    assert "options" in exc.value.message_dict


def test_duplicate_option_value_is_refused():
    with pytest.raises(ValidationError) as exc:
        AttributeDefinition(
            ref="cor", label="Cor", type="choice",
            options=[{"value": "azul", "label": "Azul"}, {"value": "azul", "label": "Anil"}],
        ).full_clean()
    assert "options" in exc.value.message_dict


def test_unknown_purpose_is_refused():
    with pytest.raises(ValidationError) as exc:
        AttributeDefinition(
            ref="cor", label="Cor", type="choice",
            options=[{"value": "azul", "label": "Azul"}], purposes=["astrologia"],
        ).full_clean()
    assert "purposes" in exc.value.message_dict


def test_storage_pointing_at_a_field_the_product_does_not_have_is_refused():
    with pytest.raises(ValidationError) as exc:
        AttributeDefinition(
            ref="cor", label="Cor", type="text", storage="column:nao_existe",
        ).full_clean()
    assert "storage" in exc.value.message_dict


# --- leitura e escrita: storage padrão -------------------------------------


def test_set_and_get_on_the_default_storage():
    product = _product()
    attributes.set(product, "sabor", "doce")
    product.refresh_from_db()

    assert attributes.get(product, "sabor") == "doce"
    assert product.metadata["attributes"]["sabor"]["value"] == "doce"


def test_value_outside_the_options_is_refused():
    product = _product()
    with pytest.raises(AttributeError_, match="azedo"):
        attributes.set(product, "sabor", "azedo")


def test_unknown_ref_is_refused():
    product = _product()
    with pytest.raises(AttributeError_, match="não existe no registro"):
        attributes.set(product, "cor", "azul")
    with pytest.raises(AttributeError_):
        attributes.get(product, "cor")


def test_clearing_removes_value_and_provenance():
    product = _product()
    attributes.set(product, "sabor", "doce")
    attributes.clear(product, "sabor")
    product.refresh_from_db()

    assert attributes.get(product, "sabor") is None
    assert "sabor" not in (product.metadata.get("attributes") or {})


# --- leitura e escrita: coluna ---------------------------------------------


def test_column_storage_reads_and_writes_the_column():
    product = _product(unit_weight_g=150)
    assert attributes.get(product, "peso_unidade_g") == 150

    attributes.set(product, "peso_unidade_g", 220)
    product.refresh_from_db()
    assert product.unit_weight_g == 220
    assert attributes.get(product, "peso_unidade_g") == 220
    # O valor mora na coluna; no JSON fica só a proveniência.
    assert "value" not in product.metadata["attributes"]["peso_unidade_g"]


# --- leitura e escrita: ponteiro para chave legada --------------------------


def test_legacy_key_is_read_without_any_data_moving():
    # Produto gravado pelo formulário de rótulo do Offerman, antes do registro.
    product = _product(metadata={"allergens": ["glúten", "leite"], "serves": 2})

    assert attributes.get(product, "alergenos") == ["glúten", "leite"]
    assert attributes.get(product, "porcoes") == 2


def test_writing_a_legacy_attribute_writes_the_legacy_key():
    product = _product()
    attributes.set(product, "alergenos", ["glúten"], source="recipe")
    product.refresh_from_db()

    # É a chave que o Offerman e o `dietary_from_recipe` leem — nada mudou de lugar.
    assert product.metadata["allergens"] == ["glúten"]
    assert attributes.source(product, "alergenos") == "recipe"


def test_multi_text_accepts_terms_the_registry_does_not_enumerate():
    # Alérgeno novo não pode depender de deploy: quem escreve é o rótulo.
    product = _product()
    attributes.set(product, "alergenos", ["sulfitos"])
    assert attributes.get(product, "alergenos") == ["sulfitos"]


def test_list_attribute_refuses_a_bare_string():
    product = _product()
    with pytest.raises(AttributeError_, match="lista"):
        attributes.set(product, "alergenos", "glúten")


# --- proveniência -----------------------------------------------------------


def test_manual_is_reviewed_by_definition():
    product = _product()
    attributes.set(product, "sabor", "doce")
    assert attributes.source(product, "sabor") == "manual"
    assert attributes.is_reviewed(product, "sabor") is True


def test_ai_proposal_is_not_reviewed_until_someone_says_so():
    product = _product()
    attributes.set(product, "sabor", "doce", source="ai")
    assert attributes.is_reviewed(product, "sabor") is False

    attributes.set(product, "sabor", "doce", source="ai", reviewed=True)
    assert attributes.is_reviewed(product, "sabor") is True


def test_a_value_that_predates_the_registry_reads_as_manual():
    # Está lá, ninguém disse o contrário: foi gente que pôs.
    product = _product(metadata={"allergens": ["glúten"]})
    assert attributes.source(product, "alergenos") == "manual"
    assert attributes.is_reviewed(product, "alergenos") is True


def test_unknown_source_is_refused():
    product = _product()
    with pytest.raises(AttributeError_, match="Proveniência"):
        attributes.set(product, "sabor", "doce", source="palpite")


# --- valor órfão ------------------------------------------------------------


def test_value_outside_the_definition_reads_as_absent():
    # Opção removida do registro depois de gravada: a regra não pode ver isso.
    product = _product(metadata={"attributes": {"sabor": {"value": "azedo"}}})
    assert attributes.get(product, "sabor") is None


# --- em lote ----------------------------------------------------------------


def test_get_many_answers_one_attribute_for_many_products():
    a = _product("A", name="Doce")
    b = _product("B", name="Salgado")
    _product("C", name="Sem sabor")
    attributes.set(a, "sabor", "doce")
    attributes.set(b, "sabor", "salgado")

    got = attributes.get_many(Product.objects.order_by("sku"), "sabor")
    assert got == {"A": "doce", "B": "salgado"}


def test_for_purpose_lists_the_rule_attributes():
    refs = {d.ref for d in attributes.for_purpose("rule")}
    assert {"natureza", "sabor", "temperatura", "peso_unidade_g"} <= refs


# --- carga derivada das coleções -------------------------------------------


def _in_collection(product, collection_ref, *, primary=True):
    collection, _ = Collection.objects.get_or_create(
        ref=collection_ref, defaults={"name": collection_ref},
    )
    CollectionItem.objects.create(
        collection=collection, product=product, sort_order=0, is_primary=primary,
    )


def test_derived_load_reads_the_collections():
    from django.core.management import call_command

    cafe = _product("CAFE", name="Café")
    _in_collection(cafe, "bebidas-quentes")
    pao = _product("PAO2", name="Baguette")
    _in_collection(pao, "rusticos")
    doce = _product("MAD", name="Madeleine")
    _in_collection(doce, "doces")

    call_command("propose_product_attributes", verbosity=0)
    for p in (cafe, pao, doce):
        p.refresh_from_db()

    assert attributes.get(cafe, "natureza") == "bebida"
    assert attributes.get(cafe, "temperatura") == "quente"
    assert attributes.get(pao, "natureza") == "comida"
    assert attributes.get(pao, "sabor") == "neutro"
    assert attributes.get(doce, "sabor") == "doce"


def test_derived_load_never_overwrites_what_the_gestor_wrote():
    from django.core.management import call_command

    pao = _product("PAO3", name="Pão doce")
    _in_collection(pao, "rusticos")
    attributes.set(pao, "sabor", "doce")  # curadoria: este pão É doce

    call_command("propose_product_attributes", "--overwrite-derived", verbosity=0)
    pao.refresh_from_db()

    assert attributes.get(pao, "sabor") == "doce"
    assert attributes.source(pao, "sabor") == "manual"


def test_derived_load_marks_everything_as_a_proposal():
    from django.core.management import call_command

    cafe = _product("CAFE2", name="Café")
    _in_collection(cafe, "bebidas-quentes")

    call_command("propose_product_attributes", verbosity=0)
    cafe.refresh_from_db()

    assert attributes.source(cafe, "natureza") == "derived"
    assert attributes.is_reviewed(cafe, "natureza") is False


def test_grocery_split_by_keyword():
    from django.core.management import call_command

    geleia = _product("GL", name="Geleia")
    geleia.keywords.add("mercearia", "geleia", "fruta")
    _in_collection(geleia, "mercearia")
    grao = _product("GR", name="Café em grão")
    grao.keywords.add("mercearia", "cafe", "grao")
    _in_collection(grao, "mercearia")

    call_command("propose_product_attributes", verbosity=0)
    geleia.refresh_from_db()
    grao.refresh_from_db()

    assert attributes.get(geleia, "natureza") == "acompanhamento"
    assert attributes.get(grao, "natureza") == "outro"
