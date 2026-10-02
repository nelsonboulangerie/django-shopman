"""Aba "Escolhas" na ficha do produto: sabor obrigatório e adicionais com preço.

O cadastro mora em ``Product.metadata["option_groups"]`` e o rótulo do Cartão
de escolha em ``Product.metadata["choice_group_label"]``; formato, validação e
leitura são de :mod:`shopman.shop.product_options`. Esta tela é só a porta: um
editor do cadastro em JSON, conferido ao salvar (códigos, mínimo e máximo,
preço, e o insumo que cada opção gasta, que precisa existir no cadastro e contar
numa unidade das fichas), e o que foi gravado, em texto, com o nome do insumo.

A base é o Admin que o Core REGISTROU (Offerman + abas fiscal e social), lida
do site no ``ready()`` do backstage, o último app: a superfície herda do que o
Core pôs no Admin, sem entrar no contrib dele (mesmo padrão de
``product_enrichment``).
"""

from __future__ import annotations

import json

from django import forms
from django.contrib import admin
from unfold.widgets import UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

from shopman.shop import product_options

OPTION_FORM_FIELDS = ("choice_group_label", "option_groups_json")
OPTION_READONLY_FIELDS = ("option_groups_display",)

EXAMPLE = (
    '[{"ref": "adicionais", "label": "Adicionais", "min": 0, "max": 2, "options": ['
    '{"ref": "ovo", "label": "Ovo frito", "price_q": 400, "available": true, '
    '"consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]}]}]'
)


def build_options_form(base_form_cls):
    """``base_form_cls`` + os campos da aba Escolhas, gravados em ``metadata``."""

    class ProductOptionsAdminForm(base_form_cls):
        choice_group_label = forms.CharField(
            label="O que se escolhe no cartão",
            required=False,
            max_length=40,
            widget=UnfoldAdminTextInputWidget,
            help_text=(
                "Só para produto num Cartão de escolha (aba Publicação e venda). "
                "É o título da escolha que o cliente e o balcão leem, ex.: Sabor. Vazio: sem título."
            ),
        )
        option_groups_json = forms.CharField(
            label="Grupos de escolha",
            required=False,
            widget=UnfoldAdminTextareaWidget(attrs={"rows": 14, "spellcheck": "false"}),
            help_text=(
                "Lista de grupos. Cada grupo: ref (código), label (nome que a tela mostra), "
                "min (quantas escolhas são obrigatórias; 0 = opcional), max (até quantas), "
                "options. Cada opção: ref, label, price_q (acréscimo em centavos; 0 = sem acréscimo), "
                "available (false = fora hoje) e consumes (o insumo que a opção gasta: sku, qty, unit). "
                "O insumo é registro: a venda não baixa estoque dele. Vazio: o produto não tem escolha. "
                f"Exemplo: {EXAMPLE}"
            ),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            metadata = getattr(self.instance, "metadata", None) or {}
            self.fields["choice_group_label"].initial = product_options.choice_group_label(metadata)
            raw = metadata.get(product_options.OPTION_GROUPS_KEY)
            if raw:
                self.fields["option_groups_json"].initial = json.dumps(raw, ensure_ascii=False, indent=2)

        def clean_option_groups_json(self):
            text = (self.cleaned_data.get("option_groups_json") or "").strip()
            if not text:
                return []
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError(
                    f"JSON inválido na linha {exc.lineno}, coluna {exc.colno}: {exc.msg}."
                ) from None
            try:
                return product_options.validate_definition(raw)
            except product_options.OptionDefinitionError as exc:
                raise forms.ValidationError(exc.messages) from None

        def clean(self):
            cleaned = super().clean()
            metadata = dict(cleaned.get("metadata") or getattr(self.instance, "metadata", None) or {})
            groups = cleaned.get("option_groups_json")
            if "option_groups_json" in cleaned:
                if groups:
                    metadata[product_options.OPTION_GROUPS_KEY] = groups
                else:
                    metadata.pop(product_options.OPTION_GROUPS_KEY, None)
            label = " ".join((cleaned.get("choice_group_label") or "").split())
            if label:
                metadata[product_options.CHOICE_GROUP_LABEL_KEY] = label
            else:
                metadata.pop(product_options.CHOICE_GROUP_LABEL_KEY, None)
            cleaned["metadata"] = metadata
            if self.instance is not None:
                self.instance.metadata = metadata
            return cleaned

    return ProductOptionsAdminForm


def describe_groups(product) -> str:
    """O cadastro gravado, em texto, com o insumo pelo nome e pela unidade."""
    from shopman.utils.monetary import format_money

    from shopman.shop.adapters.sku_validator import get_composed_sku_validator

    groups = product_options.parse(product)
    if not groups:
        return "Sem escolhas: o item entra na venda direto."
    validator = get_composed_sku_validator()
    lines: list[str] = []
    for group in groups:
        if group.min == 0:
            rule = f"opcional, até {group.max}"
        elif group.min == group.max:
            rule = f"escolher {group.min}"
        else:
            rule = f"escolher de {group.min} a {group.max}"
        lines.append(f"{group.label} ({rule})")
        for option in group.options:
            price = f"+ R$ {format_money(option.price_q)}" if option.price_q else "sem acréscimo"
            state = "" if option.available else ", fora hoje"
            consumes = []
            for entry in option.consumes:
                info = validator.get_sku_info(entry["sku"])
                name = getattr(info, "name", "") or "insumo não cadastrado"
                consumes.append(f"{name} ({entry['sku']}) {entry['qty']} {entry['unit']}")
            spent = f"; gasta {', '.join(consumes)}" if consumes else "; sem insumo declarado"
            lines.append(f"  · {option.label}: {price}{state}{spent}")
    return "\n".join(lines)


def build_options_product_admin(base_admin_cls):
    """``base_admin_cls`` + o form e a aba "Escolhas"."""
    base_form = getattr(base_admin_cls, "form", None) or forms.ModelForm
    options_form = build_options_form(base_form)

    class ProductOptionsAdmin(base_admin_cls):
        form = options_form

        def get_readonly_fields(self, request, obj=None):
            return (*super().get_readonly_fields(request, obj), *OPTION_READONLY_FIELDS)

        def get_fieldsets(self, request, obj=None):
            fieldsets = list(super().get_fieldsets(request, obj))
            options_fieldset = (
                "Escolhas",
                {
                    "fields": (*OPTION_FORM_FIELDS, *OPTION_READONLY_FIELDS),
                    "classes": ("tab",),
                    "description": (
                        "Sabor obrigatório e adicionais com preço. O cliente e o balcão escolhem ao "
                        "pôr o item na venda; o acréscimo soma no preço do item, que sai numa linha só "
                        "na nota, e a escolha aparece no card da cozinha."
                    ),
                },
            )
            insert_at = max(len(fieldsets) - 1, 0)
            fieldsets.insert(insert_at, options_fieldset)
            return fieldsets

        @admin.display(description="Como está gravado")
        def option_groups_display(self, obj):
            return describe_groups(obj) if obj is not None and obj.pk else "Salve o produto para ver."

    ProductOptionsAdmin.__name__ = base_admin_cls.__name__
    ProductOptionsAdmin.__qualname__ = base_admin_cls.__qualname__
    ProductOptionsAdmin._product_options_tab = True
    return ProductOptionsAdmin


def install_product_options_admin() -> None:
    """Compõe a aba Escolhas sobre o Admin de Produto registrado. Idempotente."""
    from shopman.offerman.models import Product

    current = admin.site._registry.get(Product)
    if current is None or getattr(current, "_product_options_tab", False):
        return
    admin.site.unregister(Product)
    admin.site.register(Product, build_options_product_admin(type(current)))
