"""O peso anunciado da peça, derivado da ficha — e sempre pelo lado de baixo.

``Product.unit_weight_g`` é o peso da peça **assada** que o cliente lê na loja.
Até aqui ele era digitado à mão, a partir de uma perda de forno de ~12% que o
próprio comando de medidas admite nunca ter passado pela balança. Isto o torna
derivável, com uma regra que é sobre a direção do erro antes de ser sobre o
número:

    cru por unidade = soma dos insumos em massa (g) ÷ ``batch_size``
    assado esperado = cru por unidade × (1 − perda de forno)
    anunciado       = arredonda PARA BAIXO (assado esperado × (1 − folga))

O dono: *"o cliente se importa mais se está pagando o preço por menos do que o
mostrado, nunca por mais... esse pão nunca sai menor que 90 g... calcularíamos
para que o assado mire uns 96 g."* Por isso o anunciado é **piso**: a folga
puxa para baixo e o arredondamento também, e nunca o contrário. Duas
consequências que valem como invariante:

    anunciado ≤ assado esperado ≤ cru por unidade

**A divisão por ``batch_size`` não depende do formato da ficha.** Outra frente
está transformando a ficha de produto em "por unidade" (``batch_size = 1``);
com o rendimento no denominador, a conta dá o mesmo antes e depois, porque a
reexpressão preserva a razão.

**Peso posto à mão nunca é sobrescrito.** O sentinela é o carimbo de origem
(:mod:`shopman.shop.services.derived_provenance`): só um peso que o próprio
sistema derivou **e que continua sendo o número que ele deixou**, ou um campo
vazio, é regravável. Peso sem carimbo é peso que alguém digitou — hoje isso
vale para todo o catálogo — e peso que difere do carimbo é edição posterior; os
dois ficam onde estão, ganhando o aviso de divergência na leitura da promessa.

**Ficha sem ponte até grama recusa derivar.** Item em volume sem
``density_g_per_ml`` ou em contagem sem ``unit_weight_g`` não tem massa
conhecida; somar só o que dá converteria a falta de dado num peso menor, e um
peso menor **parece** seguro (é piso!) sem ter relação nenhuma com a peça. Aqui
a soma incompleta é recusa, não estimativa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

from shopman.offerman.models import Product

from shopman.shop.services.derived_provenance import (
    FACT_UNIT_WEIGHT,
    build_recipe_stamp,
    is_derived,
    is_manual,
    read_stamp,
    stamp_moved,
    with_stamp,
)
from shopman.shop.services.recipe_bom import expand_recipe_items, item_quantity_grams

logger = logging.getLogger(__name__)

#: Espécies da perda de forno, na ordem em que a casa confia nelas.
BAKE_LOSS_HOUSE_DEFAULT = "house_default"  # o ~12% da casa: estimativa, nunca pesada
BAKE_LOSS_ESTIMATED = "estimated"  # declarado na ficha, mas não pesado
BAKE_LOSS_WEIGHED = "weighed"  # conferido na balança, com autor e data

#: Unidades de saída em que "uma peça" faz sentido. Ficha de pré-preparo rende
#: massa em kg, e dividir gramas por quilos daria um número sem significado.
UNIT_OUTPUTS = frozenset({"un", "und", "unid", "unidade", "unidades", "pc", "peça"})


@dataclass(frozen=True)
class UnitWeightDerivation:
    """O peso anunciado e todo o caminho até ele, para a tela poder explicar."""

    raw_unit_g: Decimal
    bake_loss_pct: Decimal
    bake_loss_source: str
    bake_loss_by: str
    bake_loss_at: str
    slack_pct: Decimal
    expected_baked_g: Decimal
    announced_g: int

    @property
    def bake_loss_is_audited(self) -> bool:
        """Só perda pesada, com quem pesou e quando, conta como conferida.

        Falha fechado: ``weighed`` sem autor nem data é uma declaração que
        ninguém assinou, e passá-la por conferida esconderia exatamente a
        incerteza que este campo existe para mostrar.
        """
        return self.bake_loss_source == BAKE_LOSS_WEIGHED and bool(
            self.bake_loss_by and self.bake_loss_at
        )


def derive_unit_weight(recipe) -> UnitWeightDerivation | None:
    """O peso anunciado que esta ficha sustenta, ou ``None`` quando não sustenta.

    Recusa (e diz por quê no log) quando: o rendimento não é em peças, algum
    insumo não tem ponte até grama, a ficha não tem item nenhum, ou a conta
    chegaria a zero grama — peça de 0 g não é promessa, é ausência de promessa.
    """
    output_unit = str((getattr(recipe, "meta", None) or {}).get("output_unit") or "").strip().lower()
    if output_unit and output_unit not in UNIT_OUTPUTS:
        logger.info(
            "unit_weight_from_recipe: %s rende em '%s', não em peças; sem peso por unidade.",
            recipe.ref, output_unit,
        )
        return None

    raw_unit_g = raw_unit_grams(recipe)
    if raw_unit_g is None:
        return None

    bake_loss_pct, bake_loss_source, bake_loss_by, bake_loss_at = _bake_loss(recipe)
    slack_pct = _slack(recipe)

    expected_baked_g = raw_unit_g * (Decimal("1") - bake_loss_pct / Decimal("100"))
    announced = (expected_baked_g * (Decimal("1") - slack_pct / Decimal("100"))).to_integral_value(
        rounding=ROUND_FLOOR
    )
    announced_g = int(announced)
    if announced_g <= 0:
        logger.info(
            "unit_weight_from_recipe: %s derivaria %s g; peso zero não é promessa.",
            recipe.ref, announced_g,
        )
        return None

    return UnitWeightDerivation(
        raw_unit_g=raw_unit_g,
        bake_loss_pct=bake_loss_pct,
        bake_loss_source=bake_loss_source,
        bake_loss_by=bake_loss_by,
        bake_loss_at=bake_loss_at,
        slack_pct=slack_pct,
        expected_baked_g=expected_baked_g,
        announced_g=announced_g,
    )


def raw_unit_grams(recipe) -> Decimal | None:
    """Massa crua de UMA peça, em gramas, ou ``None`` quando a ficha não fecha.

    A soma é do BOM expandido (sub-fichas abertas até a folha), dividida pelo
    ``batch_size``. É essa divisão que faz a conta funcionar tanto na ficha por
    fornada quanto na ficha por unidade.
    """
    batch_size = Decimal(str(getattr(recipe, "batch_size", 0) or 0))
    if batch_size <= 0:
        return None

    items = expand_recipe_items(recipe)
    if not items:
        return None

    total_g = Decimal("0")
    for item in items:
        grams = item_quantity_grams(item)
        if grams is None:
            logger.info(
                "unit_weight_from_recipe: %s tem insumo sem ponte até grama (%s em %s); "
                "sem peso derivado (soma incompleta viraria peso inventado).",
                recipe.ref, item.input_sku, item.unit,
            )
            return None
        total_g += grams

    if total_g <= 0:
        return None
    return total_g / batch_size


def fill_unit_weight_from_recipe(product: Product) -> bool:
    """Grava ``unit_weight_g`` derivado quando — e só quando — é permitido.

    Devolve ``True`` quando o produto mudou. Peso à mão, bundle, ficha ausente
    ou derivação que não fecha devolvem ``False`` sem tocar em nada.
    """
    if product.is_bundle:
        logger.debug("unit_weight_from_recipe: %s é bundle; ignorado.", product.sku)
        return False

    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        logger.debug("unit_weight_from_recipe: craftsman não instalado.")
        return False

    recipe = get_active_recipe_for_output_sku(product.sku)
    if recipe is None:
        return False

    if not weight_is_writable(product):
        logger.info(
            "unit_weight_from_recipe: %s tem peso posto à mão (%s g); não sobrescrevo — "
            "a divergência aparece na leitura da promessa.",
            product.sku, product.unit_weight_g,
        )
        return False

    derivation = derive_unit_weight(recipe)
    if derivation is None:
        return False

    update_fields: list[str] = []
    if int(product.unit_weight_g or 0) != derivation.announced_g:
        product.unit_weight_g = derivation.announced_g
        update_fields.append("unit_weight_g")

    stamp = build_recipe_stamp(recipe, value=derivation.announced_g)
    if stamp_moved(read_stamp(product, FACT_UNIT_WEIGHT), stamp):
        product.metadata = with_stamp(product.metadata, FACT_UNIT_WEIGHT, stamp)
        update_fields.append("metadata")

    if not update_fields:
        return False

    product.save(update_fields=update_fields)
    logger.info(
        "unit_weight_from_recipe: %s = %s g (cru %s g, perda %s%% [%s], folga %s%%).",
        product.sku, derivation.announced_g, derivation.raw_unit_g,
        derivation.bake_loss_pct, derivation.bake_loss_source, derivation.slack_pct,
    )
    return True


def weight_is_writable(product: Product) -> bool:
    """O peso deste produto pode ser (re)derivado?

    Três recusas, e todas dizem a mesma coisa: peso de gente é intocável.

    - carimbo manual (alguém assinou o número) — nunca;
    - número no campo sem carimbo nenhum — é o estado de todo o catálogo hoje,
      onde o peso foi digitado à mão;
    - número no campo diferente do que a última derivação deixou ali — alguém
      editou DEPOIS, e a edição vence a derivação. Sem esta terceira, o
      operador corrigiria o peso no Admin e o próximo save da ficha o
      reverteria calado, que é exatamente a promessa falsa que o WP combate.

    Sim quando o campo está vazio (não há promessa para atropelar) ou quando o
    carimbo diz que foi o próprio sistema quem o pôs, e ele continua lá.
    """
    stamp = read_stamp(product, FACT_UNIT_WEIGHT)
    if is_manual(stamp):
        return False

    grams = int(product.unit_weight_g or 0)
    if grams <= 0:
        return True

    if not is_derived(stamp):
        return False
    stamped_value = stamp.get("value")
    return stamped_value is not None and int(stamped_value) == grams


# ──────────────────────────────────────────────────────────────────────
# Internos
# ──────────────────────────────────────────────────────────────────────


def _bake_loss(recipe) -> tuple[Decimal, str, str, str]:
    """Perda de forno da ficha, com a espécie dela e quem a assinou.

    Cascata: ``Recipe.meta["bake_loss_pct"]`` → padrão da casa. O padrão da
    casa **nunca** vira "declarado": ele sai daqui rotulado ``house_default``
    justamente para o número de 12% não virar verdade silenciosa na tela.
    """
    from shopman.shop.production_config import ProductionConfig

    meta = getattr(recipe, "meta", None) or {}
    declared = _percent(meta.get("bake_loss_pct"))
    if declared is None:
        return (
            ProductionConfig.load().weight.default_bake_loss_pct_decimal,
            BAKE_LOSS_HOUSE_DEFAULT,
            "",
            "",
        )

    source = str(meta.get("bake_loss_source") or "").strip().lower()
    if source not in (BAKE_LOSS_ESTIMATED, BAKE_LOSS_WEIGHED):
        source = BAKE_LOSS_ESTIMATED
    return (
        declared,
        source,
        str(meta.get("bake_loss_weighed_by") or "").strip(),
        str(meta.get("bake_loss_weighed_at") or "").strip(),
    )


def _slack(recipe) -> Decimal:
    """Folga de segurança: ficha → loja → padrão conservador do código."""
    from shopman.shop.production_config import ProductionConfig

    meta = getattr(recipe, "meta", None) or {}
    declared = _percent(meta.get("weight_slack_pct"))
    if declared is not None:
        return declared
    return ProductionConfig.load().weight.default_slack_pct_decimal


def _percent(value) -> Decimal | None:
    """Percentual válido de uma fração que sobra: ``[0, 100)``.

    Zero é legítimo (ficha que declara não perder nada no forno), 100 não: em
    100% de perda não sobra peça, e o anunciado viraria zero. Valor ilegível
    devolve ``None`` e cai na cascata, em vez de virar um número qualquer.
    """
    if value in (None, ""):
        return None
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if percent < 0 or percent >= Decimal("100"):
        return None
    return percent
