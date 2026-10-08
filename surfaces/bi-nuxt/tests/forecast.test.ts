import { describe, expect, it } from "vitest";
import {
  FORECAST_SERIES,
  forecastChartPoints,
  forecastDayLabel,
  forecastDayRows,
  forecastDaysCsv,
  forecastFromQuery,
  forecastToQuery,
  missingDaysLabel,
  occasionRatioLabel,
  occasionTitle,
  occasionYearRows,
  occasionYearsCsv,
  ordinaryWeekdayLabel,
} from "~/presentation/forecast";
import type { DayForecast } from "~/types/bi";

function day(overrides: Partial<DayForecast> = {}): DayForecast {
  return {
    date: "2026-10-09",
    weekday: 4,
    weekday_label: "sexta-feira",
    closed: false,
    closed_reason: "",
    revenue_q: { expected: 1103323.8, low: 938204.8, high: 1322464.2 },
    orders: { expected: 140.4, low: 120.8, high: 165.2 },
    branches: [],
    occasion: null,
    basis: null,
    missing_reason: "",
    ...overrides,
  };
}

describe("rótulos da Projeção", () => {
  it("dia curto com inicial maiúscula", () => {
    expect(forecastDayLabel(day())).toBe("Sex 09/10");
    expect(forecastDayLabel(day({ weekday_label: "sábado", date: "2026-10-10" }))).toBe("Sáb 10/10");
  });

  it("o artigo do dia comum segue o gênero do dia da semana", () => {
    expect(ordinaryWeekdayLabel("sexta-feira")).toBe("Uma sexta-feira comum");
    expect(ordinaryWeekdayLabel("sábado")).toBe("Um sábado comum");
    expect(ordinaryWeekdayLabel("domingo")).toBe("Um domingo comum");
  });

  it("ocasião diz a véspera entre parênteses", () => {
    expect(occasionTitle({ name: "Dia das Mães", is_eve: true })).toBe("Dia das Mães (véspera)");
    expect(occasionTitle({ name: "Dia das Mães", is_eve: false })).toBe("Dia das Mães");
  });

  it("razão com vírgula decimal", () => {
    expect(occasionRatioLabel(1.2044)).toBe("1,2×");
  });

  it("dias sem base por extenso", () => {
    expect(missingDaysLabel(["2026-10-12", "2026-10-13"])).toBe("12/10, 13/10");
  });
});

describe("ocorrências anteriores", () => {
  const years = [{ date: "2025-10-09", revenue_q: 838971, ratio: 1.2044516 }];

  it("linha da tabela formatada", () => {
    expect(occasionYearRows(years)).toEqual([
      { date: "2025-10-09", label: "09/10/2025", revenue: expect.stringContaining("8.389,71"), ratio: "1,2×" },
    ]);
  });

  it("CSV em reais inteiros, número cru", () => {
    expect(occasionYearsCsv(years)).toEqual({
      header: ["Ocorrência", "Faturamento (R$)", "Contra um dia normal"],
      rows: [["09/10/2025", 8390, 1.2]],
    });
  });
});

describe("o período dia a dia", () => {
  const days = [
    day(),
    day({ date: "2026-10-11", weekday_label: "domingo", closed: true, closed_reason: "feriado", revenue_q: null, orders: null }),
    day({ date: "2026-10-12", weekday_label: "segunda-feira", revenue_q: null, orders: null, missing_reason: "x" }),
  ];

  it("dia fechado ou sem base não vira zero no gráfico", () => {
    const points = forecastChartPoints(days);
    expect(points[0]).toEqual({
      label: "Sex 09/10",
      values: { expected: 1103323.8, low: 938204.8, high: 1322464.2 },
    });
    expect(points[1]!.values).toEqual({ expected: null, low: null, high: null });
    expect(points[2]!.values).toEqual({ expected: null, low: null, high: null });
    expect(FORECAST_SERIES.map((s) => s.key)).toEqual(["expected", "low", "high"]);
  });

  it("a tabela diz o porquê de cada dia sem número", () => {
    const rows = forecastDayRows(days);
    expect(rows[0]).toMatchObject({ label: "Sex 09/10", orders: "140", note: "" });
    expect(rows[0]!.revenue).toContain("11.033,24");
    expect(rows[1]).toMatchObject({ revenue: "sem dado", range: "sem dado", orders: "sem dado", note: "Fechado (feriado)" });
    expect(rows[2]!.note).not.toBe("");
  });

  it("CSV com os mesmos dias, em reais inteiros", () => {
    const csv = forecastDaysCsv(days);
    expect(csv.header[0]).toBe("Dia");
    expect(csv.rows[0]).toEqual(["sexta-feira", "09/10/2026", 11033, 9382, 13225, 140, ""]);
    expect(csv.rows[1]).toEqual(["domingo", "11/10/2026", "", "", "", "", "Fechado (feriado)"]);
  });
});

describe("o planejamento na URL", () => {
  const tomorrow = "2026-10-09";

  it("sem nada na URL, amanhã e um dia", () => {
    expect(forecastFromQuery({}, tomorrow)).toEqual({ horizon: "day", target: tomorrow });
  });

  it("lê horizonte e dia; valor ilegível cai no padrão", () => {
    expect(forecastFromQuery({ horizon: "week", target: "2026-10-12" }, tomorrow)).toEqual({
      horizon: "week",
      target: "2026-10-12",
    });
    expect(forecastFromQuery({ horizon: "year", target: "ontem" }, tomorrow)).toEqual({
      horizon: "day",
      target: tomorrow,
    });
  });

  it("não lê a janela das outras telas", () => {
    expect(forecastFromQuery({ period: "28d", from: "2026-09-01" }, tomorrow)).toEqual({
      horizon: "day",
      target: tomorrow,
    });
  });

  it("só o que difere do padrão ocupa a URL", () => {
    expect(forecastToQuery({ horizon: "day", target: tomorrow }, tomorrow)).toEqual({});
    expect(forecastToQuery({ horizon: "month", target: "2026-11-01" }, tomorrow)).toEqual({
      horizon: "month",
      target: "2026-11-01",
    });
  });
});
