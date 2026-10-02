"""Escolhas no produto: sabor obrigatório e adicionais com preço (Fase 1, 02/10/2026).

Dado, não código. O cadastro mora em ``Product.metadata["option_groups"]``
(escrito na aba "Escolhas" do Admin)::

    [{"ref": "adicionais", "label": "Adicionais", "min": 0, "max": 2,
      "options": [{"ref": "ovo", "label": "Ovo frito", "price_q": 400,
                   "available": true,
                   "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]}]}]

A escolha do cliente viaja como ``[{group, ref}]`` e nada mais: preço, nome e
insumo são relidos do catálogo aqui. A linha da sacola/comanda guarda o que foi
escolhido em ``meta["options"]`` (``group, group_label, ref, name, qty,
unit_price_q, consumes``), com o ``consumes`` CONGELADO no momento da venda: é o
registro do que a opção gasta, gravado e mostrado, sem baixar estoque na venda
(a baixa de insumo do item preparado na hora é decisão separada do dono).

O formato da linha é o mesmo que o iFood já grava (``ifood_orders._map_options``:
``name, group, qty, unit_price_q``), só que o iFood não tem ``ref``: opção sem
``ref`` não é desta casa, e quem reprecifica ou resume para a cozinha a ignora
(o preço do iFood é externo e a nota de preparo dele já vem pronta).

Decisões do dono (02/10): na NFC-e o adicional sai SOMADO ao item (uma linha,
preço unitário = produto + opções); o nome da linha leva o resumo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

OPTION_GROUPS_KEY = "option_groups"
CHOICE_GROUP_LABEL_KEY = "choice_group_label"
LINE_OPTIONS_KEY = "options"

_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


# ── Formato ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Option:
    ref: str
    label: str
    price_q: int
    available: bool
    consumes: tuple[dict, ...] = ()


@dataclass(frozen=True)
class OptionGroup:
    ref: str
    label: str
    min: int
    max: int
    options: tuple[Option, ...] = field(default_factory=tuple)

    def option(self, ref: str) -> Option | None:
        return next((option for option in self.options if option.ref == ref), None)


def _metadata(product_or_metadata) -> dict:
    if isinstance(product_or_metadata, dict):
        return product_or_metadata
    metadata = getattr(product_or_metadata, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _int(value, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value) -> str:
    return " ".join(str(value or "").split()) if isinstance(value, str) else ""


def _parse_consumes(raw) -> tuple[dict, ...]:
    if not isinstance(raw, list):
        return ()
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        sku = str(entry.get("sku") or "").strip()
        qty = str(entry.get("qty") or "").strip()
        unit = str(entry.get("unit") or "").strip()
        if sku and qty and unit:
            out.append({"sku": sku, "qty": qty, "unit": unit})
    return tuple(out)


def parse(product_or_metadata) -> list[OptionGroup]:
    """Os grupos do produto, TOLERANTE: o que estiver malformado fica de fora.

    Leitura de vitrine e de venda nunca explode por cadastro torto; quem barra o
    cadastro torto é :func:`validate_definition`, no Admin. Grupo sem opção
    válida some (um grupo obrigatório sem opção travaria o produto).
    """
    raw = _metadata(product_or_metadata).get(OPTION_GROUPS_KEY)
    if not isinstance(raw, list):
        return []
    groups: list[OptionGroup] = []
    seen_groups: set[str] = set()
    for raw_group in raw:
        if not isinstance(raw_group, dict):
            continue
        ref = str(raw_group.get("ref") or "").strip()
        label = _clean_text(raw_group.get("label"))
        if not ref or not label or ref in seen_groups:
            continue
        options: list[Option] = []
        seen_options: set[str] = set()
        for raw_option in raw_group.get("options") or []:
            if not isinstance(raw_option, dict):
                continue
            option_ref = str(raw_option.get("ref") or "").strip()
            option_label = _clean_text(raw_option.get("label"))
            price_q = _int(raw_option.get("price_q", 0), None)
            if not option_ref or not option_label or option_ref in seen_options or price_q is None or price_q < 0:
                continue
            seen_options.add(option_ref)
            options.append(Option(
                ref=option_ref,
                label=option_label,
                price_q=price_q,
                available=raw_option.get("available", True) is not False,
                consumes=_parse_consumes(raw_option.get("consumes")),
            ))
        if not options:
            continue
        minimum = max(0, _int(raw_group.get("min"), 0) or 0)
        maximum = _int(raw_group.get("max"), 1) or 1
        maximum = max(1, min(maximum, len(options)))
        minimum = min(minimum, maximum)
        seen_groups.add(ref)
        groups.append(OptionGroup(ref=ref, label=label, min=minimum, max=maximum, options=tuple(options)))
    return groups


def has_options(product) -> bool:
    return bool(parse(product))


def requires_choice(product) -> bool:
    """Algum grupo é obrigatório: o produto não entra na venda sem escolha."""
    return any(group.min > 0 for group in parse(product))


def public_groups(product) -> list[dict]:
    """O formato que a loja e o PDV leem. SEM ``consumes`` (insumo é da casa)."""
    return [
        {
            "ref": group.ref,
            "label": group.label,
            "min": group.min,
            "max": group.max,
            "options": [
                {"ref": option.ref, "label": option.label, "price_q": option.price_q, "available": option.available}
                for option in group.options
            ],
        }
        for group in parse(product)
    ]


def choice_group_label(product) -> str:
    """O rótulo do que se escolhe no Cartão de escolha ("Sabor"), ou ``""``."""
    return _clean_text(_metadata(product).get(CHOICE_GROUP_LABEL_KEY))


# ── Validação do cadastro (Admin) ─────────────────────────────────────────────


class OptionDefinitionError(ValueError):
    """O cadastro de escolhas tem problemas; ``messages`` lista cada um."""

    def __init__(self, messages: list[str]):
        super().__init__("; ".join(messages))
        self.messages = messages


def _recipe_units() -> dict[str, str]:
    from shopman.craftsman.models.recipe import RECIPE_ITEM_UNIT_VALUES
    from shopman.utils import units

    return {units.normalize(value): value for value in RECIPE_ITEM_UNIT_VALUES}


def _decimal_text(value) -> str | None:
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return format(number.normalize(), "f")


def validate_definition(raw: Any) -> list[dict]:
    """Confere e normaliza o cadastro de escolhas; levanta :class:`OptionDefinitionError`.

    Regras: grupo e opção com ``ref`` (minúsculas, números, ``-``/``_``) único e
    rótulo; ``0 <= min <= max <= nº de opções``; ``price_q`` inteiro ``>= 0``;
    cada ``consumes`` aponta um SKU que existe (``ComposedSkuValidator``: insumo
    do Compras ou produto), com quantidade positiva e unidade das fichas
    (``RECIPE_ITEM_UNIT_VALUES``) na mesma dimensão da unidade do cadastro.
    Devolve a lista normalizada, pronta para ``metadata["option_groups"]``.
    """
    from shopman.utils import units

    from shopman.shop.adapters.sku_validator import get_composed_sku_validator

    if raw in (None, "", []):
        return []
    if not isinstance(raw, list):
        raise OptionDefinitionError(["As escolhas são uma lista de grupos."])

    errors: list[str] = []
    recipe_units = _recipe_units()
    validator = get_composed_sku_validator()
    normalized: list[dict] = []
    group_refs: set[str] = set()

    for g_index, raw_group in enumerate(raw, start=1):
        where = f"Grupo {g_index}"
        if not isinstance(raw_group, dict):
            errors.append(f"{where}: formato inválido.")
            continue
        ref = str(raw_group.get("ref") or "").strip()
        label = _clean_text(raw_group.get("label"))
        if label:
            where = f"Grupo {label}"
        if not _REF_RE.match(ref):
            errors.append(f"{where}: o código (ref) usa só minúsculas, números, - e _.")
        elif ref in group_refs:
            errors.append(f"{where}: o código {ref} se repete.")
        group_refs.add(ref)
        if not label:
            errors.append(f"{where}: falta o nome do grupo.")
        raw_options = raw_group.get("options")
        if not isinstance(raw_options, list) or not raw_options:
            errors.append(f"{where}: precisa de pelo menos uma opção.")
            raw_options = []
        minimum = _int(raw_group.get("min", 0), None)
        maximum = _int(raw_group.get("max", 1), None)
        if minimum is None or minimum < 0:
            errors.append(f"{where}: mínimo inválido (0 = opcional).")
            minimum = 0
        if maximum is None or maximum < 1:
            errors.append(f"{where}: máximo precisa ser 1 ou mais.")
            maximum = 1
        if minimum > maximum:
            errors.append(f"{where}: o mínimo ({minimum}) passa do máximo ({maximum}).")
        if raw_options and maximum > len(raw_options):
            errors.append(f"{where}: o máximo ({maximum}) passa do número de opções ({len(raw_options)}).")

        options: list[dict] = []
        option_refs: set[str] = set()
        for o_index, raw_option in enumerate(raw_options, start=1):
            o_where = f"{where}, opção {o_index}"
            if not isinstance(raw_option, dict):
                errors.append(f"{o_where}: formato inválido.")
                continue
            o_ref = str(raw_option.get("ref") or "").strip()
            o_label = _clean_text(raw_option.get("label"))
            if o_label:
                o_where = f"{where}, opção {o_label}"
            if not _REF_RE.match(o_ref):
                errors.append(f"{o_where}: o código (ref) usa só minúsculas, números, - e _.")
            elif o_ref in option_refs:
                errors.append(f"{o_where}: o código {o_ref} se repete no grupo.")
            option_refs.add(o_ref)
            if not o_label:
                errors.append(f"{o_where}: falta o nome da opção.")
            price_q = _int(raw_option.get("price_q", 0), None)
            if price_q is None or price_q < 0:
                errors.append(f"{o_where}: preço em centavos, inteiro, 0 ou mais.")
                price_q = 0
            available = raw_option.get("available", True)
            if not isinstance(available, bool):
                errors.append(f"{o_where}: disponível é true ou false.")
                available = True

            consumes: list[dict] = []
            raw_consumes = raw_option.get("consumes", [])
            if raw_consumes in (None, ""):
                raw_consumes = []
            if not isinstance(raw_consumes, list):
                errors.append(f"{o_where}: o insumo (consumes) é uma lista.")
                raw_consumes = []
            for raw_entry in raw_consumes:
                if not isinstance(raw_entry, dict):
                    errors.append(f"{o_where}: insumo com formato inválido.")
                    continue
                sku = str(raw_entry.get("sku") or "").strip()
                qty = _decimal_text(raw_entry.get("qty"))
                unit = recipe_units.get(units.normalize(raw_entry.get("unit")))
                if not sku:
                    errors.append(f"{o_where}: insumo sem SKU.")
                    continue
                if qty is None:
                    errors.append(f"{o_where}: quantidade do insumo {sku} precisa ser maior que zero.")
                if unit is None:
                    errors.append(
                        f"{o_where}: unidade do insumo {sku} fora das unidades das fichas "
                        f"({', '.join(recipe_units.values())})."
                    )
                if not validator.validate_sku(sku).valid:
                    errors.append(f"{o_where}: o insumo {sku} não existe no cadastro.")
                elif unit is not None:
                    info = validator.get_sku_info(sku)
                    base_unit = getattr(info, "unit", "") if info is not None else ""
                    if base_unit and units.is_known(base_unit) and not units.same_dimension(unit, base_unit):
                        errors.append(
                            f"{o_where}: o insumo {sku} conta em {base_unit}; {unit} não converte para essa unidade."
                        )
                consumes.append({"sku": sku, "qty": qty or "", "unit": unit or ""})
            options.append({
                "ref": o_ref,
                "label": o_label,
                "price_q": price_q,
                "available": available,
                "consumes": consumes,
            })
        normalized.append({"ref": ref, "label": label, "min": minimum, "max": maximum, "options": options})

    if errors:
        raise OptionDefinitionError(errors)
    return normalized


# ── Escolha do cliente → linha ────────────────────────────────────────────────


class OptionSelectionError(ValueError):
    """A escolha não fecha com o cadastro. ``code`` é estável; ``message`` vai à tela.

    Códigos: ``option_required`` (grupo obrigatório sem escolha),
    ``option_unknown`` (grupo/opção que não existe, repetida, ou além do máximo),
    ``option_unavailable`` (opção existe mas está fora hoje).
    """

    def __init__(self, code: str, message: str, *, group: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.group = group


def _product_name(product) -> str:
    return str(getattr(product, "name", "") or getattr(product, "sku", "") or "")


def resolve_selection(product, selection) -> list[dict]:
    """Confere ``[{group, ref}]`` contra o cadastro ATUAL e devolve ``meta["options"]``.

    Cada opção da linha leva ``group, group_label, ref, name, qty, unit_price_q,
    consumes`` lidos do catálogo agora (o cliente nunca manda preço nem nome).
    A ordem é a do cadastro, para que a mesma escolha dê sempre a mesma linha.
    """
    groups = parse(product)
    if selection in (None, ""):
        selection = []
    if not isinstance(selection, list | tuple):
        raise OptionSelectionError("option_unknown", "Escolha inválida. Abra o item de novo.")

    chosen: dict[str, list[str]] = {}
    for entry in selection:
        if not isinstance(entry, dict):
            raise OptionSelectionError("option_unknown", "Escolha inválida. Abra o item de novo.")
        group_ref = str(entry.get("group") or "").strip()
        option_ref = str(entry.get("ref") or "").strip()
        group = next((candidate for candidate in groups if candidate.ref == group_ref), None)
        option = group.option(option_ref) if group else None
        if group is None or option is None:
            raise OptionSelectionError(
                "option_unknown",
                f"Uma das escolhas de {_product_name(product)} não existe mais. Abra o item e escolha de novo.",
                group=group_ref,
            )
        refs = chosen.setdefault(group.ref, [])
        if option.ref in refs:
            raise OptionSelectionError(
                "option_unknown", f"{option.label} foi escolhido duas vezes.", group=group.ref,
            )
        refs.append(option.ref)
        if not option.available:
            raise OptionSelectionError(
                "option_unavailable", f"{option.label} está indisponível.", group=group.ref,
            )

    resolved: list[dict] = []
    for group in groups:
        refs = chosen.get(group.ref, [])
        if len(refs) < group.min:
            raise OptionSelectionError(
                "option_required",
                f"Falta escolher {group.label} de {_product_name(product)}."
                if group.min == 1
                else f"Em {group.label}, escolha {group.min} opções.",
                group=group.ref,
            )
        if len(refs) > group.max:
            raise OptionSelectionError(
                "option_unknown",
                f"Em {group.label}, escolha até {group.max}.",
                group=group.ref,
            )
        for option in group.options:
            if option.ref in refs:
                resolved.append({
                    "group": group.ref,
                    "group_label": group.label,
                    "ref": option.ref,
                    "name": option.label,
                    "qty": 1,
                    "unit_price_q": option.price_q,
                    "consumes": [dict(entry) for entry in option.consumes],
                })
    return resolved


def line_options(line_or_meta) -> list[dict]:
    """As opções gravadas numa linha (dict de sessão, ``OrderItem`` ou ``meta``)."""
    if isinstance(line_or_meta, dict) and "meta" not in line_or_meta and LINE_OPTIONS_KEY in line_or_meta:
        raw = line_or_meta.get(LINE_OPTIONS_KEY)
    else:
        meta = line_or_meta.get("meta") if isinstance(line_or_meta, dict) else getattr(line_or_meta, "meta", None)
        raw = (meta or {}).get(LINE_OPTIONS_KEY) if isinstance(meta, dict) else None
    return [option for option in raw if isinstance(option, dict)] if isinstance(raw, list) else []


def own_options(options) -> list[dict]:
    """Só as opções desta casa (com ``ref``); as do iFood ficam de fora."""
    return [option for option in options or [] if isinstance(option, dict) and option.get("ref")]


def signature(options) -> str:
    """Identidade da escolha: ``"adicionais:ovo|sabor:cafe"`` (ou ``""``).

    Duas linhas do mesmo SKU com a mesma assinatura são a MESMA linha.
    """
    pairs = sorted(f"{option.get('group', '')}:{option.get('ref', '')}" for option in own_options(options))
    return "|".join(pairs)


def summary(options) -> str:
    """Resumo legível: ``"+ Ovo frito · Salada"`` (opção com preço leva ``+``)."""
    parts = []
    for option in own_options(options):
        name = _clean_text(option.get("name")) or str(option.get("ref"))
        qty = _int(option.get("qty"), 1) or 1
        text = f"{qty}× {name}" if qty > 1 else name
        if (_int(option.get("unit_price_q"), 0) or 0) > 0:
            text = f"+ {text}"
        parts.append(text)
    return " · ".join(parts)


def line_name(product_name: str, options) -> str:
    """Nome da linha: ``"Croque Monsieur (+ Ovo frito)"``; sem opção, o nome puro."""
    text = summary(options)
    return f"{product_name} ({text})" if text else product_name


def base_name(name: str, options) -> str:
    """O nome do produto sem o resumo que :func:`line_name` acrescentou."""
    text = summary(options)
    suffix = f" ({text})"
    if text and name.endswith(suffix):
        return name[: -len(suffix)]
    return name


def kitchen_note(meta) -> str:
    """A observação do card da cozinha: resumo das escolhas + a nota do item.

    Não grava nada: o resumo é derivado de ``meta["options"]`` a cada leitura, e
    ``meta["notes"]`` continua sendo só o texto que o cliente/operador escreveu.
    Opção sem ``ref`` (iFood) não entra: a nota de preparo do iFood já a traz.
    """
    meta = meta if isinstance(meta, dict) else {}
    lines = []
    text = summary(line_options(meta))
    if text:
        lines.append(text)
    notes = str(meta.get("notes") or "").strip()
    if notes:
        lines.append(notes)
    return "\n".join(lines)


def options_unit_price_q(product, options) -> int:
    """Quanto as opções da linha somam ao preço unitário, RELIDAS no catálogo atual.

    Opção sem ``ref`` (iFood) não entra; opção que sumiu do cadastro conta 0
    (a linha já foi aceita; o preço do produto continua valendo).
    """
    groups = {group.ref: group for group in parse(product)}
    total = 0
    for option in own_options(options):
        group = groups.get(str(option.get("group") or ""))
        current = group.option(str(option.get("ref"))) if group else None
        if current is not None:
            total += current.price_q * (_int(option.get("qty"), 1) or 1)
    return total


def public_line_options(options) -> list[dict]:
    """As opções da linha para a tela (sem ``consumes``)."""
    return [
        {
            "group": str(option.get("group") or ""),
            "ref": str(option.get("ref") or ""),
            "group_label": str(option.get("group_label") or ""),
            "name": str(option.get("name") or ""),
            "unit_price_q": _int(option.get("unit_price_q"), 0) or 0,
        }
        for option in own_options(options)
    ]


def selection_of(options) -> list[dict]:
    """``[{group, ref}]`` de uma linha já resolvida (para revalidar na recompra)."""
    return [{"group": str(option.get("group")), "ref": str(option.get("ref"))} for option in own_options(options)]
