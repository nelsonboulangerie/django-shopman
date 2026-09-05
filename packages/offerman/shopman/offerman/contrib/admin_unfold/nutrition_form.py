"""ProductForm with dedicated nutrition fields.

The ``Product.nutrition_facts`` JSONField is edited through virtual form
fields — one ``IntegerField`` / ``FloatField`` per nutrient — never as
raw JSON. The form serializes these back into the JSON on save.

Dataclass-driven: field names and types follow
``shopman.offerman.nutrition.NutritionFacts``.
"""

from __future__ import annotations

from django import forms
from shopman.offerman.models import Product
from shopman.offerman.nutrition import (
    NUTRIENT_LABELS_PT,
    NutritionFacts,
)
from unfold.widgets import (
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminURLInputWidget,
    UnfoldBooleanSwitchWidget,
)

# Ordered groups for fieldset rendering ("fieldset-like" sub-order in the admin).
SERVING_FIELDS = ("serving_size_g", "servings_per_container")
MACRONUTRIENTS = (
    "energy_kcal",
    "carbohydrates_g",
    "sugars_g",
    "proteins_g",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
)
MICRONUTRIENTS = ("fiber_g", "sodium_mg")


def _widget_for(field_name: str) -> forms.Widget:
    """Widget do Unfold, não `NumberInput` com a classe legada do Django admin.

    Era `forms.NumberInput(attrs={"class": "vTextField"})`: `vTextField` é do
    Admin antigo do Django, e nesta tela o campo saía com a cara de 2010 no meio
    de um formulário Unfold.
    """
    return UnfoldAdminDecimalFieldWidget(attrs={"step": "0.01"})


def _field_for(field_name: str) -> forms.Field:
    label = NUTRIENT_LABELS_PT.get(field_name, field_name)
    if field_name in ("serving_size_g", "servings_per_container"):
        return forms.IntegerField(
            label=label, required=False, min_value=0, widget=_widget_for(field_name),
        )
    return forms.FloatField(
        label=label, required=False, min_value=0.0, widget=_widget_for(field_name),
    )


NUTRITION_FORM_FIELDS: tuple[str, ...] = (
    SERVING_FIELDS + MACRONUTRIENTS + MICRONUTRIENTS
)

#: Campo do formulário → ``ref`` do atributo no registro do TENANT.
#: O Offerman não conhece esse vocabulário: ele pergunta ao provedor
#: (``OFFERMAN["LABEL_ATTRIBUTES_PROVIDER"]``) como ler e escrever, do mesmo
#: jeito que o Craftsman pergunta as variantes de lifecycle. Sem provedor
#: configurado, os campos somem e o pacote segue de pé sozinho — que é o ponto
#: de ele ser Core.
LABEL_ATTRIBUTE_FIELDS = {
    "allergens_text": "alergenos",
    "dietary_info_text": "dieta",
    "serves_text": "porcoes",
}


def _label_attributes():
    """O provedor de atributos de rótulo, ou ``None`` se não houver."""
    from shopman.offerman.conf import get_offerman_settings

    path = get_offerman_settings().LABEL_ATTRIBUTES_PROVIDER
    if not path:
        return None
    try:
        from django.utils.module_loading import import_string

        return import_string(path)()
    except Exception:  # pragma: no cover — configuração, não fluxo
        import logging

        logging.getLogger(__name__).warning(
            "Failed to load OFFERMAN['LABEL_ATTRIBUTES_PROVIDER']: %s", path, exc_info=True,
        )
        return None
REMOTE_PURCHASE_FORM_FIELDS = (
    "allergens_text",
    "dietary_info_text",
    "serves_text",
    "approx_dimensions_text",
)


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return value.strip()
    return ""


class ProductAdminForm(forms.ModelForm):
    """Form that exposes nutrition_facts as flat per-nutrient fields."""

    image_url = forms.URLField(
        label="URL da imagem",
        required=False,
        widget=UnfoldAdminURLInputWidget,
        max_length=500,
        assume_scheme="https",
        help_text="URL da imagem principal do produto (ex: Unsplash, Cloudinary, S3)",
    )
    allergens_text = forms.CharField(
        label="Alérgenos",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        help_text="Separe por vírgula. Ex.: glúten, leite, gergelim.",
    )
    dietary_info_text = forms.CharField(
        label="Restrições",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        help_text="Separe por vírgula. Ex.: 100% vegetal, sem lactose.",
    )
    serves_text = forms.CharField(
        label="Serve",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        help_text="Ex.: 2 a 4 pessoas.",
    )
    approx_dimensions_text = forms.CharField(
        label="Medidas aproximadas",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        help_text="Ex.: aprox. 24 x 12 x 10 cm.",
    )
    allows_next_day_sale = forms.BooleanField(
        label="Permite venda no dia seguinte",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text="Produto pode ser vendido no dia seguinte com preço reduzido.",
    )
    made_to_order = forms.BooleanField(
        label="Preparado na hora",
        required=False,
        widget=UnfoldBooleanSwitchWidget,
        help_text=(
            "Finalizado no momento de servir (gratinado, montado, extraído). "
            "É o que a loja PROMETE sobre o produto — vale mesmo quando ele sai "
            "da vitrine. Não confundir com a política de disponibilidade, que é "
            "sobre conferir estoque."
        ),
    )
    ready_from = forms.CharField(
        label="Pronto a partir de",
        required=False,
        widget=UnfoldAdminTextInputWidget,
        help_text=(
            "Hora em que este produto fica pronto num dia normal (HH:MM). "
            "É o que impede o balcão e a loja de prometerem a baguete de "
            "tradição para as 9h. Em branco, a hora é deduzida do histórico "
            "de fornadas — declare quando a casa souber a resposta."
        ),
    )

    # Virtual nutrient fields are declared at class scope (dataclass-driven via
    # NutritionFacts) so the admin fieldsets that reference them validate. The
    # admin builds the form with ``modelform_factory(fields=flatten_fieldsets)``,
    # which only resolves model fields and *declared* form fields — fields added
    # in ``__init__`` are invisible to it and raise FieldError.
    locals().update({name: _field_for(name) for name in NUTRITION_FORM_FIELDS})

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide the raw JSON field from the admin rendering.
        if "nutrition_facts" in self.fields:
            self.fields["nutrition_facts"].widget = forms.HiddenInput()
            self.fields["nutrition_facts"].required = False

        # Populate from the stored dict on edit.
        if self.instance and self.instance.pk:
            facts = NutritionFacts.from_dict(self.instance.nutrition_facts or {})
            if facts is not None:
                for name in NUTRITION_FORM_FIELDS:
                    self.fields[name].initial = getattr(facts, name)

            metadata = self.instance.metadata or {}
            provider = _label_attributes()
            if provider is not None:
                for field, ref in LABEL_ATTRIBUTE_FIELDS.items():
                    value = provider.get(self.instance, ref)
                    self.fields[field].initial = (
                        _join_list(value) if isinstance(value, list) else str(value or "")
                    )
            self.fields["approx_dimensions_text"].initial = str(
                metadata.get("approx_dimensions") or ""
            )
            self.fields["allows_next_day_sale"].initial = bool(
                metadata.get("allows_next_day_sale", False)
            )
            self.fields["made_to_order"].initial = bool(metadata.get("made_to_order", False))
            self.fields["ready_from"].initial = str(metadata.get("ready_from") or "")

    def clean_ready_from(self):
        """Hora inválida é RECUSADA na porta, não guardada para falhar depois.

        Um "12h" digitado no Admin viraria ausência de declaração lá adiante — o
        cadastro diria que a casa respondeu e o sistema agiria como se ninguém
        tivesse respondido. Erro de digitação tem que doer aqui.

        A leitura é local de propósito: o Offerman é Core e não importa o
        orquestrador. São quatro linhas de ``HH:MM``, não uma regra de negócio.
        """
        raw = (self.cleaned_data.get("ready_from") or "").strip()
        if not raw:
            return ""
        parts = raw.split(":")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except (IndexError, ValueError):
            raise forms.ValidationError("Use o formato HH:MM. Ex.: 12:00.") from None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise forms.ValidationError("Hora fora do dia. Use de 00:00 a 23:59.")
        return f"{hour:02d}:{minute:02d}"

    def clean(self):
        cleaned = super().clean()

        # Gather per-nutrient cleaned values into a dict.
        collected: dict[str, object] = {}
        for name in NUTRITION_FORM_FIELDS:
            value = cleaned.get(name)
            if value not in (None, ""):
                collected[name] = value

        # Preserve the auto_filled flag from the existing instance when the
        # operator touches the form — we default to "manual override" because
        # the operator is literally editing the field.
        has_any_nutrient = any(
            k for k in collected if k not in SERVING_FIELDS
        )
        if has_any_nutrient or "serving_size_g" in collected:
            collected["auto_filled"] = False

        cleaned["nutrition_facts"] = collected

        metadata = dict(cleaned.get("metadata") or {})
        metadata.pop("approx_dimensions", None)

        approx_dimensions = (cleaned.get("approx_dimensions_text") or "").strip()
        if approx_dimensions:
            metadata["approx_dimensions"] = approx_dimensions

        metadata["allows_next_day_sale"] = bool(cleaned.get("allows_next_day_sale"))
        metadata["made_to_order"] = bool(cleaned.get("made_to_order"))
        # Em branco APAGA a declaração (volta a valer só o histórico) — um campo
        # de texto que não sabe se esvaziar prende a casa na primeira resposta
        # que ela deu.
        ready_from = (cleaned.get("ready_from") or "").strip()
        if ready_from:
            metadata["ready_from"] = ready_from
        else:
            metadata.pop("ready_from", None)

        cleaned["metadata"] = metadata

        # A rotulagem do tenant vai para o registro, pelo provedor. Só marca
        # como escrita pelo gestor quando ela REALMENTE muda: re-salvar um
        # produto derivado da ficha não pode congelar a derivação.
        provider = _label_attributes()
        if provider is not None and self.instance is not None:
            # ⚠️ O `metadata` cru do formulário NÃO manda no registro. Ele é uma
            # textarea de JSON, e deixar que ela reescrevesse `attributes`
            # significaria um save qualquer apagar a rotulagem inteira sem que
            # ninguém tivesse tocado nos campos de rótulo.
            guardado = (self.instance.metadata or {}).get("attributes")
            if guardado:
                metadata["attributes"] = guardado
            self.instance.metadata = metadata
            for field, ref in LABEL_ATTRIBUTE_FIELDS.items():
                raw = (cleaned.get(field) or "").strip()
                novo = _split_list(raw) if field != "serves_text" else raw
                atual = provider.get(self.instance, ref)
                if novo == atual or (not novo and not atual):
                    continue
                try:
                    provider.set(self.instance, ref, novo or None)
                except ValueError as exc:
                    # Opção fora do registro (alérgeno digitado errado) é
                    # RECUSADA na porta. Guardar para falhar depois seria o
                    # rótulo dizer que a casa respondeu quando ninguém respondeu.
                    self.add_error(field, str(exc))
            cleaned["metadata"] = self.instance.metadata

        # Mirror into self.instance so Model.clean() sees the new value.
        if self.instance is not None:
            self.instance.nutrition_facts = collected
            self.instance.metadata = metadata
        return cleaned
