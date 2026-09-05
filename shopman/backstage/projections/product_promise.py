"""A promessa do catálogo: o que o cliente lê ainda corresponde à ficha?

Esta é a leitura do bloco C do WP-FICHA-DE-PRODUTO-E-PROMESSA. Ela responde,
por produto e por fato derivado, cinco coisas:

- **valor** — o que o cliente vê hoje na loja;
- **origem** — derivado da ficha ou escrito à mão;
- **de qual versão** — o ``version_ref`` carimbado na derivação;
- **vencido** — comparação EXATA contra a versão atual da ficha, sem limiar
  nem data: ou é a mesma versão, ou não é;
- **quem/quando conferiu** — para o valor manual, que nada recalcula.

Duas honestidades que a tela precisa carregar até o fim:

- ficha nunca publicada pelo inventário não tem versão, e o carimbo dela é
  vazio. Ali a defasagem é **indetectável**, não "em dia": ``is_versioned``
  fica ``False`` para a tela poder dizer isso em vez de mostrar um verde que
  ninguém pode sustentar;
- valor manual sem assinatura é reportado como **nunca conferido**
  (``needs_audit``), não como conferido há muito tempo. A conferência é
  declarada por gente (``derived_provenance.record_manual_audit``), nunca
  deduzida — mesma doutrina das conversões de insumo do Buyman (ADR-024).

O peso da peça leva uma coluna a mais: quando ele é manual, a projeção mostra
**ao lado** o peso que a ficha sustentaria. É assim que um peso digitado
divergente acusa sem nunca ser sobrescrito.

Alimenta ``api/v1/backstage/catalog/promise/`` (persona gestor). Nunca importa
views.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone
from shopman.offerman.models import Product

from shopman.shop.services.derived_provenance import (
    DERIVED_FACTS,
    FACT_DIETARY,
    FACT_NUTRITION,
    FACT_UNIT_WEIGHT,
    SOURCE_MANUAL,
    SOURCE_RECIPE,
    read_stamp,
    recipe_version_ref,
    stamp_is_stale,
)
from shopman.shop.services.unit_weight_from_recipe import derive_unit_weight

logger = logging.getLogger(__name__)

FACT_LABELS: dict[str, str] = {
    FACT_UNIT_WEIGHT: "Peso da peça",
    FACT_NUTRITION: "Tabela nutricional",
    FACT_DIETARY: "Alérgenos e dieta",
}

SOURCE_LABELS: dict[str, str] = {
    SOURCE_RECIPE: "Derivado da ficha",
    SOURCE_MANUAL: "Escrito à mão",
}

#: Sem carimbo não dá para afirmar de onde o número veio. Ele existe, alguém o
#: pôs ali, e é só isso que sabemos — dizer "derivado" seria inventar origem.
SOURCE_UNKNOWN = "unknown"
SOURCE_UNKNOWN_LABEL = "Origem não registrada"

VERSION_LABEL_UNVERSIONED = "ficha sem versão"
VERSION_LABEL_NONE = "sem ficha"


@dataclass(frozen=True)
class DerivedFactProjection:
    """Um fato do catálogo que vem (ou deveria vir) da ficha."""

    fact: str
    label: str
    value: str
    has_value: bool
    source: str
    source_label: str
    version_ref: str
    version_label: str
    is_versioned: bool
    is_stale: bool
    needs_audit: bool
    audited_by: str
    audited_at: str
    #: O que a ficha sustentaria hoje, quando dá para calcular e difere do que
    #: está publicado. Vazio quando não há o que comparar.
    expected_value: str
    diverges: bool
    note: str


@dataclass(frozen=True)
class ProductPromiseProjection:
    """A promessa de um produto, fato a fato."""

    sku: str
    name: str
    is_published: bool
    has_recipe: bool
    recipe_ref: str
    recipe_version_ref: str
    recipe_version_label: str
    is_stale: bool
    needs_audit: bool
    facts: tuple[DerivedFactProjection, ...]


@dataclass(frozen=True)
class CatalogPromiseProjection:
    """O catálogo inteiro sob a mesma pergunta."""

    products: tuple[ProductPromiseProjection, ...]
    total_count: int
    stale_count: int
    needs_audit_count: int
    generated_at: datetime


# ── Builders ───────────────────────────────────────────────────────────


def build_product_promise(product: Product, *, recipe=None) -> ProductPromiseProjection:
    """A promessa de um produto: valor, origem, versão, defasagem e conferência."""
    if recipe is None:
        recipe = _active_recipe_for(product.sku)

    current_version = recipe_version_ref(recipe) if recipe else ""
    facts = tuple(
        _build_fact(product, fact, recipe, current_version) for fact in DERIVED_FACTS
    )
    return ProductPromiseProjection(
        sku=product.sku,
        name=product.name,
        is_published=bool(product.is_published),
        has_recipe=recipe is not None,
        recipe_ref=str(getattr(recipe, "ref", "") or "") if recipe else "",
        recipe_version_ref=current_version,
        recipe_version_label=_version_label(current_version, has_stamp=recipe is not None),
        is_stale=any(fact.is_stale for fact in facts),
        needs_audit=any(fact.needs_audit for fact in facts),
        facts=facts,
    )


def build_catalog_promise(
    *, only_stale: bool = False, include_unpublished: bool = False
) -> CatalogPromiseProjection:
    """Todo o catálogo publicado sob a pergunta "isto ainda é verdade?".

    ``only_stale`` filtra a LISTA, nunca as contagens: quem abre a tela por um
    problema ainda precisa saber o tamanho do catálogo em que ele está.

    Produto despublicado fica de fora por padrão — o cliente não o lê, então
    ele não carrega promessa nenhuma.
    """
    queryset = Product.objects.all().order_by("sku")
    if not include_unpublished:
        queryset = queryset.filter(is_published=True)

    promises = [
        build_product_promise(product)
        for product in queryset
        if not product.is_bundle
    ]
    stale_count = sum(1 for promise in promises if promise.is_stale)
    needs_audit_count = sum(1 for promise in promises if promise.needs_audit)

    listed = [p for p in promises if p.is_stale] if only_stale else promises
    return CatalogPromiseProjection(
        products=tuple(listed),
        total_count=len(promises),
        stale_count=stale_count,
        needs_audit_count=needs_audit_count,
        generated_at=timezone.now(),
    )


# ── Internos ───────────────────────────────────────────────────────────


def _build_fact(product: Product, fact: str, recipe, current_version: str) -> DerivedFactProjection:
    stamp = read_stamp(product, fact)
    value, has_value = _value_of(product, fact)

    stamped_source = str((stamp or {}).get("source") or "")
    if stamped_source in (SOURCE_RECIPE, SOURCE_MANUAL):
        source = stamped_source
    elif has_value:
        source = SOURCE_UNKNOWN
    else:
        source = ""

    # Carimbo que diz "derivado" mas cujo valor não é mais o que está no campo
    # descreve um número que já não existe: alguém editou depois. Chamar isso
    # de derivado seria o carimbo mentindo, então ele volta a ser origem não
    # registrada, que é a verdade.
    if source == SOURCE_RECIPE and _value_was_edited_after(product, fact, stamp):
        source = SOURCE_UNKNOWN

    is_manual = source == SOURCE_MANUAL

    stamped_version = str((stamp or {}).get("version_ref") or "")
    is_versioned = bool(stamp) and bool(stamped_version)
    audited_by = str((stamp or {}).get("by") or "")

    # Vencido só existe contra uma versão gravada. Sem carimbo não há
    # comparação possível, e a resposta certa é "confira", não "está em dia".
    is_stale = recipe is not None and stamp_is_stale(stamp, current_version)
    # Nunca conferido: o valor está publicado e nada diz de onde ele veio — ou
    # veio de uma conferência que ninguém assinou.
    needs_audit = has_value and (source == SOURCE_UNKNOWN or (is_manual and not audited_by))

    expected_value, diverges = _expected_of(product, fact, recipe, value if has_value else "")

    return DerivedFactProjection(
        fact=fact,
        label=FACT_LABELS.get(fact, fact),
        value=value,
        has_value=has_value,
        source=source,
        source_label=(
            SOURCE_UNKNOWN_LABEL if source == SOURCE_UNKNOWN else SOURCE_LABELS.get(source, "")
        ),
        version_ref=stamped_version,
        version_label=_version_label(stamped_version, has_stamp=stamp is not None),
        is_versioned=is_versioned,
        is_stale=is_stale,
        needs_audit=needs_audit,
        audited_by=audited_by,
        audited_at=str((stamp or {}).get("at") or ""),
        expected_value=expected_value,
        diverges=diverges,
        note=_note(
            has_value=has_value,
            is_stale=is_stale,
            needs_audit=needs_audit,
            is_manual=is_manual,
            diverges=diverges,
            is_versioned=is_versioned,
            has_recipe=recipe is not None,
        ),
    )


def _value_was_edited_after(product: Product, fact: str, stamp: dict | None) -> bool:
    """O campo mudou depois que a derivação o escreveu?

    Só o peso guarda o valor no carimbo (``value``), então só ele responde a
    esta pergunta. Os outros dois têm o próprio sentinela dentro do valor.
    """
    if fact != FACT_UNIT_WEIGHT or not stamp:
        return False
    stamped_value = stamp.get("value")
    if stamped_value is None:
        return False
    return int(stamped_value) != int(product.unit_weight_g or 0)


def _value_of(product: Product, fact: str) -> tuple[str, bool]:
    """O que o cliente vê hoje, resumido em uma linha."""
    if fact == FACT_UNIT_WEIGHT:
        grams = int(product.unit_weight_g or 0)
        return (f"{grams} g", True) if grams > 0 else ("", False)

    if fact == FACT_NUTRITION:
        facts = product.nutrition_facts or {}
        energy = facts.get("energy_kcal")
        serving = facts.get("serving_size_g")
        if not facts or (energy is None and serving is None):
            return "", False
        if energy is None:
            return f"porção de {serving} g", True
        return f"{energy} kcal por porção de {serving} g", True

    if fact == FACT_DIETARY:
        metadata = product.metadata or {}
        allergens = list(metadata.get("allergens") or [])
        dietary = list(metadata.get("dietary_info") or [])
        if not allergens and not dietary:
            return "", False
        parts = []
        if allergens:
            parts.append("contém " + ", ".join(str(a) for a in allergens))
        if dietary:
            parts.append(", ".join(str(d) for d in dietary))
        return "; ".join(parts), True

    return "", False


def _expected_of(product: Product, fact: str, recipe, current_value: str) -> tuple[str, bool]:
    """O que a ficha sustentaria hoje — só o peso, que é o fato calculável aqui.

    Nutrição e dieta não entram: recalcular a soma inteira só para comparar
    custaria o BOM de todo produto do catálogo numa tela de leitura, e para
    esses dois a defasagem já é respondida pela versão de origem. O peso é
    barato e é o único onde o dono pediu explicitamente o aviso de divergência.
    """
    if fact != FACT_UNIT_WEIGHT or recipe is None:
        return "", False

    derivation = derive_unit_weight(recipe)
    if derivation is None:
        return "", False

    expected = f"{derivation.announced_g} g"
    return expected, bool(current_value) and expected != current_value


def _note(
    *,
    has_value: bool,
    is_stale: bool,
    needs_audit: bool,
    is_manual: bool,
    diverges: bool,
    is_versioned: bool,
    has_recipe: bool,
) -> str:
    """A frase que diz ao gestor o que fazer. Uma por estado, em pt-BR."""
    if not has_value:
        return "O catálogo não mostra este dado."
    if is_stale and is_manual:
        return "A ficha andou desde a conferência. Reconfira o número escrito à mão."
    if is_stale:
        return "A ficha andou depois desta derivação. Salve a ficha para recalcular."
    if needs_audit:
        return "Número sem origem registrada. Confira e assine para virar conferido."
    if diverges:
        return "O número à mão difere do que a ficha sustenta hoje. Confira na balança."
    if not has_recipe:
        return "Produto sem ficha ativa: este dado é responsabilidade de quem o cadastrou."
    if not is_versioned:
        return "Ficha nunca publicada pelo inventário: não dá para detectar defasagem."
    return "Em dia com a versão publicada da ficha."


def _version_label(version_ref: str, *, has_stamp: bool) -> str:
    """O rótulo da versão. Vazio com carimbo é ficha sem versão; sem carimbo é sem ficha."""
    if version_ref:
        return version_ref
    return VERSION_LABEL_UNVERSIONED if has_stamp else VERSION_LABEL_NONE


def _active_recipe_for(sku: str):
    try:
        from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku
    except ImportError:
        return None
    return get_active_recipe_for_output_sku(sku)
