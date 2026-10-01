"""Nota de receita: gravar a avaliação do operador e ler as médias por versão (D7).

O desenho mora em ``shopman.backstage.models.recipe_rating``. Aqui:

- ``rate`` grava (ou substitui) a avaliação de UM operador sobre UMA versão,
  rascunho incluído (D24, dono, 01/10/2026), com uma nota inteira de 0 a 5 para
  CADA critério ativo, nem mais nem menos.
- ``summaries`` lê, por versão, a contagem de avaliações e as médias por
  critério e geral, só dos critérios ATIVOS (critério desativado sai da média;
  a nota antiga fica guardada). A média geral é a média de todas as notas dos
  critérios ativos.

Quem confere que a receita e a versão existem é a view (404 antes de chegar
aqui), como na Favorita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count
from shopman.craftsman.models import RecipeVersion

from shopman.backstage.models import RecipeRatingCriterion, RecipeVersionRating, RecipeVersionRatingScore
from shopman.backstage.models.recipe_rating import RATING_MAX, RATING_MIN
from shopman.backstage.services.exceptions import RecipeBookServiceError


def _fail(detail: str, *, field_name: str = "scores", code: str = "INVALID_PAYLOAD") -> RecipeBookServiceError:
    return RecipeBookServiceError(detail, field=field_name, code=code)


def active_criteria() -> list[RecipeRatingCriterion]:
    return list(RecipeRatingCriterion.objects.filter(is_active=True).order_by("position", "name"))


def _score(value: Any, criterion: RecipeRatingCriterion) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        else:
            raise _fail(f"A nota de {criterion.name} precisa ser um número inteiro de 0 a 5.",
                        field_name=f"scores.{criterion.pk}")
    if not RATING_MIN <= value <= RATING_MAX:
        raise _fail(f"A nota de {criterion.name} vai de 0 a 5.", field_name=f"scores.{criterion.pk}")
    return value


def clean_scores(raw: Any, criteria: list[RecipeRatingCriterion]) -> dict[int, int]:
    """``{"<id do critério>": nota}`` → ``{id: nota}``, exigindo cada critério ativo uma vez."""
    if not isinstance(raw, dict) or not raw:
        raise _fail("Dê uma nota de 0 a 5 a cada critério.")
    by_id = {criterion.pk: criterion for criterion in criteria}
    cleaned: dict[int, int] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        criterion = by_id.get(int(key_text)) if key_text.isdigit() else None
        if criterion is None:
            raise _fail("Critério desconhecido ou desativado. Recarregue a tela.", field_name=f"scores.{key_text}")
        cleaned[criterion.pk] = _score(value, criterion)
    missing = [criterion.name for criterion in criteria if criterion.pk not in cleaned]
    if missing:
        raise _fail(f"Falta a nota de: {', '.join(missing)}.")
    return cleaned


@transaction.atomic
def rate(operator_ref: str, version: RecipeVersion, scores: Any) -> RecipeVersionRating:
    """Grava a avaliação do operador sobre a versão. Avaliar de novo substitui a anterior."""
    if not operator_ref:
        raise _fail("Avaliação sem operador.", field_name="operator")
    criteria = active_criteria()
    if not criteria:
        raise _fail("Nenhum critério de nota ativo. Ative um no Admin.", code="NO_ACTIVE_CRITERIA")
    cleaned = clean_scores(scores, criteria)
    rating, created = RecipeVersionRating.objects.select_for_update().get_or_create(
        entry_ref=version.entry.ref, version_number=version.number, operator_ref=operator_ref,
    )
    if not created:
        rating.scores.all().delete()
        rating.save(update_fields=["updated_at"])
    RecipeVersionRatingScore.objects.bulk_create(
        RecipeVersionRatingScore(rating=rating, criterion_id=criterion_id, score=score)
        for criterion_id, score in cleaned.items()
    )
    return rating


def forget_deleted_version(sender, instance: RecipeVersion, **kwargs) -> None:
    """``pre_delete`` da ``RecipeVersion``: a nota sai junto com a versão.

    Versão se apaga (D11), e o número volta a ser usado: ``create_version``
    numera por último + 1, então apagar o rascunho v3 e criar outro dá outro
    v3. Sem esta limpeza, o rascunho novo nasceria com a nota da fórmula
    apagada. Vale também na cascata ao apagar a receita.
    """
    RecipeVersionRating.objects.filter(
        entry_ref=instance.entry.ref, version_number=instance.number,
    ).delete()


# ── Leitura ──────────────────────────────────────────────────────────────────


@dataclass
class CriterionAverage:
    criterion_id: int
    name: str
    average: Decimal | None
    count: int
    my_score: int | None


@dataclass
class VersionRatingSummary:
    version_number: int
    ratings_count: int
    overall: Decimal | None
    criteria: list[CriterionAverage] = field(default_factory=list)
    my_rated_at: Any = None


def _one_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def summaries(entry_ref: str, *, operator_ref: str = "", criteria: list[RecipeRatingCriterion] | None = None
              ) -> dict[int, VersionRatingSummary]:
    """Por número de versão que TEM avaliação: contagem, médias por critério ativo, geral e a nota de quem pede."""
    criteria = active_criteria() if criteria is None else criteria
    active_ids = [criterion.pk for criterion in criteria]
    scores = RecipeVersionRatingScore.objects.filter(rating__entry_ref=entry_ref, criterion_id__in=active_ids)
    per_criterion = {
        (row["rating__version_number"], row["criterion_id"]): row
        for row in scores.values("rating__version_number", "criterion_id").annotate(avg=Avg("score"), n=Count("id"))
    }
    overall = {
        row["rating__version_number"]: row["avg"]
        for row in scores.values("rating__version_number").annotate(avg=Avg("score"))
    }
    counts = {
        row["version_number"]: row["n"]
        for row in RecipeVersionRating.objects.filter(entry_ref=entry_ref, scores__criterion_id__in=active_ids)
        .values("version_number").annotate(n=Count("id", distinct=True))
    }
    mine: dict[int, dict[int, int]] = {}
    my_dates: dict[int, Any] = {}
    if operator_ref:
        for rating in RecipeVersionRating.objects.filter(entry_ref=entry_ref, operator_ref=operator_ref).prefetch_related("scores"):
            mine[rating.version_number] = {score.criterion_id: score.score for score in rating.scores.all()}
            my_dates[rating.version_number] = rating.updated_at

    result: dict[int, VersionRatingSummary] = {}
    for number in sorted(set(counts) | set(mine), reverse=True):
        result[number] = VersionRatingSummary(
            version_number=number,
            ratings_count=counts.get(number, 0),
            overall=_one_decimal(overall.get(number)),
            criteria=[
                CriterionAverage(
                    criterion_id=criterion.pk,
                    name=criterion.name,
                    average=_one_decimal((per_criterion.get((number, criterion.pk)) or {}).get("avg")),
                    count=int((per_criterion.get((number, criterion.pk)) or {}).get("n") or 0),
                    my_score=mine.get(number, {}).get(criterion.pk),
                )
                for criterion in criteria
            ],
            my_rated_at=my_dates.get(number),
        )
    return result


def overall_by_entry(entry_refs: list[str], numbers: dict[str, int]) -> dict[str, tuple[Decimal | None, int]]:
    """Média geral e contagem da VERSÃO ATUAL de cada receita (o cartão do inventário). Uma consulta por eixo."""
    if not entry_refs or not numbers:
        return {}
    active_ids = list(RecipeRatingCriterion.objects.filter(is_active=True).values_list("pk", flat=True))
    rows = (
        RecipeVersionRatingScore.objects.filter(rating__entry_ref__in=entry_refs, criterion_id__in=active_ids)
        .values("rating__entry_ref", "rating__version_number")
        .annotate(avg=Avg("score"), raters=Count("rating_id", distinct=True))
    )
    result: dict[str, tuple[Decimal | None, int]] = {}
    for row in rows:
        ref = row["rating__entry_ref"]
        if numbers.get(ref) == row["rating__version_number"]:
            result[ref] = (_one_decimal(row["avg"]), int(row["raters"]))
    return result
