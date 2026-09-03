"""Porcentagem do padeiro: a matemática pura da fórmula de uma receita.

Módulo sem Django. Recebe a ``formula`` de uma ``RecipeVersion`` (schema na
``docs/plans/RECIPE-INVENTORY-PLAN.md`` §3) e responde, só com ``Decimal``:

* :func:`classify_ingredient` / :func:`looks_like_flour` — o papel (``role``) de
  um ingrediente pelo nome e pelo SKU, em pt/en/fr/ja, sem acento e sem caixa;
* :func:`item_grams` — quanto pesa um item da fórmula, em grama, ou ``None``
  quando a física não deixa saber (contagem sem ``grams_per_unit``);
* :func:`analyze` — âncora, porcentagens, hidratação, sal, fermento, farinha
  pré-fermentada, **mistura final** (base menos o que já está nas partes) e o
  **BOM de consumo** (mistura final + partes prontas), com avisos;
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
PART_KINDS = ("preferment", "autolyse", "soaker", "old_dough")
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
    (
        "yeast",
        ("fermento", "levure", "yeast", "levain", "sourdough", "levedura", "lievito"),
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

_PREFERMENT_NAMES = ("levain", "sourdough", "poolish", "biga", "fermento", "starter", "esponja", "sponge")
_AUTOLYSE_NAMES = ("autoliz", "autolys")
_SOAKER_NAMES = ("yudane", "tangzhong", "escald", "soaker", "mingau")


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
    """Papel do ingrediente pelo nome e pelo SKU (``FARINHA-T55`` também conta)."""
    text = normalize_text(f"{name} {str(sku or '').replace('-', ' ').replace('_', ' ')}")
    if not text:
        return "other"
    for role, latin, cjk in _ROLE_KEYWORDS:
        if _matches(text, latin, cjk):
            return role
    return "other"


def looks_like_flour(name: str, sku: str = "") -> bool:
    """``True`` quando o ingrediente conta como farinha para a âncora e a hidratação."""
    return classify_ingredient(name, sku) == "flour"


def part_kind_from_name(*names: str) -> str:
    """``kind`` de uma parte pelo que ela se chama (nome, ref, SKU)."""
    text = normalize_text(" ".join(str(n or "") for n in names))
    if any(word in text for word in _AUTOLYSE_NAMES):
        return "autolyse"
    if any(word in text for word in _SOAKER_NAMES):
        return "soaker"
    return "preferment"


def part_reference_key(part: dict) -> str:
    """Chave da faixa de referência de uma parte (levain, poolish, biga, ...)."""
    kind = str(part.get("kind") or "preferment")
    if kind != "preferment":
        return kind
    text = normalize_text(f"{part.get('name', '')} {part.get('entry_ref', '')} {part.get('sku', '')}")
    if "poolish" in text:
        return "poolish"
    if "biga" in text:
        return "biga"
    return "levain"


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
    """Massa do item em grama, ou ``None`` quando não dá para saber.

    Massa converte pela física. Volume passa pela ``density_g_per_ml`` do item;
    sem densidade, líquido (``role="liquid"``) assume 1,0 e o resto fica sem
    resposta. Contagem só entra com ``grams_per_unit``.
    """
    quantity = to_decimal(item.get("quantity"))
    if quantity is None:
        return None
    unit = normalize_unit(item.get("unit") or "g")
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
    """Um ingrediente com o peso em grama e a porcentagem sobre a âncora."""

    sku: str
    name: str
    role: str
    quantity: Decimal
    unit: str
    grams: Decimal | None
    pct: Decimal | None


@dataclass(frozen=True)
class FormulaPartAnalysis:
    """Uma parte resolvida: quanto pesa e quanta farinha da base leva."""

    sku: str
    entry_ref: str
    kind: str
    name: str
    quantity_g: Decimal | None
    unit: str
    flour_pct: Decimal | None
    flour_g: Decimal
    cap_pct: Decimal | None
    has_formula: bool
    contents: tuple[FormulaItemAnalysis, ...] = ()


@dataclass(frozen=True)
class FormulaAnalysis:
    """A fórmula lida pela lente do padeiro."""

    anchor_kind: str
    anchor_total_g: Decimal | None
    total_mass_g: Decimal
    items: tuple[FormulaItemAnalysis, ...]
    hydration_pct: Decimal | None
    salt_pct: Decimal | None
    yeast_pct: Decimal | None
    prefermented_flour_pct: Decimal | None
    fat_pct: Decimal | None
    sugar_pct: Decimal | None
    egg_pct: Decimal | None
    final_mix: tuple[FormulaItemAnalysis, ...]
    final_mix_at_cap: tuple[FormulaItemAnalysis, ...]
    bom: tuple[dict, ...]
    parts: tuple[FormulaPartAnalysis, ...]
    old_dough_cap_pct: Decimal | None
    warnings: tuple[FormulaWarning, ...] = field(default_factory=tuple)

    def metrics(self) -> dict[str, Decimal | None]:
        return {
            "hydration_pct": self.hydration_pct,
            "salt_pct": self.salt_pct,
            "yeast_pct": self.yeast_pct,
            "prefermented_flour_pct": self.prefermented_flour_pct,
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


def _read_items(items: list[dict], warnings: list[FormulaWarning]) -> list[dict]:
    """Itens da base com ``grams`` resolvidos e avisos de física."""
    read: list[dict] = []
    for index, raw in enumerate(items):
        quantity = to_decimal(raw.get("quantity")) or _ZERO
        unit = normalize_unit(raw.get("unit") or "g")
        role = str(raw.get("role") or "") or classify_ingredient(raw.get("name", ""), raw.get("sku", ""))
        item = {**raw, "quantity": quantity, "unit": unit, "role": role}
        grams = item_grams(item)
        label = str(raw.get("name") or raw.get("sku") or f"item {index + 1}")
        if grams is None:
            if unit == "un":
                warnings.append(FormulaWarning(
                    "COUNT_WITHOUT_GRAMS_PER_UNIT",
                    f"{label}: contagem sem peso por unidade fica fora da conta.",
                    metric=f"items[{index}]",
                ))
            elif unit in _ML_PER_UNIT:
                warnings.append(FormulaWarning(
                    "VOLUME_WITHOUT_DENSITY",
                    f"{label}: volume sem densidade declarada fica fora da conta.",
                    metric=f"items[{index}]",
                ))
        elif unit in _ML_PER_UNIT and to_decimal(raw.get("density_g_per_ml")) in (None, _ZERO) and role == "liquid":
            warnings.append(FormulaWarning(
                "LIQUID_DENSITY_ASSUMED",
                f"{label}: volume de líquido sem densidade; assumido 1,0 g/ml.",
                metric=f"items[{index}]",
            ))
        item["grams"] = grams
        item["key"] = _item_key(raw)
        read.append(item)
    return read


def _role_total(items: list[dict], role: str) -> Decimal:
    return sum((it["grams"] for it in items if it["role"] == role and it["grams"] is not None), _ZERO)


def _to_analysis_item(item: dict, anchor: Decimal | None, *, grams: Decimal | None = None,
                      quantity: Decimal | None = None) -> FormulaItemAnalysis:
    grams_value = item["grams"] if grams is None else grams
    quantity_value = item["quantity"] if quantity is None else quantity
    return FormulaItemAnalysis(
        sku=str(item.get("sku") or ""),
        name=str(item.get("name") or item.get("sku") or ""),
        role=item["role"],
        quantity=quantize(quantity_value),
        unit=item["unit"],
        grams=None if grams_value is None else quantize(grams_value),
        pct=_pct(grams_value, anchor),
    )


def _part_composition(part_formula: dict) -> tuple[list[dict], Decimal, Decimal]:
    """Itens da parte com grama, total em grama e farinha em grama."""
    ignored: list[FormulaWarning] = []
    items = [it for it in _read_items(list(part_formula.get("items") or []), ignored) if it["grams"] is not None]
    total = sum((it["grams"] for it in items), _ZERO)
    flour = _role_total(items, "flour")
    return items, total, flour


def analyze(formula: dict, part_formulas: dict[str, dict] | None = None) -> FormulaAnalysis:
    """Lê a fórmula: âncora, porcentagens, métricas, mistura final e BOM.

    ``part_formulas`` mapeia o ``sku`` de cada parte para a ``formula`` da
    versão atual da receita da parte (o serviço monta com ``part_formulas_for``).
    Parte sem fórmula fica na base e sai com aviso ``PART_WITHOUT_FORMULA``.
    """
    part_formulas = part_formulas or {}
    warnings: list[FormulaWarning] = []
    base = _read_items(list(formula.get("items") or []), warnings)
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

    items = tuple(_to_analysis_item(it, anchor_total) for it in base)

    # Mistura final: começa igual à base e vai perdendo o que as partes levam.
    remaining: dict[str, Decimal | None] = {it["key"]: it["grams"] for it in base}
    base_by_key = {it["key"]: it for it in base}
    parts: list[FormulaPartAnalysis] = []
    prefermented_flour = _ZERO
    old_dough_cap: Decimal | None = None

    for index, raw_part in enumerate(list(formula.get("parts") or [])):
        kind = str(raw_part.get("kind") or "preferment")
        if kind == "old_dough":
            old_dough_cap = to_decimal(raw_part.get("cap_pct"))
            parts.append(FormulaPartAnalysis(
                sku="", entry_ref="", kind=kind, name=str(raw_part.get("name") or "Massa velha"),
                quantity_g=None, unit="g", flour_pct=None, flour_g=_ZERO, cap_pct=old_dough_cap,
                has_formula=False,
            ))
            continue

        sku = str(raw_part.get("sku") or "")
        name = str(raw_part.get("name") or sku)
        unit = normalize_unit(raw_part.get("unit") or "g")
        declared_pct = to_decimal(raw_part.get("flour_pct"))
        declared_quantity = to_decimal(raw_part.get("quantity"))
        part_formula = part_formulas.get(sku)

        if not part_formula:
            warnings.append(FormulaWarning(
                "PART_WITHOUT_FORMULA",
                f"{name}: a parte não tem fórmula conhecida e ficou na base.",
                metric=f"parts[{index}]",
            ))
            parts.append(FormulaPartAnalysis(
                sku=sku, entry_ref=str(raw_part.get("entry_ref") or ""), kind=kind, name=name,
                quantity_g=None if declared_quantity is None else _grams_of(declared_quantity, unit),
                unit=unit, flour_pct=declared_pct, flour_g=_ZERO, cap_pct=None, has_formula=False,
            ))
            continue

        composition, part_total, part_flour = _part_composition(part_formula)
        flour_fraction = (part_flour / part_total) if part_total > 0 else _ZERO

        quantity_g: Decimal | None = None
        if anchor_kind == "flour" and declared_pct is not None and anchor_total:
            if flour_fraction > 0:
                quantity_g = (declared_pct / _HUNDRED * anchor_total) / flour_fraction
                declared_g = None if declared_quantity is None else _grams_of(declared_quantity, unit)
                if declared_g and abs(quantity_g - declared_g) <= declared_g * _SAME_DECLARATION_TOLERANCE:
                    # A quantidade declarada é a mesma declaração da porcentagem,
                    # escrita com mais casas: ela vence, e a conta fecha exata.
                    quantity_g = declared_g
            else:
                warnings.append(FormulaWarning(
                    "PART_WITHOUT_FLOUR",
                    f"{name}: a parte não tem farinha; o tamanho veio da quantidade declarada.",
                    metric=f"parts[{index}]",
                ))
        if quantity_g is None and declared_quantity is not None:
            quantity_g = _grams_of(declared_quantity, unit)
        if quantity_g is None or part_total <= 0:
            warnings.append(FormulaWarning(
                "PART_WITHOUT_SIZE",
                f"{name}: sem porcentagem de farinha nem quantidade; a parte ficou na base.",
                metric=f"parts[{index}]",
            ))
            parts.append(FormulaPartAnalysis(
                sku=sku, entry_ref=str(raw_part.get("entry_ref") or ""), kind=kind, name=name,
                quantity_g=None, unit=unit, flour_pct=declared_pct, flour_g=_ZERO, cap_pct=None,
                has_formula=True,
            ))
            continue

        contents: list[FormulaItemAnalysis] = []
        part_flour_g = _ZERO
        for component in composition:
            contained = component["grams"] / part_total * quantity_g
            key = component["key"]
            if component["role"] == "flour":
                part_flour_g += contained
            available = remaining.get(key)
            if key not in base_by_key or available is None:
                warnings.append(FormulaWarning(
                    "PART_EXCEEDS_BASE",
                    f"{name} leva {component.get('name') or component.get('sku')}, que a base não declara.",
                    metric=f"parts[{index}]",
                ))
            elif contained > available + Decimal("0.0005"):
                warnings.append(FormulaWarning(
                    "PART_EXCEEDS_BASE",
                    f"{name} leva mais {component.get('name') or component.get('sku')} do que a base tem.",
                    metric=f"parts[{index}]",
                    value=quantize(contained), high=quantize(available),
                ))
                remaining[key] = _ZERO
            else:
                remaining[key] = available - contained
            contents.append(_to_analysis_item(
                {**component, "unit": "g"}, anchor_total, grams=contained, quantity=contained,
            ))

        if kind == "preferment":
            prefermented_flour += part_flour_g
        parts.append(FormulaPartAnalysis(
            sku=sku, entry_ref=str(raw_part.get("entry_ref") or ""), kind=kind, name=name,
            quantity_g=quantize(quantity_g), unit=unit,
            flour_pct=_pct(part_flour_g, anchor_total) if anchor_kind == "flour" else declared_pct,
            flour_g=quantize(part_flour_g), cap_pct=None, has_formula=True, contents=tuple(contents),
        ))

    final_mix = tuple(
        _final_mix_item(it, remaining[it["key"]], anchor_total)
        for it in base
    )
    factor_at_cap = Decimal(1) - (old_dough_cap / _HUNDRED) if old_dough_cap else Decimal(1)
    final_mix_at_cap = tuple(
        _final_mix_item(it, None if remaining[it["key"]] is None else remaining[it["key"]] * factor_at_cap, anchor_total)
        for it in base
    )

    bom = tuple(_bom_items(base, remaining, parts, total_mass, old_dough_cap))

    metrics_on = anchor_kind == "flour" and anchor_total is not None and anchor_total > 0
    return FormulaAnalysis(
        anchor_kind=anchor_kind,
        anchor_total_g=None if anchor_total is None else quantize(anchor_total),
        total_mass_g=quantize(total_mass),
        items=items,
        hydration_pct=_pct(_role_total(base, "liquid"), anchor_total) if metrics_on else None,
        salt_pct=_pct(_role_total(base, "salt"), anchor_total) if metrics_on else None,
        yeast_pct=_pct(_role_total(base, "yeast"), anchor_total) if metrics_on else None,
        prefermented_flour_pct=_pct(prefermented_flour, anchor_total) if metrics_on else None,
        fat_pct=_pct(_role_total(base, "fat"), anchor_total) if metrics_on else None,
        sugar_pct=_pct(_role_total(base, "sugar"), anchor_total) if metrics_on else None,
        egg_pct=_pct(_role_total(base, "egg"), anchor_total) if metrics_on else None,
        final_mix=final_mix,
        final_mix_at_cap=final_mix_at_cap,
        bom=bom,
        parts=tuple(parts),
        old_dough_cap_pct=old_dough_cap,
        warnings=tuple(warnings),
    )


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


def _bom_items(base: list[dict], remaining: dict, parts: list[FormulaPartAnalysis],
               total_mass: Decimal, old_dough_cap: Decimal | None) -> list[dict]:
    bom: list[dict] = []
    for item in base:
        grams = remaining[item["key"]]
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
            "meta": {},
        })
    for part in parts:
        if part.kind == "old_dough":
            continue
        if not part.has_formula or part.quantity_g is None:
            continue
        factor = _GRAMS_PER_UNIT.get(part.unit, Decimal(1))
        bom.append({
            "sku": part.sku,
            "name": part.name,
            "role": part.kind,
            "quantity": quantize(part.quantity_g / factor),
            "unit": part.unit if part.unit in _GRAMS_PER_UNIT else "g",
            "is_optional": False,
            "meta": {},
        })
    if old_dough_cap:
        bom.append({
            "sku": "",
            "name": "Massa velha",
            "role": "old_dough",
            "quantity": quantize(total_mass * old_dough_cap / _HUNDRED) or quantize(Decimal("0.001")),
            "unit": "g",
            "is_optional": True,
            "meta": {"role": "old_dough", "cap_pct": number_text(old_dough_cap)},
        })
    return bom


def derive_bom(formula: dict, part_formulas: dict[str, dict] | None = None) -> list[dict]:
    """Itens prontos para virar ``RecipeItem``: ``{sku, name, role, quantity, unit, is_optional, meta}``.

    A massa velha sai com ``is_optional=True`` e ``meta={"role": "old_dough",
    "cap_pct": ...}`` e ``sku=""``: quem publica troca o SKU pelo da própria
    receita. Avisos moram em :func:`analyze`; aqui só a lista.
    """
    return list(analyze(formula, part_formulas).bom)


# ── Escala e padronização ────────────────────────────────────────────────────


def scale(formula: dict, factor: Decimal | int | str) -> dict:
    """A fórmula inteira multiplicada por ``factor``; porcentagens ficam."""
    ratio = to_decimal(factor)
    if ratio is None or ratio <= 0:
        raise RecipeBookError("FORMULA_INVALID", field="factor", message="O fator de escala precisa ser positivo.")
    scaled = {**formula, "items": [], "parts": [], "basis_g": None, "standardized": False}
    for item in list(formula.get("items") or []):
        quantity = to_decimal(item.get("quantity")) or _ZERO
        scaled["items"].append({**item, "quantity": number_text(quantity * ratio)})
    for part in list(formula.get("parts") or []):
        copy = dict(part)
        quantity = to_decimal(part.get("quantity"))
        if quantity is not None:
            copy["quantity"] = number_text(quantity * ratio)
        scaled["parts"].append(copy)
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


def _range(low, high, maximum=None, note="") -> dict:
    return {
        "low": None if low is None else Decimal(str(low)),
        "high": None if high is None else Decimal(str(high)),
        "max": None if maximum is None else Decimal(str(maximum)),
        "note": note,
    }


#: Faixas por métrica; dentro, por ``kind`` da receita (``"*"`` vale para todas)
#: ou, em ``part_flour_pct``, por tipo de parte. Fonte: Hamelman *Bread*, Suas
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
    "prefermented_flour_pct": {
        "bread": _range("15", "40", "60", "Levain 15 a 30; poolish 20 a 40; biga 30 a 50."),
        "viennoiserie": _range("0", "30", "40", "Pré-fermento em massa enriquecida costuma ser menor."),
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
    "part_flour_pct": {
        "levain": _range("15", "30", "40", "Farinha pré-fermentada no levain."),
        "poolish": _range("20", "40", "50", "Farinha pré-fermentada no poolish."),
        "biga": _range("30", "50", "60", "Farinha pré-fermentada na biga."),
        "soaker": _range("10", "20", "30", "Yudane e tangzhong."),
        "old_dough": _range("15", "25", "30", "Massa velha, sobre a fórmula inteira."),
        "autolyse": _range("0", "100", "100", "Autólise pode levar toda a farinha."),
    },
}

_ALWAYS_CHECKED = ("hydration_pct", "salt_pct")

_METRIC_LABELS = {
    "hydration_pct": "Hidratação",
    "salt_pct": "Sal",
    "yeast_pct": "Fermento",
    "prefermented_flour_pct": "Farinha pré-fermentada",
    "fat_pct": "Gordura",
    "sugar_pct": "Açúcar",
    "egg_pct": "Ovos",
}


def reference_for(metric: str, kind: str) -> dict | None:
    """A faixa de ``metric`` para o ``kind`` da receita, ou ``None`` se não há."""
    table = REFERENCE_RANGES.get(metric) or {}
    return table.get(kind) or table.get(_ALL)


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
    """Compara as métricas (e a farinha de cada parte) com a literatura. Nunca bloqueia."""
    out: list[FormulaWarning] = []
    if analysis.anchor_kind != "flour":
        return out
    for metric, value in analysis.metrics().items():
        # Ausente não é errado: pão de levain não leva fermento, massa magra não
        # leva açúcar. Só hidratação e sal em zero merecem aviso.
        if value == _ZERO and metric not in _ALWAYS_CHECKED:
            continue
        _check_value("REFERENCE", _METRIC_LABELS[metric], metric, value, reference_for(metric, kind), out)
    for part in analysis.parts:
        if part.kind == "old_dough":
            _check_value("REFERENCE", f"Massa velha ({part.name})", "part_flour_pct", part.cap_pct,
                         REFERENCE_RANGES["part_flour_pct"].get("old_dough"), out)
            continue
        key = part_reference_key({"kind": part.kind, "name": part.name, "entry_ref": part.entry_ref, "sku": part.sku})
        _check_value("REFERENCE", f"Farinha na parte {part.name}", "part_flour_pct", part.flour_pct,
                     REFERENCE_RANGES["part_flour_pct"].get(key), out)
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

    items = formula.get("items")
    if not isinstance(items, list):
        raise _invalid("items", "Os ingredientes precisam ser uma lista.")
    for index, item in enumerate(items):
        path = f"items[{index}]"
        if not isinstance(item, dict):
            raise _invalid(path, "Cada ingrediente precisa ser um objeto.")
        sku = item.get("sku", "")
        name = item.get("name", "")
        if not isinstance(sku, str) or not isinstance(name, str):
            raise _invalid(f"{path}.name", "Nome e SKU precisam ser texto.")
        if not sku.strip() and not name.strip():
            raise _invalid(f"{path}.name", "Ingrediente sem nome e sem SKU.")
        role = item.get("role")
        if role is not None and role not in ROLES:
            raise _invalid(f"{path}.role", f"Papel desconhecido; use um de: {', '.join(ROLES)}.")
        _require_positive(item.get("quantity"), f"{path}.quantity")
        unit = normalize_unit(item.get("unit") or "g")
        if unit not in UNITS:
            raise _invalid(f"{path}.unit", f"Unidade desconhecida; use uma de: {', '.join(UNITS)}.")
        for optional in ("grams_per_unit", "density_g_per_ml"):
            if item.get(optional) not in (None, ""):
                _require_positive(item.get(optional), f"{path}.{optional}")

    parts = formula.get("parts", [])
    if parts is None:
        parts = []
    if not isinstance(parts, list):
        raise _invalid("parts", "As partes precisam ser uma lista.")
    old_dough_seen = False
    for index, part in enumerate(parts):
        path = f"parts[{index}]"
        if not isinstance(part, dict):
            raise _invalid(path, "Cada parte precisa ser um objeto.")
        kind = part.get("kind")
        if kind not in PART_KINDS:
            raise _invalid(f"{path}.kind", f"Tipo de parte desconhecido; use um de: {', '.join(PART_KINDS)}.")
        if kind == "old_dough":
            if old_dough_seen:
                raise _invalid(f"{path}.kind", "Só pode haver uma massa velha na fórmula.")
            old_dough_seen = True
            cap = _require_positive(part.get("cap_pct"), f"{path}.cap_pct")
            if cap >= 100:
                raise _invalid(f"{path}.cap_pct", "O teto da massa velha precisa ser menor que 100%.")
            continue
        sku = part.get("sku", "")
        if not isinstance(sku, str):
            raise _invalid(f"{path}.sku", "O SKU da parte precisa ser texto.")
        flour_pct = part.get("flour_pct")
        quantity = part.get("quantity")
        if flour_pct in (None, "") and quantity in (None, ""):
            raise _invalid(f"{path}.flour_pct", "A parte precisa de flour_pct ou de quantity.")
        if flour_pct not in (None, ""):
            pct = _require_positive(flour_pct, f"{path}.flour_pct")
            if pct > 100:
                raise _invalid(f"{path}.flour_pct", "A farinha da parte não pode passar de 100% da farinha total.")
        if quantity not in (None, ""):
            _require_positive(quantity, f"{path}.quantity")
        unit = normalize_unit(part.get("unit") or "g")
        if unit not in _GRAMS_PER_UNIT:
            raise _invalid(f"{path}.unit", "A parte é medida em massa (g ou kg).")
