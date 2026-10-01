import { describe, expect, it } from "vitest";

import {
  RATING_SCALE,
  initialScores,
  missingCriteria,
  overallLabel,
  ratingFor,
  scoresForPayload,
} from "~/presentation/recipeRating";
import type { RatingCriterionProjection, VersionRatingProjection } from "~/types/recipeBook";

const CRITERIA: RatingCriterionProjection[] = [
  { id: 1, name: "Sabor", description: "" },
  { id: 2, name: "Textura", description: "" },
];

const RATED: VersionRatingProjection = {
  version_number: 2,
  version_ref: "baguete@2",
  ratings_count: 2,
  ratings_count_display: "2 avaliações",
  overall_display: "4,3",
  criteria: [
    { criterion_id: 1, name: "Sabor", average_display: "4,5", count: 2, my_score: 5 },
    { criterion_id: 2, name: "Textura", average_display: "4", count: 2, my_score: 0 },
  ],
  rated_by_me: true,
  my_rated_at_display: "01/10/2026 08:00",
};

describe("recipe rating", () => {
  it("the scale is 0 to 5", () => {
    expect(RATING_SCALE).toEqual([0, 1, 2, 3, 4, 5]);
  });

  it("finds the rating of a version", () => {
    expect(ratingFor([RATED], 2)).toBe(RATED);
    expect(ratingFor([RATED], 3)).toBeNull();
    expect(ratingFor([RATED], null)).toBeNull();
  });

  it("starts from my own scores, zero included", () => {
    expect(initialScores(RATED)).toEqual({ "1": 5, "2": 0 });
    expect(initialScores(null)).toEqual({});
  });

  it("names what is missing and sends only active criteria with a score", () => {
    expect(missingCriteria(CRITERIA, {}).map((c) => c.name)).toEqual(["Sabor", "Textura"]);
    expect(missingCriteria(CRITERIA, { "1": 0 }).map((c) => c.name)).toEqual(["Textura"]);
    expect(missingCriteria(CRITERIA, { "1": 0, "2": 7 }).map((c) => c.name)).toEqual(["Textura"]);
    expect(missingCriteria(CRITERIA, { "1": 0, "2": 5 })).toEqual([]);
    expect(scoresForPayload(CRITERIA, { "1": 0, "2": 5, "9": 3 })).toEqual({ "1": 0, "2": 5 });
  });

  it("labels the overall average", () => {
    expect(overallLabel(RATED)).toBe("Média 4,3 de 5");
    expect(overallLabel(null)).toBe("Sem nota ainda");
    expect(overallLabel({ ...RATED, overall_display: "" })).toBe("Sem nota ainda");
  });
});
