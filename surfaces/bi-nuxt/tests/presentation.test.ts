import { describe, expect, it } from "vitest";
import {
  WEEKDAY_LABELS,
  bucketSalesDays,
  coverageLabel,
  formatMinutes,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
  shortDate,
} from "~/presentation/bi";

describe("presentation/bi", () => {
  it("formata centavos em pt-BR", () => {
    expect(formatMoney(123456).replace(/ /g, " ")).toBe("R$ 1.234,56");
    expect(formatMoney(-200).replace(/ /g, " ")).toBe("-R$ 2,00");
  });

  it("compacta valores grandes para tiles", () => {
    expect(formatMoneyCompact(123456789).replace(/ /g, " ")).toBe("R$ 1.234,6 mil");
    expect(formatMoneyCompact(4000).replace(/ /g, " ")).toBe("R$ 40,00");
  });

  it("quantidades e minutos trocam ponto por vírgula", () => {
    expect(formatQty("38.5")).toBe("38,5");
    expect(formatMinutes("23.5")).toBe("23,5 min");
  });

  it("datas curtas e rótulos", () => {
    expect(shortDate("2026-08-14")).toBe("14/08");
    expect(hourLabel(5)).toBe("5h");
    expect(WEEKDAY_LABELS[0]).toBe("seg");
  });

  it("cobertura sempre carrega o denominador", () => {
    expect(coverageLabel(3, 12)).toBe("3 de 12 fornadas medidas");
    expect(coverageLabel(0, 0)).toBe("sem fornadas no período");
  });
});

describe("bucketSalesDays", () => {
  const day = (date: string, revenue: number, source = "shopman", orders = 1) => ({
    date, orders: revenue ? orders : 0, revenue_q: revenue, source,
  });

  it("janela curta fica diária", () => {
    const out = bucketSalesDays([day("2026-08-13", 100), day("2026-08-14", 200)]);
    expect(out).toHaveLength(2);
    expect(out[0]!.weekly).toBe(false);
  });

  it("janela longa agrega por semana começando na segunda", () => {
    const days = Array.from({ length: 130 }, (_, index) => {
      const d = new Date(Date.UTC(2026, 0, 1 + index));
      return day(d.toISOString().slice(0, 10), 100, "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out.length).toBeLessThan(25);
    expect(out[0]!.weekly).toBe(true);
    expect(out.reduce((sum, bucket) => sum + bucket.revenue_q, 0)).toBe(13000);
    // 2026-01-01 é quinta: o primeiro balde ancora na segunda anterior.
    expect(out[0]!.date).toBe("2025-12-29");
  });

  it("semana mista veste a fonte nativa; semana só-histórico fica yooga", () => {
    const days = Array.from({ length: 130 }, (_, index) => {
      const d = new Date(Date.UTC(2026, 0, 5 + index)); // 05/01 é segunda
      return day(d.toISOString().slice(0, 10), 100, index < 7 ? "yooga" : index < 14 ? "shopman" : "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out[0]!.source).toBe("yooga");
    expect(out[1]!.source).toBe("shopman");
  });
});
