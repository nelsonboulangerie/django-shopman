"""Inventário de receitas: a linhagem (``RecipeEntry``) e a fórmula congelada (``RecipeVersion``).

Autoria e execução são duas coisas. A ``Recipe`` continua sendo a ficha de
execução (o BOM que a fornada consome). O inventário é onde o padeiro escreve,
padroniza, compara e versiona; **publicar** uma versão é o único caminho que
escreve na ficha. Ver ``docs/plans/RECIPE-INVENTORY-PLAN.md`` §2.

**Versão fechada é história, e o modelo recusa reescrevê-la.** Publicada ou
substituída, a ``RecipeVersion`` não aceita mais mudança de conteúdo nem
exclusão, venha de onde vier (serviço, shell, seed, Admin, ``.update()`` em
massa, cascata da receita). O único caminho nomeado que reescreve uma versão
fechada é o restore do cofre (:func:`restoring_recipe_versions`). SQL cru e o
``_base_manager`` passam por baixo, como em qualquer trava de ORM.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from shopman.craftsman.exceptions import RecipeBookError
from shopman.utils.refs import RefField


class RecipeEntry(models.Model):
    """Uma receita do inventário, com a sua linhagem de versões."""

    class Kind(models.TextChoices):
        BREAD = "bread", _("Pão")
        VIENNOISERIE = "viennoiserie", _("Viennoiserie")
        SWEET_DOUGH = "sweet_dough", _("Massa doce")
        COOKIE = "cookie", _("Biscoito")
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


#: Ligado só dentro de :func:`restoring_recipe_versions`. ``ContextVar`` e não
#: global de módulo: vale para a thread (e a corrotina) que abriu o restore, e
#: para nenhuma outra requisição que esteja rodando ao lado.
_restoring_versions: ContextVar[bool] = ContextVar("craftsman_restoring_recipe_versions", default=False)


@contextmanager
def restoring_recipe_versions() -> Iterator[None]:
    """O único caminho que reescreve uma versão fechada: o restore do cofre.

    Restaurar é exatamente devolver a uma versão publicada o conteúdo que ela
    tinha quando foi exportada, inclusive por cima de uma versão adulterada no
    banco. Fora deste bloco, a trava do ``save()`` e do ``.update()`` recusa.
    Não abre a exclusão: restore não apaga.
    """
    token = _restoring_versions.set(True)
    try:
        yield
    finally:
        _restoring_versions.reset(token)


class RecipeVersionQuerySet(models.QuerySet):
    """``.update()`` em massa respeita a mesma trava do ``save()``.

    Rascunho é livre. Em versão fechada, o único ``.update()`` aceito é o do
    ``publish_version``: ``status`` para ``superseded``, e nada mais.
    """

    def update(self, **kwargs):
        if not _restoring_versions.get():
            other_fields = sorted(set(kwargs) - {"status"})
            bad_status = "status" in kwargs and kwargs["status"] != RecipeVersion.Status.SUPERSEDED
            if other_fields or bad_status:
                closed = self.exclude(status=RecipeVersion.Status.DRAFT).first()
                if closed is not None:
                    raise RecipeBookError(
                        "VERSION_IMMUTABLE",
                        version_ref=str(closed),
                        status=closed.status,
                        fields=other_fields + (["status"] if bad_status else []),
                    )
        return super().update(**kwargs)


class RecipeVersion(models.Model):
    """Uma fórmula congelada de uma receita do inventário.

    Rascunho é editável. Publicada ou substituída, é história: ``save()``
    recusa mudar qualquer campo (o único movimento é ``status`` de publicada
    para substituída) e o ``pre_delete`` recusa a exclusão por qualquer caminho
    do ORM. Ver o docstring do módulo.
    """

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
        # Grama é a unidade-base da casa (ADR-024, emenda de 24/09/2026).
        default=YieldUnit.GRAM,
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

    objects = models.Manager.from_queryset(RecipeVersionQuerySet)()

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

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk is not None and not _restoring_versions.get():
            self._refuse_rewrite(kwargs.get("update_fields"))
        return super().save(*args, **kwargs)

    def _refuse_rewrite(self, update_fields) -> None:
        """Recusa mudar uma versão que o banco já guarda como fechada."""
        written = None if update_fields is None else set(update_fields)
        fields = [
            field for field in self._meta.concrete_fields
            if not field.primary_key
            and (written is None or field.name in written or field.attname in written)
        ]
        stored = type(self)._base_manager.filter(pk=self.pk).values(
            "status", *{field.attname for field in fields}
        ).first()
        if stored is None or stored["status"] == self.Status.DRAFT:
            return
        changed = []
        for field in fields:
            name = field.name
            before = field.to_python(stored[field.attname])
            after = field.to_python(getattr(self, field.attname))
            if before == after:
                continue
            if name == "status" and before == self.Status.PUBLISHED and after == self.Status.SUPERSEDED:
                continue
            changed.append(name)
        if changed:
            raise RecipeBookError(
                "VERSION_IMMUTABLE", version_ref=str(self), status=stored["status"], fields=changed,
            )


@receiver(pre_delete, sender=RecipeVersion, dispatch_uid="craftsman_recipe_version_undeletable")
def _refuse_closed_version_delete(sender, instance, **kwargs):
    """Versão fechada não se apaga, por caminho nenhum do ORM.

    Um ``delete()`` no modelo não bastaria: ``.delete()`` em massa e a cascata
    da ``RecipeEntry`` não passam por ele, e passam por este sinal. A coleta
    roda numa transação, então a recusa não deixa nada apagado pela metade.
    """
    if instance.status != RecipeVersion.Status.DRAFT:
        raise RecipeBookError("VERSION_UNDELETABLE", version_ref=str(instance), status=instance.status)


def validate_formula(formula) -> None:
    """Schema da fórmula (§3 do plano). Levanta ``RecipeBookError("FORMULA_INVALID", field=...)``."""
    from shopman.craftsman.contrib.formula.percentages import validate_formula as _validate

    _validate(formula)
