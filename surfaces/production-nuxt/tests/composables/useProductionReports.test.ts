import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useProductionReports } from "~/composables/useProductionReports";
import type { ReportFiltersQuery } from "~/presentation/reports";

const env = installNuxtGlobals();

function filters(
  overrides: Partial<ReportFiltersQuery> = {},
): ReportFiltersQuery {
  return {
    selected_only: true,
    report_kind: "history",
    date_from: "2026-07-10",
    date_to: "2026-07-17",
    recipe_ref: "",
    position_ref: "",
    operator_ref: "",
    sort: "default",
    page_size: 50,
    cursor: "",
    ...overrides,
  };
}

describe("useProductionReports", () => {
  beforeEach(() => env.reset());

  it("derives the three row sets and the filter options", () => {
    env.fetchData.value = {
      pagination: {
        total: 2,
        page_size: 50,
        from: 1,
        to: 2,
        sort: "default",
        next_cursor: "",
        previous_cursor: "",
      },
      reports: {
        filters: {
          report_kind: "history",
          date_from: "2026-07-10",
          date_to: "2026-07-17",
        },
        history_rows: [{ ref: "WO-001" }, { ref: "WO-002" }],
        operator_rows: [{ operator_ref: "ana" }],
        waste_rows: [{ recipe_ref: "pao" }],
        available_recipes: [{ ref: "pao", name: "Pão" }],
        available_positions: [{ ref: "forno", name: "Forno" }],
      },
    };
    const {
      pagination,
      historyRows,
      operatorRows,
      wasteRows,
      availableRecipes,
      availablePositions,
      forbidden,
    } = useProductionReports(ref(filters()), ref(true));

    expect(historyRows.value).toHaveLength(2);
    expect(pagination.value?.total).toBe(2);
    expect(operatorRows.value).toHaveLength(1);
    expect(wasteRows.value).toHaveLength(1);
    expect(availableRecipes.value[0]?.name).toBe("Pão");
    expect(availablePositions.value[0]?.ref).toBe("forno");
    expect(forbidden.value).toBe(false);
  });

  it("downloads CSV through an explicit successful lifecycle", async () => {
    const click = vi.fn();
    vi.stubGlobal("document", {
      createElement: () => ({ href: "", download: "", click }),
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:report");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    env.fetchMock.mockResolvedValue(new Blob(["report"]));
    const state = useProductionReports(
      ref(filters({ report_kind: "recipe_waste", recipe_ref: "pao" })),
      ref(true),
    );

    expect(await state.downloadCsv()).toBe(true);
    expect(state.exportStatus.value).toBe("success");
    expect(click).toHaveBeenCalledOnce();
    expect(env.fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("format=csv"),
      expect.objectContaining({ responseType: "blob" }),
    );
  });

  it("cancels an in-flight CSV export without reporting failure", async () => {
    env.fetchMock.mockImplementation(
      (_url, options: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener("abort", () =>
            reject(Object.assign(new Error("cancelled"), { name: "AbortError" })),
          );
        }),
    );
    const state = useProductionReports(ref(filters()), ref(true));

    const result = state.downloadCsv();
    expect(state.exportStatus.value).toBe("pending");
    state.cancelExport();
    expect(await result).toBe(false);
    expect(state.exportStatus.value).toBe("cancelled");
  });

  it("distinguishes session expiry from an ordinary export failure", async () => {
    const state = useProductionReports(ref(filters()), ref(true));
    env.fetchMock.mockRejectedValueOnce({
      status: 403,
      data: { error: { code: "not_authenticated" } },
    });
    await state.downloadCsv();
    expect(state.exportStatus.value).toBe("session_expired");

    env.fetchMock.mockRejectedValueOnce({ status: 500 });
    await state.downloadCsv();
    expect(state.exportStatus.value).toBe("failure");
  });

  it("degrades to empty rows when the payload is null", () => {
    env.fetchData.value = null;
    const { reports, historyRows, operatorRows, wasteRows } =
      useProductionReports(ref(filters()), ref(true));
    expect(reports.value).toBeNull();
    expect(historyRows.value).toEqual([]);
    expect(operatorRows.value).toEqual([]);
    expect(wasteRows.value).toEqual([]);
  });

  it("exposes the stale-cursor recovery state", () => {
    env.fetchError.value = {
      status: 409,
      data: { error: { code: "stale_report_cursor" } },
    };

    const { cursorStale, canExport } = useProductionReports(
      ref(filters({ cursor: "page-2" })),
      ref(true),
    );

    expect(cursorStale.value).toBe(true);
    expect(canExport.value).toBe(false);
  });
});
