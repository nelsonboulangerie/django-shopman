"""Inventário de receitas: a linhagem (``RecipeEntry``) e a fórmula congelada (``RecipeVersion``).

Autoria e execução são duas coisas. A ``Recipe`` continua sendo a ficha de
execução (o BOM que a fornada consome). O inventário é onde o padeiro escreve,
padroniza, compara e versiona; **publicar** uma versão é o único caminho que
escreve na ficha. Ver ``docs/plans/RECIPE-INVENTORY-PLAN.md`` §2.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.craftsman.exceptions import RecipeBookError
from shopman.utils.refs import RefField


class RecipeEntry(models.Model):
    """Uma receita do inventário, com a sua linhagem de versões."""

    class Kind(models.TextChoices):
        BREAD = "bread", _("Pão")
        VIENNOISERIE = "viennoiserie", _("Viennoiserie")
        SWEET_DOUGH = "sweet_dough", _("Massa doce")
        FILLING = "filling", _("Recheio")
        CREAM = "cream", _("Creme")
        SAUCE = "sauce", _("Molho")
        BEVERAGE = "beverage", _("Bebida")
        OTHER = "other", _("Outra")

    ref = models.SlugField(
        unique=True,
        max_length=50,
        verbose_name=_("Ref"),
        help_text=_("Identificador único; igual ao ref da ficha técnica quando publicada."),
    )
    name = models.CharField(max_length=200, verbose_name=_("Nome"))
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.OTHER,
        verbose_name=_("Tipo"),
    )
    output_sku = RefField(
        ref_type="SKU",
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("SKU produzido"),
        help_text=_("Vazio = receita sem SKU, só conhecimento."),
    )
    notes = models.TextField(blank=True, default="", verbose_name=_("Observações"))
    is_archived = models.BooleanField(default=False, verbose_name=_("Arquivada"))
    current_version = models.ForeignKey(
        "craftsman.RecipeVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Versão atual"),
        help_text=_("A última versão publicada."),
    )
    meta = models.JSONField(default=dict, blank=True, verbose_name=_("Metadados"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        db_table = "crafting_recipe_entry"
        verbose_name = _("receita")
        verbose_name_plural = _("receitas")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["output_sku"]),
            models.Index(fields=["kind"]),
        ]

    def __str__(self) -> str:
        return self.name


class RecipeVersion(models.Model):
    """Uma fórmula congelada de uma receita do inventário."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Rascunho")
        PUBLISHED = "published", _("Publicada")
        SUPERSEDED = "superseded", _("Substituída")

    class YieldUnit(models.TextChoices):
        KILOGRAM = "kg", _("kg")
        GRAM = "g", _("g")
        UNIT = "un", _("un.")
        LITER = "L", _("L")
        MILLILITER = "ml", _("ml")

    entry = models.ForeignKey(
        RecipeEntry,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Receita"),
    )
    number = models.PositiveIntegerField(verbose_name=_("Número"))
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("Status"),
    )
    label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("O que mudou"),
    )
    yield_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("1"),
        verbose_name=_("Rendimento"),
        help_text=_("Rendimento da fórmula tal como escrita."),
    )
    yield_unit = models.CharField(
        max_length=5,
        choices=YieldUnit.choices,
        default=YieldUnit.KILOGRAM,
        verbose_name=_("Unidade do rendimento"),
    )
    formula = models.JSONField(default=dict, blank=True, verbose_name=_("Fórmula"))
    origin = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Como foi informada"),
        help_text=_("A receita como chegou (quantidades, unidades, texto). Imutável."),
    )
    source = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Origem"),
        help_text=_("{kind: manual|note|photo|ficha|import, text?, language?, image_name?, model?}"),
    )
    steps = models.JSONField(default=list, blank=True, verbose_name=_("Etapas"))
    notes = models.TextField(blank=True, default="", verbose_name=_("Observações"))
    created_by = models.CharField(max_length=100, blank=True, default="", verbose_name=_("Criado por"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Publicada em"))
    meta = models.JSONField(default=dict, blank=True, verbose_name=_("Metadados"))

    class Meta:
        db_table = "crafting_recipe_version"
        verbose_name = _("versão de receita")
        verbose_name_plural = _("versões de receita")
        ordering = ["entry", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["entry", "number"], name="craft_recipeversion_entry_number_uq"),
            models.CheckConstraint(
                condition=models.Q(yield_quantity__gt=0),
                name="craft_recipeversion_yield_positive",
            ),
        ]

    @property
    def version_ref(self) -> str:
        """Carimbo ``<ref>@<n>`` que a ficha e o snapshot da fornada carregam."""
        return f"{self.entry.ref}@{self.number}"

    def clean(self):
        super().clean()
        if self.yield_quantity is not None and self.yield_quantity <= 0:
            raise ValidationError({"yield_quantity": _("Deve ser maior que zero.")})
        if self.steps and not isinstance(self.steps, list):
            raise ValidationError({"steps": _("Deve ser uma lista de nomes de etapas.")})
        try:
            validate_formula(self.formula)
        except RecipeBookError as exc:
            field = exc.data.get("field", "formula")
            raise ValidationError({"formula": f"{field}: {exc.message}"}) from exc

    def __str__(self) -> str:
        return self.version_ref if self.entry_id else f"@{self.number}"


def validate_formula(formula) -> None:
    """Schema da fórmula (§3 do plano). Levanta ``RecipeBookError("FORMULA_INVALID", field=...)``."""
    from shopman.craftsman.contrib.formula.percentages import validate_formula as _validate

    _validate(formula)
