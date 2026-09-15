import { describe, expect, it } from "vitest";
import { useReportFilters } from "~/composables/useReportFilters";
import type { ReportFiltersQuery } from "~/presentation/reports";

const INITIAL: ReportFiltersQuery = {
  selected_only: true,
  report_kind: "history",
  date_from: "2026-09-01",
  date_to: "2026-09-07",
  recipe_ref: "",
  position_ref: "",
  operator_ref: "",
  sort: "default",
  page_size: 50,
  cursor: "",
};

describe("useReportFilters", () => {
  it("keeps typing local until Apply and resets the cursor", () => {
    const state = useReportFilters({ ...INITIAL, cursor: "old-page" });
    state.draft.operator_ref = "  ana  ";

    expect(state.isDirty.value).toBe(true);
    expect(state.applied.value.operator_ref).toBe("");
    expect(state.applied.value.cursor).toBe("old-page");

    expect(state.apply()).toBe(true);
    expect(state.applied.value.operator_ref).toBe("ana");
    expect(state.applied.value.cursor).toBe("");
    expect(state.isDirty.value).toBe(false);
  });

  it("normalizes an incompatible date sort when the report kind changes", () => {
    const state = useReportFilters({ ...INITIAL, sort: "date_desc" });

    state.selectKind("operator_productivity");

    expect(state.draft.sort).toBe("default");
    expect(state.isDirty.value).toBe(true);
    state.apply();
    expect(state.applied.value.report_kind).toBe("operator_productivity");
    expect(state.applied.value.sort).toBe("default");
  });

  it("blocks inverted and oversized periods before changing the request", () => {
    const state = useReportFilters(INITIAL);
    state.draft.date_from = "2026-09-08";
    state.draft.date_to = "2026-09-01";
    expect(state.apply()).toBe(false);
    expect(state.validationError.value).toContain("anterior");

    state.draft.date_from = "2026-01-01";
    state.draft.date_to = "2026-09-01";
    expect(state.apply()).toBe(false);
    expect(state.validationError.value).toContain("93 dias");
    expect(state.applied.value).toEqual(INITIAL);
  });
});
