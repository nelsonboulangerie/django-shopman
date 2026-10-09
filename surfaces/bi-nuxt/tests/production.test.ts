// A Produção no cânon do kit (PR-B2 do WP-BI-CANON-LAUDO): a série dos lotes no
// período vira os pontos do gráfico de leitura e as linhas do "Dia a dia" (o previsto
// e a perda que antes só existiam no `:hover`, F01), e a tabela produto a produto
// ganha CSV, selo e o "Ver os outros N".
import { describe, expect, it } from "vitest";
import type { BIOverShortRow, BIProductionReport } from "~/types/bi";
import { overShortCsv, showHiddenLabel, verdictColor } from "~/presentation/overShort";
import {
  bucketAxisLabel,
  finishedPoints,
  ovenCsv,
  ovenRows,
  ovenScale,
  productionBuckets,
  productionDayRows,
  productionDaysCsv,
  productionView,
  showAllLabel,
  yieldPercent,
  yieldPoints,
} from "~/presentation/production";

function day(date: string, started: string, finished: string, loss = "0") {
  return { date, planned: started, started, finished, loss, yield_percent: null, full_price: finished, discounted: "0" };
}

const report: BIProductionReport = {
  date_from: "2026-10-01",
  date_to: "2026-10-03",
  days: [day("2026-10-01", "100", "90", "10"), day("2026-10-02", "0", "0"), day("2026-10-03", "50", "50")],
  oven_time_by_recipe: [
    { ref: "BGT", label: "Baguette", runs: 8, avg_minutes: "26.6", p50_minutes: "26", p90_minutes: "30.9", avg_planned_minutes: "24.8" },
    { ref: "LEV", label: "Levain", runs: 1, avg_minutes: "33.0", p50_minutes: "33", p90_minutes: "33.0", avg_planned_minutes: "30.0" },
  ],
  oven_time_by_oven: [],
  batches_finished: 3,
  batches_started_assumed: 0,
  batches_measured: 2,
  oven_coverage_percent: 66,
  previous: {
    date_from: "2026-09-28",
    date_to: "2026-09-30",
    batches_finished: 2,
    started_total: "120",
    finished_total: "110",
    loss_total: "10",
    finished_by_day: ["40", "30", "40"],
  },
};

describe("lotes no período: a série do gráfico e do Dia a dia", () => {
  const buckets = productionBuckets(report);

  it("dia sem previsto não tem aproveitamento (sem dado, nunca zero)", () => {
    expect(yieldPercent(90, 100)).toBe(90);
    expect(yieldPercent(0, 0)).toBeNull();
    expect(yieldPoints(buckets).map((p) => p.values.yield)).toEqual([90, null, 100]);
  });

  it("a comparação leva o período anterior dia a dia", () => {
    expect(finishedPoints(buckets)[0]).toEqual({ label: "01/10", values: { finished: 90, previous: 40 } });
    expect(bucketAxisLabel(buckets)).toBe("Dia");
  });

  it("o Dia a dia diz previsto, perda e aproveitamento à vista", () => {
    expect(productionDayRows(buckets)[0]).toMatchObject({ started: "100", finished: "90", loss: "10", yield: "90%" });
    expect(productionDayRows(buckets)[1]!.yield).toBe("sem produção");
  });

  it("o CSV do Dia a dia leva número cru", () => {
    const csv = productionDaysCsv(buckets);
    expect(csv.header[0]).toBe("Dia");
    expect(csv.rows[1]).toEqual(["02/10", 0, 0, 30, 0, "", 0, 0]);
  });
});

describe("tempo de forno: tabela com barra e Ver todas", () => {
  it("formata a linha e mede a barra pela maior média", () => {
    const rows = ovenRows(report.oven_time_by_recipe);
    expect(rows[0]).toMatchObject({ label: "Baguette", minutes: 26.6, runs: "8" });
    expect(ovenScale(rows)).toBe(33);
    expect(ovenScale([])).toBe(1);
  });

  it("CSV e rótulo do Ver todas", () => {
    expect(ovenCsv("Receita", report.oven_time_by_recipe).header).toEqual(["Receita", "Média (min)", "p90 (min)", "Armado (min)", "Medições"]);
    expect(showAllLabel(26, { one: "receita", many: "receitas" })).toBe("Ver as 26 receitas");
  });
});

describe("Sobrou ou faltou: a tabela produto a produto", () => {
  const row = { sku: "CRO", name: "Croissant", verdict: "over", made: "40", sold: "30", leftover: "10", soldout_at: "", lost_estimate: "0", typical_sold: "32", leftover_cost_q: 6150 } as BIOverShortRow;

  it("selo na cor do veredito, desconhecido cai em na medida", () => {
    expect(verdictColor("short")).toBe("error");
    expect(verdictColor("over")).toBe("warning");
    expect(verdictColor("???")).toBe("success");
  });

  it("CSV com o veredito por extenso e o custo em reais", () => {
    expect(overShortCsv([row]).rows[0]).toEqual(["Croissant", "CRO", "Sobrou", 40, 30, 0, 10, "", 32, "61,50"]);
  });

  it("o botão diz quantos produtos faltam ver", () => {
    expect(showHiddenLabel(1)).toBe("Ver o outro produto");
    expect(showHiddenLabel(3)).toBe("Ver os outros 3 produtos");
  });

  it("a aba mora na URL: só `lots` abre os lotes, o resto é o dia", () => {
    expect(productionView("lots")).toBe("lots");
    expect(productionView(undefined)).toBe("day");
    expect(productionView(["lots"])).toBe("day");
  });
});
