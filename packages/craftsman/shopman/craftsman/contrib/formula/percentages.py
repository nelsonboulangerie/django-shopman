"""Porcentagem do padeiro: a matemática pura da fórmula de uma receita.

Módulo sem Django. Recebe a ``formula`` de uma ``RecipeVersion`` (schema na
``docs/plans/completed/RECIPE-INVENTORY-PLAN.md`` §3) e responde, só com ``Decimal``:

* :func:`classify_ingredient` / :func:`looks_like_flour` — o papel (``role``) de
  um ingrediente pelo nome e pelo SKU, em pt/en/fr/ja, sem acento e sem caixa;
* :func:`item_grams` — quanto pesa um item da fórmula, em grama, ou ``None``
  quando a física não deixa saber (contagem sem ``grams_per_unit``);
* :func:`analyze` — âncora, porcentagens, mistura final e BOM imediata;
* :func:`standardize` / :func:`scale` — a fórmula inteira reescrita para a
  âncora somar ``basis_g`` (padrão da casa: 1000 g de farinhas), ou escalada por
  um fator;
* :data:`REFERENCE_RANGES` / :func:`check_references` — faixas da literatura
  (Hamelman, Suas, convenção BBGA). São referência; o padeiro decide;
* :func:`derive_bom` — os itens prontos para virar ``RecipeItem`` ao publicar;
* :func:`validate_formula` — o schema, com o caminho do campo ofensor.

Quantidades saem como ``str`` de ``Decimal`` (3 casas, sem zeros à direita):
é o que o ``JSONField`` guarda sem perder precisão, no mesmo dialeto do
``contrib/formula/service.py``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from shopman.craftsman.exceptions import RecipeBookError

ROLES = ("flour", "liquid", "salt", "yeast", "fat", "sugar", "egg", "dairy", "inclusion", "other")
ANCHOR_KINDS = ("flour", "total", "ingredient")
COMPOSITIONS = ("additional", "included")
QUANTITY_KINDS = ("fixed", "ratio")
BASIS_KINDS = ("flour", "total", "ingredient")
UNITS = ("g", "kg", "mg", "ml", "L", "un")

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_THOUSANDTH = Decimal("0.001")
#: Quantidade declarada e derivada da porcentagem a menos de 0,01% uma da outra
#: são a mesma declaração (a porcentagem tem 3 casas; a quantidade, mais).
_SAME_DECLARATION_TOLERANCE = Decimal("0.0001")
#: Resíduo de arredondamento abaixo disto não vira linha do BOM: ninguém pesa 10 mg.
_BOM_RESIDUE_G = Decimal("0.01")
_GRAMS_PER_UNIT = {"g": Decimal(1), "kg": Decimal(1000), "mg": Decimal("0.001")}
_ML_PER_UNIT = {"ml": Decimal(1), "L": Decimal(1000)}
_UNIT_SPELLING = {
    "g": "g", "gr": "g", "grama": "g", "gramas": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilo": "kg", "quilo": "kg", "kilos": "kg", "quilos": "kg",
    "mg": "mg",
    "ml": "ml",
    "l": "L", "lt": "L", "lts": "L", "litro": "L", "litros": "L", "liter": "L", "liters": "L",
    "un": "un", "un.": "un", "unit": "un", "units": "un", "unidade": "un", "unidades": "un",
}

# ── Papel do ingrediente ─────────────────────────────────────────────────────
#
# Palavras latinas casam por token inteiro ("sal" não casa "salsa"); as
# japonesas casam por substring (não há espaço entre palavras). A ORDEM das
# tuplas importa: "farinha de castanha" é farinha antes de ser castanha,
# "creme de leite" é laticínio antes de ser leite, "azeitona" é inclusão
# antes de "azeite" ser gordura.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "flour",
        (
            "farinha", "farinhas", "flour", "farine", "centeio", "rye", "seigle", "semola",
            "semolina", "trigo", "trigo integral", "farinha integral", "whole wheat", "whole meal",
            "wholemeal", "wholewheat", "farine complete", "fuba", "cornmeal",
            "t45", "t55", "t65", "t80", "t110", "t150",
        ),
        ("粉", "小麦粉", "強力粉", "薄力粉", "ライ麦", "全粒粉"),
    ),
    (
        "dairy",
        (
            "creme de leite", "leite em po", "milk powder", "lait en poudre", "nata", "cream",
            "creme", "queijo", "cheese", "fromage", "iogurte", "yogurt", "yaourt", "requeijao",
        ),
        ("チーズ", "生クリーム", "ヨーグルト"),
    ),
    ("liquid", ("agua", "water", "eau", "leite", "milk", "lait"), ("水", "牛乳")),
    ("salt", ("sal", "salt", "sel"), ("塩",)),
    # Fermento natural (a cultura, o levain como ingrediente) NÃO é fermento
    # biológico: fica fora da métrica de fermento e da faixa de 0,5 a 3%. Vem
    # antes de "fermento" porque "fermento natural" contém a palavra.
    (
        "other",
        (
            "fermento natural", "fermento nat", "levain", "sourdough", "masa madre",
            "lievito madre", "starter", "isca",
        ),
        ("サワー種", "ルヴァン"),
    ),
    (
        "yeast",
        ("fermento", "levure", "yeast", "levedura", "lievito"),
        ("イースト", "酵母"),
    ),
    ("egg", ("ovo", "ovos", "egg", "eggs", "oeuf", "oeufs", "gema", "gemas", "yolk", "yolks"), ("卵",)),
    (
        "inclusion",
        (
            "passas", "passa", "castanha", "castanhas", "chocolate", "gotas", "nuts", "nozes",
            "noz", "raisins", "raisin", "azeitona", "azeitonas", "olive", "olives", "gergelim",
            "sesame", "sementes", "semente", "seeds", "seed", "graines", "amendoa", "amendoas",
            "avela", "avelas", "cranberry", "damasco", "chips",
        ),
        ("ナッツ", "レーズン", "チョコ", "ゴマ", "オリーブ"),
    ),
    (
        "fat",
        (
            "manteiga", "butter", "beurre", "azeite", "oleo", "oil", "huile", "banha", "lard",
            "margarina", "margarine", "gordura", "shortening",
        ),
        ("バター", "油"),
    ),
    (
        "sugar",
        ("acucar", "sugar", "sucre", "mel", "honey", "miel", "malte", "malt", "melado", "glucose"),
        ("砂糖",),
    ),
)

def normalize_text(value: Any) -> str:
    """Texto sem acento, em minúsculas, com espaços únicos. Kana e kanji ficam."""
    raw = str(value or "")
    for ligature, plain in (("œ", "oe"), ("Œ", "oe"), ("æ", "ae"), ("Æ", "ae"), ("ß", "ss")):
        raw = raw.replace(ligature, plain)
    # Tira o acento só de letra latina: o dakuten de "バ" também é marca
    # combinante, e sem ele "バター" viraria "ハター".
    kept: list[str] = []
    for ch in unicodedata.normalize("NFKD", raw):
        if unicodedata.combining(ch) and kept and kept[-1].isascii():
            continue
        kept.append(ch)
    recomposed = unicodedata.normalize("NFC", "".join(kept))
    return re.sub(r"\s+", " ", recomposed.lower()).strip()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(tok for tok in re.split(r"[^0-9a-z぀-ヿ一-鿿]+", text) if tok)


def _matches(text: str, latin: tuple[str, ...], cjk: tuple[str, ...]) -> bool:
    tokens = _tokens(text)
    padded = f" {' '.join(tokens)} "
    for keyword in latin:
        if " " in keyword:
            if f" {keyword} " in padded:
                return True
        elif keyword in tokens:
            return True
    return any(keyword in text for keyword in cjk)


def classify_ingredient(name: str, sku: str = "") -> str:
    """Papel do ingrediente pelo nome e pelo SKU (``FARINHA-ANACONDA-PREMIUM`` também conta).

    Vence a palavra que aparece **primeiro no texto**, não a primeira regra da
    tabela — e isso é a gramática do português, não uma preferência: o
    substantivo vem antes do qualificador. *Manteiga* sem sal, *manteiga* com
    sal, *chocolate* ao leite, *farinha* de centeio. É também, por construção, a
    convenção de SKU desta casa, que põe a **família na frente**.

    ⚠️ Antes disso valia a ordem da tabela, e o defeito apareceu em 24/09/2026:
    a curadoria trocou `MANTEIGA-FR` por `MANTEIGA-PRESIDENT-SEM-SAL` e a
    manteiga de 16 fichas virou SAL, porque `salt` está listada antes de `fat`.
    O SKU não estava errado — o mundo diz "manteiga sem sal". O papel alimenta a
    lente de padaria, então o engano entrava direto no percentual do padeiro.
    """
    text = normalize_text(f"{name} {str(sku or '').replace('-', ' ').replace('_', ' ')}")
    if not text:
        return "other"

    melhor, posicao = "other", len(text) + 1
    for role, latin, cjk in _ROLE_KEYWORDS:
        onde = _first_position(text, latin, cjk)
        if onde is not None and onde < posicao:
            melhor, posicao = role, onde
    return melhor


def _first_position(text: str, latin, cjk) -> int | None:
    """Onde, no texto, esta categoria aparece primeiro — ``None`` se não aparece.

    Reaproveita o casamento de ``_matches`` (prefixo para palavra longa, token
    exato para curta), porque afrouxar aqui faria "sal" casar dentro de
    "salsinha".
    """
    tokens = text.split()
    for i, token in enumerate(tokens):
        if _matches(token, latin, cjk):
            return i
    return None


def looks_like_flour(name: str, sku: str = "") -> bool:
    """``True`` quando o ingrediente conta como farinha para a âncora e a hidratação."""
    return classify_ingredient(name, sku) == "flour"


# ── Números ──────────────────────────────────────────────────────────────────


def to_decimal(value: Any) -> Decimal | None:
    """``Decimal`` de qualquer coisa que pareça número; ``None`` quando não é."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def quantize(value: Decimal) -> Decimal:
    """Três casas, meio para cima, sem zeros à direita e sem notação científica."""
    rounded = value.quantize(_THOUSANDTH, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return Decimal(text or "0")


def number_text(value: Decimal | None) -> str:
    """Texto do ``Decimal`` para o JSON da fórmula."""
    if value is None:
        return ""
    return format(quantize(value), "f")


def normalize_unit(value: Any) -> str:
    """Grafia canônica da unidade da fórmula (``l`` → ``L``); desconhecida volta como veio."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw in UNITS:
        return raw
    return _UNIT_SPELLING.get(raw.lower(), raw)


def item_grams(item: dict) -> Decimal | None:
    """Massa-alvo do ingrediente em grama, quando a quantidade é fixa."""
    spec = item.get("quantity")
    if isinstance(spec, dict):
        if spec.get("kind") != "fixed":
            return None
        quantity = to_decimal(spec.get("target"))
        unit = normalize_unit(spec.get("unit") or "g")
    else:
        quantity = to_decimal(spec)
        unit = normalize_unit(item.get("unit") or "g")
    if quantity is None:
        return None
    if unit in _GRAMS_PER_UNIT:
        return quantity * _GRAMS_PER_UNIT[unit]
    if unit in _ML_PER_UNIT:
        density = to_decimal(item.get("density_g_per_ml"))
        if density is None or density <= 0:
            if item.get("role") == "liquid":
                density = Decimal(1)
            else:
                return None
        return quantity * _ML_PER_UNIT[unit] * density
    if unit == "un":
        per_unit = to_decimal(item.get("grams_per_unit"))
        if per_unit is None or per_unit <= 0:
            return None
        return quantity * per_unit
    return None


# ── Resultado da análise ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class FormulaWarning:
    """Aviso da análise. Nunca bloqueia: a tela mostra em tom calmo."""

    code: str
    message: str
    metric: str = ""
    value: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None


@dataclass(frozen=True)
class FormulaItemAnalysis:
    """Um ingrediente unificado, simples ou produzido por outra receita."""

    sku: str
    name: str
    role: str
    quantity: Decimal
    unit: str
    grams: Decimal | None
    pct: Decimal | None
    ingredient_ref: str = ""
    quantity_kind: str = "fixed"
    basis_kind: str = ""
    basis_sku: str = ""
    recipe_version_ref: str = ""
    composition: str = "additional"
    minimum: Decimal | None = None
    target: Decimal | None = None
    maximum: Decimal | None = None
    contents: tuple[FormulaItemAnalysis, ...] = ()


@dataclass(frozen=True)
class QuantityDeviation:
    ingredient_ref: str
    sku: str
    name: str
    minimum: Decimal | None
    target: Decimal
    maximum: Decimal | None
    actual: Decimal
    within_bounds: bool


@dataclass(frozen=True)
class FormulaAnalysis:
    """A fórmula lida pela lente do padeiro."""

    anchor_kind: str
    anchor_total_g: Decimal | None
    total_mass_g: Decimal
    ingredients: tuple[FormulaItemAnalysis, ...]
    hydration_pct: Decimal | None
    salt_pct: Decimal | None
    yeast_pct: Decimal | None
    fat_pct: Decimal | None
    sugar_pct: Decimal | None
    egg_pct: Decimal | None
    final_mix: tuple[FormulaItemAnalysis, ...]
    bom: tuple[dict, ...]
    deviations: tuple[QuantityDeviation, ...] = ()
    warnings: tuple[FormulaWarning, ...] = field(default_factory=tuple)

    def metrics(self) -> dict[str, Decimal | None]:
        return {
            "hydration_pct": self.hydration_pct,
            "salt_pct": self.salt_pct,
            "yeast_pct": self.yeast_pct,
            "fat_pct": self.fat_pct,
            "sugar_pct": self.sugar_pct,
            "egg_pct": self.egg_pct,
        }


# ── Análise ──────────────────────────────────────────────────────────────────


def _item_key(item: dict) -> str:
    sku = str(item.get("sku") or "").strip()
    return sku or f"name:{normalize_text(item.get('name'))}"


def _pct(grams: Decimal | None, anchor: Decimal | None) -> Decimal | None:
    if grams is None or anchor is None or anchor <= 0:
        return None
    return quantize(grams / anchor * _HUNDRED)


def _quantity_spec(raw: dict) -> dict:
    internal = raw.get("_quantity_spec")
    if isinstance(internal, dict):
        return internal
    spec = raw.get("quantity")
    return spec if isinstance(spec, dict) else {}


def _fixed_as_item(raw: dict) -> dict:
    spec = _quantity_spec(raw)
    return {
        **raw,
        "_quantity_spec": spec,
        "quantity": spec.get("target"),
        "unit": spec.get("unit") or "g",
    }


def _read_fixed(ingredients: list[dict], warnings: list[FormulaWarning], actuals: dict[str, Any] | None = None) -> list[dict]:
    """Ingredientes simples de quantidade fixa que definem a fórmula global."""
    read: list[dict] = []
    for index, raw in enumerate(ingredients):
        spec = _quantity_spec(raw)
        if raw.get("recipe_version_ref") or spec.get("kind") != "fixed":
            continue
        fixed = _fixed_as_item(raw)
        ingredient_ref = str(raw.get("ref") or "")
        if actuals and ingredient_ref in actuals:
            fixed["quantity"] = actuals[ingredient_ref]
        quantity = to_decimal(fixed.get("quantity")) or _ZERO
        unit = normalize_unit(fixed.get("unit") or "g")
        role = str(raw.get("role") or "") or classify_ingredient(raw.get("name", ""), raw.get("sku", ""))
        item = {**fixed, "quantity": quantity, "unit": unit, "role": role, "source_index": index, "_quantity_spec": spec}
        grams = item_grams(item)
        label = str(raw.get("name") or raw.get("sku") or f"item {index + 1}")
        if grams is None:
            if unit == "un":
                warnings.append(FormulaWarning(
                    "COUNT_WITHOUT_GRAMS_PER_UNIT",
                    f"{label}: contagem sem peso por unidade fica fora da conta.",
                    metric=f"ingredients[{index}]",
                ))
            elif unit in _ML_PER_UNIT:
                warnings.append(FormulaWarning(
                    "VOLUME_WITHOUT_DENSITY",
                    f"{label}: volume sem densidade declarada fica fora da conta.",
                    metric=f"ingredients[{index}]",
                ))
        elif unit in _ML_PER_UNIT and to_decimal(raw.get("density_g_per_ml")) in (None, _ZERO) and role == "liquid":
            warnings.append(FormulaWarning(
                "LIQUID_DENSITY_ASSUMED",
                f"{label}: volume de líquido sem densidade; assumido 1,0 g/ml.",
                metric=f"ingredients[{index}]",
            ))
        item["grams"] = grams
        item["key"] = _item_key(raw)
        item["line"] = index
        read.append(item)
    return read


def _role_total(items: list[dict], role: str) -> Decimal:
    return sum((it["grams"] for it in items if it["role"] == role and it["grams"] is not None), _ZERO)


def _to_analysis_item(item: dict, anchor: Decimal | None, *, grams: Decimal | None = None,
                      quantity: Decimal | None = None) -> FormulaItemAnalysis:
    grams_value = item["grams"] if grams is None else grams
    quantity_value = item["quantity"] if quantity is None else quantity
    spec = _quantity_spec(item)
    basis = spec.get("basis") if isinstance(spec.get("basis"), dict) else {}
    return FormulaItemAnalysis(
        sku=str(item.get("sku") or ""),
        name=str(item.get("name") or item.get("sku") or ""),
        role=item["role"],
        quantity=quantize(quantity_value),
        unit=item["unit"],
        grams=None if grams_value is None else quantize(grams_value),
        pct=_pct(grams_value, anchor),
        ingredient_ref=str(item.get("ref") or ""),
        quantity_kind=str(spec.get("kind") or "fixed"),
        basis_kind=str(basis.get("kind") or ""),
        basis_sku=str(basis.get("sku") or ""),
        recipe_version_ref=str(item.get("recipe_version_ref") or ""),
        composition=str(item.get("composition") or "additional"),
        minimum=to_decimal(spec.get("minimum")),
        target=to_decimal(spec.get("target")),
        maximum=to_decimal(spec.get("maximum")),
        contents=tuple(item.get("contents") or ()),
    )


def _basis_grams(spec: dict, base: list[dict]) -> Decimal | None:
    basis = spec.get("basis") or {}
    kind = basis.get("kind")
    if kind == "total":
        return sum((it["grams"] for it in base if it["grams"] is not None), _ZERO)
    if kind == "flour":
        return _role_total(base, "flour")
    if kind == "ingredient":
        sku = str(basis.get("sku") or "")
        return sum((it["grams"] for it in base if it["grams"] is not None and it.get("sku") == sku), _ZERO)
    return None


def _resolve_target(raw: dict, base: list[dict], actual: Any = None) -> tuple[Decimal | None, str, Decimal | None]:
    spec = _quantity_spec(raw)
    target = to_decimal(spec.get("target") if actual is None else actual)
    if target is None:
        return None, "g", None
    if spec.get("kind") == "ratio":
        basis = _basis_grams(spec, base)
        return (None if basis is None else basis * target / _HUNDRED), "g", basis
    unit = normalize_unit(spec.get("unit") or "g")
    fixed = {**raw, "quantity": target, "unit": unit}
    return item_grams(fixed), unit, None


def _global_composition(formula: dict, formulas: dict[str, dict], stack: tuple[str, ...] = ()) -> list[dict]:
    """Composição elementar da receita sem contar duas vezes ingredientes inclusos."""
    warnings: list[FormulaWarning] = []
    declared = list(formula.get("ingredients") or [])
    base = _read_fixed(declared, warnings)
    out = [dict(it) for it in base if it["grams"] is not None]
    for raw in declared:
        ref = str(raw.get("recipe_version_ref") or "")
        if not ref or raw.get("composition") != "additional" or ref in stack:
            continue
        child = formulas.get(ref)
        target_g, _, _ = _resolve_target(raw, base)
        if not child or target_g is None:
            continue
        child_items = _global_composition(child, formulas, (*stack, ref))
        child_total = sum((it["grams"] for it in child_items if it["grams"] is not None), _ZERO)
        if child_total <= 0:
            continue
        for component in child_items:
            out.append({**component, "grams": component["grams"] / child_total * target_g})
    return out


def analyze(formula: dict, ingredient_formulas: dict[str, dict] | None = None, *,
            actual_quantities: dict[str, Any] | None = None) -> FormulaAnalysis:
    """Resolve a fórmula unificada no alvo, preservando fórmula global e BOM imediata."""
    ingredient_formulas = ingredient_formulas or {}
    warnings: list[FormulaWarning] = []
    declared = list(formula.get("ingredients") or [])
    actual_quantities = actual_quantities or {}
    base = _read_fixed(declared, warnings, actual_quantities)
    anchor = formula.get("anchor") or {}
    anchor_kind = str(anchor.get("kind") or "total")

    flour_total = _role_total(base, "flour")
    total_mass = sum((it["grams"] for it in base if it["grams"] is not None), _ZERO)
    if anchor_kind == "flour":
        anchor_total: Decimal | None = flour_total
    elif anchor_kind == "ingredient":
        anchor_sku = str(anchor.get("sku") or "")
        anchor_total = sum((it["grams"] for it in base if it["grams"] is not None and it.get("sku") == anchor_sku), _ZERO)
        if anchor_total == _ZERO:
            warnings.append(FormulaWarning(
                "ANCHOR_NOT_FOUND", f"O ingrediente âncora ({anchor_sku or 'sem SKU'}) não está na fórmula.",
                metric="anchor",
            ))
            anchor_total = None
    else:
        anchor_total = total_mass
    if anchor_kind == "flour" and flour_total == _ZERO:
        warnings.append(FormulaWarning("ANCHOR_EMPTY", "A fórmula não tem farinha; a âncora soma zero.", metric="anchor"))
        anchor_total = None

    analyses: list[FormulaItemAnalysis] = [_to_analysis_item(it, anchor_total) for it in base]
    remaining = _grams_by_key(base)
    base_by_key = {it["key"]: it for it in base}
    recipe_rows: list[dict] = []
    for index, raw in enumerate(declared):
        ref = str(raw.get("recipe_version_ref") or "")
        if not ref:
            continue
        name = str(raw.get("name") or raw.get("sku") or "")
        actual = actual_quantities.get(str(raw.get("ref") or ""))
        target_g, unit, _ = _resolve_target(raw, base, actual)
        child = ingredient_formulas.get(ref)
        if not child:
            warnings.append(FormulaWarning(
                "INGREDIENT_RECIPE_NOT_FOUND", f"{name}: a versão {ref} não foi encontrada.",
                metric=f"ingredients[{index}].recipe_version_ref",
            ))
        child_items = _global_composition(child or {}, ingredient_formulas, (ref,))
        child_total = sum((it["grams"] for it in child_items if it["grams"] is not None), _ZERO)
        contents: list[FormulaItemAnalysis] = []
        for component in child_items:
            if target_g is None or child_total <= 0:
                break
            contained = component["grams"] / child_total * target_g
            key = component["key"]
            if raw.get("composition") == "included":
                available = remaining.get(key)
                if key not in base_by_key or available is None or contained > available + Decimal("0.0005"):
                    warnings.append(FormulaWarning(
                        "INCLUDED_COMPOSITION_EXCEEDS_FORMULA",
                        f"{name} usa mais {component.get('name') or component.get('sku')} do que a fórmula contém.",
                        metric=f"ingredients[{index}].composition",
                        value=quantize(contained), high=None if available is None else quantize(available),
                    ))
                    if available is not None:
                        remaining[key] = _ZERO
                else:
                    remaining[key] = available - contained
            contents.append(_to_analysis_item(
                {**component, "unit": "g"}, anchor_total, grams=contained, quantity=contained,
            ))
        factor = _GRAMS_PER_UNIT.get(unit, Decimal(1))
        analysis_raw = {
            **raw,
            "_quantity_spec": _quantity_spec(raw),
            "quantity": _quantity_spec(raw).get("target"),
            "unit": unit,
            "role": str(raw.get("role") or "other"), "grams": target_g, "contents": tuple(contents),
        }
        analyses.append(_to_analysis_item(
            analysis_raw, anchor_total, grams=target_g,
            quantity=None if target_g is None else target_g / factor,
        ))
        recipe_rows.append({**analysis_raw, "target_g": target_g})

    # O que sobrou de cada ingrediente depois das composições inclusas.
    # (inclusive o "-0" do Decimal) vira zero, não linha negativa na tela.
    remaining = _remaining_by_line(base, {
        key: (_ZERO if grams is not None and abs(grams) < _BOM_RESIDUE_G else grams)
        for key, grams in remaining.items()
    })
    final_mix = tuple(
        _final_mix_item(it, remaining[it["line"]], anchor_total)
        for it in base
    )
    bom = tuple(_bom_items(base, remaining, recipe_rows))
    additional_mass = sum((row["target_g"] or _ZERO for row in recipe_rows if row.get("composition") == "additional"), _ZERO)

    metrics_on = anchor_kind == "flour" and anchor_total is not None and anchor_total > 0
    deviations = tuple(_quantity_deviation(raw, actual_quantities[str(raw.get("ref") or "")])
                       for raw in declared if str(raw.get("ref") or "") in actual_quantities)
    return FormulaAnalysis(
        anchor_kind=anchor_kind,
        anchor_total_g=None if anchor_total is None else quantize(anchor_total),
        total_mass_g=quantize(total_mass + additional_mass),
        ingredients=tuple(analyses),
        hydration_pct=_pct(_role_total(base, "liquid"), anchor_total) if metrics_on else None,
        salt_pct=_pct(_role_total(base, "salt"), anchor_total) if metrics_on else None,
        yeast_pct=_pct(_role_total(base, "yeast"), anchor_total) if metrics_on else None,
        fat_pct=_pct(_role_total(base, "fat"), anchor_total) if metrics_on else None,
        sugar_pct=_pct(_role_total(base, "sugar"), anchor_total) if metrics_on else None,
        egg_pct=_pct(_role_total(base, "egg"), anchor_total) if metrics_on else None,
        final_mix=final_mix,
        bom=bom,
        deviations=deviations,
        warnings=tuple(warnings),
    )


def _quantity_deviation(raw: dict, actual_value: Any) -> QuantityDeviation:
    spec = _quantity_spec(raw)
    target = to_decimal(spec.get("target")) or _ZERO
    actual = to_decimal(actual_value) or _ZERO
    minimum = to_decimal(spec.get("minimum"))
    maximum = to_decimal(spec.get("maximum"))
    return QuantityDeviation(
        ingredient_ref=str(raw.get("ref") or ""),
        sku=str(raw.get("sku") or ""), name=str(raw.get("name") or raw.get("sku") or ""),
        minimum=minimum, target=target, maximum=maximum, actual=actual,
        within_bounds=(minimum is None or actual >= minimum) and (maximum is None or actual <= maximum),
    )


def resolve_execution(formula: dict, actual_quantities: dict[str, Any],
                      ingredient_formulas: dict[str, dict] | None = None) -> FormulaAnalysis:
    """Recalcula a fórmula pela quantidade real; desvios permanecem explícitos para autorização."""
    return analyze(formula, ingredient_formulas, actual_quantities=actual_quantities)


def _grams_by_key(base: list[dict]) -> dict[str, Decimal | None]:
    """Grama de cada insumo somando as linhas dele; ``None`` se nenhuma linha tem peso."""
    totals: dict[str, Decimal | None] = {}
    for item in base:
        key, grams = item["key"], item["grams"]
        if grams is None:
            totals.setdefault(key, None)
        else:
            totals[key] = (totals.get(key) or _ZERO) + grams
    return totals


def _remaining_by_line(base: list[dict], remaining_by_key: dict[str, Decimal | None]) -> dict[int, Decimal | None]:
    """O que sobrou do insumo, de volta a cada LINHA da fórmula.

    O que as composições inclusas levaram sai das linhas na ordem da
    fórmula, a primeira primeiro: o levain tira a água da água da massa, e a
    bassinage (escrita depois) fica inteira. Linha sem peso (contagem sem
    grama por unidade) fica ``None``, como sempre ficou.
    """
    taken = {
        key: (total - remaining_by_key[key]) if total is not None and remaining_by_key.get(key) is not None else _ZERO
        for key, total in _grams_by_key(base).items()
    }
    out: dict[int, Decimal | None] = {}
    for item in base:
        grams = item["grams"]
        if grams is None:
            out[item["line"]] = None
            continue
        take = min(grams, max(taken[item["key"]], _ZERO))
        taken[item["key"]] -= take
        left = grams - take
        out[item["line"]] = _ZERO if abs(left) < _BOM_RESIDUE_G else left
    return out


def _grams_of(quantity: Decimal, unit: str) -> Decimal | None:
    factor = _GRAMS_PER_UNIT.get(normalize_unit(unit) or "g")
    return None if factor is None else quantity * factor


def _quantity_in_own_unit(item: dict, grams: Decimal | None) -> Decimal:
    """De volta à unidade em que o item foi escrito (kg, ml, un...)."""
    if grams is None or item["grams"] in (None, _ZERO) or item["quantity"] == _ZERO:
        return item["quantity"]
    return grams / item["grams"] * item["quantity"]


def _final_mix_item(item: dict, grams: Decimal | None, anchor: Decimal | None) -> FormulaItemAnalysis:
    return _to_analysis_item(item, anchor, grams=grams, quantity=_quantity_in_own_unit(item, grams))


def _note_meta(note: Any) -> dict:
    text = note.strip() if isinstance(note, str) else ""
    return {"note": text} if text else {}


def _bom_items(base: list[dict], remaining: dict, recipe_rows: list[dict]) -> list[dict]:
    bom: list[dict] = []
    for item in base:
        grams = remaining[item["line"]]
        quantity = _quantity_in_own_unit(item, grams)
        if grams is not None and grams < _BOM_RESIDUE_G:
            continue
        if quantize(quantity) <= _ZERO:
            continue
        bom.append({
            "sku": str(item.get("sku") or ""),
            "name": str(item.get("name") or item.get("sku") or ""),
            "role": item["role"],
            "quantity": quantize(quantity),
            "unit": item["unit"],
            # A densidade viaja com a linha: é ela que leva "700 g de água" até o
            # insumo cadastrado em litro na hora de publicar.
            "density_g_per_ml": to_decimal(item.get("density_g_per_ml")),
            "is_optional": False,
            # A anotação prática do item ("a farinha do bairro pede 2% mais água")
            # chega à ficha: sem isso ela morria no ato de publicar.
            "meta": _note_meta(item.get("note")),
        })
    for ingredient in recipe_rows:
        target_g = ingredient.get("target_g")
        if target_g is None:
            continue
        unit = ingredient.get("unit") or "g"
        factor = _GRAMS_PER_UNIT.get(unit, Decimal(1))
        bom.append({
            "sku": str(ingredient.get("sku") or ""),
            "name": str(ingredient.get("name") or ingredient.get("sku") or ""),
            "role": str(ingredient.get("role") or "other"),
            "quantity": quantize(target_g / factor),
            "unit": unit if unit in _GRAMS_PER_UNIT else "g",
            "is_optional": False,
            "meta": {"recipe_version_ref": ingredient.get("recipe_version_ref"), "composition": ingredient.get("composition")},
        })
    return bom


def derive_bom(formula: dict, ingredient_formulas: dict[str, dict] | None = None) -> list[dict]:
    """BOM imediata: mistura direta restante mais ingredientes produzidos."""
    return list(analyze(formula, ingredient_formulas).bom)


# ── Escala e padronização ────────────────────────────────────────────────────


def scale(formula: dict, factor: Decimal | int | str) -> dict:
    """A fórmula inteira multiplicada por ``factor``; porcentagens ficam."""
    ratio = to_decimal(factor)
    if ratio is None or ratio <= 0:
        raise RecipeBookError("FORMULA_INVALID", field="factor", message="O fator de escala precisa ser positivo.")
    scaled = {**formula, "ingredients": [], "basis_g": None, "standardized": False}
    for ingredient in list(formula.get("ingredients") or []):
        spec = dict(_quantity_spec(ingredient))
        if spec.get("kind") == "fixed":
            for key in ("minimum", "target", "maximum"):
                value = to_decimal(spec.get(key))
                if value is not None:
                    spec[key] = number_text(value * ratio)
        scaled["ingredients"].append({**ingredient, "quantity": spec})
    return scaled


def standardize(formula: dict, basis_g: Decimal | int | str = Decimal(1000)) -> dict:
    """A fórmula reescrita para a âncora somar ``basis_g`` (padrão da casa: 1000 g)."""
    basis = to_decimal(basis_g)
    if basis is None or basis <= 0:
        raise RecipeBookError("FORMULA_INVALID", field="basis_g", message="A base precisa ser positiva.")
    analysis = analyze(formula)
    if not analysis.anchor_total_g or analysis.anchor_total_g <= 0:
        raise RecipeBookError("ANCHOR_EMPTY", field="anchor")
    result = scale(formula, basis / analysis.anchor_total_g)
    result["basis_g"] = number_text(basis)
    result["standardized"] = True
    return result


# ── Referências da literatura ────────────────────────────────────────────────

_ALL = "*"

# As faixas desta lente vêm da literatura de panificação. Biscoito pode usar
# âncora de farinha para leitura percentual sem por isso herdar hidratação,
# sal ou fermento de pão.
REFERENCE_EXCLUDED_KINDS = ("cookie",)


def _range(low, high, maximum=None, note="") -> dict:
    return {
        "low": None if low is None else Decimal(str(low)),
        "high": None if high is None else Decimal(str(high)),
        "max": None if maximum is None else Decimal(str(maximum)),
        "note": note,
    }


#: Faixas por métrica; dentro, por ``kind`` da receita (``"*"`` vale para todas).
#: *Advanced Bread and Pastry*, convenção BBGA. Referência, não regra.
REFERENCE_RANGES: dict[str, dict[str, dict]] = {
    "salt_pct": {
        _ALL: _range("1.8", "2.2", "2.5", "Sal sobre a farinha total."),
    },
    "yeast_pct": {
        _ALL: _range("0.5", "2", "3", "Fermento fresco; seco vale cerca de um terço."),
    },
    "hydration_pct": {
        "bread": _range("60", "85", None, "Rústico 68 a 80; baguete e tradição 65 a 75; ciabatta 75 a 85; forma e shokupan 60 a 72."),
        "viennoiserie": _range("50", "60", None, "Croissant 50 a 58; brioche 50 a 60 contando todo o líquido."),
        "sweet_dough": _range("50", "65", None, "Massa doce enriquecida."),
    },
    "sugar_pct": {
        "viennoiserie": _range("10", "20", None, "Massa enriquecida."),
        "sweet_dough": _range("10", "20", None, "Massa enriquecida."),
    },
    "fat_pct": {
        "viennoiserie": _range("40", "60", None, "Manteiga de brioche; croissant conta a manteiga de laminação."),
        "sweet_dough": _range("10", "30", None, "Massa doce."),
    },
    "egg_pct": {
        "viennoiserie": _range("40", "60", None, "Brioche."),
        "sweet_dough": _range("10", "40", None, "Massa doce."),
    },
}

_ALWAYS_CHECKED = ("hydration_pct", "salt_pct")

_METRIC_LABELS = {
    "hydration_pct": "Hidratação",
    "salt_pct": "Sal",
    "yeast_pct": "Fermento",
    "fat_pct": "Gordura",
    "sugar_pct": "Açúcar",
    "egg_pct": "Ovos",
}


def reference_for(metric: str, kind: str) -> dict | None:
    """A faixa de ``metric`` para o ``kind`` da receita, ou ``None`` se não há."""
    table = REFERENCE_RANGES.get(metric) or {}
    exact = table.get(kind)
    if exact:
        return exact
    return None if kind in REFERENCE_EXCLUDED_KINDS else table.get(_ALL)


def _pct_text(value: Decimal | None) -> str:
    return "" if value is None else format(quantize(value), "f").replace(".", ",")


def _check_value(code_prefix: str, label: str, metric: str, value: Decimal | None, bounds: dict | None,
                 out: list[FormulaWarning]) -> None:
    if value is None or not bounds:
        return
    low, high, maximum = bounds["low"], bounds["high"], bounds["max"]
    if maximum is not None and value > maximum:
        out.append(FormulaWarning(
            f"{code_prefix}_ABOVE_MAX",
            f"{label} em {_pct_text(value)}% passa do teto da literatura ({_pct_text(maximum)}%).",
            metric=metric, value=value, low=low, high=high,
        ))
        return
    if (low is not None and value < low) or (high is not None and value > high):
        out.append(FormulaWarning(
            f"{code_prefix}_OUT_OF_RANGE",
            f"{label} em {_pct_text(value)}% está fora da faixa de referência "
            f"({_pct_text(low)} a {_pct_text(high)}%).",
            metric=metric, value=value, low=low, high=high,
        ))


def check_references(analysis: FormulaAnalysis, kind: str) -> list[FormulaWarning]:
    """Compara métricas globais com a literatura. Nunca bloqueia."""
    out: list[FormulaWarning] = []
    if analysis.anchor_kind != "flour" or kind in REFERENCE_EXCLUDED_KINDS:
        return out
    for metric, value in analysis.metrics().items():
        # Ausente não é errado: pão de levain não leva fermento, massa magra não
        # leva açúcar. Só hidratação e sal em zero merecem aviso.
        if value == _ZERO and metric not in _ALWAYS_CHECKED:
            continue
        _check_value("REFERENCE", _METRIC_LABELS[metric], metric, value, reference_for(metric, kind), out)
    return out


# ── Schema ───────────────────────────────────────────────────────────────────


def _invalid(field_path: str, message: str) -> RecipeBookError:
    return RecipeBookError("FORMULA_INVALID", field=field_path, message=message)


def _require_positive(value: Any, field_path: str, *, allow_zero: bool = False) -> Decimal:
    number = to_decimal(value)
    if number is None:
        raise _invalid(field_path, "Precisa ser um número.")
    if number < 0 or (number == 0 and not allow_zero):
        raise _invalid(field_path, "Precisa ser maior que zero.")
    return number


def validate_formula(formula: Any) -> None:
    """Confere o schema da fórmula (§3 do plano). Levanta ``FORMULA_INVALID`` com ``field``."""
    if not isinstance(formula, dict):
        raise _invalid("formula", "A fórmula precisa ser um objeto.")

    anchor = formula.get("anchor")
    if not isinstance(anchor, dict):
        raise _invalid("anchor", "A âncora precisa ser um objeto com kind.")
    anchor_kind = anchor.get("kind")
    if anchor_kind not in ANCHOR_KINDS:
        raise _invalid("anchor.kind", f"Âncora desconhecida; use uma de: {', '.join(ANCHOR_KINDS)}.")
    if anchor_kind == "ingredient" and not str(anchor.get("sku") or "").strip():
        raise _invalid("anchor.sku", "Âncora por ingrediente precisa do SKU.")

    if formula.get("basis_g") not in (None, ""):
        _require_positive(formula.get("basis_g"), "basis_g")
    if "standardized" in formula and not isinstance(formula.get("standardized"), bool):
        raise _invalid("standardized", "Precisa ser verdadeiro ou falso.")

    ingredients = formula.get("ingredients")
    if not isinstance(ingredients, list):
        raise _invalid("ingredients", "Os ingredientes precisam ser uma lista.")
    seen_refs: set[str] = set()
    for index, ingredient in enumerate(ingredients):
        path = f"ingredients[{index}]"
        if not isinstance(ingredient, dict):
            raise _invalid(path, "Cada ingrediente precisa ser um objeto.")
        sku = ingredient.get("sku", "")
        name = ingredient.get("name", "")
        if not isinstance(sku, str) or not isinstance(name, str):
            raise _invalid(f"{path}.name", "Nome e SKU precisam ser texto.")
        if not sku.strip() and not name.strip():
            raise _invalid(f"{path}.name", "Ingrediente sem nome e sem SKU.")
        ingredient_ref = ingredient.get("ref")
        if not isinstance(ingredient_ref, str) or not ingredient_ref.strip():
            raise _invalid(f"{path}.ref", "A participação precisa de uma referência estável.")
        if ingredient_ref in seen_refs:
            raise _invalid(f"{path}.ref", "A referência da participação precisa ser única na fórmula.")
        seen_refs.add(ingredient_ref)
        role = ingredient.get("role")
        if role is not None and role not in ROLES:
            raise _invalid(f"{path}.role", f"Papel desconhecido; use um de: {', '.join(ROLES)}.")
        ref = ingredient.get("recipe_version_ref", "")
        if not isinstance(ref, str):
            raise _invalid(f"{path}.recipe_version_ref", "A versão da receita precisa ser uma referência textual.")
        composition = ingredient.get("composition")
        if composition not in COMPOSITIONS:
            raise _invalid(f"{path}.composition", "Composição desconhecida; use additional ou included.")
        if composition == "included" and not ref.strip():
            raise _invalid(f"{path}.composition", "Composição inclusa exige a versão da receita do ingrediente.")

        spec = ingredient.get("quantity")
        if not isinstance(spec, dict):
            raise _invalid(f"{path}.quantity", "A quantidade precisa declarar kind, target e seus limites.")
        kind = spec.get("kind")
        if kind not in QUANTITY_KINDS:
            raise _invalid(f"{path}.quantity.kind", "Use fixed ou ratio.")
        target = _require_positive(spec.get("target"), f"{path}.quantity.target")
        minimum = None
        maximum = None
        if spec.get("minimum") not in (None, ""):
            minimum = _require_positive(spec.get("minimum"), f"{path}.quantity.minimum", allow_zero=True)
            if minimum > target:
                raise _invalid(f"{path}.quantity.minimum", "O mínimo não pode superar o alvo.")
        if spec.get("maximum") not in (None, ""):
            maximum = _require_positive(spec.get("maximum"), f"{path}.quantity.maximum")
            if maximum < target:
                raise _invalid(f"{path}.quantity.maximum", "O máximo não pode ficar abaixo do alvo.")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise _invalid(f"{path}.quantity", "O mínimo não pode superar o máximo.")
        if kind == "fixed":
            unit = normalize_unit(spec.get("unit") or "g")
            if unit not in UNITS:
                raise _invalid(f"{path}.quantity.unit", f"Unidade desconhecida; use uma de: {', '.join(UNITS)}.")
        else:
            basis = spec.get("basis")
            if not isinstance(basis, dict) or basis.get("kind") not in BASIS_KINDS:
                raise _invalid(f"{path}.quantity.basis", "A base precisa ser flour, total ou ingredient.")
            if basis.get("kind") == "ingredient" and not str(basis.get("sku") or "").strip():
                raise _invalid(f"{path}.quantity.basis.sku", "A base por ingrediente precisa do SKU.")
        for optional in ("grams_per_unit", "density_g_per_ml"):
            if ingredient.get(optional) not in (None, ""):
                _require_positive(ingredient.get(optional), f"{path}.{optional}")
        if ingredient.get("note") is not None and not isinstance(ingredient.get("note"), str):
            raise _invalid(f"{path}.note", "A anotação do ingrediente precisa ser texto.")
