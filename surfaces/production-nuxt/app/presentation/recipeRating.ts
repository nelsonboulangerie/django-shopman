// Nota da receita (0 a 5 por critério, por versão fechada) — lógica pura da tela.
// Os critérios vêm do servidor (editáveis no Admin); a tela não conhece nenhum
// pelo nome. A média chega pronta (`average_display`, `overall_display`).
import type {
  RatingCriterionProjection,
  RecipeVersionProjection,
  VersionRatingProjection,
} from "~/types/recipeBook";

/** A escala inteira, na ordem dos botões. */
export const RATING_SCALE: readonly number[] = [0, 1, 2, 3, 4, 5] as const;

/** A nota da versão `number`, ou `null` (rascunho não tem). */
export function ratingFor(
  ratings: readonly VersionRatingProjection[],
  number: number | null | undefined,
): VersionRatingProjection | null {
  if (!number) return null;
  return ratings.find((rating) => rating.version_number === number) ?? null;
}

/** Só versão fechada recebe nota: rascunho ainda muda. */
export function isRateable(version: Pick<RecipeVersionProjection, "status"> | null | undefined): boolean {
  return !!version && version.status !== "draft";
}

/** O ponto de partida do formulário: a nota que este operador já deu, critério a critério. */
export function initialScores(rating: VersionRatingProjection | null): Record<string, number | null> {
  const scores: Record<string, number | null> = {};
  for (const criterion of rating?.criteria ?? []) scores[String(criterion.criterion_id)] = criterion.my_score;
  return scores;
}

/** Os critérios que ainda estão sem nota (o botão de gravar só acende sem nenhum). */
export function missingCriteria(
  criteria: readonly RatingCriterionProjection[],
  scores: Record<string, number | null | undefined>,
): RatingCriterionProjection[] {
  return criteria.filter((criterion) => {
    const value = scores[String(criterion.id)];
    return typeof value !== "number" || !RATING_SCALE.includes(value);
  });
}

/** O corpo do PUT: só os critérios ativos, só com nota. */
export function scoresForPayload(
  criteria: readonly RatingCriterionProjection[],
  scores: Record<string, number | null | undefined>,
): Record<string, number> {
  const payload: Record<string, number> = {};
  for (const criterion of criteria) {
    const value = scores[String(criterion.id)];
    if (typeof value === "number") payload[String(criterion.id)] = value;
  }
  return payload;
}

/** "Média 4,3 de 5" ou "Sem nota ainda". */
export function overallLabel(rating: VersionRatingProjection | null): string {
  return rating?.overall_display ? `Média ${rating.overall_display} de 5` : "Sem nota ainda";
}
