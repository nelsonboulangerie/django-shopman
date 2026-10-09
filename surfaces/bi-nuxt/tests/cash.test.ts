import { describe, expect, it } from "vitest";

import {
  cashDifferenceAxis,
  cashDifferenceCsv,
  cashDifferencePoints,
  cashMethodRows,
  drawerCsv,
  drawerHourPoints,
  formatDuration,
  methodsCsv,
  openAccountsCsv,
  operatorCsv,
} from "~/presentation/cash";

const day = (date: string, difference_q: number, extra: Partial<{ shifts: number; sangria_q: number; suprimento_q: number }> = {}) => ({
  date,
  difference_q,
  shifts: extra.shifts ?? 1,
  sangria_q: extra.sangria_q ?? 0,
  suprimento_q: extra.suprimento_q ?? 0,
});

describe("caixa: quebra por dia", () => {
  it("um ponto por dia, em reais, com a quebra e o que o CSV leva junto", () => {
    const points = cashDifferencePoints([day("2026-10-06", -300, { sangria_q: 10000 }), day("2026-10-07", 150)]);
    expect(points).toEqual([
      { label: "06/10", values: { difference: -3, shifts: 1, sangria: 100, suprimento: 0 } },
      { label: "07/10", values: { difference: 1.5, shifts: 1, sangria: 0, suprimento: 0 } },
    ]);
    expect(cashDifferenceAxis([day("2026-10-06", 0)])).toBe("Dia");
  });

  it("série longa agrega por semana e o eixo diz o grão", () => {
    const days = Array.from({ length: 150 }, (_, i) => {
      const date = new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10);
      return day(date, -100);
    });
    const points = cashDifferencePoints(days);
    expect(points.length).toBeLessThan(days.length);
    expect(points[0]!.label).toMatch(/semana$/);
    expect(cashDifferenceAxis(days)).toBe("Semana");
    const total = points.reduce((sum, point) => sum + (point.values.difference ?? 0), 0);
    expect(total).toBe(-150);
  });

  it("o CSV do quadro traz as quatro colunas: dinheiro em reais com vírgula, turnos como número", () => {
    const csv = cashDifferenceCsv("Dia", cashDifferencePoints([day("2026-10-06", -300, { sangria_q: 1050 })]));
    expect(csv.header).toEqual(["Dia", "Quebra (R$)", "Turnos fechados", "Sangrias (R$)", "Suprimentos (R$)"]);
    expect(csv.rows).toEqual([["06/10", "-3,00", 1, "10,50", "0,00"]]);
  });
});

describe("caixa: gaveta e meios", () => {
  it("hora com dois dígitos e as quatro grandezas", () => {
    expect(drawerHourPoints([{ hour: 7, drawer_openings: 3, drawer_unlocks: 1, blocks: 2, open_seconds: 95 }])).toEqual([
      { label: "07h", values: { openings: 3, unlocks: 1, blocks: 2, open_seconds: 95 } },
    ]);
  });

  it("fatia de cada meio, escrita e para a barra", () => {
    const rows = cashMethodRows([
      { method: "Dinheiro", amount_q: 3000 },
      { method: "PIX", amount_q: 1000 },
    ]);
    expect(rows.map((row) => [row.share, row.shareLabel])).toEqual([
      [75, "75%"],
      [25, "25%"],
    ]);
    expect(cashMethodRows([{ method: "PIX", amount_q: 0 }])[0]!.share).toBe(0);
    expect(methodsCsv(rows).header).toEqual(["Meio de pagamento", "Valor (R$)", "Fatia (%)"]);
    expect(methodsCsv(rows).rows[0]).toEqual(["Dinheiro", "30,00", 75]);
  });

  it("duração em linguagem de balcão", () => {
    expect(formatDuration(0)).toBe("0 s");
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(184)).toBe("3 min 4 s");
    expect(formatDuration(3720)).toBe("1 h 2 min");
  });

  it("CSV das tabelas com a mesma ordem das colunas da tela", () => {
    expect(
      operatorCsv([
        { operator: "Ana", shifts: 2, difference_q: -300, drawer_openings: 4, drawer_unlocks: 1, change_requests: 0, account_settled_q: 0 },
      ]).rows,
    ).toEqual([["Ana", 2, "-3,00", 4, 1, 0]]);
    expect(
      drawerCsv([
        {
          operator: "Ana",
          blocks: 1,
          open_seconds: 30,
          longest_open_seconds: 20,
          dismissals: 0,
          overrides: 0,
          unlock_attempts: 0,
          sensor_blind: 0,
          left_open: 0,
        },
      ]).header,
    ).toHaveLength(9);
    expect(openAccountsCsv([{ customer_name: "Café Parisiense", balance_q: 15600 }]).rows).toEqual([["Café Parisiense", "156,00"]]);
  });
});
