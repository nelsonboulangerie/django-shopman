"""Venda por peso no balcão: o que o operador tem em mãos vira QUANTIDADE.

O queijo fracionado chega à vitrine pesado e etiquetado à mão: a etiqueta tem o
peso e o valor. O operador digita o VALOR da etiqueta e o PDV deriva o peso pelo
preço por quilo do CATÁLOGO — que não muda na venda. Com uma balança no balcão, a
loja pode ligar a entrada pelo PESO (:func:`weight_entry_enabled`); desligada por
padrão, porque hoje a pesagem é manual e antecipada e o que o operador lê é o
valor impresso.

Por que isto não é o ``price_override`` que saiu (ver ``pos._approval_reasons``):
o valor digitado nunca vira preço. Ele vira **peso** (a quantidade da linha), e
o kernel precifica esse peso como precifica qualquer linha — preço do catálogo,
"maior desconto ganha", limite de desconto da loja. Não há campo de preço que o
operador escreva; se o valor da etiqueta vier maior do que o peso vale, a linha
cobra o que o peso vale, nunca o que foi digitado.

Contrato do produto: ``Product.unit == "kg"`` é "vendido por peso", e então o
MESMO preço do catálogo (``base_price_q`` ou o preço do listing do canal) é o
preço **do quilo**. Sem ele, o produto não vende: nenhum canal vende item com
preço zero (ver ``shop/rules/validation.PricedItemsRule``). Zerar uma venda é
desconto de 100%, pela régua de desconto.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from shopman.utils.monetary import format_money, monetary_mult

WEIGHT_UNIT = "kg"
ENTRY_LABEL = "label"
ENTRY_WEIGHT = "weight"
ENTRIES = (ENTRY_LABEL, ENTRY_WEIGHT)

#: Teto de sanidade de uma peça pesada no balcão. Acima disso é dedo no zero a
#: mais (3120 g digitado como 31200), e o fechamento cobraria dez vezes.
MAX_WEIGHT_G = 20_000

_GRAMS_PER_KG = 1000
_QTY_PLACES = Decimal("0.001")


def is_sold_by_weight(unit: str | None) -> bool:
    """O produto é vendido por peso (preço por quilo, quantidade em kg)?"""
    return str(unit or "").strip().lower() == WEIGHT_UNIT


def weight_entry_enabled() -> bool:
    """A loja deixa o operador digitar o PESO (além do valor da etiqueta)?

    ``Shop.defaults["pos"]["weighed_weight_entry"]`` — ``True`` quando há balança
    no balcão. Ausente/qualquer outro valor = desligado: o PDV só pede o valor da
    etiqueta e a opção "Peso" nem aparece. Por LOJA, não por terminal: a balança
    é equipamento do balcão, e uma chave só evita dois PDVs da mesma loja
    discordando sobre o que o operador pode digitar.
    """
    from shopman.shop.models import Shop

    shop = Shop.load()
    pos_cfg = (shop.defaults or {}).get("pos") if shop else None
    return isinstance(pos_cfg, dict) and pos_cfg.get("weighed_weight_entry") is True


def kg_display(weight_g: int) -> str:
    """``312`` → ``"0,312 kg"`` — a grafia da etiqueta e da tela."""
    return f"{int(weight_g) / _GRAMS_PER_KG:.3f}".replace(".", ",") + " kg"


def qty_for_grams(weight_g: int) -> Decimal:
    """Gramas → quantidade da linha em kg, com as 3 casas do ``SessionItem.qty``."""
    return (Decimal(int(weight_g)) / _GRAMS_PER_KG).quantize(_QTY_PLACES)


def total_for_grams(weight_g: int, price_per_kg_q: int) -> int:
    """O que o peso vale — a MESMA conta do kernel (``monetary_mult``, meio para cima)."""
    return monetary_mult(qty_for_grams(weight_g), int(price_per_kg_q))


def grams_for_label(label_q: int, price_per_kg_q: int) -> int:
    """O MAIOR peso, em gramas, cujo valor não passa do valor da etiqueta.

    A quantidade tem 3 casas (a grama), então nem todo valor em centavos tem um
    peso exato: a R$ 89,90/kg cada grama vale ~9 centavos. Quando a etiqueta foi
    feita com o mesmo preço do quilo, a grama que ela pesou reproduz o valor
    exato (a conta é a mesma: peso × preço, arredondado). Quando não reproduz,
    o preço do quilo da balança é outro — e a escolha é para BAIXO: o cliente
    nunca paga mais que o valor impresso na embalagem, e a diferença (menos de
    uma grama de preço) aparece na tela, não some.

    Conta: ``round_half_up(g × p / 1000) ≤ V``  ⇔  ``g × p < 1000·V + 500``.
    """
    price = int(price_per_kg_q)
    if price <= 0:
        raise ValueError("preço por quilo precisa ser positivo")
    return (int(label_q) * _GRAMS_PER_KG + _GRAMS_PER_KG // 2 - 1) // price


@dataclass(frozen=True)
class WeighedLine:
    """Uma linha de venda por peso resolvida: peso, preço do quilo e valor."""

    entry: str
    weight_g: int
    price_per_kg_q: int
    total_q: int
    label_q: int | None = None

    @property
    def qty(self) -> Decimal:
        return qty_for_grams(self.weight_g)

    @property
    def label_gap_q(self) -> int:
        """Quanto a linha ficou ABAIXO da etiqueta (0 quando bate ou quando veio o peso)."""
        if self.label_q is None:
            return 0
        return max(0, self.label_q - self.total_q)

    def as_meta(self) -> dict:
        """O registro da linha em ``meta["weighed"]`` (ver data-schemas.md)."""
        meta = {
            "entry": self.entry,
            "weight_g": self.weight_g,
            "price_per_kg_q": self.price_per_kg_q,
            "total_q": self.total_q,
        }
        if self.label_q is not None:
            meta["label_q"] = self.label_q
        return meta


class WeighedEntryError(ValueError):
    """O que o operador digitou não vira uma linha de peso. ``code`` é estável."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def resolve(
    *,
    name: str,
    entry: str,
    price_per_kg_q: int,
    label_q: int | None = None,
    weight_g: int | None = None,
) -> WeighedLine:
    """Etiqueta (R$) ou peso (g) → a linha, pelo preço do quilo do catálogo."""
    price = int(price_per_kg_q or 0)
    if price <= 0:
        raise WeighedEntryError(
            "price_missing",
            f"{name} está sem preço do quilo no cadastro. Cadastre o preço do quilo para vender.",
        )
    if entry == ENTRY_LABEL:
        value_q = int(label_q or 0)
        if value_q <= 0:
            raise WeighedEntryError("weight_label_required", f"Informe o valor da etiqueta de {name}.")
        grams = grams_for_label(value_q, price)
        if grams <= 0:
            raise WeighedEntryError(
                "weight_label_below_one_gram",
                f"R$ {format_money(value_q)} não chega a 1 g de {name} "
                f"(R$ {format_money(price)}/kg). Confira o valor da etiqueta.",
            )
    elif entry == ENTRY_WEIGHT:
        grams = int(weight_g or 0)
        value_q = None
        if grams <= 0:
            raise WeighedEntryError("weight_grams_required", f"Informe o peso de {name}.")
    else:
        raise WeighedEntryError("weight_entry_invalid", "Informe o valor da etiqueta.")
    if grams > MAX_WEIGHT_G:
        raise WeighedEntryError(
            "weight_too_large",
            f"{kg_display(grams)} de {name} passa do máximo de "
            f"{MAX_WEIGHT_G // _GRAMS_PER_KG} kg por peça. Confira o que foi digitado.",
        )
    return WeighedLine(
        entry=entry,
        weight_g=grams,
        price_per_kg_q=price,
        total_q=total_for_grams(grams, price),
        label_q=value_q,
    )


def price_per_kg_q(sku: str, channel) -> int:
    """O preço do quilo que a VITRINE do canal mostra: listing do canal, ou o base.

    Sem cliente de propósito. O valor da etiqueta é convertido em PESO, e peso é
    físico: a balança usou o preço da casa, não o da faixa de um cliente. A faixa
    (e todo desconto) entra depois, quando o kernel precifica o peso.
    """
    from shopman.shop.handlers.pricing import OffermanPricingBackend

    return int(OffermanPricingBackend().get_price(sku, channel, qty=Decimal(1)) or 0)


def apply_to_payload(payload: dict, *, channel) -> None:
    """Resolve, no payload do PDV já parseado, toda linha de produto vendido por peso.

    Escreve na linha ``qty`` (kg, 3 casas), ``unit_price_q`` (o preço do quilo) e
    ``weighed`` (o registro completo). Recusa com ``PosIntentError``: produto por
    peso sem valor da etiqueta, peso digitado com a entrada por peso desligada, e
    peso informado para produto por unidade.
    """
    from shopman.offerman.models import Product

    from shopman.shop.services.pos_intent import PosIntentError

    items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
    if not items:
        return
    units = dict(
        Product.objects.filter(sku__in={str(item.get("sku") or "") for item in items}).values_list("sku", "unit")
    )
    by_weight_allowed: bool | None = None
    for idx, item in enumerate(items):
        sku = str(item.get("sku") or "")
        name = str(item.get("name") or sku)
        declared = item.get("weighed")
        field = f"items.{idx}.weighed"
        if not is_sold_by_weight(units.get(sku)):
            if declared:
                raise PosIntentError(
                    code="not_sold_by_weight",
                    message=f"{name} é vendido por unidade, não por peso.",
                    field=field,
                    focus="cart",
                )
            continue
        if not declared:
            raise PosIntentError(
                code="weight_entry_required",
                message=f"{name} é vendido por peso: informe o valor da etiqueta.",
                field=field,
                focus="cart",
            )
        entry = declared.get("entry", "")
        if entry == ENTRY_WEIGHT:
            if by_weight_allowed is None:
                by_weight_allowed = weight_entry_enabled()
            if not by_weight_allowed:
                raise PosIntentError(
                    code="weight_entry_disabled",
                    message=f"Esta loja lança {name} pelo valor da etiqueta, não pelo peso.",
                    field=field,
                    focus="cart",
                )
        try:
            line = resolve(
                name=name,
                entry=entry,
                price_per_kg_q=price_per_kg_q(sku, channel),
                label_q=declared.get("label_q"),
                weight_g=declared.get("weight_g"),
            )
        except WeighedEntryError as exc:
            raise PosIntentError(code=exc.code, message=exc.message, field=field, focus="cart") from exc
        item["qty"] = line.qty
        item["unit_price_q"] = line.price_per_kg_q
        item["weighed"] = line.as_meta()


def qty_number(value) -> int | float:
    """Quantidade para JSON de TELA: inteiro quando inteira, fração quando pesada."""
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        # Tela nunca quebra por quantidade malformada.
        return 1
    if not qty.is_finite():
        return 1
    return int(qty) if qty == qty.to_integral_value() else float(qty)


__all__ = [
    "ENTRY_LABEL",
    "ENTRY_WEIGHT",
    "MAX_WEIGHT_G",
    "WeighedEntryError",
    "WeighedLine",
    "apply_to_payload",
    "grams_for_label",
    "is_sold_by_weight",
    "kg_display",
    "price_per_kg_q",
    "qty_for_grams",
    "qty_number",
    "resolve",
    "total_for_grams",
    "weight_entry_enabled",
]
