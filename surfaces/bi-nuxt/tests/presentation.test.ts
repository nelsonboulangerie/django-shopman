import { describe, expect, it } from "vitest";
import {
  DATA_EPOCH,
  WEEKDAY_LABELS,
  bucketLabel,
  bucketSalesDays,
  coverageLabel,
  delta,
  formatMinutes,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
  resolveWindowRange,
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
    expect(coverageLabel(0, 0)).toBe("Sem fornadas no período");
  });

  it("delta honesto: sem base vira travessão; tom segue melhorou/piorou", () => {
    expect(delta(100, 0)).toEqual({ text: "—", tone: "neutral" });
    expect(delta(120, 100)).toEqual({ text: "▲ 20% vs Período anterior", tone: "positive" });
    expect(delta(80, 100)).toEqual({ text: "▼ 20% vs Período anterior", tone: "negative" });
    expect(delta(100, 100)).toEqual({ text: "Estável vs Período anterior", tone: "neutral" });
    // Perda subindo é RUIM: downIsGood inverte o tom, nunca o texto.
    expect(delta(120, 100, { downIsGood: true }).tone).toBe("negative");
    expect(delta(80, 100, { downIsGood: true }).tone).toBe("positive");
  });
});

describe("bucketSalesDays", () => {
  const day = (date: string, revenue: number, source = "shopman", orders = 1) => ({
    date, orders: revenue ? orders : 0, revenue_q: revenue, source,
  });

  it("janela curta fica diária", () => {
    const out = bucketSalesDays([day("2026-08-13", 100), day("2026-08-14", 200)]);
    expect(out).toHaveLength(2);
    expect(out[0]!.span).toBe("day");
  });

  it("janela longa agrega por semana começando na segunda", () => {
    const days = Array.from({ length: 130 }, (_, index) => {
      const d = new Date(Date.UTC(2026, 0, 1 + index));
      return day(d.toISOString().slice(0, 10), 100, "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out.length).toBeLessThan(25);
    expect(out[0]!.span).toBe("week");
    expect(out.reduce((sum, bucket) => sum + bucket.revenue_q, 0)).toBe(13000);
    // 2026-01-01 é quinta: o primeiro balde ancora na segunda anterior.
    expect(out[0]!.date).toBe("2025-12-29");
  });

  it("acima de ~2 anos agrega por mês, com rótulo de mês", () => {
    const days = Array.from({ length: 800 }, (_, index) => {
      const d = new Date(Date.UTC(2024, 6, 1 + index));
      return day(d.toISOString().slice(0, 10), 100, "yooga");
    });
    const out = bucketSalesDays(days);
    expect(out[0]!.span).toBe("month");
    expect(out[0]!.date).toBe("2024-07-01");
    expect(bucketLabel(out[0]!.date, out[0]!.span)).toBe("jul/24");
    expect(out.reduce((sum, bucket) => sum + bucket.revenue_q, 0)).toBe(80000);
  });

  it("resolveWindowRange: janelas móveis, Máx e personalizado", () => {
    const today = new Date("2026-08-14T12:00:00Z");
    expect(resolveWindowRange({ preset: "7d", from: "", to: "" }, today)).toEqual({
      date_from: "2026-08-08",
      date_to: "2026-08-14",
    });
    expect(resolveWindowRange({ preset: "max", from: "", to: "" }, today).date_from).toBe(
      DATA_EPOCH,
    );
    expect(
      resolveWindowRange({ preset: "custom", from: "2025-01-10", to: "2025-02-10" }, today),
    ).toEqual({ date_from: "2025-01-10", date_to: "2025-02-10" });
  });

  it("resolveWindowRange: períodos do calendário correm do início até hoje", () => {
    const friday = new Date("2026-08-14T12:00:00Z");
    expect(resolveWindowRange({ preset: "day", from: "", to: "" }, friday)).toEqual({
      date_from: "2026-08-14",
      date_to: "2026-08-14",
    });
    // Semana começa na segunda: sexta 14/08 → segunda 10/08.
    expect(resolveWindowRange({ preset: "week", from: "", to: "" }, friday).date_from).toBe(
      "2026-08-10",
    );
    expect(resolveWindowRange({ preset: "month", from: "", to: "" }, friday).date_from).toBe(
      "2026-08-01",
    );
    expect(resolveWindowRange({ preset: "year", from: "", to: "" }, friday).date_from).toBe(
      "2026-01-01",
    );
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
