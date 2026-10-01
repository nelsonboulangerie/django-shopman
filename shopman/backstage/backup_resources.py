"""Entidades do backstage no cofre de dados curados.

Entram só as tabelas de curadoria manual — os de-paras confirmados a mão
(tradução de anos de histórico), o vocabulário de consumo do B.I., o mapa do
salão e a nota das receitas (critérios e avaliações, D24; as fontes já viajam
no ``meta`` da receita, na aba ``recipe_entries``). O transacional do backstage
(tickets, fechamentos, episódios, histórico importado) fica com o backup do
banco, como todo transacional.

A direção de import respeita a regra dos 3 apps: backstage → shop, nunca o
contrário — o registro do cofre mora no shop e o backstage se inscreve nele.
"""

from __future__ import annotations

import json

from import_export import fields, resources
from shopman.offerman.models import Product

from shopman.backstage.models import (
    CategoryAlias,
    ConsumptionRole,
    PaymentMethodAlias,
    ProductAlias,
    ProductConsumptionTag,
    RecipeRatingCriterion,
    RecipeVersionRating,
    RecipeVersionRatingScore,
    SeatingSpot,
)
from shopman.shop.backup import registry
from shopman.shop.backup.resources import NaturalKeyMeta, _fk


class ConsumptionRoleResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = ConsumptionRole
        import_id_fields = ("ref",)


class ProductConsumptionTagResource(resources.ModelResource):
    role = _fk(ConsumptionRole, "ref", "role")

    class Meta(NaturalKeyMeta):
        model = ProductConsumptionTag
        import_id_fields = ("sku",)


class SeatingSpotResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = SeatingSpot
        import_id_fields = ("ref",)


#: FKs de assinatura (``confirmed_by`` → User) ficam fora, como todo usuário.
class _AliasMeta(NaturalKeyMeta):
    exclude = NaturalKeyMeta.exclude + ("confirmed_by",)


class ProductAliasResource(resources.ModelResource):
    product = _fk(Product, "sku", "product")

    class Meta(_AliasMeta):
        model = ProductAlias
        import_id_fields = ("source", "external_sku", "external_name")


class CategoryAliasResource(resources.ModelResource):
    class Meta(_AliasMeta):
        model = CategoryAlias
        import_id_fields = ("pattern",)


class PaymentMethodAliasResource(resources.ModelResource):
    class Meta(_AliasMeta):
        model = PaymentMethodAlias
        import_id_fields = ("pattern",)


class RecipeRatingCriterionResource(resources.ModelResource):
    """Os eixos da nota ("Sabor", "Textura", "Aparência"), com o nome como chave."""

    class Meta(NaturalKeyMeta):
        model = RecipeRatingCriterion
        import_id_fields = ("name",)


class RatingScoresField(fields.Field):
    """``scores``: as notas da avaliação, ``{"<nome do critério>": nota}`` em JSON.

    A nota por critério não tem chave natural própria (a avaliação é composta:
    receita, versão e operador), então viaja dentro da linha da avaliação, pelo
    nome do critério. Critério que não existe no banco reprova a linha antes do
    save, no dry-run também.
    """

    def __init__(self):
        super().__init__(column_name="scores", attribute=None, readonly=False)

    def export(self, instance, **kwargs):
        if instance.pk is None:
            return ""
        scores = instance.scores.select_related("criterion").order_by("criterion__position", "criterion__name")
        return json.dumps({score.criterion.name: score.score for score in scores}, ensure_ascii=False)

    def save(self, instance, row, is_m2m=False, **kwargs):
        # A escrita real acontece em after_save_instance, com a avaliação salva.
        parse_rating_scores(row.get("scores"))


def parse_rating_scores(raw) -> dict[RecipeRatingCriterion, int]:
    """O JSON da coluna ``scores`` → ``{critério: nota}``; nome desconhecido é erro."""
    text = str(raw or "").strip()
    data = json.loads(text) if text else {}
    if not isinstance(data, dict):
        raise ValueError("scores: esperado um objeto {critério: nota}.")
    by_name = {criterion.name: criterion for criterion in RecipeRatingCriterion.objects.filter(name__in=list(data))}
    unknown = sorted(set(data) - set(by_name))
    if unknown:
        raise ValueError(f"scores: critério desconhecido: {', '.join(unknown)}.")
    return {by_name[name]: int(score) for name, score in data.items()}


class RecipeVersionRatingResource(resources.ModelResource):
    """A nota de UM operador sobre UMA versão de receita, com as notas por critério.

    Aponta para a versão por ``entry_ref`` + ``version_number`` (texto, sem FK),
    então restaura sem depender da ordem das abas do Craftsman. ``created_at`` e
    ``updated_at`` não viajam (regra do cofre): o restore data a avaliação de novo.
    """

    scores = RatingScoresField()

    class Meta(NaturalKeyMeta):
        model = RecipeVersionRating
        import_id_fields = ("entry_ref", "version_number", "operator_ref")
        # A comparação de "linha igual" não enxerga as notas (moram em outra
        # tabela): sem isto, uma nota perdida com a avaliação de pé não voltaria.
        skip_unchanged = False

    def after_save_instance(self, instance, row, **kwargs):
        if kwargs.get("dry_run"):
            return
        scores = parse_rating_scores(row.get("scores"))
        instance.scores.all().delete()
        RecipeVersionRatingScore.objects.bulk_create(
            RecipeVersionRatingScore(rating=instance, criterion=criterion, score=score)
            for criterion, score in scores.items()
        )


def register_backstage_resources() -> None:
    for name, resource, tier in (
        ("consumption_roles", ConsumptionRoleResource, 0),
        ("seating_spots", SeatingSpotResource, 0),
        ("category_aliases", CategoryAliasResource, 0),
        ("payment_method_aliases", PaymentMethodAliasResource, 0),
        ("recipe_rating_criteria", RecipeRatingCriterionResource, 0),
        ("product_consumption_tags", ProductConsumptionTagResource, 1),
        ("product_aliases", ProductAliasResource, 1),
        ("recipe_version_ratings", RecipeVersionRatingResource, 1),
    ):
        registry.register(name, resource, tier=tier)
