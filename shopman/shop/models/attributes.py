"""Registro de atributos de produto — chave/valor **com definição**.

O insight do dono era "chave/valor ultra flexível, que sirva até para grades,
cores e tamanhos". A resposta dos PIMs que resolveram isso (Akeneo, metafields
do Shopify, Saleor, Odoo) é sempre a mesma: chave/valor **sim, com definição**.
Sem um registro, "cor", "Cor" e "côr" convivem no JSON e nenhuma regra consegue
ler o catálogo.

Isto aqui é o registro. É **configuração do tenant**, não regra de catálogo: a
Nelson decide que "sabor" existe e vale doce/salgado/neutro; outro tenant
decidiria outra coisa. Por isso mora em ``shop/models``, ao lado de
``RuleConfig``, ``QualityDefect`` e ``OmotenashiCopy`` — e o Offerman continua
sabendo só de produto, preço, vitrine e ``metadata``.

⚠️ **A definição diz onde o valor mora.** Nem todo atributo guarda o valor no
mesmo lugar, e fingir que guarda custaria migração de dados sem ganho:

- ``attributes`` (padrão) — ``Product.metadata["attributes"][ref]["value"]``.
  É a casa dos atributos que nascem aqui (natureza, sabor, temperatura).
- ``column:<campo>`` — o valor é coluna do ``Product``. O peso por unidade é
  fato físico com integridade no banco e **continua coluna**; o registro só o
  torna legível pelas regras.
- ``metadata:<chave>`` — o valor já mora numa chave solta do ``metadata``, de
  antes deste registro existir (``allergens``, ``dietary_info``, ``serves``).
  O ponteiro deixa o registro completo hoje sem mexer no editor de rótulo do
  Offerman, que é quem escreve essas chaves. Rebatizar as três é WP próprio,
  com migração de dados e os leitores do Core junto — ver
  ``docs/plans/WP-ATRIBUTOS-RENAME-CHAVES-LEGADAS.md``.

Ninguém lê estes campos direto: quem lê e escreve valor é
``shopman.shop.services.attributes``.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models

#: Onde o valor de um atributo mora. ``attributes`` é o padrão; os outros dois
#: são ponteiros para um lugar que já existia antes do registro.
STORAGE_ATTRIBUTES = "attributes"
STORAGE_COLUMN_PREFIX = "column:"
STORAGE_METADATA_PREFIX = "metadata:"

_STORAGE_RE = re.compile(r"^(attributes|column:[a-z_][a-z0-9_]*|metadata:[a-z_][a-z0-9_]*)$")

#: Chave do ``Product.metadata`` que hospeda valores e proveniência.
METADATA_ROOT = "attributes"


class AttributeType(models.TextChoices):
    """O tipo decide a validação e o campo que o gestor vê no Admin."""

    CHOICE = "choice", "Escolha única"
    MULTI_CHOICE = "multi_choice", "Escolha múltipla"
    #: Lista de termos livres, sem opções fechadas. Existe para os atributos
    #: cujo valor ainda é escrito por outro editor (alérgenos e dieta saem do
    #: formulário de rótulo do Offerman, em texto separado por vírgula):
    #: declarar opções fechadas para eles seria o registro prometer uma
    #: restrição que não tem como aplicar.
    MULTI_TEXT = "multi_text", "Lista de termos"
    NUMBER = "number", "Número"
    TEXT = "text", "Texto"
    BOOLEAN = "boolean", "Sim / Não"


class AttributeSource(models.TextChoices):
    """De onde veio o valor — a proveniência que ``dietary_auto_filled`` e
    ``ProductConsumptionTag.reviewed`` faziam cada um do seu jeito."""

    MANUAL = "manual", "Gestor"
    AI = "ai", "IA (proposta)"
    DERIVED = "derived", "Derivado do catálogo"
    RECIPE = "recipe", "Ficha técnica"


class AttributePurpose(models.TextChoices):
    """Para que o atributo serve. Um atributo pode servir a mais de uma coisa."""

    FACET = "facet", "Filtro na loja"
    RULE = "rule", "Regra de sugestão"
    FEED = "feed", "Feed de catálogo"
    VARIANT = "variant", "Grade / variante"
    LABEL = "label", "Rótulo e ficha"


class AttributeDefinitionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class AttributeDefinition(models.Model):
    """Um atributo que o catálogo desta casa conhece.

    ``ref`` e os ``value`` das opções são **dados do tenant, em português**
    (``sabor``, ``doce``), como as coleções ``paes`` e ``folhados``. A convenção
    de identificador em inglês vale para model, campo, service e tipo de regra —
    não para o vocabulário que o gestor cadastra.
    """

    ref = models.SlugField(
        "ref", max_length=40, unique=True,
        help_text="Identificador usado nas regras de sugestão. Ex.: sabor, natureza.",
    )
    label = models.CharField("rótulo", max_length=80)
    hint = models.CharField(
        "dica", max_length=200, blank=True,
        help_text="Para quem preenche o produto escolher sem pensar duas vezes.",
    )
    type = models.CharField(
        "tipo", max_length=16,
        choices=AttributeType.choices, default=AttributeType.CHOICE,
    )
    options = models.JSONField(
        "opções", default=list, blank=True,
        help_text=(
            'Lista de {"value", "label", "meta"} — obrigatória para escolha '
            "única e múltipla, vazia para os demais tipos."
        ),
    )
    unit = models.CharField(
        "unidade", max_length=16, blank=True,
        help_text="Só para número. Ex.: g, porções.",
    )
    purposes = models.JSONField(
        "serve para", default=list, blank=True,
        help_text="Subconjunto de: facet, rule, feed, variant, label.",
    )
    storage = models.CharField(
        "onde o valor mora", max_length=60, default=STORAGE_ATTRIBUTES,
        help_text=(
            "attributes (padrão) · column:<campo do Product> · "
            "metadata:<chave solta do metadata>."
        ),
    )
    required = models.BooleanField(
        "obrigatório", default=False,
        help_text="O Admin acusa os produtos que estão sem valor.",
    )
    ordering = models.IntegerField("ordem", default=0)
    is_active = models.BooleanField("ativo", default=True)

    objects = AttributeDefinitionQuerySet.as_manager()

    class Meta:
        ordering = ["ordering", "ref"]
        verbose_name = "atributo de produto"
        verbose_name_plural = "atributos de produto"

    def __str__(self):
        return f"{self.label} ({self.ref})"

    # --- leitura do desenho (sem tocar em produto) -------------------------

    @property
    def is_choice(self) -> bool:
        """Se o tipo usa a lista de opções fechada do registro."""
        return self.type in (AttributeType.CHOICE, AttributeType.MULTI_CHOICE)

    @property
    def is_list(self) -> bool:
        """Se o valor é uma lista (com ou sem opções fechadas)."""
        return self.type in (AttributeType.MULTI_CHOICE, AttributeType.MULTI_TEXT)

    def option_values(self) -> tuple[str, ...]:
        return tuple(str(o.get("value")) for o in (self.options or []) if o.get("value"))

    def option_label(self, value) -> str:
        for option in self.options or []:
            if str(option.get("value")) == str(value):
                return str(option.get("label") or option.get("value"))
        return str(value)

    def option_meta(self, value) -> dict:
        for option in self.options or []:
            if str(option.get("value")) == str(value):
                meta = option.get("meta")
                return dict(meta) if isinstance(meta, dict) else {}
        return {}

    def serves(self, purpose: str) -> bool:
        return purpose in (self.purposes or [])

    # --- onde o valor mora -------------------------------------------------

    @property
    def column_field(self) -> str | None:
        """Nome do campo do ``Product``, quando o valor é coluna."""
        if self.storage.startswith(STORAGE_COLUMN_PREFIX):
            return self.storage[len(STORAGE_COLUMN_PREFIX):]
        return None

    @property
    def metadata_key(self) -> str | None:
        """Chave solta do ``metadata``, quando o valor é anterior ao registro."""
        if self.storage.startswith(STORAGE_METADATA_PREFIX):
            return self.storage[len(STORAGE_METADATA_PREFIX):]
        return None

    # --- validação ---------------------------------------------------------

    def clean(self):
        errors: dict[str, str] = {}

        if not _STORAGE_RE.match(self.storage or ""):
            errors["storage"] = (
                "Use 'attributes', 'column:<campo>' ou 'metadata:<chave>' "
                "(minúsculas e underscore)."
            )

        column = self.column_field
        if column:
            from shopman.offerman.models import Product

            field_names = {f.name for f in Product._meta.get_fields()}
            if column not in field_names:
                errors["storage"] = f"O Product não tem o campo '{column}'."

        if not isinstance(self.options, list):
            errors["options"] = "As opções precisam ser uma lista."
        else:
            values = [o.get("value") for o in self.options if isinstance(o, dict)]
            if len(values) != len(self.options):
                errors["options"] = 'Cada opção é um objeto com "value" e "label".'
            elif any(not v for v in values):
                errors["options"] = 'Toda opção precisa de um "value" não vazio.'
            elif len(set(map(str, values))) != len(values):
                errors["options"] = "Há dois 'value' iguais entre as opções."

        if "options" not in errors:
            if self.is_choice and not self.options:
                errors["options"] = "Escolha única e múltipla precisam de opções."
            if not self.is_choice and self.options:
                errors["options"] = f"O tipo '{self.get_type_display()}' não usa opções."

        if not isinstance(self.purposes, list):
            errors["purposes"] = "Use uma lista."
        else:
            allowed = set(AttributePurpose.values)
            unknown = sorted({str(p) for p in self.purposes} - allowed)
            if unknown:
                errors["purposes"] = (
                    f"Não conheço: {', '.join(unknown)}. Use: {', '.join(sorted(allowed))}."
                )

        if self.unit and self.type != AttributeType.NUMBER:
            errors["unit"] = "Unidade só faz sentido em atributo de número."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
