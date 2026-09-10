"""Registro de atributos de produto — config, não operação.

Ninguém no balcão passa por aqui. O gestor cadastra o vocabulário que o catálogo
desta casa conhece (natureza, sabor, temperatura, alérgenos…) e as regras de
sugestão passam a poder falar dele **sem deploy**: atributo novo aqui amplia o
vocabulário das regras em ``RuleConfig``.

⚠️ **Mexer numa opção mexe em produto já etiquetado.** Remover "gelado" de
``temperatura`` não apaga o valor gravado nos produtos — ele passa a ler como
ausente, e as regras que dependiam dele param de casar, em silêncio. Por isso
``ref`` é imutável depois de criado e a exclusão está fechada: sai de circulação
desativando.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.widgets import (
    UnfoldAdminCheckboxSelectMultipleWidget,
    UnfoldAdminTextareaWidget,
)

from shopman.shop.models import AttributeDefinition
from shopman.shop.models.attributes import AttributePurpose, AttributeType


class AttributeDefinitionForm(forms.ModelForm):
    """As opções são JSON, mas ninguém deveria digitar JSON para dizer
    "doce, salgado, neutro". O campo abaixo aceita a lista humana e o
    ``meta`` de cada opção continua editável para quem precisar dele."""

    options_text = forms.CharField(
        label="opções",
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 4}),
        help_text=(
            "Uma por linha, no formato valor = Rótulo. "
            "Ex.: doce = Doce. Só para escolha única e múltipla."
        ),
    )
    # ``purposes`` é JSONField no banco, mas a pergunta ao gestor é uma lista de
    # caixas — não um JSON para digitar à mão.
    purposes = forms.MultipleChoiceField(
        label="serve para",
        required=False,
        choices=AttributePurpose.choices,
        widget=UnfoldAdminCheckboxSelectMultipleWidget,
        help_text="Onde este atributo é lido. Um atributo pode servir a mais de uma coisa.",
    )

    class Meta:
        model = AttributeDefinition
        fields = (
            "ref", "label", "hint", "type", "unit", "purposes",
            "storage", "required", "ordering", "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance") or getattr(self, "instance", None)
        if instance and instance.pk:
            self.fields["options_text"].initial = "\n".join(
                f"{o.get('value')} = {o.get('label') or o.get('value')}"
                for o in (instance.options or [])
            )

    def clean(self):
        cleaned = super().clean()
        parsed, errors = _parse_options(cleaned.get("options_text") or "")
        if errors:
            self.add_error("options_text", errors)
            return cleaned
        # ``meta`` de opção já cadastrada não se perde ao reeditar o rótulo: o
        # texto edita valor e rótulo; o resto da opção sobrevive pelo `value`.
        existing = {str(o.get("value")): o for o in (self.instance.options or [])}
        for option in parsed:
            meta = (existing.get(option["value"]) or {}).get("meta")
            if isinstance(meta, dict) and meta:
                option["meta"] = meta
        self.instance.options = parsed
        return cleaned


def _parse_options(text: str) -> tuple[list[dict], list[str]]:
    options: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        value, _, label = line.partition("=")
        value = value.strip()
        label = label.strip() or value
        if not value:
            errors.append(f"Linha {number}: falta o valor antes do '='.")
            continue
        if value in seen:
            errors.append(f"Linha {number}: '{value}' aparece duas vezes.")
            continue
        seen.add(value)
        options.append({"value": value, "label": label})
    return options, errors


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(ModelAdmin):
    form = AttributeDefinitionForm
    list_display = (
        "label", "ref", "type_display", "options_display", "purposes_display",
        "storage_display", "required", "ordering", "is_active",
    )
    list_editable = ("ordering", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("ref", "label", "hint")
    ordering = ("ordering", "ref")
    fields = (
        "ref", "label", "hint", "type", "options_text", "unit",
        "purposes", "storage", "required", "ordering", "is_active",
    )

    def get_readonly_fields(self, request, obj=None):
        # As regras de sugestão e os valores gravados apontam para o ref; o
        # rótulo edita à vontade, o ref não.
        return ("ref", "storage") if obj else ()

    @display(description="tipo")
    def type_display(self, obj):
        return obj.get_type_display()

    @display(description="opções")
    def options_display(self, obj):
        if not obj.is_choice:
            return f"— {obj.unit}" if obj.unit else "—"
        values = obj.option_values()
        shown = ", ".join(values[:4])
        return f"{shown}…" if len(values) > 4 else shown

    @display(description="serve para")
    def purposes_display(self, obj):
        labels = dict(AttributePurpose.choices)
        return ", ".join(str(labels.get(p, p)) for p in (obj.purposes or [])) or "—"

    @display(
        description="onde mora",
        label={"produto": "success", "coluna": "info", "chave legada": "warning"},
    )
    def storage_display(self, obj):
        if obj.column_field:
            return "coluna"
        if obj.metadata_key:
            return "chave legada"
        return "produto"

    def has_delete_permission(self, request, obj=None):
        # Apagar a definição deixa os valores gravados órfãos e as regras que a
        # citam sem casar, em silêncio. Sai de circulação desativando.
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "type" in form.base_fields:
            form.base_fields["type"].help_text = (
                "Escolha única e múltipla usam o campo de opções; "
                f"'{AttributeType.NUMBER.label}' usa a unidade."
            )
        return form
