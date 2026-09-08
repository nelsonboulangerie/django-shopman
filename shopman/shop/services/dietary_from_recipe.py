"""Deriva os atributos ``alergenos`` e ``dieta`` do produto a partir da Recipe.

Mirror of :mod:`shopman.shop.services.nutrition_from_recipe`, for the
dietary axis that ADR-008 deliberately postponed (nutrients are an
arithmetic sum; allergens are a *union* and require per-insumo flags).

Design
------
- Product is the surface. The storefront reads
  os atributos ``alergenos`` / ``dieta`` do registro, pelo service
  (see :mod:`shopman.storefront.presentation.dietary`); it never imports
  Craftsman.
- When a Recipe is active and its ``output_sku`` matches a Product SKU,
  this service unions the dietary profile of every leaf insumo
  (:class:`shopman.craftsman.dietary.IngredientDietary`) and writes the
  result back onto the Product. Called from the same Recipe ``post_save``
  signal as the nutrition derivation (``shop.apps`` wires it).
- Idempotente e **recusa sobrescrever o que o gestor escreveu**. Quem diz isso
  é a PROVENIÊNCIA do valor (``source``), não mais um sentinela à parte:
  ``manual`` bloqueia, ``recipe`` é recalculável, ausente é preenchível — a
  ficha, que é a fonte da verdade, ganha.
- Carimba a versão de origem em ``metadata['derived_from']['dietary']``
  (:mod:`shopman.shop.services.derived_provenance`), pelo mesmo motivo da
  nutrição: alérgeno que veio de uma versão antiga é promessa velha, e sem o
  carimbo ninguém consegue perguntar de qual versão ele veio.
- Bundles (``is_bundle=True``) are skipped, like nutrition.
- **Safety:** allergen labelling is materialized only when *every* leaf
  insumo declares a dietary profile. A single undeclared insumo means we
  cannot guarantee what is absent, so we leave whatever is there untouched
  rather than risk an under-reported allergen or a false "sem X" claim.

O ``dieta`` derivado tem UM termo: ``100% vegetal``. Os avisos de preferência
da loja (contém glúten, contém lactose) vêm do campo de ALÉRGENOS, não daqui —
e afirmação de ausência que a casa não pode honrar não é derivada de propósito.
"""

from __future__ import annotations

import logging

from shopman.craftsman.dietary import (
    DIET_ANIMAL,
    DIET_VEGAN,
    IngredientDietary,
)
from shopman.offerman.models import Product

from shopman.shop.services.derived_provenance import (
    FACT_DIETARY,
    build_recipe_stamp,
    read_stamp,
    stamp_moved,
    with_stamp,
)

logger = logging.getLogger(__name__)

#: O que, no vocabulário dos insumos, significa LEITE — e portanto lactose.
#:
#: ⚠️ Não há `GLUTEN_TOKENS` gêmeo, e a ausência é deliberada: a casa não afirma
#: ausência de glúten em produto nenhum (sem linha segregada, e sem intenção de
#: ter). Ver `shop/legal_parameters.py::declaracao_gluten`.
LACTOSE_TOKENS = frozenset({"lactose", "leite", "laticínios", "laticinios", "manteiga"})

# Allergen tokens that defeat a free-from claim. Matched case-insensitively
# against the unioned allergen list. Kept aligned with the storefront
# preference triggers in ``storefront.presentation.dietary``.


def aggregate_dietary_from_recipe(product: Product) -> bool:
    """Materialize allergens + dietary_info from the active Recipe.

    Returns ``True`` when the product was updated, ``False`` otherwise
    (no recipe, manual override, bundle, incomplete insumo data, no change).
    Never raises on business conditions — logs and returns ``False``.
    """
    if product.is_bundle:
        logger.debug("dietary_from_recipe: %s is a bundle; skipping.", product.sku)
        return False

    if not _is_auto_filled(product):
        logger.info(
            "dietary_from_recipe: %s tem valor escrito pelo gestor "
            "(source=manual); não sobrescreve.", product.sku,
        )
        return False

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        logger.debug("dietary_from_recipe: craftsman not installed.")
        return False

    recipe = get_active_recipe_for_output_sku(product.sku)
    if recipe is None:
        return False

    from shopman.shop.services.recipe_bom import expand_recipe_items

    items = expand_recipe_items(recipe)
    if not items:
        return False

    profiles: list[IngredientDietary] = []
    for item in items:
        meta = item.meta if isinstance(item.meta, dict) else {}
        profile = IngredientDietary.from_meta(meta)
        if profile is None:
            logger.info(
                "dietary_from_recipe: %s has insumo without dietary profile (%s); "
                "skipping (incomplete data is unsafe for allergen labelling).",
                product.sku, item.input_sku,
            )
            return False
        profiles.append(profile)

    allergens = _union_allergens(profiles)
    dietary_info = _derive_dietary_info(profiles, allergens)

    from shopman.shop.services import attributes

    current = dict(product.metadata or {})
    attributes.set(product, "alergenos", allergens, source="recipe", save=False)
    attributes.set(product, "dieta", dietary_info, source="recipe", save=False)

    # Carimbo da origem: mesmo quando alérgeno e dieta não mudam, publicar uma
    # versão nova move a versão de origem, e é isso que a leitura compara.
    # ⚠️ `attributes.set(save=False)` já mutou `product.metadata`; o carimbo
    # entra por cima dela, e `with_stamp` devolve cópia (não muta), então a
    # comparação com `current` continua valendo.
    stamp = build_recipe_stamp(recipe)
    if stamp_moved(read_stamp(product, FACT_DIETARY), stamp):
        product.metadata = with_stamp(product.metadata, FACT_DIETARY, stamp)

    if product.metadata == current:
        return False

    product.save(update_fields=["metadata"])
    logger.info(
        "dietary_from_recipe: %s updated (allergens=%s, dietary_info=%s).",
        product.sku, allergens, dietary_info,
    )
    return True


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _is_auto_filled(product) -> bool:
    """Se a ficha técnica pode sobrescrever o que está gravado.

    Era o sentinela `metadata["dietary_auto_filled"]`; agora é a **proveniência
    do próprio valor**, que é onde essa informação sempre pertenceu: valor que o
    gestor escreveu (`source="manual"`) manda; valor que veio da ficha
    (`source="recipe"`) é recalculável. Sem valor nenhum, não há o que proteger.
    """
    from shopman.shop.services import attributes

    for ref in ("alergenos", "dieta"):
        if attributes.get(product, ref) is None:
            continue
        if attributes.source(product, ref) != "recipe":
            return False
    return True


def _union_allergens(profiles: list[IngredientDietary]) -> list[str]:
    """Union of insumo allergens, in first-appearance order (heaviest first)."""
    seen: list[str] = []
    for profile in profiles:
        for allergen in profile.allergens:
            if allergen not in seen:
                seen.append(allergen)
    return seen


def _derive_dietary_info(
    profiles: list[IngredientDietary], allergens: list[str]
) -> list[str]:
    """O que a FÓRMULA permite afirmar — nunca o que o ambiente não garante.

    ⚠️ A linha que separa o que entra do que não entra é
    **composição × contaminação cruzada**, e confundi-las custou uma correção no
    ar (08/09/2026):

    - `100% vegetal` e `vegetariano` são fatos sobre a receita. Só eles sabem
      dizer "não tem NADA de origem animal": mel, banha e gelatina não são
      alergênicos e não aparecem no campo de alérgenos.
    - `sem lactose` é fato sobre a receita **com limiar objetivo na norma**
      (RDC 135/2017: < 100 mg/100 g). Pão de farinha, água, sal e levain está em
      zero. E não conflita com o aviso de traços: intolerância à lactose é
      dose-dependente; alergia à proteína do leite é outra coisa, e é dela que o
      `food_safety_notice` cuida.
    - `sem glúten` **NÃO é derivado, nunca**. Numa casa sem linha segregada — e a
      Nelson não tem nem pretende ter — a afirmação seria sobre o ambiente, não
      sobre a fórmula. É a única da família em que um celíaco pode se machucar,
      e a casa declara o oposto em voz alta.

    Ver `shop/legal_parameters.py`: os números que vêm da lei têm data de
    conferência e catraca.
    """
    diets = {profile.diet for profile in profiles}
    lowered = {a.lower() for a in allergens}
    info: list[str] = []

    if diets <= {DIET_VEGAN}:
        info.append("100% vegetal")
    elif DIET_ANIMAL not in diets:
        info.append("vegetariano")

    if not (lowered & LACTOSE_TOKENS):
        info.append("sem lactose")

    return info
