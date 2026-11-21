import { describe, expect, it } from "vitest";

import { aiAnswer, csvBrl, csvRate, csvUsd, formatPerCall, formatSpend, quoteHint } from "~/presentation/ai";
import type { BIAiReport } from "~/types/bi";

const nbsp = (text: string) => text.replace(/ /g, " ");

const report: BIAiReport = {
  date_from: "2026-11-15",
  date_to: "2026-11-21",
  conference_mode: "shadow",
  cost_usd_micros: 1_739_300,
  cost_brl_micros: 10_100_911,
  calls: 1758,
  errors: 2,
  denied: 0,
  estimated_calls: 0,
  provisional_quotes: false,
  rows: [],
  days: [
    { date: "2026-11-21", cost_usd_micros: 202_400, cost_brl_micros: 1_191_915, rate: "5.8889", quoted_on: "2026-11-19", provisional: false },
  ],
  conferred: 31,
  would_fall: 9,
  reasons: [],
  gaps: [],
  fallbacks: [],
};

// Decisão de 21/11/2026 (DEV-2026-067): em reais pela PTAX de venda do dia, total com 2
// casas, custo por chamada com 4; o CSV leva US$ com 6 casas, R$ e a cotação.
describe("seção IA do B.I.", () => {
  it("o total sai em reais com 2 casas", () => {
    expect(nbsp(formatSpend(10_100_911, 1_739_300))).toBe("R$ 10,10");
  });

  it("sem cotação, o total sai em dólar, dito como dólar", () => {
    expect(formatSpend(null, 1_739_300)).toBe("US$ 1,74");
  });

  it("o custo por chamada sai com 4 casas", () => {
    expect(nbsp(formatPerCall(10_100_911, 1_739_300, 1758))).toBe("R$ 0,0057");
  });

  it("o CSV leva o dólar com 6 casas, o real e a cotação", () => {
    expect(csvUsd(1_739_300)).toBe("1.739300");
    expect(csvBrl(10_100_911)).toBe("10.1009");
    expect(csvRate(1_191_915, 202_400)).toBe("5.8889");
  });

  it("a frase do topo junta o gasto e a conferência", () => {
    expect(nbsp(aiAnswer(report))).toBe("R$ 10,10 em 1.758 chamadas; 29% das respostas reprovadas na conferência");
  });

  it("diz de onde vem a cotação", () => {
    expect(quoteHint(report)).toBe("Pela PTAX de venda do dia (última: R$ 5,8889)");
    expect(quoteHint({ ...report, provisional_quotes: true })).toContain("a de hoje ainda pode mudar");
  });
});
