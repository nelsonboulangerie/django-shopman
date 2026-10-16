import { describe, expect, it } from "vitest";
import {
  REPORT_KINDS,
  REPORT_PERIOD_PRESETS,
  capacityLabel,
  reportDimensions,
  reportPanelFilters,
  reportRecortesFromPanel,
  reportKindLabel,
  reportsCsvUrl,
  reportsQuery,
  type ReportFiltersQuery,
} from "~/presentation/reports";

const FILTERS: ReportFiltersQuery = {
  selected_only: true,
  report_kind: "history",
  date_from: "2026-07-10",
  date_to: "2026-07-17",
  recipe_ref: "",
  position_ref: "forno",
  operator_ref: "",
  sort: "quantity_desc",
  page_size: 50,
  cursor: "next-page",
};

describe("reportKindLabel", () => {
  it("labels the four report kinds in pt-br", () => {
    expect(reportKindLabel("history")).toBe("Histórico");
    expect(reportKindLabel("operator_productivity")).toBe("Produtividade");
    expect(reportKindLabel("recipe_waste")).toBe("Desperdício");
    expect(reportKindLabel("quality")).toBe("Qualidade");
  });

  it("exposes the kinds in the tab order of the page", () => {
    expect(REPORT_KINDS.map((entry) => entry.kind)).toEqual([
      "history",
      "operator_productivity",
      "recipe_waste",
      "quality",
    ]);
  });
});

describe("reportsQuery", () => {
  it("keeps only non-empty filters", () => {
    expect(reportsQuery(FILTERS)).toEqual({
      selected_only: true,
      report_kind: "history",
      date_from: "2026-07-10",
      date_to: "2026-07-17",
      position_ref: "forno",
      sort: "quantity_desc",
      page_size: 50,
      cursor: "next-page",
    });
  });
});

describe("reportsCsvUrl", () => {
  it("links the same endpoint with format=csv and the active filters", () => {
    const url = reportsCsvUrl(FILTERS);
    expect(url.startsWith("/api/v1/backstage/production/reports/?")).toBe(true);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("format")).toBe("csv");
    expect(params.get("selected_only")).toBe("true");
    expect(params.get("report_kind")).toBe("history");
    expect(params.get("date_from")).toBe("2026-07-10");
    expect(params.get("position_ref")).toBe("forno");
    expect(params.get("recipe_ref")).toBeNull();
    expect(params.get("sort")).toBe("quantity_desc");
    expect(params.get("cursor")).toBeNull();
    expect(params.get("page_size")).toBeNull();
  });
});

describe("capacityLabel", () => {
  it("renders percent when configured and empty when not", () => {
    expect(capacityLabel(50)).toBe("50%");
    expect(capacityLabel(0)).toBe("0%");
    expect(capacityLabel(null)).toBe("");
  });
});

describe("painel de filtros dos relatórios", () => {
  it("põe ficha técnica e posto como lista e o operador como texto digitado", () => {
    const dimensions = reportDimensions(
      [{ ref: "baguete", name: "Baguete" }],
      [{ ref: "forno", name: "Forno" }],
    );
    expect(dimensions.map((d) => [d.id, d.label, d.type])).toEqual([
      ["recipe", "Ficha técnica", "single-select"],
      ["position", "Posto", "single-select"],
      ["operator", "Operador", "text"],
    ]);
    expect(dimensions[0]!.options).toEqual([{ value: "baguete", label: "Baguete" }]);
    expect(REPORT_PERIOD_PRESETS).toEqual(["day", "week", "month", "7d", "28d"]);
  });

  it("vai do rascunho ao painel e volta, os três recortes de uma vez", () => {
    expect(reportPanelFilters({ recipe_ref: "", position_ref: "forno", operator_ref: "  " })).toEqual({
      position: ["forno"],
    });
    expect(reportRecortesFromPanel({ recipe: ["baguete"], operator: ["ana"] })).toEqual({
      recipe_ref: "baguete",
      position_ref: "",
      operator_ref: "ana",
    });
  });
});
